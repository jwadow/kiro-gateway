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

        elif item_type == "reasoning":
            # Ignore server-side reasoning items - Kiro has no encrypted reasoning
            ignored_reasoning += 1

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

def convert_responses_tools_to_unified(
    tools: Optional[List[ResponsesTool]],
) -> Optional[List[UnifiedTool]]:
    """
    Convert Responses tools (flat format) to unified tools.

    Only `function` type tools are supported; built-in tool types (web_search,
    file_search, etc.) are skipped since Kiro only accepts custom functions.

    Args:
        tools: List of ResponsesTool objects

    Returns:
        List of UnifiedTool objects, or None if no usable tools
    """
    if not tools:
        return None

    unified_tools: List[UnifiedTool] = []
    for tool in tools:
        if tool.type != "function":
            logger.debug(f"Skipping non-function Responses tool: type={tool.type}")
            continue
        if not tool.name:
            logger.warning("Skipping Responses function tool with no name")
            continue
        unified_tools.append(UnifiedTool(
            name=tool.name,
            description=tool.description,
            input_schema=tool.parameters,
        ))

    return unified_tools if unified_tools else None


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
    unified_tools = convert_responses_tools_to_unified(request_data.tools)

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
