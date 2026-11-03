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
Converters for transforming OpenAI format to Kiro format.

This module is an adapter layer that converts OpenAI-specific formats
to the unified format used by converters_core.py.

Contains functions for:
- Converting OpenAI messages to unified format
- Converting OpenAI tools to unified format
- Building Kiro payload from OpenAI requests
"""

import json
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from kiro.config import HIDDEN_MODELS
from kiro.model_resolver import get_model_id_for_kiro
from kiro.models_openai import ChatMessage, ChatCompletionRequest, Tool

# Import from core - reuse shared logic
from kiro.converters_core import (
    extract_text_content,
    extract_images_from_content,
    UnifiedMessage,
    UnifiedTool,
    UnifiedToolChoice,
    ThinkingConfig,
    TOOL_CHOICE_AUTO,
    TOOL_CHOICE_NONE,
    TOOL_CHOICE_REQUIRED,
    TOOL_CHOICE_TOOL,
    append_system_section,
    build_kiro_payload as core_build_kiro_payload,
)


# System instructions that emulate response_format (Kiro API has no such parameter).
JSON_OBJECT_INSTRUCTION: str = (
    "Respond only with a single valid JSON object. "
    "Do not include any text, explanation, or Markdown code fences outside the JSON."
)
JSON_SCHEMA_INSTRUCTION_TEMPLATE: str = (
    "Respond only with a single valid JSON value that conforms to the following JSON Schema{name_part}. "
    "Do not include any text, explanation, or Markdown code fences outside the JSON.\n\n"
    "JSON Schema:\n{schema}"
)


# ==================================================================================================
# OpenAI-specific Message Processing
# ==================================================================================================

def _extract_tool_results_from_openai(content: Any) -> List[Dict[str, Any]]:
    """
    Extracts tool results from OpenAI message content.
    
    Args:
        content: Message content (can be a list with tool_result blocks)
    
    Returns:
        List of tool results in unified format for UnifiedMessage
    """
    tool_results = []
    
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "tool_result":
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": item.get("tool_use_id", ""),
                    "content": extract_text_content(item.get("content", "")) or "(empty result)"
                })
    
    return tool_results


def _extract_images_from_tool_message(content: Any) -> List[Dict[str, Any]]:
    """
    Extracts images from OpenAI tool message content.
    
    Tool messages from MCP servers (e.g., browsermcp) can contain images
    (screenshots) alongside text. This function extracts those images.
    
    Args:
        content: Tool message content (can be string or list of content blocks)
    
    Returns:
        List of images in unified format: [{"media_type": "image/jpeg", "data": "base64..."}]
    
    Example:
        >>> content = [
        ...     {"type": "text", "text": "Screenshot captured"},
        ...     {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
        ... ]
        >>> images = _extract_images_from_tool_message(content)
        >>> len(images)
        1
    """
    # If content is not a list, no images to extract
    if not isinstance(content, list):
        return []
    
    # Use core function to extract images from content list
    images = extract_images_from_content(content)
    
    if images:
        logger.debug(f"Extracted {len(images)} image(s) from tool message content")
    
    return images


def _extract_tool_calls_from_openai(msg: ChatMessage) -> List[Dict[str, Any]]:
    """
    Extracts tool calls from OpenAI assistant message.
    
    Args:
        msg: OpenAI ChatMessage
    
    Returns:
        List of tool calls in unified format
    """
    tool_calls = []
    
    if msg.tool_calls:
        for tc in msg.tool_calls:
            if isinstance(tc, dict):
                tool_calls.append({
                    "id": tc.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": tc.get("function", {}).get("name", ""),
                        "arguments": tc.get("function", {}).get("arguments", "{}")
                    }
                })
    
    return tool_calls


def convert_openai_messages_to_unified(messages: List[ChatMessage]) -> Tuple[str, List[UnifiedMessage]]:
    """
    Converts OpenAI messages to unified format.
    
    Handles:
    - System messages (extracted as system prompt)
    - Tool messages (converted to user messages with tool_results)
    - Tool calls in assistant messages
    
    Args:
        messages: List of OpenAI ChatMessage objects
    
    Returns:
        Tuple of (system_prompt, unified_messages)
    """
    # Extract system prompt
    system_prompt = ""
    non_system_messages = []
    
    for msg in messages:
        if msg.role == "system":
            system_prompt += extract_text_content(msg.content) + "\n"
        else:
            non_system_messages.append(msg)
    
    system_prompt = system_prompt.strip()
    
    # Process tool messages - convert to user messages with tool_results
    processed = []
    pending_tool_results = []
    pending_tool_images = []
    total_tool_calls = 0
    total_tool_results = 0
    total_images = 0

    for msg in non_system_messages:
        if msg.role == "tool":
            # Collect tool results
            tool_result = {
                "type": "tool_result",
                "tool_use_id": msg.tool_call_id or "",
                "content": extract_text_content(msg.content) or "(empty result)"
            }
            pending_tool_results.append(tool_result)
            total_tool_results += 1
            
            # Extract images from tool message content (e.g., screenshots from MCP tools)
            tool_images = _extract_images_from_tool_message(msg.content)
            if tool_images:
                pending_tool_images.extend(tool_images)
                total_images += len(tool_images)
        else:
            # If there are accumulated tool results, create user message with them
            if pending_tool_results:
                unified_msg = UnifiedMessage(
                    role="user",
                    content="",
                    tool_results=pending_tool_results.copy(),
                    images=pending_tool_images.copy() if pending_tool_images else None
                )
                processed.append(unified_msg)
                pending_tool_results.clear()
                pending_tool_images.clear()
            
            # Convert regular message
            tool_calls = None
            tool_results = None
            images = None

            if msg.role == "assistant":
                tool_calls = _extract_tool_calls_from_openai(msg) or None
                if tool_calls:
                    total_tool_calls += len(tool_calls)
            elif msg.role == "user":
                tool_results = _extract_tool_results_from_openai(msg.content) or None
                if tool_results:
                    total_tool_results += len(tool_results)
                # Extract images from user messages
                images = extract_images_from_content(msg.content) or None
                if images:
                    total_images += len(images)

            unified_msg = UnifiedMessage(
                role=msg.role,
                content=extract_text_content(msg.content),
                tool_calls=tool_calls,
                tool_results=tool_results,
                images=images
            )
            processed.append(unified_msg)
    
    # If tool results remain at the end
    if pending_tool_results:
        unified_msg = UnifiedMessage(
            role="user",
            content="",
            tool_results=pending_tool_results.copy(),
            images=pending_tool_images.copy() if pending_tool_images else None
        )
        processed.append(unified_msg)
    
    # Log summary if any tool content or images were found
    if total_tool_calls > 0 or total_tool_results > 0 or total_images > 0:
        logger.debug(
            f"Converted {len(messages)} OpenAI messages: "
            f"{total_tool_calls} tool_calls, {total_tool_results} tool_results, {total_images} images"
        )
    
    return system_prompt, processed


def convert_openai_tools_to_unified(tools: Optional[List[Tool]]) -> Optional[List[UnifiedTool]]:
    """
    Converts OpenAI tools to unified format.
    
    Supports two formats:
    1. Standard OpenAI format: {"type": "function", "function": {"name": "...", ...}}
    2. Flat format (Cursor-style): {"name": "...", "description": "...", "input_schema": {...}}
    
    Args:
        tools: List of OpenAI Tool objects
    
    Returns:
        List of UnifiedTool objects, or None if no tools
    """
    if not tools:
        return None
    
    unified_tools = []
    for tool in tools:
        if tool.type != "function":
            continue
        
        # Standard OpenAI format (function field) takes priority
        if tool.function is not None:
            unified_tools.append(UnifiedTool(
                name=tool.function.name,
                description=tool.function.description,
                input_schema=tool.function.parameters
            ))
        # Flat format compatibility (Cursor-style)
        elif tool.name is not None:
            unified_tools.append(UnifiedTool(
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema
            ))
        # Skip invalid tools
        else:
            logger.warning(f"Skipping invalid tool: no function or name field found")
            continue
    
    return unified_tools if unified_tools else None


# ==================================================================================================
# tool_choice / response_format Emulation
# ==================================================================================================

def extract_tool_choice_from_openai(request: ChatCompletionRequest) -> Optional[UnifiedToolChoice]:
    """
    Converts OpenAI tool_choice and parallel_tool_calls to unified format.

    Mapping:
    - None / "auto" -> auto
    - "none" -> none (tools removed)
    - "required" -> at least one tool call
    - {"type": "function", "function": {"name": X}} -> forced tool X
      (the flat {"type": "function", "name": X} form is accepted too)
    - parallel_tool_calls=False -> at most one tool call
    Unrecognized values are logged and treated as auto.

    Args:
        request: OpenAI ChatCompletionRequest

    Returns:
        UnifiedToolChoice, or None when nothing deviates from the default
    """
    tool_choice = request.tool_choice
    disable_parallel = request.parallel_tool_calls is False
    mode = TOOL_CHOICE_AUTO
    tool_name: Optional[str] = None

    if isinstance(tool_choice, str):
        if tool_choice in (TOOL_CHOICE_NONE, TOOL_CHOICE_REQUIRED, TOOL_CHOICE_AUTO):
            mode = tool_choice
        else:
            logger.warning(f"Ignoring unsupported OpenAI tool_choice {tool_choice!r}; using auto")
    elif isinstance(tool_choice, dict):
        function = tool_choice.get("function")
        name = function.get("name") if isinstance(function, dict) else None
        name = name or tool_choice.get("name")
        if tool_choice.get("type") == "function" and isinstance(name, str) and name:
            mode = TOOL_CHOICE_TOOL
            tool_name = name
        else:
            logger.warning(f"Ignoring unsupported OpenAI tool_choice {tool_choice!r}; using auto")

    if mode == TOOL_CHOICE_AUTO and not disable_parallel:
        return None
    return UnifiedToolChoice(mode=mode, tool_name=tool_name, disable_parallel=disable_parallel)


def build_response_format_instruction(response_format: Optional[Dict[str, Any]]) -> str:
    """
    Builds a system instruction emulating OpenAI response_format.

    Kiro API cannot constrain output format, so the requested format is
    stated to the model instead. Output is not validated by the gateway.

    - None / {"type": "text"} -> no instruction
    - {"type": "json_object"} -> respond with a JSON object
    - {"type": "json_schema", "json_schema": {"name": ..., "schema": {...}}}
      -> respond with JSON matching the schema (schema included verbatim)

    Args:
        response_format: response_format value from the request

    Returns:
        Instruction text, or "" when no instruction is needed
    """
    if not isinstance(response_format, dict):
        return ""

    format_type = response_format.get("type")
    if format_type in (None, "text"):
        return ""

    if format_type == "json_object":
        logger.debug("response_format=json_object: adding JSON output instruction")
        return JSON_OBJECT_INSTRUCTION

    if format_type == "json_schema":
        json_schema = response_format.get("json_schema")
        if not isinstance(json_schema, dict):
            logger.warning("response_format json_schema has no json_schema object; asking for plain JSON")
            return JSON_OBJECT_INSTRUCTION
        schema = json_schema.get("schema", {})
        name = json_schema.get("name")
        name_part = f" (schema name: {name})" if isinstance(name, str) and name else ""
        schema_text = json.dumps(schema, ensure_ascii=False, indent=2)
        logger.debug(f"response_format=json_schema{name_part}: adding schema instruction")
        return JSON_SCHEMA_INSTRUCTION_TEMPLATE.format(name_part=name_part, schema=schema_text)

    logger.warning(f"Ignoring unsupported response_format type {format_type!r}")
    return ""


# ==================================================================================================
# Thinking Configuration Extraction
# ==================================================================================================

def reasoning_effort_to_budget(max_tokens: int, effort: str) -> int:
    """
    Convert reasoning_effort to thinking budget (production-grade mapping).
    
    Uses percentage-based approach that adapts to different max_tokens limits.
    This ensures that thinking budget scales proportionally with the output limit.
    
    Args:
        max_tokens: Maximum output tokens for the request
        effort: Reasoning effort level ("none", "minimal", "low", "medium", "high", "xhigh")
    
    Returns:
        Thinking budget in tokens
    
    Examples:
        >>> reasoning_effort_to_budget(4096, "high")
        3276  # 80% of 4096
        >>> reasoning_effort_to_budget(10000, "medium")
        5000  # 50% of 10000
    """
    percent = {
        "none": 0.0,      # 0% - thinking disabled (handled separately)
        "minimal": 0.10,  # 10% - minimal reasoning
        "low": 0.20,      # 20% - quick reasoning
        "medium": 0.50,   # 50% - balanced reasoning
        "high": 0.80,     # 80% - deep reasoning
        "xhigh": 0.95,    # 95% - maximum reasoning depth
    }
    return int(max_tokens * percent[effort])


def extract_thinking_config_from_openai(request: ChatCompletionRequest) -> ThinkingConfig:
    """
    Extract thinking configuration from OpenAI request.
    
    Handles reasoning_effort parameter:
    - "none" → disabled (no thinking tags injected)
    - "minimal", "low", "medium", "high", "xhigh" → enabled with percentage-based budget
    - None (not specified) → enabled with default budget
    
    Args:
        request: OpenAI ChatCompletionRequest
    
    Returns:
        ThinkingConfig for core layer
    
    Examples:
        >>> # No reasoning_effort specified → use defaults
        >>> request = ChatCompletionRequest(model="claude-sonnet-4.5", messages=[...])
        >>> extract_thinking_config_from_openai(request)
        ThinkingConfig(enabled=True, budget_tokens=None)
        
        >>> # Explicitly disabled
        >>> request.reasoning_effort = "none"
        >>> extract_thinking_config_from_openai(request)
        ThinkingConfig(enabled=False, budget_tokens=None)
        
        >>> # Custom budget from reasoning_effort
        >>> request.reasoning_effort = "high"
        >>> request.max_tokens = 4096
        >>> extract_thinking_config_from_openai(request)
        ThinkingConfig(enabled=True, budget_tokens=3276)  # 80% of 4096
    """
    if not request.reasoning_effort:
        # No reasoning_effort specified → use defaults
        return ThinkingConfig(enabled=True, budget_tokens=None)
    
    if request.reasoning_effort == "none":
        # Explicitly disabled
        return ThinkingConfig(enabled=False, budget_tokens=None)
    
    # Calculate budget from reasoning_effort
    # Get max_tokens from request (OUTPUT tokens limit)
    max_tokens = request.max_tokens or request.max_completion_tokens
    if not max_tokens:
        # Fallback to reasonable default for OUTPUT tokens
        # NOT DEFAULT_MAX_INPUT_TOKENS (200000) - that's for INPUT
        max_tokens = 4096  # Standard output limit
    
    budget = reasoning_effort_to_budget(max_tokens, request.reasoning_effort)
    
    logger.debug(
        f"Extracted thinking config from OpenAI: reasoning_effort='{request.reasoning_effort}', "
        f"max_tokens={max_tokens}, budget={budget}"
    )
    
    return ThinkingConfig(enabled=True, budget_tokens=budget)


# ==================================================================================================
# Main Entry Point
# ==================================================================================================

def build_kiro_payload(
    request_data: ChatCompletionRequest,
    conversation_id: str,
    profile_arn: str
) -> dict:
    """
    Builds complete payload for Kiro API from OpenAI request.
    
    This is the main entry point for OpenAI → Kiro conversion.
    Uses the core build_kiro_payload function with OpenAI-specific adapters.
    
    Args:
        request_data: Request in OpenAI format
        conversation_id: Unique conversation ID
        profile_arn: AWS CodeWhisperer profile ARN
    
    Returns:
        Payload dictionary for POST request to Kiro API
    
    Raises:
        ValueError: If there are no messages to send
    """
    # Convert messages to unified format
    system_prompt, unified_messages = convert_openai_messages_to_unified(request_data.messages)
    
    # Convert tools to unified format
    unified_tools = convert_openai_tools_to_unified(request_data.tools)
    
    # Get model ID for Kiro API (normalizes + resolves hidden models)
    # Pass-through principle: we normalize and send to Kiro, Kiro decides if valid
    model_id = get_model_id_for_kiro(request_data.model, HIDDEN_MODELS)
    
    # Extract thinking configuration from reasoning_effort
    thinking_config = extract_thinking_config_from_openai(request_data)

    # Emulate response_format with a system instruction
    system_prompt = append_system_section(
        system_prompt, build_response_format_instruction(request_data.response_format)
    )

    # Convert tool_choice / parallel_tool_calls to unified format
    tool_choice = extract_tool_choice_from_openai(request_data)

    logger.debug(
        f"Converting OpenAI request: model={request_data.model} -> {model_id}, "
        f"messages={len(unified_messages)}, tools={len(unified_tools) if unified_tools else 0}, "
        f"system_prompt_length={len(system_prompt)}, "
        f"thinking_enabled={thinking_config.enabled}, thinking_budget={thinking_config.budget_tokens}"
    )
    
    # Use core function to build payload
    result = core_build_kiro_payload(
        messages=unified_messages,
        system_prompt=system_prompt,
        model_id=model_id,
        tools=unified_tools,
        conversation_id=conversation_id,
        profile_arn=profile_arn,
        thinking_config=thinking_config,
        tool_choice=tool_choice,
    )

    return result.payload