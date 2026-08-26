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
Converters for transforming OpenAI Responses API format to Kiro format.

This is the adapter layer for the Responses API (used by Codex CLI). It converts
Responses-specific structures into the unified format used by converters_core.py.

Key differences handled here:
- `input` may be a string or a list of typed items
- `instructions` (+ any system/developer messages) become the system prompt
- `function_call` / `function_call_output` are TOP-LEVEL items (not nested in a
  message). We emit them as separate assistant/user UnifiedMessages carrying
  tool_calls / tool_results; the core layer merges adjacent same-role messages.
- `reasoning` items (id=rs_..., encrypted_content) are IGNORED. Kiro produces
  plaintext thinking only, so we cannot honor server-side reasoning references.
  Passing them through would trigger "Item with id rs_... not found" style errors.
- Tools use a flat structure (no nested `function` object)
"""

import json
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from kiro.config import HIDDEN_MODELS
from kiro.model_resolver import get_model_id_for_kiro
from kiro.models_responses import ResponsesRequest, ResponsesTool

from kiro.converters_core import (
    extract_text_content,
    UnifiedMessage,
    UnifiedTool,
    ThinkingConfig,
    build_kiro_payload as core_build_kiro_payload,
)
from kiro.converters_openai import reasoning_effort_to_budget


# ==================================================================================================
# Content part normalization
# ==================================================================================================

def _normalize_content_parts(content: Any) -> Any:
    """
    Normalize Responses content parts into blocks the core layer understands.

    Responses uses part types like `input_text`, `output_text`, `input_image`.
    The core's extract_text_content()/extract_images_from_content() understand
    `text` blocks and OpenAI-style `image_url` blocks, so we translate.

    Args:
        content: Message content (string or list of content parts)

    Returns:
        Normalized content (string passed through; list of blocks otherwise)
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)

    normalized: List[Dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            if isinstance(part, str):
                normalized.append({"type": "text", "text": part})
            continue

        part_type = part.get("type")

        if part_type in ("input_text", "output_text", "text", "summary_text"):
            normalized.append({"type": "text", "text": part.get("text", "")})
        elif part_type in ("input_image", "image"):
            # Responses puts the URL/data URL directly in `image_url` (a string)
            url = part.get("image_url")
            if isinstance(url, dict):
                url = url.get("url", "")
            if url:
                normalized.append({"type": "image_url", "image_url": {"url": url}})
        elif "text" in part:
            normalized.append({"type": "text", "text": part.get("text", "")})

    return normalized


# ==================================================================================================
# Input items -> Unified messages
# ==================================================================================================

def _function_call_to_unified(item: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a Responses function_call item to a unified tool_call."""
    arguments = item.get("arguments", "{}")
    if not isinstance(arguments, str):
        # Some clients may send arguments as an object
        try:
            arguments = json.dumps(arguments, ensure_ascii=False)
        except (TypeError, ValueError):
            arguments = "{}"
    return {
        "id": item.get("call_id") or item.get("id") or "",
        "type": "function",
        "function": {
            "name": item.get("name", ""),
            "arguments": arguments or "{}",
        },
    }


def _function_call_output_to_unified(item: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a Responses function_call_output item to a unified tool_result."""
    output = item.get("output", "")
    if isinstance(output, str):
        content_text = output
    else:
        # output may be a list of content parts or structured data
        content_text = extract_text_content(_normalize_content_parts(output))
        if not content_text and output is not None:
            try:
                content_text = json.dumps(output, ensure_ascii=False)
            except (TypeError, ValueError):
                content_text = str(output)
    return {
        "type": "tool_result",
        "tool_use_id": item.get("call_id") or item.get("id") or "",
        "content": content_text or "(empty result)",
    }


# Property name used to carry a custom tool's freeform text through the synthesized
# JSON-schema function (Kiro only accepts JSON-schema functions, not freeform text).
CUSTOM_TOOL_INPUT_KEY = "input"


def _custom_tool_call_to_unified(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a Responses custom_tool_call item to a unified tool_call.

    Custom tools carry freeform text in `input` (not JSON arguments). To keep the
    Kiro conversation history consistent with the synthesized JSON-schema function
    (see _synthesize_custom_tool), we wrap that text as {"input": "<raw text>"}.
    """
    raw_input = item.get("input", "")
    if not isinstance(raw_input, str):
        try:
            raw_input = json.dumps(raw_input, ensure_ascii=False)
        except (TypeError, ValueError):
            raw_input = str(raw_input)
    return {
        "id": item.get("call_id") or item.get("id") or "",
        "type": "function",
        "function": {
            "name": item.get("name", ""),
            "arguments": json.dumps({CUSTOM_TOOL_INPUT_KEY: raw_input}, ensure_ascii=False),
        },
    }


def _custom_tool_call_output_to_unified(item: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a Responses custom_tool_call_output item to a unified tool_result."""
    output = item.get("output", "")
    if isinstance(output, str):
        content_text = output
    else:
        content_text = extract_text_content(_normalize_content_parts(output))
        if not content_text and output is not None:
            try:
                content_text = json.dumps(output, ensure_ascii=False)
            except (TypeError, ValueError):
                content_text = str(output)
    return {
        "type": "tool_result",
        "tool_use_id": item.get("call_id") or item.get("id") or "",
        "content": content_text or "(empty result)",
    }


def convert_responses_input_to_unified(
    request: ResponsesRequest,
) -> Tuple[str, List[UnifiedMessage]]:
    """
    Convert Responses `input` + `instructions` into (system_prompt, unified_messages).

    Args:
        request: The parsed Responses request

    Returns:
        Tuple of (system_prompt, unified_messages)
    """
    system_parts: List[str] = []
    if request.instructions:
        system_parts.append(request.instructions)

    unified: List[UnifiedMessage] = []

    # Plain string input -> single user message
    if isinstance(request.input, str):
        unified.append(UnifiedMessage(role="user", content=request.input))
        return "\n".join(system_parts).strip(), unified

    ignored_reasoning = 0
    tool_calls_seen = 0
    tool_results_seen = 0

    for item in request.input:
        if not isinstance(item, dict):
            # Bare string item -> user message
            if isinstance(item, str):
                unified.append(UnifiedMessage(role="user", content=item))
            continue

        item_type = item.get("type", "message")

        if item_type == "message":
            role = item.get("role", "user")
            normalized = _normalize_content_parts(item.get("content"))

            # system / developer messages fold into the system prompt
            if role in ("system", "developer"):
                text = extract_text_content(normalized)
                if text:
                    system_parts.append(text)
                continue

            unified.append(UnifiedMessage(role=role, content=normalized))

        elif item_type == "function_call":
            unified.append(UnifiedMessage(
                role="assistant",
                content="",
                tool_calls=[_function_call_to_unified(item)],
            ))
            tool_calls_seen += 1

        elif item_type == "function_call_output":
            unified.append(UnifiedMessage(
                role="user",
                content="",
                tool_results=[_function_call_output_to_unified(item)],
            ))
            tool_results_seen += 1

        elif item_type == "custom_tool_call":
            # Freeform custom tool invocation (e.g. Codex `exec`). Wrapped as a
            # normal tool_call so Kiro sees consistent history.
            unified.append(UnifiedMessage(
                role="assistant",
                content="",
                tool_calls=[_custom_tool_call_to_unified(item)],
            ))
            tool_calls_seen += 1

        elif item_type == "custom_tool_call_output":
            unified.append(UnifiedMessage(
                role="user",
                content="",
                tool_results=[_custom_tool_call_output_to_unified(item)],
            ))
            tool_results_seen += 1

        elif item_type == "reasoning":
            # Ignore server-side reasoning items - Kiro has no encrypted reasoning
            ignored_reasoning += 1

        elif item_type == "additional_tools":
            # Tool definitions embedded in input (Codex CLI). Collected separately
            # by collect_unified_tools(); nothing to add to the message list here.
            continue

        else:
            # Unknown item type - try to salvage any text content
            text = extract_text_content(_normalize_content_parts(item.get("content")))
            if text:
                unified.append(UnifiedMessage(role=item.get("role", "user"), content=text))
            else:
                logger.debug(f"Ignoring unsupported Responses input item type: {item_type}")

    if ignored_reasoning or tool_calls_seen or tool_results_seen:
        logger.debug(
            f"Converted Responses input: {len(unified)} messages, "
            f"{tool_calls_seen} function_call(s), {tool_results_seen} function_call_output(s), "
            f"{ignored_reasoning} reasoning item(s) ignored"
        )

    return "\n".join(system_parts).strip(), unified


# ==================================================================================================
# Tools
# ==================================================================================================

def _tool_to_dict(tool: Any) -> Dict[str, Any]:
    """Normalize a tool (ResponsesTool object or raw dict) to a plain dict."""
    if isinstance(tool, dict):
        return tool
    if hasattr(tool, "model_dump"):
        return tool.model_dump()
    return {}


def _synthesize_custom_tool(t: Dict[str, Any]) -> Optional[UnifiedTool]:
    """
    Synthesize a JSON-schema function for a Responses `custom` tool.

    Custom tools (e.g. Codex `exec`, `apply_patch`) take FREEFORM text input, not
    JSON arguments. Kiro only accepts JSON-schema functions, so we wrap the
    freeform text in a single string property (CUSTOM_TOOL_INPUT_KEY). The
    streaming layer later unwraps this back into a `custom_tool_call` whose
    `input` is the raw string.

    The original `format` (lark grammar / text) cannot be enforced by Kiro's
    model, so we surface the tool's description and instruct the model to place
    the entire freeform payload in the `input` field verbatim.

    Returns:
        A UnifiedTool, or None if the tool has no name.
    """
    name = t.get("name")
    if not name:
        logger.warning("Skipping custom Responses tool with no name")
        return None

    base_desc = t.get("description") or ""
    fmt = t.get("format") or {}
    fmt_type = fmt.get("type")
    grammar_note = ""
    if fmt_type == "grammar":
        grammar_note = (
            f" The payload must follow the tool's {fmt.get('syntax', '')} grammar "
            f"exactly as described above."
        )

    description = (
        f"{base_desc}\n\n"
        f"[Freeform tool] Put the ENTIRE raw tool payload as plain text in the "
        f"`{CUSTOM_TOOL_INPUT_KEY}` string field. Do NOT wrap it in JSON, quotes, "
        f"or markdown fences.{grammar_note}"
    ).strip()

    return UnifiedTool(
        name=name,
        description=description,
        input_schema={
            "type": "object",
            "properties": {
                CUSTOM_TOOL_INPUT_KEY: {
                    "type": "string",
                    "description": "The complete freeform tool payload as plain text.",
                }
            },
            "required": [CUSTOM_TOOL_INPUT_KEY],
        },
    )


def convert_responses_tools_to_unified(
    tools: Optional[List[Any]],
) -> Optional[List[UnifiedTool]]:
    """
    Convert Responses tools (flat format) to unified tools.

    Handles the tool shapes Codex CLI sends:
    - `function`: a standard JSON-schema function -> UnifiedTool
    - `namespace`: a grouping (e.g. "collaboration") whose `tools` are flattened;
      the model calls the sub-tools by their bare name, so no prefix is added
    - `custom`: freeform-text tools (e.g. `exec`, lark grammar) -> synthesized into
      a JSON-schema function with a single `input` string field, since Kiro only
      accepts JSON-schema functions. The streaming layer unwraps these back into
      `custom_tool_call` events (see collect_custom_tool_names).
    - other built-in types (web_search, file_search, ...) -> skipped

    Args:
        tools: List of ResponsesTool objects and/or raw tool dicts

    Returns:
        List of UnifiedTool objects, or None if no usable tools
    """
    if not tools:
        return None

    unified_tools: List[UnifiedTool] = []
    synthesized_custom: List[str] = []

    def _add(tool: Any) -> None:
        t = _tool_to_dict(tool)
        ttype = t.get("type", "function")

        if ttype == "namespace":
            for sub in t.get("tools") or []:
                _add(sub)
            return

        if ttype == "custom":
            synth = _synthesize_custom_tool(t)
            if synth:
                unified_tools.append(synth)
                synthesized_custom.append(synth.name)
            return

        if ttype != "function":
            logger.debug(f"Skipping non-function Responses tool: type={ttype}")
            return

        name = t.get("name")
        if not name:
            logger.warning("Skipping Responses function tool with no name")
            return

        unified_tools.append(UnifiedTool(
            name=name,
            description=t.get("description"),
            input_schema=t.get("parameters"),
        ))

    for tool in tools:
        _add(tool)

    if synthesized_custom:
        logger.debug(
            f"Synthesized {len(synthesized_custom)} custom freeform tool(s) as "
            f"JSON-schema functions: {', '.join(synthesized_custom)}"
        )

    return unified_tools if unified_tools else None


def collect_custom_tool_names(request: ResponsesRequest) -> set:
    """
    Collect the names of all `custom` (freeform) tools in a Responses request.

    The streaming/collection layer uses this set to decide which tool calls must
    be emitted as `custom_tool_call` events (freeform `input`) rather than
    ordinary `function_call` events (JSON `arguments`).

    Walks the same sources as collect_unified_tools: top-level `tools` and any
    `additional_tools` input items, descending into `namespace` groups.

    Args:
        request: The parsed Responses request

    Returns:
        Set of custom tool names (may be empty)
    """
    names: set = set()

    def _scan(tool: Any) -> None:
        t = _tool_to_dict(tool)
        ttype = t.get("type", "function")
        if ttype == "namespace":
            for sub in t.get("tools") or []:
                _scan(sub)
        elif ttype == "custom":
            name = t.get("name")
            if name:
                names.add(name)

    if request.tools:
        for tool in request.tools:
            _scan(tool)

    if isinstance(request.input, list):
        for item in request.input:
            if isinstance(item, dict) and item.get("type") == "additional_tools":
                for sub in item.get("tools") or []:
                    _scan(sub)

    return names


def collect_unified_tools(request: ResponsesRequest) -> Optional[List[UnifiedTool]]:
    """
    Collect tools from every place a Responses request may carry them.

    Codex CLI does not use the top-level `tools` field; instead it embeds an
    `additional_tools` item (role="developer") as the first element of `input`,
    whose `tools` list holds the real tool definitions. We gather from both the
    top-level field and any `additional_tools` items so no tools are lost.

    Args:
        request: The parsed Responses request

    Returns:
        List of UnifiedTool objects, or None if no usable tools
    """
    if request.tool_choice == "none":
        logger.debug("Responses tool_choice='none': omitting tools from Kiro payload")
        return None

    raw_tools: List[Any] = []

    if request.tools:
        raw_tools.extend(request.tools)

    if isinstance(request.input, list):
        for item in request.input:
            if isinstance(item, dict) and item.get("type") == "additional_tools":
                sub = item.get("tools")
                if isinstance(sub, list):
                    raw_tools.extend(sub)

    return convert_responses_tools_to_unified(raw_tools)


# ==================================================================================================
# Thinking configuration
# ==================================================================================================

def extract_thinking_config_from_responses(request: ResponsesRequest) -> ThinkingConfig:
    """
    Extract thinking configuration from a Responses request's `reasoning.effort`.

    - No reasoning specified -> enabled with default budget
    - effort "none" -> disabled
    - effort minimal/low/medium/high/xhigh -> percentage-based budget

    Args:
        request: The parsed Responses request

    Returns:
        ThinkingConfig for the core layer
    """
    effort = request.reasoning.effort if request.reasoning else None

    if not effort:
        return ThinkingConfig(enabled=True, budget_tokens=None)

    if effort == "none":
        return ThinkingConfig(enabled=False, budget_tokens=None)

    max_tokens = request.max_output_tokens or 4096

    # Unknown effort levels fall back to the default budget
    try:
        budget = reasoning_effort_to_budget(max_tokens, effort)
    except KeyError:
        logger.debug(f"Unknown reasoning effort '{effort}', using default budget")
        return ThinkingConfig(enabled=True, budget_tokens=None)

    logger.debug(
        f"Extracted thinking config from Responses: effort='{effort}', "
        f"max_output_tokens={max_tokens}, budget={budget}"
    )
    return ThinkingConfig(enabled=True, budget_tokens=budget)


# ==================================================================================================
# Main entry point
# ==================================================================================================

def build_kiro_payload(
    request_data: ResponsesRequest,
    conversation_id: str,
    profile_arn: str,
) -> dict:
    """
    Build a complete Kiro API payload from a Responses API request.

    Args:
        request_data: Request in Responses API format
        conversation_id: Unique conversation ID
        profile_arn: AWS CodeWhisperer profile ARN

    Returns:
        Payload dictionary for POST to Kiro API

    Raises:
        ValueError: If there are no messages to send
    """
    system_prompt, unified_messages = convert_responses_input_to_unified(request_data)
    unified_tools = collect_unified_tools(request_data)

    model_id = get_model_id_for_kiro(request_data.model, HIDDEN_MODELS)
    thinking_config = extract_thinking_config_from_responses(request_data)

    logger.debug(
        f"Converting Responses request: model={request_data.model} -> {model_id}, "
        f"messages={len(unified_messages)}, tools={len(unified_tools) if unified_tools else 0}, "
        f"system_prompt_length={len(system_prompt)}, "
        f"thinking_enabled={thinking_config.enabled}, thinking_budget={thinking_config.budget_tokens}"
    )

    result = core_build_kiro_payload(
        messages=unified_messages,
        system_prompt=system_prompt,
        model_id=model_id,
        tools=unified_tools,
        conversation_id=conversation_id,
        profile_arn=profile_arn,
        thinking_config=thinking_config,
    )

    return result.payload
