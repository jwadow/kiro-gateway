# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Converters between the OpenAI Responses API and Chat Completions format.

The /v1/responses endpoint is implemented as an adapter over the existing
/v1/chat/completions pipeline:

1. Request: ResponsesRequest -> ChatCompletionRequest (responses_request_to_chat)
2. Non-streaming: chat.completion dict -> response object (chat_completion_to_response)
3. Streaming: chat.completion.chunk SSE -> Responses SSE events (ResponsesStreamTranslator)

The gateway keeps no server-side state, so features that need it
(previous_response_id, conversation, item_reference) are rejected with 400.
"""

import json
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from loguru import logger
from pydantic import ValidationError

from kiro.models_openai import ChatCompletionRequest, ChatMessage, Tool, ToolFunction
from kiro.models_responses import ResponsesRequest


# ==================================================================================================
# Constants
# ==================================================================================================

# Message roles accepted in Responses input items, mapped to Chat Completions roles.
# "developer" is the Responses-era name for system instructions.
ROLE_MAP: Dict[str, str] = {
    "user": "user",
    "assistant": "assistant",
    "system": "system",
    "developer": "system",
}

# Text content part types (input from user, output echoed back from assistant)
TEXT_PART_TYPES = frozenset({"input_text", "output_text", "text"})

# Input item types silently skipped: reasoning items are echoed back by clients
# (e.g. Codex) but carry no information Kiro can consume.
SKIPPED_ITEM_TYPES = frozenset({"reasoning"})

# Chat Completions finish_reason values that map to an incomplete response
INCOMPLETE_FINISH_REASONS: Dict[str, str] = {
    "length": "max_output_tokens",
    "content_filter": "content_filter",
}

STATELESS_HINT = (
    "Kiro Gateway does not store responses. Send the full conversation history "
    "in 'input' instead."
)


class ResponsesConversionError(ValueError):
    """
    Raised when a Responses API request cannot be translated.

    Attributes:
        message: User-facing error message
        param: Name/path of the offending request parameter (OpenAI error 'param')
    """

    def __init__(self, message: str, param: Optional[str] = None) -> None:
        """
        Args:
            message: User-facing error message
            param: Offending request parameter, if known
        """
        super().__init__(message)
        self.message = message
        self.param = param


def generate_item_id(prefix: str) -> str:
    """
    Generate a Responses API object id.

    Args:
        prefix: Id prefix ("resp", "msg", "fc", "rs")

    Returns:
        Id like "msg_0123abcd..."
    """
    return f"{prefix}_{uuid.uuid4().hex}"


# ==================================================================================================
# Request translation: Responses -> Chat Completions
# ==================================================================================================

def _convert_content_parts(parts: List[Any], param: str) -> Any:
    """
    Convert Responses content parts into Chat Completions content.

    Text-only content becomes a single string. Content containing images becomes
    a list of chat parts ({"type": "text"} / {"type": "image_url"}).

    Args:
        parts: Responses content parts (input_text, output_text, input_image, refusal)
        param: Parameter path for error messages

    Returns:
        String or list of Chat Completions content parts

    Raises:
        ResponsesConversionError: On malformed or unsupported parts
    """
    chat_parts: List[Dict[str, Any]] = []
    has_image = False

    for idx, part in enumerate(parts):
        part_param = f"{param}[{idx}]"
        if isinstance(part, str):
            chat_parts.append({"type": "text", "text": part})
            continue
        if not isinstance(part, dict):
            raise ResponsesConversionError(
                f"Content part must be an object, got {type(part).__name__}.", part_param
            )

        part_type = part.get("type")
        if part_type in TEXT_PART_TYPES:
            text = part.get("text")
            if not isinstance(text, str):
                raise ResponsesConversionError(
                    f"Content part of type '{part_type}' requires a string 'text' field.", part_param
                )
            chat_parts.append({"type": "text", "text": text})
        elif part_type == "refusal":
            chat_parts.append({"type": "text", "text": str(part.get("refusal", ""))})
        elif part_type == "input_image":
            image_url = part.get("image_url")
            if isinstance(image_url, dict):
                image_url = image_url.get("url")
            if not isinstance(image_url, str) or not image_url:
                raise ResponsesConversionError(
                    "input_image requires 'image_url' (a URL or data: URI). "
                    "'file_id' references are not supported because the gateway has no file storage.",
                    part_param,
                )
            image_part: Dict[str, Any] = {"url": image_url}
            if part.get("detail"):
                image_part["detail"] = part["detail"]
            chat_parts.append({"type": "image_url", "image_url": image_part})
            has_image = True
        else:
            raise ResponsesConversionError(
                f"Unsupported content part type '{part_type}'. "
                "Supported: input_text, output_text, input_image, refusal.",
                part_param,
            )

    if has_image:
        return chat_parts
    return "\n".join(p["text"] for p in chat_parts)


def _convert_message_item(item: Dict[str, Any], param: str) -> ChatMessage:
    """
    Convert a Responses message item into a ChatMessage.

    Args:
        item: Item with 'role' and 'content'
        param: Parameter path for error messages

    Returns:
        ChatMessage with mapped role and content

    Raises:
        ResponsesConversionError: On unknown role or malformed content
    """
    role = item.get("role")
    if role not in ROLE_MAP:
        raise ResponsesConversionError(
            f"Invalid message role '{role}'. Supported: {', '.join(ROLE_MAP)}.", f"{param}.role"
        )

    content = item.get("content")
    if isinstance(content, str):
        chat_content: Any = content
    elif isinstance(content, list):
        chat_content = _convert_content_parts(content, f"{param}.content")
    else:
        raise ResponsesConversionError(
            "Message 'content' must be a string or a list of content parts.", f"{param}.content"
        )

    return ChatMessage(role=ROLE_MAP[role], content=chat_content)


def _convert_function_call_item(item: Dict[str, Any], param: str) -> Dict[str, Any]:
    """
    Convert a Responses function_call item into a Chat Completions tool_call.

    Args:
        item: function_call item (call_id, name, arguments)
        param: Parameter path for error messages

    Returns:
        Chat tool_call dict {"id", "type", "function": {"name", "arguments"}}

    Raises:
        ResponsesConversionError: If call_id or name is missing
    """
    call_id = item.get("call_id")
    name = item.get("name")
    if not isinstance(call_id, str) or not call_id:
        raise ResponsesConversionError("function_call item requires a string 'call_id'.", f"{param}.call_id")
    if not isinstance(name, str) or not name:
        raise ResponsesConversionError("function_call item requires a string 'name'.", f"{param}.name")

    arguments = item.get("arguments", "{}")
    if isinstance(arguments, (dict, list)):
        arguments = json.dumps(arguments, ensure_ascii=False)
    elif arguments is None or arguments == "":
        arguments = "{}"
    elif not isinstance(arguments, str):
        raise ResponsesConversionError(
            "function_call 'arguments' must be a JSON string.", f"{param}.arguments"
        )

    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


def _convert_function_call_output_item(item: Dict[str, Any], param: str) -> ChatMessage:
    """
    Convert a Responses function_call_output item into a tool message.

    Args:
        item: function_call_output item (call_id, output)
        param: Parameter path for error messages

    Returns:
        ChatMessage with role "tool"

    Raises:
        ResponsesConversionError: If call_id is missing or output is malformed
    """
    call_id = item.get("call_id")
    if not isinstance(call_id, str) or not call_id:
        raise ResponsesConversionError(
            "function_call_output item requires a string 'call_id'.", f"{param}.call_id"
        )

    output = item.get("output", "")
    if isinstance(output, str):
        content: Any = output
    elif isinstance(output, list):
        content = _convert_content_parts(output, f"{param}.output")
    elif isinstance(output, dict):
        content = json.dumps(output, ensure_ascii=False)
    elif output is None:
        content = ""
    else:
        raise ResponsesConversionError(
            "function_call_output 'output' must be a string or a list of content parts.", f"{param}.output"
        )

    return ChatMessage(role="tool", content=content, tool_call_id=call_id)


def convert_input_items(input_value: Any) -> List[ChatMessage]:
    """
    Convert Responses 'input' into a list of ChatMessages.

    Consecutive function_call items (and a function_call directly after an
    assistant message) are merged into one assistant message with tool_calls,
    matching how Chat Completions represents parallel tool calls.

    Args:
        input_value: String or list of input items

    Returns:
        List of ChatMessage objects

    Raises:
        ResponsesConversionError: On malformed or unsupported items
    """
    if isinstance(input_value, str):
        return [ChatMessage(role="user", content=input_value)]

    messages: List[ChatMessage] = []
    # Assistant message that can still absorb function_call items
    open_assistant: Optional[ChatMessage] = None

    for idx, item in enumerate(input_value):
        param = f"input[{idx}]"
        if not isinstance(item, dict):
            raise ResponsesConversionError(
                f"Input item must be an object, got {type(item).__name__}.", param
            )

        item_type = item.get("type")
        if item_type is None and "role" in item:
            item_type = "message"

        if item_type == "message":
            msg = _convert_message_item(item, param)
            messages.append(msg)
            open_assistant = msg if msg.role == "assistant" else None
        elif item_type == "function_call":
            tool_call = _convert_function_call_item(item, param)
            if open_assistant is None:
                open_assistant = ChatMessage(role="assistant", content="", tool_calls=[])
                messages.append(open_assistant)
            if open_assistant.tool_calls is None:
                open_assistant.tool_calls = []
            open_assistant.tool_calls.append(tool_call)
        elif item_type == "function_call_output":
            messages.append(_convert_function_call_output_item(item, param))
            open_assistant = None
        elif item_type in SKIPPED_ITEM_TYPES:
            logger.debug(f"Skipping '{item_type}' input item at {param} (not used by Kiro)")
        elif item_type == "item_reference":
            raise ResponsesConversionError(
                f"item_reference is not supported. {STATELESS_HINT}", param
            )
        else:
            raise ResponsesConversionError(
                f"Unsupported input item type '{item_type}'. "
                "Supported: message, function_call, function_call_output, reasoning.",
                f"{param}.type",
            )

    return messages


def convert_tools(tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Tool]]:
    """
    Convert Responses tool definitions into Chat Completions tools.

    Responses function tools are flat ({"type": "function", "name", "description",
    "parameters"}). Built-in tool types (web_search, file_search, computer_use, ...)
    have no Kiro equivalent and are skipped with a warning.

    Args:
        tools: Responses tool definitions

    Returns:
        List of chat Tool objects, or None if there are none

    Raises:
        ResponsesConversionError: If a function tool is malformed
    """
    if not tools:
        return None

    chat_tools: List[Tool] = []
    for idx, tool in enumerate(tools):
        param = f"tools[{idx}]"
        if not isinstance(tool, dict):
            raise ResponsesConversionError(f"Tool must be an object, got {type(tool).__name__}.", param)

        tool_type = tool.get("type", "function")
        if tool_type != "function":
            logger.warning(f"Ignoring unsupported Responses tool type '{tool_type}' at {param}")
            continue

        name = tool.get("name")
        if not isinstance(name, str) or not name:
            raise ResponsesConversionError("Function tool requires a string 'name'.", f"{param}.name")
        parameters = tool.get("parameters")
        if parameters is not None and not isinstance(parameters, dict):
            raise ResponsesConversionError(
                "Function tool 'parameters' must be a JSON Schema object.", f"{param}.parameters"
            )

        chat_tools.append(
            Tool(
                type="function",
                function=ToolFunction(
                    name=name,
                    description=tool.get("description"),
                    parameters=parameters,
                ),
            )
        )

    return chat_tools or None


def convert_tool_choice(tool_choice: Any) -> Any:
    """
    Convert Responses tool_choice into Chat Completions tool_choice.

    Args:
        tool_choice: "auto" / "none" / "required" or {"type": "function", "name": ...}

    Returns:
        Chat tool_choice value, or None when it cannot be mapped

    Raises:
        ResponsesConversionError: If a function tool_choice lacks a name
    """
    if tool_choice is None or isinstance(tool_choice, str):
        return tool_choice

    if isinstance(tool_choice, dict) and tool_choice.get("type") == "function":
        name = tool_choice.get("name") or (tool_choice.get("function") or {}).get("name")
        if not isinstance(name, str) or not name:
            raise ResponsesConversionError("Function tool_choice requires a 'name'.", "tool_choice.name")
        return {"type": "function", "function": {"name": name}}

    logger.warning(f"Ignoring unsupported tool_choice {tool_choice!r}; using default behavior")
    return None


def responses_request_to_chat(request: ResponsesRequest) -> ChatCompletionRequest:
    """
    Translate a Responses API request into a ChatCompletionRequest.

    Args:
        request: Validated Responses request

    Returns:
        Equivalent ChatCompletionRequest for the chat completions pipeline

    Raises:
        ResponsesConversionError: On stateful features, malformed items or invalid values
    """
    if request.previous_response_id:
        raise ResponsesConversionError(
            f"previous_response_id is not supported. {STATELESS_HINT}", "previous_response_id"
        )
    if request.conversation:
        raise ResponsesConversionError(
            f"conversation is not supported. {STATELESS_HINT}", "conversation"
        )
    if request.store:
        logger.debug("Responses 'store' requested; ignored (gateway is stateless)")

    messages: List[ChatMessage] = []
    if request.instructions:
        messages.append(ChatMessage(role="system", content=request.instructions))
    messages.extend(convert_input_items(request.input))

    if not messages:
        raise ResponsesConversionError("'input' must contain at least one item.", "input")

    reasoning_effort = None
    if request.reasoning and request.reasoning.get("effort"):
        reasoning_effort = request.reasoning["effort"]

    try:
        chat_request = ChatCompletionRequest(
            model=request.model,
            messages=messages,
            stream=request.stream,
            temperature=request.temperature,
            top_p=request.top_p,
            max_tokens=request.max_output_tokens,
            reasoning_effort=reasoning_effort,
            tools=convert_tools(request.tools),
            tool_choice=convert_tool_choice(request.tool_choice),
            parallel_tool_calls=request.parallel_tool_calls,
            user=request.user,
        )
    except ValidationError as e:
        first = e.errors()[0] if e.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", ()))
        if field == "reasoning_effort":
            field = "reasoning.effort"
        raise ResponsesConversionError(
            f"Invalid value for '{field}': {first.get('msg', str(e))}", field or None
        ) from e

    logger.debug(
        f"Translated Responses request: {len(messages)} message(s), "
        f"{len(chat_request.tools or [])} tool(s), stream={chat_request.stream}"
    )
    return chat_request


# ==================================================================================================
# Response building: Chat Completions -> Responses
# ==================================================================================================

def build_usage(chat_usage: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Convert Chat Completions usage into Responses usage.

    Args:
        chat_usage: {"prompt_tokens", "completion_tokens", "total_tokens", ...}

    Returns:
        {"input_tokens", "input_tokens_details", "output_tokens",
         "output_tokens_details", "total_tokens"}
    """
    chat_usage = chat_usage or {}
    input_tokens = int(chat_usage.get("prompt_tokens") or 0)
    output_tokens = int(chat_usage.get("completion_tokens") or 0)
    total_tokens = int(chat_usage.get("total_tokens") or (input_tokens + output_tokens))
    return {
        "input_tokens": input_tokens,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens": output_tokens,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": total_tokens,
    }


def status_from_finish_reason(finish_reason: Optional[str]) -> Tuple[str, Optional[Dict[str, str]]]:
    """
    Map a Chat Completions finish_reason to Responses status.

    Args:
        finish_reason: "stop", "tool_calls", "length", ...

    Returns:
        (status, incomplete_details) e.g. ("incomplete", {"reason": "max_output_tokens"})
    """
    reason = INCOMPLETE_FINISH_REASONS.get(finish_reason or "")
    if reason:
        return "incomplete", {"reason": reason}
    return "completed", None


def build_response_object(
    request: ResponsesRequest,
    response_id: str,
    created_at: int,
    status: str,
    output: List[Dict[str, Any]],
    usage: Optional[Dict[str, Any]] = None,
    incomplete_details: Optional[Dict[str, str]] = None,
    error: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a Responses API response object, echoing request parameters.

    Args:
        request: Original Responses request
        response_id: "resp_..." id
        created_at: Unix timestamp
        status: "in_progress", "completed", "incomplete" or "failed"
        output: Output items
        usage: Responses usage (None while in progress)
        incomplete_details: {"reason": ...} for incomplete responses
        error: {"code", "message"} for failed responses

    Returns:
        Response object dict
    """
    return {
        "id": response_id,
        "object": "response",
        "created_at": created_at,
        "status": status,
        "error": error,
        "incomplete_details": incomplete_details,
        "instructions": request.instructions,
        "max_output_tokens": request.max_output_tokens,
        "model": request.model,
        "output": output,
        "parallel_tool_calls": request.parallel_tool_calls if request.parallel_tool_calls is not None else True,
        "previous_response_id": None,
        "reasoning": request.reasoning or {"effort": None, "summary": None},
        "store": False,
        "temperature": request.temperature,
        "text": request.text or {"format": {"type": "text"}},
        "tool_choice": request.tool_choice if request.tool_choice is not None else "auto",
        "tools": request.tools or [],
        "top_p": request.top_p,
        "truncation": "disabled",
        "usage": usage,
        "user": request.user,
        "metadata": request.metadata or {},
    }


def _reasoning_item(item_id: str, text: str) -> Dict[str, Any]:
    """Build a reasoning output item with one summary_text part."""
    return {"type": "reasoning", "id": item_id, "summary": [{"type": "summary_text", "text": text}]}


def _message_item(item_id: str, text: str, status: str) -> Dict[str, Any]:
    """Build an assistant message output item with one output_text part."""
    return {
        "type": "message",
        "id": item_id,
        "status": status,
        "role": "assistant",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def _function_call_item(item_id: str, call_id: str, name: str, arguments: str, status: str) -> Dict[str, Any]:
    """Build a function_call output item."""
    return {
        "type": "function_call",
        "id": item_id,
        "call_id": call_id,
        "name": name,
        "arguments": arguments,
        "status": status,
    }


def chat_completion_to_response(chat_response: Dict[str, Any], request: ResponsesRequest) -> Dict[str, Any]:
    """
    Convert a non-streaming chat.completion dict into a Responses object.

    Output order: reasoning (if any), message (if text or no tool calls), function calls.

    Args:
        chat_response: Result of collect_stream_response (chat.completion)
        request: Original Responses request

    Returns:
        Responses API response object
    """
    choices = chat_response.get("choices") or [{}]
    choice = choices[0] or {}
    message = choice.get("message") or {}
    status, incomplete_details = status_from_finish_reason(choice.get("finish_reason"))
    item_status = "incomplete" if status == "incomplete" else "completed"

    output: List[Dict[str, Any]] = []
    reasoning_text = message.get("reasoning_content")
    if reasoning_text:
        output.append(_reasoning_item(generate_item_id("rs"), reasoning_text))

    text = message.get("content") or ""
    tool_calls = message.get("tool_calls") or []
    if text or not tool_calls:
        output.append(_message_item(generate_item_id("msg"), text, item_status))

    for tc in tool_calls:
        func = tc.get("function") or {}
        output.append(
            _function_call_item(
                generate_item_id("fc"),
                tc.get("id") or generate_item_id("call"),
                func.get("name") or "",
                func.get("arguments") or "{}",
                "completed",
            )
        )

    return build_response_object(
        request,
        response_id=generate_item_id("resp"),
        created_at=int(chat_response.get("created") or time.time()),
        status=status,
        output=output,
        usage=build_usage(chat_response.get("usage")),
        incomplete_details=incomplete_details,
    )


# ==================================================================================================
# Streaming: chat.completion.chunk SSE -> Responses SSE events
# ==================================================================================================

def format_sse_event(event: Dict[str, Any]) -> str:
    """
    Format a Responses event as an SSE frame.

    Args:
        event: Event dict containing "type"

    Returns:
        "event: <type>\\ndata: <json>\\n\\n"
    """
    return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


class ResponsesStreamTranslator:
    """
    Stateful translator from Chat Completions stream chunks to Responses events.

    Feed parsed chunk dicts with process_chunk(), then call finish() (normal end)
    or fail() (error). Every method returns a list of event dicts, already
    stamped with a monotonically increasing sequence_number.
    """

    def __init__(self, request: ResponsesRequest) -> None:
        """
        Args:
            request: Original Responses request (echoed into response objects)
        """
        self.request = request
        self.response_id = generate_item_id("resp")
        self.created_at = int(time.time())
        self._sequence = 0
        self._output: List[Optional[Dict[str, Any]]] = []
        self._finish_reason: Optional[str] = None
        self._usage: Optional[Dict[str, Any]] = None
        self._finished = False

        # Currently open items: (output_index, item_id, accumulated_text)
        self._reasoning: Optional[List[Any]] = None
        self._message: Optional[List[Any]] = None
        # Tool calls keyed by chat tool_call index -> state dict
        self._tools: Dict[int, Dict[str, Any]] = {}

    # --- helpers ---

    def _event(self, event_type: str, **fields: Any) -> Dict[str, Any]:
        """Create an event dict with type and next sequence_number."""
        event = {"type": event_type, "sequence_number": self._sequence, **fields}
        self._sequence += 1
        return event

    def _reserve_output_index(self) -> int:
        """Reserve the next output slot (filled when the item is done)."""
        self._output.append(None)
        return len(self._output) - 1

    def _snapshot(self, status: str, **extra: Any) -> Dict[str, Any]:
        """Response object for lifecycle events."""
        output = [item for item in self._output if item is not None]
        return build_response_object(
            self.request, self.response_id, self.created_at, status, output, **extra
        )

    # --- lifecycle ---

    def start(self) -> List[Dict[str, Any]]:
        """
        Emit response.created and response.in_progress.

        Returns:
            List of events
        """
        return [
            self._event("response.created", response=self._snapshot("in_progress")),
            self._event("response.in_progress", response=self._snapshot("in_progress")),
        ]

    def _close_reasoning(self) -> List[Dict[str, Any]]:
        """Close the open reasoning item, if any."""
        if self._reasoning is None:
            return []
        index, item_id, text = self._reasoning
        self._reasoning = None
        part = {"type": "summary_text", "text": text}
        item = _reasoning_item(item_id, text)
        self._output[index] = item
        return [
            self._event("response.reasoning_summary_text.done", item_id=item_id, output_index=index,
                        summary_index=0, text=text),
            self._event("response.reasoning_summary_part.done", item_id=item_id, output_index=index,
                        summary_index=0, part=part),
            self._event("response.output_item.done", output_index=index, item=item),
        ]

    def _close_message(self, item_status: str = "completed") -> List[Dict[str, Any]]:
        """Close the open message item, if any."""
        if self._message is None:
            return []
        index, item_id, text = self._message
        self._message = None
        part = {"type": "output_text", "text": text, "annotations": []}
        item = _message_item(item_id, text, item_status)
        self._output[index] = item
        return [
            self._event("response.output_text.done", item_id=item_id, output_index=index,
                        content_index=0, text=text),
            self._event("response.content_part.done", item_id=item_id, output_index=index,
                        content_index=0, part=part),
            self._event("response.output_item.done", output_index=index, item=item),
        ]

    def _close_tools(self) -> List[Dict[str, Any]]:
        """Close all open function_call items in output order."""
        events: List[Dict[str, Any]] = []
        for state in sorted(self._tools.values(), key=lambda s: s["output_index"]):
            arguments = state["arguments"] or "{}"
            item = _function_call_item(state["item_id"], state["call_id"], state["name"], arguments, "completed")
            self._output[state["output_index"]] = item
            events.append(self._event("response.function_call_arguments.done", item_id=state["item_id"],
                                      output_index=state["output_index"], arguments=arguments))
            events.append(self._event("response.output_item.done", output_index=state["output_index"], item=item))
        self._tools = {}
        return events

    # --- chunk handling ---

    def _on_reasoning(self, text: str) -> List[Dict[str, Any]]:
        """Handle a reasoning_content delta."""
        events: List[Dict[str, Any]] = []
        if self._reasoning is None:
            events.extend(self._close_message())
            index = self._reserve_output_index()
            item_id = generate_item_id("rs")
            self._reasoning = [index, item_id, ""]
            events.append(self._event("response.output_item.added", output_index=index,
                                      item={"type": "reasoning", "id": item_id, "summary": []}))
            events.append(self._event("response.reasoning_summary_part.added", item_id=item_id,
                                      output_index=index, summary_index=0,
                                      part={"type": "summary_text", "text": ""}))
        self._reasoning[2] += text
        events.append(self._event("response.reasoning_summary_text.delta", item_id=self._reasoning[1],
                                  output_index=self._reasoning[0], summary_index=0, delta=text))
        return events

    def _on_text(self, text: str) -> List[Dict[str, Any]]:
        """Handle a content delta."""
        events: List[Dict[str, Any]] = self._close_reasoning()
        if self._message is None:
            index = self._reserve_output_index()
            item_id = generate_item_id("msg")
            self._message = [index, item_id, ""]
            events.append(self._event("response.output_item.added", output_index=index,
                                      item={"type": "message", "id": item_id, "status": "in_progress",
                                            "role": "assistant", "content": []}))
            events.append(self._event("response.content_part.added", item_id=item_id, output_index=index,
                                      content_index=0,
                                      part={"type": "output_text", "text": "", "annotations": []}))
        self._message[2] += text
        events.append(self._event("response.output_text.delta", item_id=self._message[1],
                                  output_index=self._message[0], content_index=0, delta=text))
        return events

    def _on_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Handle a tool_calls delta (complete or incremental per index)."""
        events: List[Dict[str, Any]] = self._close_reasoning() + self._close_message()
        for position, tc in enumerate(tool_calls):
            if not isinstance(tc, dict):
                continue
            key = tc.get("index", position)
            func = tc.get("function") or {}
            state = self._tools.get(key)
            if state is None:
                index = self._reserve_output_index()
                state = {
                    "output_index": index,
                    "item_id": generate_item_id("fc"),
                    "call_id": tc.get("id") or generate_item_id("call"),
                    "name": func.get("name") or "",
                    "arguments": "",
                }
                self._tools[key] = state
                events.append(self._event(
                    "response.output_item.added", output_index=index,
                    item=_function_call_item(state["item_id"], state["call_id"], state["name"], "", "in_progress"),
                ))
            elif func.get("name") and not state["name"]:
                state["name"] = func["name"]

            fragment = func.get("arguments")
            if fragment:
                state["arguments"] += fragment
                events.append(self._event("response.function_call_arguments.delta", item_id=state["item_id"],
                                          output_index=state["output_index"], delta=fragment))
        return events

    def process_chunk(self, chunk: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Translate one chat.completion.chunk.

        Args:
            chunk: Parsed chunk dict

        Returns:
            List of Responses events
        """
        events: List[Dict[str, Any]] = []
        if chunk.get("usage"):
            self._usage = chunk["usage"]

        choices = chunk.get("choices") or []
        if not choices:
            return events
        choice = choices[0] or {}
        delta = choice.get("delta") or {}

        if delta.get("reasoning_content"):
            events.extend(self._on_reasoning(delta["reasoning_content"]))
        if delta.get("content"):
            events.extend(self._on_text(delta["content"]))
        if delta.get("tool_calls"):
            events.extend(self._on_tool_calls(delta["tool_calls"]))
        if choice.get("finish_reason"):
            self._finish_reason = choice["finish_reason"]
        return events

    def finish(self) -> List[Dict[str, Any]]:
        """
        Close all open items and emit response.completed / response.incomplete.

        Returns:
            List of events (empty if already finished)
        """
        if self._finished:
            return []
        self._finished = True
        status, incomplete_details = status_from_finish_reason(self._finish_reason)
        item_status = "incomplete" if status == "incomplete" else "completed"

        events = self._close_reasoning() + self._close_message(item_status) + self._close_tools()
        event_type = "response.incomplete" if status == "incomplete" else "response.completed"
        events.append(self._event(
            event_type,
            response=self._snapshot(status, usage=build_usage(self._usage), incomplete_details=incomplete_details),
        ))
        return events

    def fail(self, message: str, code: str = "server_error") -> List[Dict[str, Any]]:
        """
        Emit response.failed. Partial output already streamed is included as-is.

        Args:
            message: User-facing error message
            code: Error code

        Returns:
            List with the response.failed event (empty if already finished)
        """
        if self._finished:
            return []
        self._finished = True
        return [self._event(
            "response.failed",
            response=self._snapshot("failed", usage=build_usage(self._usage),
                                    error={"code": code, "message": message}),
        )]


async def _iter_sse_data(chunks: AsyncIterator[Any]) -> AsyncIterator[str]:
    """
    Yield the 'data:' payloads of an SSE byte/str stream, frame by frame.

    Args:
        chunks: Async iterator of str or bytes SSE fragments

    Yields:
        Data payload strings (without the "data: " prefix)
    """
    buffer = ""
    async for chunk in chunks:
        buffer += chunk.decode("utf-8") if isinstance(chunk, (bytes, bytearray)) else chunk
        while "\n\n" in buffer:
            frame, buffer = buffer.split("\n\n", 1)
            for line in frame.splitlines():
                if line.startswith("data:"):
                    yield line[5:].strip()
    for line in buffer.splitlines():
        if line.startswith("data:"):
            yield line[5:].strip()


async def stream_chat_to_responses(
    chat_stream: AsyncIterator[Any],
    request: ResponsesRequest,
) -> AsyncIterator[str]:
    """
    Re-emit a Chat Completions SSE stream as Responses SSE events.

    The chat stream signals errors by raising (after possibly yielding [DONE]),
    so completion is emitted only when the stream ends without an exception.

    Args:
        chat_stream: Async iterator of chat completion SSE chunks
        request: Original Responses request

    Yields:
        Responses SSE frames
    """
    translator = ResponsesStreamTranslator(request)
    for event in translator.start():
        yield format_sse_event(event)

    try:
        async for data in _iter_sse_data(chat_stream):
            if not data or data == "[DONE]":
                continue
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                logger.warning(f"Skipping malformed chat stream chunk: {data[:100]}")
                continue
            if not isinstance(chunk, dict):
                continue
            for event in translator.process_chunk(chunk):
                yield format_sse_event(event)
    except Exception as e:  # noqa: BLE001 - any upstream failure must become response.failed
        message = str(e) or type(e).__name__
        detail = getattr(e, "detail", None)
        if detail:
            message = str(detail)
        logger.error(f"Responses stream failed: [{type(e).__name__}] {message[:200]}")
        for event in translator.fail(message):
            yield format_sse_event(event)
        return
    finally:
        aclose = getattr(chat_stream, "aclose", None)
        if aclose is not None:
            try:
                await aclose()
            except RuntimeError as close_error:
                logger.debug(f"Error closing chat stream: {close_error}")

    for event in translator.finish():
        yield format_sse_event(event)
