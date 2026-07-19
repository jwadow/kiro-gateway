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
Converters for transforming Anthropic Messages API format to Kiro format.

This module is an adapter layer that converts Anthropic-specific formats
to the unified format used by converters_core.py.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from kiro.config import (
    HIDDEN_MODELS,
    MODEL_ALIASES,
    STRIP_BILLING_HEADER,
    KIRO_NATIVE_THINKING_MODE,
    KIRO_NATIVE_THINKING_DISPLAY,
)
from kiro.model_resolver import get_model_id_for_kiro
from kiro.models_anthropic import (
    AnthropicMessagesRequest,
    AnthropicMessage,
    AnthropicTool,
)
from kiro.converters_core import (
    UnifiedMessage,
    UnifiedTool,
    ThinkingConfig,
    NativeThinkingConfig,
    build_native_thinking_config,
    build_kiro_payload,
    extract_text_content,
    extract_images_from_content,
    extract_document_text_from_content_block,
    KIRO_CACHE_POINT,
)


# ==================================================================================================
# Billing Attribution Stripping
# ==================================================================================================

_BILLING_HEADER_LINE_PATTERN = re.compile(
    r"^x-anthropic-billing-header:[^\n]*\n?", re.IGNORECASE
)
_BILLING_FOOTER_RE = re.compile(r"Response from [^.]+\.model\..+?\.(.+?) via", re.DOTALL)


def _strip_billing_attribution(text: str) -> str:
    """
    Strip AWS Q Developer / Kiro billing attribution from response text.

    Handles two patterns:
    1. Claude Code's per-request billing header line:
       ``x-anthropic-billing-header: cc_version=...; cc_entrypoint=...``
    2. Kiro API's billing footer:
       ``Response from prod.us-east-1.deflector.9x7g0y8h model.claude-3-5-sonnet-20241022-v2:0 via ...``

    Both are billing/metering metadata, not assistant content.

    Args:
        text: Response text that may contain billing attribution.

    Returns:
        Text with billing attribution stripped.
    """
    if not text or not STRIP_BILLING_HEADER:
        return text

    # Strip Claude Code billing header line
    stripped = _BILLING_HEADER_LINE_PATTERN.sub("", text, count=1)
    if stripped != text:
        text = stripped.lstrip("\n")

    # Strip Kiro billing footer
    match = _BILLING_FOOTER_RE.search(text)
    if match:
        start = match.start()
        text = text[:start].rstrip()

    return text


# ==================================================================================================
# Inline System Message Extraction
# ==================================================================================================

def separate_inline_system_messages(
    messages: List[UnifiedMessage],
) -> Tuple[Optional[str], List[UnifiedMessage]]:
    """
    Separate inline system messages from conversation messages.

    Some clients send system instructions as user messages with specific prefixes.
    This function extracts them and returns them as a system prompt string,
    along with the remaining conversation messages.

    Args:
        messages: List of unified messages.

    Returns:
        Tuple of (system_prompt_or_None, remaining_messages).
    """
    system_parts: List[str] = []
    remaining: List[UnifiedMessage] = []

    for msg in messages:
        if msg.role == "user":
            text = extract_text_content(msg.content) if msg.content else ""
            if text.startswith("[SYSTEM INSTRUCTION]"):
                system_parts.append(text.replace("[SYSTEM INSTRUCTION]", "").strip())
                continue
        remaining.append(msg)

    system_prompt = "\n\n".join(system_parts) if system_parts else None
    return system_prompt, remaining


# ==================================================================================================
# Cache Control Detection
# ==================================================================================================

def get_cache_control(value: Any) -> Optional[Dict[str, str]]:
    """
    Extract cache_control from a value if present.

    Args:
        value: Dict or object that may have a cache_control field.

    Returns:
        Cache control dict if present, None otherwise.
    """
    if isinstance(value, dict):
        cc = value.get("cache_control")
        if isinstance(cc, dict):
            return cc
    elif hasattr(value, "cache_control"):
        cc = getattr(value, "cache_control", None)
        if isinstance(cc, dict):
            return cc
    return None


def has_supported_cache_control(value: Any) -> bool:
    """
    Check if a value has a supported cache_control field (type: "ephemeral").

    Args:
        value: Dict or object that may have a cache_control field.

    Returns:
        True if cache_control is present and supported.
    """
    cc = get_cache_control(value)
    return cc is not None and cc.get("type") == "ephemeral"


# ==================================================================================================
# Budget to Effort Mapping
# =================================================================================================>

def _budget_to_effort_level(budget_tokens: Optional[int], max_tokens: int) -> str:
    """
    Map a fake thinking budget token count back to an effort level string
    for native thinking support.

    Args:
        budget_tokens: The fake thinking budget in tokens.
        max_tokens: Maximum output tokens for the request.

    Returns:
        Effort level string (low/medium/high/xhigh/max).
    """
    if not budget_tokens or not max_tokens:
        return "medium"

    ratio = budget_tokens / max_tokens

    if ratio >= 0.95:
        return "max"
    if ratio >= 0.80:
        return "xhigh"
    if ratio >= 0.50:
        return "high"
    if ratio >= 0.20:
        return "medium"
    return "low"


# ==================================================================================================
# Tool Choice Prompt Addition
# ==================================================================================================

def build_tool_choice_prompt_addition(tool_choice: Optional[Dict[str, Any]]) -> str:
    """
    Build system prompt addition for tool_choice instruction.

    When the client specifies a tool_choice, we need to add JSON instructions
    to the system prompt so the model knows to output a tool call in the
    specified format.

    Args:
        tool_choice: Tool choice configuration from Anthropic request.

    Returns:
        System prompt addition text (empty string if not applicable).
    """
    if not tool_choice:
        return ""

    choice_type = tool_choice.get("type", "")

    if choice_type == "auto":
        return ""

    if choice_type == "any":
        return (
            "\n\n---\n"
            "# Tool Use Instruction\n\n"
            "You MUST use a tool in your response. Select the most appropriate tool "
            "for the task and provide the necessary input parameters."
        )

    if choice_type == "tool":
        tool_name = tool_choice.get("name", "")
        if tool_name:
            return (
                f"\n\n---\n"
                f"# Tool Use Instruction\n\n"
                f"You MUST use the `{tool_name}` tool in your response. "
                f"Provide the necessary input parameters for this tool."
            )

    return ""


# ==================================================================================================
# JSON Schema Output Support
# ==================================================================================================

def extract_json_schema_output_config(
    response_format: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Extract JSON schema configuration from response_format.

    Args:
        response_format: Response format configuration from Anthropic request.

    Returns:
        JSON schema dict if present and valid, None otherwise.
    """
    if not response_format:
        return None

    fmt_type = response_format.get("type", "")
    if fmt_type != "json_schema":
        return None

    json_schema = response_format.get("json_schema")
    if not json_schema:
        return None

    schema = json_schema.get("schema")
    if not schema:
        return None

    name = json_schema.get("name", "response")
    return {"name": name, "schema": schema}


def build_json_schema_prompt_addition(
    response_format: Optional[Dict[str, Any]],
) -> str:
    """
    Build system prompt addition for JSON schema output instruction.

    Args:
        response_format: Response format configuration from Anthropic request.

    Returns:
        System prompt addition text (empty string if not applicable).
    """
    json_schema_config = extract_json_schema_output_config(response_format)
    if not json_schema_config:
        return ""

    import json as _json
    schema_str = _json.dumps(json_schema_config["schema"], indent=2)
    name = json_schema_config["name"]

    return (
        f"\n\n---\n"
        f"# Output Format Instruction\n\n"
        f"You MUST respond with a valid JSON object that conforms to the following schema "
        f"(named `{name}`):\n\n"
        f"```json\n{schema_str}\n```\n\n"
        f"Your response should be ONLY the JSON object, with no additional text, "
        f"markdown formatting, or explanation outside the JSON."
    )


# ==================================================================================================
# Content Processing Helpers
# ==================================================================================================


def convert_anthropic_content_to_text(content: Any) -> str:
    """
    Extracts text content from Anthropic message content.

    Anthropic content can be:
    - String: "Hello, world!"
    - List of content blocks: [{"type": "text", "text": "Hello"}]

    Args:
        content: Anthropic message content

    Returns:
        Extracted text content
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "document":
                    doc_text = extract_document_text_from_content_block(block)
                    if doc_text:
                        text_parts.append(doc_text)
            elif hasattr(block, "type") and block.type == "text":
                text_parts.append(block.text)
        return "".join(text_parts)

    return str(content) if content else ""


def extract_system_prompt(system: Any) -> str:
    """
    Extracts system prompt text from Anthropic system field.

    Anthropic API supports system in two formats:
    1. String: "You are helpful"
    2. List of content blocks: [{"type": "text", "text": "...", "cache_control": {...}}]

    The second format is used for prompt caching with cache_control.
    We extract only the text, ignoring cache_control (not supported by Kiro).

    Args:
        system: System prompt in string or list format

    Returns:
        Extracted system prompt as string
    """
    if system is None:
        return ""

    if isinstance(system, str):
        return _strip_billing_attribution(system)

    if isinstance(system, list):
        text_parts = []
        for block in system:
            if isinstance(block, dict):
                # Handle {"type": "text", "text": "...", "cache_control": {...}}
                if block.get("type") == "text":
                    text = block.get("text", "")
                    text_parts.append(_strip_billing_attribution(text))
            elif hasattr(block, "type") and block.type == "text":
                # Handle Pydantic model
                text = getattr(block, "text", "")
                text_parts.append(_strip_billing_attribution(text))
        return "\n".join(text_parts)

    return str(system)


def extract_tool_results_from_anthropic_content(content: Any) -> List[Dict[str, Any]]:
    """
    Extracts tool results from Anthropic message content.

    Looks for content blocks with type="tool_result".

    Args:
        content: Anthropic message content (list of content blocks)

    Returns:
        List of tool results in unified format
    """
    tool_results = []

    if not isinstance(content, list):
        return tool_results

    for block in content:
        block_type = None
        tool_use_id = None
        result_content = ""

        if isinstance(block, dict):
            block_type = block.get("type")
            tool_use_id = block.get("tool_use_id")
            result_content = block.get("content", "")
        elif hasattr(block, "type"):
            block_type = block.type
            tool_use_id = getattr(block, "tool_use_id", None)
            result_content = getattr(block, "content", "")

        if block_type == "tool_result" and tool_use_id:
            # Convert content to text if it's a list
            if isinstance(result_content, list):
                result_content = extract_text_content(result_content)
            elif not isinstance(result_content, str):
                result_content = str(result_content) if result_content else ""

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": result_content or "(empty result)",
                }
            )

    return tool_results


def extract_images_from_tool_results(content: Any) -> List[Dict[str, Any]]:
    """
    Extracts images from tool_result content blocks.

    Tool results in Anthropic format can contain images (e.g., screenshots from browser tools).
    This function extracts those images so they can be passed to the model.

    Args:
        content: Anthropic message content (list of content blocks)

    Returns:
        List of images in unified format: [{"media_type": "image/jpeg", "data": "base64..."}]
    """
    images: List[Dict[str, Any]] = []

    if not isinstance(content, list):
        return images

    for block in content:
        block_type = None
        result_content = None

        if isinstance(block, dict):
            block_type = block.get("type")
            result_content = block.get("content")
        elif hasattr(block, "type"):
            block_type = block.type
            result_content = getattr(block, "content", None)

        if block_type == "tool_result" and isinstance(result_content, list):
            # Extract images from the tool_result's content
            tool_result_images = extract_images_from_content(result_content)
            images.extend(tool_result_images)

    if images:
        logger.debug(f"Extracted {len(images)} image(s) from tool_result content")

    return images


def extract_tool_uses_from_anthropic_content(content: Any) -> List[Dict[str, Any]]:
    """
    Extracts tool uses from Anthropic assistant message content.

    Looks for content blocks with type="tool_use".

    Args:
        content: Anthropic message content (list of content blocks)

    Returns:
        List of tool calls in unified format
    """
    tool_calls = []

    if not isinstance(content, list):
        return tool_calls

    for block in content:
        block_type = None
        tool_id = None
        tool_name = None
        tool_input = {}

        if isinstance(block, dict):
            block_type = block.get("type")
            tool_id = block.get("id")
            tool_name = block.get("name")
            tool_input = block.get("input", {})
        elif hasattr(block, "type"):
            block_type = block.type
            tool_id = getattr(block, "id", None)
            tool_name = getattr(block, "name", None)
            tool_input = getattr(block, "input", {})

        if block_type == "tool_use" and tool_id and tool_name:
            tool_calls.append(
                {
                    "id": tool_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": tool_input
                        if isinstance(tool_input, str)
                        else tool_input,
                    },
                }
            )

    return tool_calls


def convert_anthropic_messages(
    messages: List[AnthropicMessage],
) -> List[UnifiedMessage]:
    """
    Converts Anthropic messages to unified format.

    Handles:
    - Text content (string or list of text blocks)
    - Tool use blocks (assistant messages)
    - Tool result blocks (user messages)

    Args:
        messages: List of Anthropic messages

    Returns:
        List of messages in unified format
    """

    unified_messages = []
    total_tool_calls = 0
    total_tool_results = 0
    total_images = 0

    for msg in messages:
        role = msg.role
        content = msg.content

        # Extract text content
        text_content = convert_anthropic_content_to_text(content)

        # Extract tool-related data and images based on role
        tool_calls = None
        tool_results = None
        images = None

        if role == "assistant":
            # Assistant messages may contain tool_use blocks
            tool_calls = extract_tool_uses_from_anthropic_content(content)
            if tool_calls:
                total_tool_calls += len(tool_calls)

        elif role == "user":
            # User messages may contain tool_result blocks and images
            tool_results = extract_tool_results_from_anthropic_content(content)
            if tool_results:
                total_tool_results += len(tool_results)

            # Extract images from user messages (both top-level and inside tool_results)
            images = extract_images_from_content(content)

            # Also extract images from inside tool_result content blocks
            # (e.g., screenshots returned by browser MCP tools)
            tool_result_images = extract_images_from_tool_results(content)
            if tool_result_images:
                if images:
                    images.extend(tool_result_images)
                else:
                    images = tool_result_images

            if images:
                total_images += len(images)

        unified_msg = UnifiedMessage(
            role=role,
            content=text_content,
            tool_calls=tool_calls if tool_calls else None,
            tool_results=tool_results if tool_results else None,
            images=images if images else None,
        )
        unified_messages.append(unified_msg)

    # Log summary if any tool content or images were found
    if total_tool_calls > 0 or total_tool_results > 0 or total_images > 0:
        logger.debug(
            f"Converted {len(messages)} Anthropic messages: "
            f"{total_tool_calls} tool_calls, {total_tool_results} tool_results, {total_images} images"
        )

    return unified_messages


def convert_anthropic_tools(
    tools: Optional[List[AnthropicTool]],
) -> Optional[List[UnifiedTool]]:
    """
    Converts Anthropic tools to unified format.

    Args:
        tools: List of Anthropic tools

    Returns:
        List of tools in unified format, or None if no tools
    """
    if not tools:
        return None

    unified_tools = []
    for tool in tools:
        # Handle both dict and Pydantic model
        if isinstance(tool, dict):
            name = tool.get("name", "")
            description = tool.get("description")
            input_schema = tool.get("input_schema")
        else:
            name = tool.name
            description = tool.description
            input_schema = getattr(tool, "input_schema", None)

        # Skip server-managed tools without input_schema (e.g., web_search)
        # Kiro API requires tools to have a valid input_schema
        if input_schema is None:
            logger.debug(f"Skipping tool '{name}' without input_schema (server-managed)")
            continue

        unified_tools.append(
            UnifiedTool(name=name, description=description, input_schema=input_schema)
        )

    return unified_tools if unified_tools else None


def extract_thinking_config_from_anthropic(request: AnthropicMessagesRequest) -> ThinkingConfig:
    """
    Extract thinking configuration from Anthropic request.
    
    Handles thinking parameter:
    - {"type": "enabled", "budget_tokens": N} → enabled with budget
    - {"type": "adaptive", "effort": "max"} → enabled with effort-based budget
    - {"type": "disabled"} → disabled
    - None → enabled with default budget
    
    Args:
        request: Anthropic MessagesRequest
    
    Returns:
        ThinkingConfig for core layer
    
    Examples:
        >>> # No thinking specified → use defaults
        >>> request = AnthropicMessagesRequest(model="claude-sonnet-4.5", messages=[...], max_tokens=4096)
        >>> extract_thinking_config_from_anthropic(request)
        ThinkingConfig(enabled=True, budget_tokens=None)
        
        >>> # Explicitly disabled
        >>> request.thinking = {"type": "disabled"}
        >>> extract_thinking_config_from_anthropic(request)
        ThinkingConfig(enabled=False, budget_tokens=None)
        
        >>> # Enabled with custom budget
        >>> request.thinking = {"type": "enabled", "budget_tokens": 8000}
        >>> extract_thinking_config_from_anthropic(request)
        ThinkingConfig(enabled=True, budget_tokens=8000)

        >>> # Adaptive effort translated to gateway fake thinking budget
        >>> request.thinking = {"type": "adaptive", "effort": "max"}
        >>> extract_thinking_config_from_anthropic(request)
        ThinkingConfig(enabled=True, budget_tokens=4096)
    """
    if not request.thinking:
        # No thinking specified → use defaults
        return ThinkingConfig(enabled=True, budget_tokens=None)
    
    if not isinstance(request.thinking, dict):
        # Invalid format → use defaults
        return ThinkingConfig(enabled=True, budget_tokens=None)
    
    thinking_type = request.thinking.get("type")
    
    if thinking_type == "disabled":
        # Explicitly disabled
        return ThinkingConfig(enabled=False, budget_tokens=None)
    
    if thinking_type == "enabled":
        # Extract budget_tokens
        budget = request.thinking.get("budget_tokens")
        if budget:
            logger.debug(f"Extracted thinking config from Anthropic: type='enabled', budget={budget}")
        return ThinkingConfig(enabled=True, budget_tokens=budget)
    
    if thinking_type == "adaptive":
        effort = request.thinking.get("effort")
        if not effort:
            logger.debug("Extracted adaptive thinking config from Anthropic without effort")
            return ThinkingConfig(enabled=True, budget_tokens=None)

        if effort == "none":
            logger.debug("Extracted adaptive thinking config from Anthropic: effort='none'")
            return ThinkingConfig(enabled=False, budget_tokens=None)

        try:
            budget = reasoning_effort_to_budget(request.max_tokens, effort)
        except ValueError:
            logger.warning(
                f"Unsupported Anthropic adaptive thinking effort '{effort}'. "
                "Using default fake thinking budget."
            )
            return ThinkingConfig(enabled=True, budget_tokens=None)

        logger.debug(
            f"Extracted adaptive thinking config from Anthropic: effort='{effort}', "
            f"max_tokens={request.max_tokens}, budget={budget}"
        )
        return ThinkingConfig(enabled=True, budget_tokens=budget)

    # Unknown type → use defaults
    return ThinkingConfig(enabled=True, budget_tokens=None)


def anthropic_to_kiro(
    request: AnthropicMessagesRequest, conversation_id: str, profile_arn: str
) -> dict:
    """
    Converts Anthropic Messages API request to Kiro API payload.

    This is the main entry point for Anthropic → Kiro conversion.

    Key differences from OpenAI:
    - System prompt is a separate field (not in messages)
    - Content can be string or list of content blocks
    - Tool format uses input_schema instead of parameters

    Args:
        request: Anthropic MessagesRequest
        conversation_id: Unique conversation ID
        profile_arn: AWS CodeWhisperer profile ARN

    Returns:
        Payload dictionary for POST request to Kiro API

    Raises:
        ValueError: If there are no messages to send
    """
    # Convert messages to unified format
    unified_messages = convert_anthropic_messages(request.messages)

    # Separate inline system messages from conversation
    inline_system_prompt, unified_messages = separate_inline_system_messages(unified_messages)

    # Convert tools to unified format
    unified_tools = convert_anthropic_tools(request.tools)

    # System prompt is already separate in Anthropic format!
    # It can be a string or list of content blocks (for prompt caching)
    system_prompt = extract_system_prompt(request.system)

    # Merge inline system prompt with main system prompt
    if inline_system_prompt:
        if system_prompt:
            system_prompt = f"{system_prompt}\n\n{inline_system_prompt}"
        else:
            system_prompt = inline_system_prompt

    # Add tool choice prompt addition if specified
    tool_choice_addition = build_tool_choice_prompt_addition(
        getattr(request, "tool_choice", None)
    )
    if tool_choice_addition:
        system_prompt = system_prompt + tool_choice_addition if system_prompt else tool_choice_addition

    # Add JSON schema output prompt addition if specified
    json_schema_addition = build_json_schema_prompt_addition(
        getattr(request, "response_format", None)
    )
    if json_schema_addition:
        system_prompt = system_prompt + json_schema_addition if system_prompt else json_schema_addition

    # Get model ID for Kiro API (normalizes + resolves hidden models)
    # Pass-through principle: we normalize and send to Kiro, Kiro decides if valid
    model_id = get_model_id_for_kiro(request.model, HIDDEN_MODELS)

    # Extract thinking configuration from thinking parameter
    thinking_config = extract_thinking_config_from_anthropic(request)

    # Build native thinking config from model and thinking effort
    native_effort: Optional[str] = None
    native_display: Optional[str] = None
    if isinstance(request.thinking, dict) and request.thinking.get("type") == "adaptive":
        native_effort = request.thinking.get("effort") or "high"
        native_display = request.thinking.get("display")
    native_thinking_config = build_native_thinking_config(model_id, native_effort)
    if native_display in ("summarized", "omitted"):
        native_thinking_config.display = native_display
    if native_thinking_config.enabled:
        # Native adaptive thinking supersedes fake tag injection for this request.
        thinking_config = ThinkingConfig(enabled=False, budget_tokens=None)

    logger.debug(
        f"Converting Anthropic request: model={request.model} -> {model_id}, "
        f"messages={len(unified_messages)}, tools={len(unified_tools) if unified_tools else 0}, "
        f"system_prompt_length={len(system_prompt)}, "
        f"thinking_enabled={thinking_config.enabled}, thinking_budget={thinking_config.budget_tokens}, "
        f"native_thinking_enabled={native_thinking_config.enabled}, native_effort={native_thinking_config.effort}"
    )

    # Use core function to build payload
    result = build_kiro_payload(
        messages=unified_messages,
        system_prompt=system_prompt,
        model_id=model_id,
        tools=unified_tools,
        conversation_id=conversation_id,
        profile_arn=profile_arn,
        thinking_config=thinking_config,
        native_thinking_config=native_thinking_config,
    )

    return result.payload
