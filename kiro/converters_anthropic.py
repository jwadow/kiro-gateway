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

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from loguru import logger

from kiro.config import HIDDEN_MODELS
from kiro.model_resolver import get_model_id_for_kiro
from kiro.models_anthropic import (
    AnthropicMessagesRequest,
    AnthropicMessage,
    AnthropicTool,
)
from kiro.converters_core import (
    REMOTE_IMAGE_PLACEHOLDER,
    TOOL_CHOICE_AUTO,
    TOOL_CHOICE_NONE,
    TOOL_CHOICE_REQUIRED,
    TOOL_CHOICE_TOOL,
    TextAccumulator,
    UnifiedMessage,
    UnifiedTool,
    UnifiedToolChoice,
    ThinkingConfig,
    build_kiro_payload,
    extract_text_content,
    extract_image_from_block,
    extract_images_from_content,
    get_remote_image_url,
)


# Placeholder for documents the gateway cannot forward (Kiro accepts text only).
DOCUMENT_OMITTED_TEMPLATE: str = "[document omitted: {media_type} not supported by gateway]"

# Block types dropped on purpose (no Kiro equivalent, no text worth keeping).
# - redacted_thinking: encrypted reasoning, unreadable by any other model
# - thinking: reasoning from earlier turns, not sent back to Kiro
_SILENTLY_DROPPED_BLOCK_TYPES = frozenset({"redacted_thinking", "thinking", "tool_reference"})

# Non-text block types whose content is converted to text.
_TEXT_BEARING_BLOCK_TYPES = frozenset({"document", "search_result"})


def _block_type(block: Any) -> Optional[str]:
    """
    Returns the "type" of a content block given as a dict or a Pydantic model.

    Args:
        block: Content block

    Returns:
        Block type, or None if the block has no type
    """
    if isinstance(block, dict):
        return block.get("type")
    return getattr(block, "type", None)


def _block_get(block: Any, key: str, default: Any = None) -> Any:
    """
    Reads a field from a content block given as a dict or a Pydantic model.

    Works for extra fields of models with extra="allow" (e.g. GenericContentBlock).

    Args:
        block: Content block
        key: Field name
        default: Value returned when the field is missing

    Returns:
        Field value or default
    """
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


def _text_of_nested_blocks(blocks: Any) -> str:
    """
    Joins the text of nested text blocks (used by document and search_result content).

    Args:
        blocks: A string or a list of content blocks

    Returns:
        Text joined with newlines (empty string if nothing found)
    """
    if isinstance(blocks, str):
        return blocks
    if not isinstance(blocks, list):
        return ""
    parts: List[str] = []
    for nested in blocks:
        if isinstance(nested, str):
            parts.append(nested)
        elif _block_type(nested) == "text":
            text = _block_get(nested, "text", "")
            if isinstance(text, str) and text:
                parts.append(text)
    return "\n".join(parts)


def convert_document_block_to_text(block: Any) -> str:
    """
    Converts an Anthropic document block to text for Kiro.

    - source.type "text": the document text, preceded by its title if present
    - source.type "content": text of the nested content blocks, same title rule
    - anything else (base64 PDF, url, file id): a placeholder, since the
      gateway cannot forward binary or remote documents to Kiro

    Args:
        block: Document content block (dict or Pydantic model)

    Returns:
        Text to include in the message
    """
    source = _block_get(block, "source")
    title = _block_get(block, "title")
    source_type = _block_get(source, "type") if source is not None else None

    text: Optional[str] = None
    if source_type == "text":
        data = _block_get(source, "data", "")
        text = data if isinstance(data, str) else ""
    elif source_type == "content":
        text = _text_of_nested_blocks(_block_get(source, "content"))

    if text is not None:
        if isinstance(title, str) and title:
            return f"{title}\n\n{text}" if text else title
        return text

    media_type = _block_get(source, "media_type") if source is not None else None
    if not isinstance(media_type, str) or not media_type:
        media_type = f"{source_type} source" if source_type else "unknown document type"
    logger.warning(
        f"Document block with source type {source_type!r} ({media_type}) cannot be forwarded "
        f"to Kiro; replaced with a placeholder. Send the document as text instead."
    )
    return DOCUMENT_OMITTED_TEMPLATE.format(media_type=media_type)


def convert_search_result_block_to_text(block: Any) -> str:
    """
    Converts an Anthropic search_result block to its text content.

    Args:
        block: search_result content block (dict or Pydantic model)

    Returns:
        Text of the nested content blocks
    """
    return _text_of_nested_blocks(_block_get(block, "content"))


def _add_block_text(text: TextAccumulator, block: Any, block_type: Optional[str]) -> None:
    """
    Adds the text contribution of one Anthropic content block.

    Handles text, document, search_result and remote image blocks; tool_use,
    tool_result and base64 images contribute no text. Other block types are
    dropped (logged at debug level).

    Args:
        text: Accumulator receiving the text
        block: Content block (dict or Pydantic model)
        block_type: Pre-computed block type
    """
    if block_type == "text":
        value = _block_get(block, "text", "")
        text.add_text(value if isinstance(value, str) else str(value))
    elif block_type == "image":
        if get_remote_image_url(block) is not None:
            text.add_notice(REMOTE_IMAGE_PLACEHOLDER)
    elif block_type == "document":
        text.add_notice(convert_document_block_to_text(block))
    elif block_type == "search_result":
        text.add_notice(convert_search_result_block_to_text(block))
    elif block_type in ("tool_use", "tool_result") or block_type in _SILENTLY_DROPPED_BLOCK_TYPES:
        return
    else:
        logger.debug(f"Dropping unsupported Anthropic content block type {block_type!r}")


def convert_anthropic_content_to_text(content: Any) -> str:
    """
    Extracts text content from Anthropic message content.

    Anthropic content can be:
    - String: "Hello, world!"
    - List of content blocks: [{"type": "text", "text": "Hello"}]

    Text blocks are concatenated as-is. document and search_result blocks
    contribute their text on separate lines; remote image URLs and
    unsupported documents leave a placeholder notice.

    Args:
        content: Anthropic message content

    Returns:
        Extracted text content
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text = TextAccumulator()
        for block in content:
            _add_block_text(text, block, _block_type(block))
        return text.result()

    return str(content) if content else ""


def extract_system_prompt(system: Any) -> str:
    """
    Extracts system prompt text from Anthropic system field.

    Anthropic API supports system in two formats:
    1. String: "You are helpful"
    2. List of content blocks: [{"type": "text", "text": "...", "cache_control": {...}}]

    The second format is used for prompt caching with cache_control.
    We extract only the text, ignoring cache_control (not supported by Kiro).
    Non-text blocks are ignored.

    Args:
        system: System prompt in string or list format

    Returns:
        Extracted system prompt as string
    """
    if system is None:
        return ""

    if isinstance(system, str):
        return system

    if isinstance(system, list):
        text_parts = []
        for block in system:
            if isinstance(block, dict):
                # Handle {"type": "text", "text": "...", "cache_control": {...}}
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            elif hasattr(block, "type") and block.type == "text":
                # Handle Pydantic model
                text_parts.append(getattr(block, "text", ""))
        return "\n".join(text_parts)

    return str(system)


def _tool_result_content_to_text(blocks: List[Any]) -> str:
    """
    Converts the list content of a tool_result block to text.

    Uses the core extract_text_content() rules, except that document and
    search_result blocks (common in tool results from search tools)
    contribute their text on separate lines.

    Args:
        blocks: Content blocks of the tool_result

    Returns:
        Text content
    """
    if not any(_block_type(item) in _TEXT_BEARING_BLOCK_TYPES for item in blocks):
        return extract_text_content(blocks)
    text = TextAccumulator()
    for item in blocks:
        item_type = _block_type(item)
        if item_type == "document":
            text.add_notice(convert_document_block_to_text(item))
        elif item_type == "search_result":
            text.add_notice(convert_search_result_block_to_text(item))
        else:
            text.add_text(extract_text_content([item]))
    return text.result()


def _convert_tool_result_block(block: Any) -> Optional[Dict[str, Any]]:
    """
    Converts one tool_result block to unified format.

    Args:
        block: tool_result content block (dict or Pydantic model)

    Returns:
        Unified tool result, or None if the block has no tool_use_id
    """
    tool_use_id = _block_get(block, "tool_use_id")
    if not tool_use_id:
        return None

    result_content = _block_get(block, "content", "")
    # Convert content to text if it's a list
    if isinstance(result_content, list):
        result_content = _tool_result_content_to_text(result_content)
    elif not isinstance(result_content, str):
        result_content = str(result_content) if result_content else ""

    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": result_content or "(empty result)",
    }


def _images_of_tool_result_block(block: Any) -> List[Dict[str, Any]]:
    """
    Extracts images nested inside one tool_result block (e.g. browser screenshots).

    Args:
        block: tool_result content block (dict or Pydantic model)

    Returns:
        Images in unified format
    """
    result_content = _block_get(block, "content")
    if isinstance(result_content, list):
        return extract_images_from_content(result_content)
    return []


def _convert_tool_use_block(block: Any) -> Optional[Dict[str, Any]]:
    """
    Converts one tool_use block to a unified tool call.

    Args:
        block: tool_use content block (dict or Pydantic model)

    Returns:
        Unified tool call, or None if id or name is missing
    """
    tool_id = _block_get(block, "id")
    tool_name = _block_get(block, "name")
    if not tool_id or not tool_name:
        return None
    return {
        "id": tool_id,
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": _block_get(block, "input", {}),
        },
    }


def extract_tool_results_from_anthropic_content(content: Any) -> List[Dict[str, Any]]:
    """
    Extracts tool results from Anthropic message content.

    Looks for content blocks with type="tool_result".

    Args:
        content: Anthropic message content (list of content blocks)

    Returns:
        List of tool results in unified format
    """
    if not isinstance(content, list):
        return []
    tool_results = []
    for block in content:
        if _block_type(block) == "tool_result":
            tool_result = _convert_tool_result_block(block)
            if tool_result is not None:
                tool_results.append(tool_result)
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
        if _block_type(block) == "tool_result":
            images.extend(_images_of_tool_result_block(block))
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
    if not isinstance(content, list):
        return []
    tool_calls = []
    for block in content:
        if _block_type(block) == "tool_use":
            tool_call = _convert_tool_use_block(block)
            if tool_call is not None:
                tool_calls.append(tool_call)
    return tool_calls


@dataclass
class _ScannedContent:
    """
    Everything extracted from one Anthropic message in a single pass.

    Attributes:
        text: Text content
        tool_calls: Unified tool calls (assistant messages)
        tool_results: Unified tool results (user messages)
        images: Top-level images followed by images nested in tool results (user messages)
    """
    text: str
    tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    images: List[Dict[str, Any]]


def _scan_anthropic_content(content: Any, role: str) -> _ScannedContent:
    """
    Extracts text, tool calls, tool results and images from one message in one pass.

    Equivalent to calling convert_anthropic_content_to_text,
    extract_tool_uses_from_anthropic_content (assistant only),
    extract_tool_results_from_anthropic_content, extract_images_from_content and
    extract_images_from_tool_results (user only), but walks the blocks once.

    Args:
        content: Anthropic message content
        role: Message role ("user" or "assistant"; other roles extract text only)

    Returns:
        _ScannedContent with the extracted data
    """
    if not isinstance(content, list):
        return _ScannedContent(convert_anthropic_content_to_text(content), [], [], [])

    text = TextAccumulator()
    tool_calls: List[Dict[str, Any]] = []
    tool_results: List[Dict[str, Any]] = []
    top_level_images: List[Dict[str, Any]] = []
    tool_result_images: List[Dict[str, Any]] = []
    is_user = role == "user"
    is_assistant = role == "assistant"

    for block in content:
        block_type = _block_type(block)
        _add_block_text(text, block, block_type)

        if is_assistant and block_type == "tool_use":
            tool_call = _convert_tool_use_block(block)
            if tool_call is not None:
                tool_calls.append(tool_call)
        elif is_user and block_type == "tool_result":
            tool_result = _convert_tool_result_block(block)
            if tool_result is not None:
                tool_results.append(tool_result)
            tool_result_images.extend(_images_of_tool_result_block(block))
        elif is_user and block_type in ("image", "image_url"):
            image = extract_image_from_block(block)
            if image is not None:
                top_level_images.append(image)

    if top_level_images:
        logger.debug(f"Extracted {len(top_level_images)} image(s) from content")
    if tool_result_images:
        logger.debug(f"Extracted {len(tool_result_images)} image(s) from tool_result content")

    return _ScannedContent(text.result(), tool_calls, tool_results, top_level_images + tool_result_images)


def convert_anthropic_messages(
    messages: List[AnthropicMessage],
) -> tuple:
    """
    Converts Anthropic messages to unified format.

    Handles:
    - System messages (extracted as inline system prompt, non-standard but sent by Claude Code)
    - Text content (string or list of text blocks)
    - Tool use blocks (assistant messages)
    - Tool result blocks (user messages)
    - document / search_result blocks (converted to text)

    Each message's content is scanned once.

    Args:
        messages: List of Anthropic messages

    Returns:
        Tuple of (inline_system_prompt, unified_messages):
        - inline_system_prompt: Text from any system-role messages found inline
        - unified_messages: List of messages in unified format (excluding system messages)
    """

    unified_messages = []
    inline_system_parts = []
    total_tool_calls = 0
    total_tool_results = 0
    total_images = 0

    for msg in messages:
        role = msg.role
        content = msg.content

        # Handle system messages inline (non-standard, sent by Claude Code)
        if role == "system":
            text_content = convert_anthropic_content_to_text(content)
            if text_content:
                inline_system_parts.append(text_content)
            continue

        scanned = _scan_anthropic_content(content, role)
        total_tool_calls += len(scanned.tool_calls)
        total_tool_results += len(scanned.tool_results)
        total_images += len(scanned.images)

        unified_msg = UnifiedMessage(
            role=role,
            content=scanned.text,
            tool_calls=scanned.tool_calls or None,
            tool_results=scanned.tool_results or None,
            images=scanned.images or None,
        )
        unified_messages.append(unified_msg)

    # Log summary if any tool content or images were found
    if total_tool_calls > 0 or total_tool_results > 0 or total_images > 0:
        logger.debug(
            f"Converted {len(messages)} Anthropic messages: "
            f"{total_tool_calls} tool_calls, {total_tool_results} tool_results, {total_images} images"
        )

    inline_system_prompt = "\n".join(inline_system_parts).strip()
    if inline_system_prompt:
        logger.debug(
            f"Extracted {len(inline_system_parts)} inline system message(s) "
            f"({len(inline_system_prompt)} chars) from Anthropic messages array"
        )

    return inline_system_prompt, unified_messages


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
            input_schema = tool.get("input_schema", {})
        else:
            name = tool.name
            description = tool.description
            input_schema = tool.input_schema

        unified_tools.append(
            UnifiedTool(name=name, description=description, input_schema=input_schema)
        )

    return unified_tools if unified_tools else None


def extract_thinking_config_from_anthropic(request: AnthropicMessagesRequest) -> ThinkingConfig:
    """
    Extract thinking configuration from Anthropic request.
    
    Handles thinking parameter:
    - {"type": "enabled", "budget_tokens": N} → enabled with budget
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
    
    # Unknown type → use defaults
    return ThinkingConfig(enabled=True, budget_tokens=None)


def extract_tool_choice_from_anthropic(request: AnthropicMessagesRequest) -> Optional[UnifiedToolChoice]:
    """
    Converts Anthropic tool_choice to unified format.

    Mapping:
    - None / {"type": "auto"} -> auto
    - {"type": "none"} -> none (tools removed)
    - {"type": "any"} -> at least one tool call
    - {"type": "tool", "name": X} -> forced tool X
    - disable_parallel_tool_use: true (on auto/any/tool) -> at most one tool call
    Unrecognized values are logged and treated as auto.

    Args:
        request: Anthropic MessagesRequest

    Returns:
        UnifiedToolChoice, or None when nothing deviates from the default
    """
    tool_choice = request.tool_choice
    if tool_choice is None:
        return None

    if hasattr(tool_choice, "model_dump"):
        tool_choice = tool_choice.model_dump()
    if not isinstance(tool_choice, dict):
        logger.warning(f"Ignoring unsupported Anthropic tool_choice {tool_choice!r}; using auto")
        return None

    choice_type = tool_choice.get("type")
    disable_parallel = tool_choice.get("disable_parallel_tool_use") is True
    mode = TOOL_CHOICE_AUTO
    tool_name: Optional[str] = None

    if choice_type == "none":
        mode = TOOL_CHOICE_NONE
    elif choice_type == "any":
        mode = TOOL_CHOICE_REQUIRED
    elif choice_type == "tool":
        name = tool_choice.get("name")
        if isinstance(name, str) and name:
            mode = TOOL_CHOICE_TOOL
            tool_name = name
        else:
            logger.warning("Ignoring Anthropic tool_choice of type 'tool' without a name; using auto")
    elif choice_type != "auto":
        logger.warning(f"Ignoring unsupported Anthropic tool_choice type {choice_type!r}; using auto")

    if mode == TOOL_CHOICE_AUTO and not disable_parallel:
        return None
    return UnifiedToolChoice(mode=mode, tool_name=tool_name, disable_parallel=disable_parallel)


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
    # Also extracts any inline system messages (non-standard, sent by Claude Code)
    inline_system_prompt, unified_messages = convert_anthropic_messages(request.messages)

    # Convert tools to unified format
    unified_tools = convert_anthropic_tools(request.tools)

    # System prompt is already separate in Anthropic format!
    # It can be a string or list of content blocks (for prompt caching)
    system_prompt = extract_system_prompt(request.system)

    # Merge inline system messages (from messages array) with the explicit system field
    if inline_system_prompt:
        if system_prompt:
            system_prompt = system_prompt + "\n\n" + inline_system_prompt
        else:
            system_prompt = inline_system_prompt

    # Get model ID for Kiro API (normalizes + resolves hidden models)
    # Pass-through principle: we normalize and send to Kiro, Kiro decides if valid
    model_id = get_model_id_for_kiro(request.model, HIDDEN_MODELS)

    # Extract thinking configuration from thinking parameter
    thinking_config = extract_thinking_config_from_anthropic(request)

    logger.debug(
        f"Converting Anthropic request: model={request.model} -> {model_id}, "
        f"messages={len(unified_messages)}, tools={len(unified_tools) if unified_tools else 0}, "
        f"system_prompt_length={len(system_prompt)}, "
        f"thinking_enabled={thinking_config.enabled}, thinking_budget={thinking_config.budget_tokens}"
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
        tool_choice=extract_tool_choice_from_anthropic(request),
    )

    return result.payload
