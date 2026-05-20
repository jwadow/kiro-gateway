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
Responses API formatting for Kiro streams.

This module adapts the existing OpenAI chat-completion stream into the
OpenAI Responses API object and semantic SSE event shape.
"""

import json
import time
import uuid
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional

import httpx

from kiro.streaming_openai import collect_stream_response, stream_kiro_to_openai

if TYPE_CHECKING:
    from kiro.auth import KiroAuthManager
    from kiro.cache import ModelInfoCache


def generate_response_id() -> str:
    """
    Generate an OpenAI Responses API-compatible response ID.

    Returns:
        ID in format ``resp_<uuid_hex>``.
    """
    return f"resp_{uuid.uuid4().hex}"


def _usage_to_responses_usage(usage: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Convert Chat Completions usage fields to Responses API usage fields.

    Args:
        usage: OpenAI chat-completion usage dictionary.

    Returns:
        Responses API usage dictionary, or None if usage is absent.
    """
    if usage is None:
        return None

    input_tokens = int(usage.get("prompt_tokens", 0) or 0)
    output_tokens = int(usage.get("completion_tokens", 0) or 0)
    total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens) or 0)

    result = {
        "input_tokens": input_tokens,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens": output_tokens,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": total_tokens,
    }

    if "credits_used" in usage:
        result["credits_used"] = usage["credits_used"]

    return result


def _message_output_item(text: str, item_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Build a Responses API message output item.

    Args:
        text: Assistant text content.
        item_id: Optional stable item ID.

    Returns:
        Responses API output item.
    """
    return {
        "id": item_id or f"msg_{uuid.uuid4().hex}",
        "type": "message",
        "status": "completed",
        "role": "assistant",
        "content": [{
            "type": "output_text",
            "text": text,
            "annotations": [],
        }],
    }


def _function_call_output_item(tool_call: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a Responses API function_call output item from a chat tool call.

    Args:
        tool_call: OpenAI chat-completion tool call.

    Returns:
        Responses API function_call item.
    """
    function = tool_call.get("function") or {}
    arguments = function.get("arguments", "{}")
    if not isinstance(arguments, str):
        arguments = json.dumps(arguments, ensure_ascii=False)

    call_id = tool_call.get("id") or f"call_{uuid.uuid4().hex}"

    return {
        "id": f"fc_{uuid.uuid4().hex}",
        "type": "function_call",
        "status": "completed",
        "call_id": call_id,
        "name": function.get("name", ""),
        "arguments": arguments,
    }


def chat_completion_to_response(
    chat_response: Dict[str, Any],
    response_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convert a non-streaming Chat Completions response to Responses API format.

    Args:
        chat_response: OpenAI chat-completion response.
        response_id: Optional response ID to use.

    Returns:
        Responses API response object.
    """
    output: List[Dict[str, Any]] = []
    message = chat_response.get("choices", [{}])[0].get("message", {})
    text = message.get("content") or ""

    if text:
        output.append(_message_output_item(text))

    for tool_call in message.get("tool_calls") or []:
        output.append(_function_call_output_item(tool_call))

    usage = _usage_to_responses_usage(chat_response.get("usage"))

    return {
        "id": response_id or generate_response_id(),
        "object": "response",
        "created_at": chat_response.get("created", int(time.time())),
        "status": "completed",
        "background": False,
        "error": None,
        "incomplete_details": None,
        "instructions": None,
        "max_output_tokens": None,
        "model": chat_response.get("model"),
        "output": output,
        "output_text": text,
        "parallel_tool_calls": True,
        "previous_response_id": None,
        "reasoning": {"effort": None, "summary": None},
        "store": True,
        "temperature": None,
        "text": {"format": {"type": "text"}},
        "tool_choice": "auto",
        "tools": [],
        "top_p": None,
        "truncation": "disabled",
        "usage": usage,
        "user": None,
        "metadata": {},
    }


def _sse_event(event_name: str, data: Dict[str, Any]) -> str:
    """
    Format a Responses API streaming server-sent event.

    Args:
        event_name: Responses API event name.
        data: JSON-serializable event payload.

    Returns:
        SSE text chunk.
    """
    return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_kiro_to_responses(
    client: httpx.AsyncClient,
    response: httpx.Response,
    model: str,
    model_cache: "ModelInfoCache",
    auth_manager: "KiroAuthManager",
    request_messages: Optional[list] = None,
    request_tools: Optional[list] = None
) -> AsyncGenerator[str, None]:
    """
    Convert a Kiro stream to OpenAI Responses API streaming events.

    Args:
        client: HTTP client.
        response: HTTP response with data stream.
        model: Model name to include in response.
        model_cache: Model cache for token limits.
        auth_manager: Authentication manager.
        request_messages: Original request messages for token fallback.
        request_tools: Original request tools for token fallback.

    Yields:
        SSE strings with Responses API event names.
    """
    response_id = generate_response_id()
    created_at = int(time.time())
    base_response = {
        "id": response_id,
        "object": "response",
        "created_at": created_at,
        "status": "in_progress",
        "model": model,
        "output": [],
        "output_text": "",
        "usage": None,
    }

    yield _sse_event("response.created", {
        "type": "response.created",
        "response": base_response,
    })

    message_item_id = f"msg_{uuid.uuid4().hex}"
    content_started = False
    full_text = ""
    final_usage = None
    tool_calls: List[Dict[str, Any]] = []

    async for chunk_str in stream_kiro_to_openai(
        client,
        response,
        model,
        model_cache,
        auth_manager,
        request_messages=request_messages,
        request_tools=request_tools,
    ):
        if not chunk_str.startswith("data:"):
            continue

        data_str = chunk_str[len("data:"):].strip()
        if not data_str or data_str == "[DONE]":
            continue

        chunk_data = json.loads(data_str)
        delta = chunk_data.get("choices", [{}])[0].get("delta", {})

        if "content" in delta and delta["content"]:
            if not content_started:
                message_item = _message_output_item("", message_item_id)
                yield _sse_event("response.output_item.added", {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": message_item,
                })
                yield _sse_event("response.content_part.added", {
                    "type": "response.content_part.added",
                    "item_id": message_item_id,
                    "output_index": 0,
                    "content_index": 0,
                    "part": {"type": "output_text", "text": "", "annotations": []},
                })
                content_started = True

            full_text += delta["content"]
            yield _sse_event("response.output_text.delta", {
                "type": "response.output_text.delta",
                "item_id": message_item_id,
                "output_index": 0,
                "content_index": 0,
                "delta": delta["content"],
            })

        if "tool_calls" in delta:
            tool_calls.extend(delta["tool_calls"])

        if "usage" in chunk_data:
            final_usage = chunk_data["usage"]

    output: List[Dict[str, Any]] = []
    if content_started:
        message_item = _message_output_item(full_text, message_item_id)
        output.append(message_item)
        yield _sse_event("response.output_text.done", {
            "type": "response.output_text.done",
            "item_id": message_item_id,
            "output_index": 0,
            "content_index": 0,
            "text": full_text,
        })
        yield _sse_event("response.content_part.done", {
            "type": "response.content_part.done",
            "item_id": message_item_id,
            "output_index": 0,
            "content_index": 0,
            "part": message_item["content"][0],
        })
        yield _sse_event("response.output_item.done", {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": message_item,
        })

    for tool_call in tool_calls:
        item = _function_call_output_item(tool_call)
        arguments = item.get("arguments", "")
        added_item = {**item, "arguments": ""}
        output.append(item)
        yield _sse_event("response.output_item.added", {
            "type": "response.output_item.added",
            "output_index": len(output) - 1,
            "item": added_item,
        })
        if arguments:
            yield _sse_event("response.function_call_arguments.delta", {
                "type": "response.function_call_arguments.delta",
                "item_id": item["id"],
                "output_index": len(output) - 1,
                "delta": arguments,
            })
        yield _sse_event("response.function_call_arguments.done", {
            "type": "response.function_call_arguments.done",
            "item_id": item["id"],
            "output_index": len(output) - 1,
            "arguments": arguments,
        })
        yield _sse_event("response.output_item.done", {
            "type": "response.output_item.done",
            "output_index": len(output) - 1,
            "item": item,
        })

    completed_response = {
        **base_response,
        "status": "completed",
        "output": output,
        "output_text": full_text,
        "usage": _usage_to_responses_usage(final_usage),
    }
    yield _sse_event("response.completed", {
        "type": "response.completed",
        "response": completed_response,
    })
    yield "data: [DONE]\n\n"


async def collect_responses_response(
    client: httpx.AsyncClient,
    response: httpx.Response,
    model: str,
    model_cache: "ModelInfoCache",
    auth_manager: "KiroAuthManager",
    request_messages: Optional[list] = None,
    request_tools: Optional[list] = None
) -> Dict[str, Any]:
    """
    Collect a Kiro stream into a non-streaming Responses API object.

    Args:
        client: HTTP client.
        response: HTTP response with data stream.
        model: Model name.
        model_cache: Model cache for token limits.
        auth_manager: Authentication manager.
        request_messages: Original request messages for token fallback.
        request_tools: Original request tools for token fallback.

    Returns:
        Responses API response object.
    """
    chat_response = await collect_stream_response(
        client,
        response,
        model,
        model_cache,
        auth_manager,
        request_messages=request_messages,
        request_tools=request_tools,
    )
    return chat_completion_to_response(chat_response)
