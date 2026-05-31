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

import base64
import re
import zlib
from io import BytesIO
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
    UnifiedMessage,
    UnifiedTool,
    ThinkingConfig,
    build_native_thinking_config,
    reasoning_effort_to_budget,
    build_kiro_payload,
    extract_text_content,
    extract_images_from_content,
)

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - exercised only when optional dependency is absent
    PdfReader = None


# Cap extracted document text so a huge PDF cannot blow up the prompt size.
MAX_EXTRACTED_DOCUMENT_CHARS = 60000

# Regexes for the dependency-free PDF text fallback (used only when pypdf is
# unavailable). They recover text from simple, uncompressed/FlateDecode text
# operators; complex PDFs degrade gracefully to a placeholder.
_PDF_TEXT_OPERAND_RE = re.compile(rb"\((?:\\.|[^\\()])*\)\s*Tj|\[(.*?)\]\s*TJ", re.DOTALL)
_PDF_STRING_RE = re.compile(rb"\((?:\\.|[^\\()])*\)")


def _block_value(block: Any, key: str, default: Any = None) -> Any:
    """Read a field from a content block that may be a dict or a Pydantic model."""
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


def _truncate_document_text(text: str) -> str:
    """Truncate extracted document text to MAX_EXTRACTED_DOCUMENT_CHARS."""
    if len(text) <= MAX_EXTRACTED_DOCUMENT_CHARS:
        return text
    return text[:MAX_EXTRACTED_DOCUMENT_CHARS] + "\n\n[Document text truncated]"


def _decode_pdf_string(raw: bytes) -> str:
    """
    Decode a single PDF literal string (the bytes between '(' and ')').

    Handles the common backslash escapes and octal escapes defined by the PDF
    spec, then decodes as UTF-8 with a latin-1 fallback.

    Args:
        raw: Raw bytes of the literal string, optionally including the
            surrounding parentheses.

    Returns:
        Decoded text.
    """
    if raw.startswith(b"(") and raw.endswith(b")"):
        raw = raw[1:-1]

    out = bytearray()
    i = 0
    mapping = {
        ord("n"): ord("\n"),
        ord("r"): ord("\r"),
        ord("t"): ord("\t"),
        ord("b"): ord("\b"),
        ord("f"): ord("\f"),
        ord("("): ord("("),
        ord(")"): ord(")"),
        ord("\\"): ord("\\"),
    }
    while i < len(raw):
        ch = raw[i]
        if ch != 0x5C:  # not a backslash
            out.append(ch)
            i += 1
            continue

        i += 1
        if i >= len(raw):
            break
        esc = raw[i]
        if esc in mapping:
            out.append(mapping[esc])
            i += 1
        elif 48 <= esc <= 55:  # octal escape (\ddd)
            octal = bytes([esc])
            i += 1
            for _ in range(2):
                if i < len(raw) and 48 <= raw[i] <= 55:
                    octal += bytes([raw[i]])
                    i += 1
                else:
                    break
            out.append(int(octal, 8) & 0xFF)
        else:
            out.append(esc)
            i += 1

    for encoding in ("utf-8", "latin-1"):
        try:
            return out.decode(encoding)
        except UnicodeDecodeError:
            continue
    return out.decode("latin-1", errors="ignore")


def _extract_pdf_text_regex_fallback(pdf_bytes: bytes) -> str:
    """
    Best-effort, dependency-free PDF text extraction.

    Used only when pypdf is not installed. Scans content streams (decompressing
    FlateDecode streams when possible) for Tj/TJ text operators. Complex or
    image-only PDFs yield an empty string.

    Args:
        pdf_bytes: Decoded PDF file bytes.

    Returns:
        Extracted text, possibly empty.
    """
    streams: List[bytes] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf_bytes, re.DOTALL):
        stream = match.group(1)
        prefix = pdf_bytes[max(0, match.start() - 300):match.start()]
        if b"FlateDecode" in prefix:
            try:
                stream = zlib.decompress(stream)
            except zlib.error:
                continue
        streams.append(stream)

    search_blobs = streams or [pdf_bytes]
    text_parts: List[str] = []
    for blob in search_blobs:
        for match in _PDF_TEXT_OPERAND_RE.finditer(blob):
            operand = match.group(0)
            strings = _PDF_STRING_RE.findall(operand)
            if not strings:
                continue
            decoded = "".join(_decode_pdf_string(s) for s in strings)
            if decoded.strip():
                text_parts.append(decoded)

    return "\n".join(text_parts).strip()


def extract_text_from_pdf_base64(data: str) -> str:
    """
    Extract text from a base64-encoded PDF document.

    Prefers pypdf for robust extraction and falls back to a dependency-free
    regex parser when pypdf is not installed, so the feature degrades
    gracefully rather than failing the request.

    Args:
        data: Base64-encoded PDF data.

    Returns:
        Extracted text, or a bracketed placeholder describing why extraction
        did not produce text.
    """
    try:
        pdf_bytes = base64.b64decode(data, validate=False)
    except (ValueError, TypeError) as exc:
        logger.debug(f"Failed to decode PDF document block: {exc}")
        return "[PDF document could not be decoded]"

    if PdfReader is not None:
        try:
            reader = PdfReader(BytesIO(pdf_bytes))
            page_texts = []
            for index, page in enumerate(reader.pages, start=1):
                text = (page.extract_text() or "").strip()
                if text:
                    page_texts.append(f"Page {index}:\n{text}")
            if page_texts:
                return _truncate_document_text("\n\n".join(page_texts))
            # pypdf parsed the file but found no extractable text; try fallback.
        except Exception as exc:  # noqa: BLE001 - pypdf raises a broad set of errors
            logger.debug(f"pypdf extraction failed, using regex fallback: {exc}")

    fallback = _extract_pdf_text_regex_fallback(pdf_bytes)
    if fallback:
        return _truncate_document_text(fallback)
    if PdfReader is None:
        return "[PDF text extraction unavailable: pypdf is not installed]"
    return "[PDF text extraction returned no text]"


def _document_block_to_text(block: Any) -> str:
    """
    Render a single Anthropic document block as labeled text.

    Args:
        block: A document content block (dict or Pydantic model).

    Returns:
        A "[Document: title]\\n<body>" string describing the document, or a
        placeholder when the source is unsupported/empty.
    """
    source = _block_value(block, "source")
    title = _block_value(block, "title")
    media_type = _block_value(source, "media_type", "") or ""
    source_type = _block_value(source, "type", "") or ""
    data = _block_value(source, "data", "") or ""
    url = _block_value(source, "url", "") or ""

    label = f"Document: {title or media_type or 'document'}"

    if source_type == "base64" and data:
        try:
            if media_type == "application/pdf":
                body = extract_text_from_pdf_base64(data)
            elif media_type.startswith("text/"):
                body = _truncate_document_text(
                    base64.b64decode(data).decode("utf-8", errors="replace")
                )
            else:
                byte_count = len(base64.b64decode(data, validate=False))
                body = f"[Document extraction unsupported for {media_type}; {byte_count} bytes]"
        except (ValueError, TypeError) as exc:
            logger.warning(f"Failed to extract Anthropic document block ({media_type}): {exc}")
            body = f"[Document extraction failed for {media_type}: {exc}]"
        return f"[{label}]\n{body}"

    if source_type == "url" and url:
        return f"[{label}]\n[URL document sources are not supported by Kiro Gateway: {url}]"

    return f"[{label}]\n[Document source was empty or unsupported]"


def extract_documents_from_anthropic_content(content: Any) -> str:
    """
    Extract all Anthropic document blocks from message content as text.

    Kiro does not accept Anthropic document blocks directly, so PDF/text
    documents (including those nested inside tool_result content) are converted
    to text and appended to the user message.

    Args:
        content: Anthropic message content (string or list of blocks).

    Returns:
        Newline-separated document text, or an empty string when there are no
        document blocks.
    """
    if not isinstance(content, list):
        return ""

    document_parts: List[str] = []
    for block in content:
        block_type = _block_value(block, "type")
        if block_type == "document":
            document_parts.append(_document_block_to_text(block))
        elif block_type == "tool_result":
            result_content = _block_value(block, "content", None)
            if isinstance(result_content, list):
                for item in result_content:
                    if _block_value(item, "type") == "document":
                        document_parts.append(_document_block_to_text(item))

    return "\n\n".join(document_parts)


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


def build_tool_choice_prompt_addition(request: AnthropicMessagesRequest) -> str:
    """
    Build prompt guidance for Anthropic tool_choice semantics Kiro can't enforce.

    Kiro has no native way to force a specific tool, so when the client sets
    tool_choice to "any" or "tool", we add an instruction nudging the model to
    answer via the selected tool's schema.

    Args:
        request: Anthropic messages request.

    Returns:
        Prompt addition string (empty when no forcing tool_choice is present).
    """
    if not request.tool_choice or not request.tools:
        return ""

    choice = request.tool_choice
    choice_type = choice.get("type") if isinstance(choice, dict) else getattr(choice, "type", None)
    tool_name = choice.get("name") if isinstance(choice, dict) else getattr(choice, "name", None)

    if choice_type not in {"any", "tool"}:
        return ""

    selected_tool = None
    if choice_type == "tool" and tool_name:
        for tool in request.tools:
            name = tool.get("name") if isinstance(tool, dict) else tool.name
            if name == tool_name:
                selected_tool = tool
                break
    elif request.tools:
        selected_tool = request.tools[0]

    if selected_tool is None:
        return ""

    name = selected_tool.get("name") if isinstance(selected_tool, dict) else selected_tool.name
    schema = selected_tool.get("input_schema") if isinstance(selected_tool, dict) else selected_tool.input_schema
    return (
        "\n\nThe client requires a structured tool-style answer. "
        f"Use the tool named `{name}` and provide arguments that strictly satisfy this JSON schema. "
        "Do not include prose outside the structured answer.\n"
        f"Schema: {schema}"
    )


def extract_json_schema_output_config(request: AnthropicMessagesRequest) -> Optional[Dict[str, Any]]:
    """
    Extract an Anthropic ``output_config.format`` json_schema when present.

    Args:
        request: Anthropic messages request (output_config is an extra field).

    Returns:
        The JSON schema dict, or None when not configured.
    """
    output_config = getattr(request, "output_config", None)
    if not isinstance(output_config, dict):
        return None

    fmt = output_config.get("format")
    if not isinstance(fmt, dict) or fmt.get("type") != "json_schema":
        return None

    schema = fmt.get("schema")
    return schema if isinstance(schema, dict) else None


def build_json_schema_prompt_addition(schema: Optional[Dict[str, Any]]) -> str:
    """
    Build prompt guidance for Anthropic json_schema output_config.

    Args:
        schema: JSON schema the response must satisfy.

    Returns:
        Prompt addition string (empty when no schema is provided).
    """
    if not schema:
        return ""

    return (
        "\n\nThe client requires a structured JSON response. "
        "Return exactly one valid JSON object that strictly satisfies this JSON schema. "
        "Do not include markdown fences, prose, comments, analysis, tool calls, or extra text. "
        "The entire assistant response must be parseable by JSON.parse.\n"
        f"JSON schema: {schema}"
    )


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

    return tool_results


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

        # Extract and append any document blocks (PDF/text) as plain text,
        # since Kiro has no native document input field.
        document_text = extract_documents_from_anthropic_content(content)
        if document_text:
            text_content = f"{text_content}\n\n{document_text}".strip()

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

    # Convert tools to unified format
    unified_tools = convert_anthropic_tools(request.tools)

    # System prompt is already separate in Anthropic format!
    # It can be a string or list of content blocks (for prompt caching)
    system_prompt = extract_system_prompt(request.system)
    # Add prompt guidance for tool_choice forcing and json_schema output_config,
    # which Kiro cannot enforce natively.
    system_prompt += build_tool_choice_prompt_addition(request)
    json_schema = extract_json_schema_output_config(request)
    system_prompt += build_json_schema_prompt_addition(json_schema)

    # Get model ID for Kiro API (normalizes + resolves hidden models)
    # Pass-through principle: we normalize and send to Kiro, Kiro decides if valid
    model_id = get_model_id_for_kiro(request.model, HIDDEN_MODELS)

    # Extract thinking configuration from thinking parameter
    thinking_config = extract_thinking_config_from_anthropic(request)
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
    # Structured JSON output and extended thinking are mutually exclusive: the
    # response must be exactly one JSON object, so disable thinking when a
    # json_schema is requested.
    if json_schema:
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
