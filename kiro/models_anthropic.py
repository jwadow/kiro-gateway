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
Pydantic models for Anthropic Messages API.

Defines data schemas for requests and responses compatible with
Anthropic's Messages API specification.

Reference: https://docs.anthropic.com/en/api/messages
"""

import time
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, model_validator


# ==================================================================================================
# Content Block Models
# ==================================================================================================

# Content block "type" values the gateway understands. Blocks whose type is not
# in this set are downgraded to text blocks before Pydantic validation (see
# AnthropicMessage.sanitize_unknown_content_blocks) so unknown / forward-
# compatible block kinds never cause a 422. Extend this set when adding a new
# content block model rather than re-patching the validator.
KNOWN_CONTENT_BLOCK_TYPES = {
    "text",
    "thinking",
    "redacted_thinking",
    "image",
    "document",
    "tool_use",
    "tool_result",
    "tool_reference",
    "server_tool_use",
    "web_search_tool_result",
}

# Content block "type" values valid inside a tool_result's content array.
KNOWN_TOOL_RESULT_INNER_TYPES = {
    "text",
    "image",
    "document",
    "tool_reference",
}


def _downgrade_unknown_block(block: Any, known_types: set) -> Any:
    """
    Downgrade an unknown content block to a text block.

    Args:
        block: A single content block (a dict, or any other value).
        known_types: Set of block ``type`` values to pass through untouched.

    Returns:
        The original block when its type is known (or it is not a dict),
        otherwise a text block preserving any identifying info (text / tool name).
    """
    if not isinstance(block, dict) or block.get("type") in known_types:
        return block
    block_type = block.get("type", "unknown")
    text = block.get("text") or block.get("tool_name") or block.get("name") or ""
    return {
        "type": "text",
        "text": f"[{block_type}: {text}]" if text else f"[{block_type}]",
    }


class TextContentBlock(BaseModel):
    """
    Text content block in Anthropic format.

    Used in both requests and responses for text content.
    """

    type: Literal["text"] = "text"
    text: str


class ThinkingContentBlock(BaseModel):
    """
    Thinking content block in Anthropic format.

    Represents the model's reasoning/thinking process.
    Used when extended thinking is enabled.

    Attributes:
        type: Always "thinking"
        thinking: The thinking/reasoning content
        signature: Cryptographic signature for verification (placeholder in our case)
    """

    type: Literal["thinking"] = "thinking"
    thinking: str
    signature: str = ""


class RedactedThinkingContentBlock(BaseModel):
    """
    Redacted thinking content block in Anthropic format.

    Claude may return encrypted reasoning when extended thinking is enabled.
    Clients can replay these blocks in later requests; the gateway accepts
    them for schema compatibility without exposing the opaque data as prompt
    text.

    Attributes:
        type: Always "redacted_thinking"
        data: Opaque, encrypted reasoning payload (passed through, not decoded)
    """

    type: Literal["redacted_thinking"] = "redacted_thinking"
    data: str


class ToolUseContentBlock(BaseModel):
    """
    Tool use content block in Anthropic format.

    Represents a tool call made by the assistant.
    """

    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: Dict[str, Any]


class ToolReferenceContentBlock(BaseModel):
    """
    Tool reference content block (Claude Code deferred tools).

    Sent by Claude Code v2.1.69+ inside tool_result blocks to indicate
    which tools were loaded via the ToolSearch deferred tool mechanism.
    """

    type: Literal["tool_reference"] = "tool_reference"
    tool_name: str

    model_config = {"extra": "allow"}


class ServerToolUseContentBlock(BaseModel):
    """
    Server-side tool use content block returned by Anthropic.

    Claude Code can include these blocks in assistant history after native
    tools such as web_search run. Kiro Gateway accepts them for history
    compatibility but does not forward them as Kiro tool calls.
    """

    type: Literal["server_tool_use"] = "server_tool_use"
    id: str
    name: str
    input: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class WebSearchResultBlock(BaseModel):
    """
    Individual web search result block from Anthropic server-side tools.
    """

    type: Literal["web_search_result"] = "web_search_result"
    title: Optional[str] = None
    url: Optional[str] = None
    encrypted_content: Optional[str] = None
    page_age: Optional[str] = None

    model_config = {"extra": "allow"}


class WebSearchToolResultContentBlock(BaseModel):
    """
    Server-side web search result block returned by Anthropic.

    These blocks appear in Claude Code conversation history paired with
    server_tool_use blocks. They are accepted to preserve compatibility and
    ignored by Kiro conversion because Kiro cannot replay Anthropic-native
    server tool results.
    """

    type: Literal["web_search_tool_result"] = "web_search_tool_result"
    tool_use_id: str
    content: Union[str, List[Union[WebSearchResultBlock, Dict[str, Any]]]]

    model_config = {"extra": "allow"}


class ToolResultContentBlock(BaseModel):
    """
    Tool result content block in Anthropic format.

    Represents the result of a tool call, sent by the user.
    Tool results can contain text, images, tool references, or a mix.
    """

    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: Optional[
        Union[
            str,
            List[
                Union[
                    "TextContentBlock",
                    "ImageContentBlock",
                    "DocumentContentBlock",
                    "ToolReferenceContentBlock",
                ]
            ],
        ]
    ] = None
    is_error: Optional[bool] = None

    model_config = {"extra": "allow"}

    @model_validator(mode="before")
    @classmethod
    def sanitize_unknown_inner_blocks(cls, data: Any) -> Any:
        """
        Downgrade unknown content block types inside a tool_result's content
        list to text blocks before validation.

        Tool results may carry inner blocks whose type is not part of the
        accepted set (e.g. a future block kind). Converting them to text keeps
        the tool result usable instead of failing the whole request with a 422.
        A string ``content`` (the common case) is passed through untouched.

        Args:
            data: Raw tool_result dict (or other value) prior to validation.

        Returns:
            The (possibly sanitized) input value.
        """
        if not isinstance(data, dict):
            return data
        content = data.get("content")
        if not isinstance(content, list):
            return data
        data["content"] = [
            _downgrade_unknown_block(block, KNOWN_TOOL_RESULT_INNER_TYPES) for block in content
        ]
        return data


# ==================================================================================================
# Image Content Block Models
# ==================================================================================================


class Base64ImageSource(BaseModel):
    """
    Base64-encoded image source in Anthropic format.

    Attributes:
        type: Always "base64"
        media_type: MIME type (e.g., "image/jpeg", "image/png", "image/gif", "image/webp")
        data: Base64-encoded image data
    """

    type: Literal["base64"] = "base64"
    media_type: str
    data: str


class URLImageSource(BaseModel):
    """
    URL-based image source in Anthropic format.

    Note: URL images require fetching and converting to base64 for Kiro API.
    Currently logged as warning and skipped.

    Attributes:
        type: Always "url"
        url: HTTP(S) URL to the image
    """

    type: Literal["url"] = "url"
    url: str


class ImageContentBlock(BaseModel):
    """
    Image content block in Anthropic format.

    Represents an image in a message. Supports both base64-encoded
    images and URL references.

    Attributes:
        type: Always "image"
        source: Image source (base64 or URL)
    """

    type: Literal["image"] = "image"
    source: Union[Base64ImageSource, URLImageSource]


class Base64DocumentSource(BaseModel):
    """
    Base64-encoded document source in Anthropic format.

    Claude Code sends PDFs read from disk as document blocks with base64
    sources. Kiro has no native document input, so converters extract text
    from supported documents and append it to the prompt.

    Attributes:
        type: Always "base64"
        media_type: MIME type (e.g., "application/pdf", "text/plain")
        data: Base64-encoded document data
    """

    type: Literal["base64"] = "base64"
    media_type: str
    data: str


class URLDocumentSource(BaseModel):
    """
    URL-based document source in Anthropic format.

    Note: URL document sources are not supported by Kiro Gateway and are
    surfaced as a placeholder note rather than fetched.

    Attributes:
        type: Always "url"
        url: HTTP(S) URL to the document
    """

    type: Literal["url"] = "url"
    url: str


class DocumentContentBlock(BaseModel):
    """
    Document content block in Anthropic format.

    Represents a document such as a PDF included in a message. The source may
    be base64-encoded, a URL, or a raw dict for forward compatibility.

    Attributes:
        type: Always "document"
        source: Document source (base64, URL, or raw dict)
        title: Optional document title
        context: Optional context string supplied by the client
        cache_control: Optional prompt-caching directive (passed through)
    """

    type: Literal["document"] = "document"
    source: Union[Base64DocumentSource, URLDocumentSource, Dict[str, Any]]
    title: Optional[str] = None
    context: Optional[str] = None
    cache_control: Optional[Dict[str, Any]] = None

    model_config = {"extra": "allow"}


# Union type for all content blocks (including images and thinking)
ContentBlock = Union[
    TextContentBlock,
    ThinkingContentBlock,
    RedactedThinkingContentBlock,
    ImageContentBlock,
    DocumentContentBlock,
    ToolUseContentBlock,
    ToolResultContentBlock,
    ToolReferenceContentBlock,
    ServerToolUseContentBlock,
    WebSearchToolResultContentBlock,
]


# ==================================================================================================
# Message Models
# ==================================================================================================


class AnthropicMessage(BaseModel):
    """
    Message in Anthropic format.

    Attributes:
        role: Message role. The Anthropic spec only defines "user" and
            "assistant" for the messages array (system is a top-level field),
            but some clients (notably Claude Code on certain model ids) emit
            other inline roles such as "system" or "developer". We accept any
            string here and rely on ``normalize_message_roles`` in the
            conversion pipeline to collapse unknown roles to "user" before the
            request reaches upstream Kiro. This prevents 422s on novel roles
            (see #190) without hardcoding a closed set.
        content: Message content (string or list of content blocks)
    """

    role: str
    content: Union[str, List[ContentBlock]]

    model_config = {"extra": "allow"}

    @model_validator(mode="before")
    @classmethod
    def sanitize_unknown_content_blocks(cls, data: Any) -> Any:
        """
        Convert unknown content block types to text blocks before validation.

        Some clients emit content blocks whose ``type`` is not part of the
        Anthropic spec (e.g. future block kinds). Rather than rejecting the
        whole request with a 422, we downgrade unknown blocks to a text block
        that preserves any useful identifying info. Known types listed in
        ``KNOWN_CONTENT_BLOCK_TYPES`` are passed through untouched.

        Args:
            data: Raw message dict (or other value) prior to validation.

        Returns:
            The (possibly sanitized) input value.
        """
        if not isinstance(data, dict):
            return data
        content = data.get("content")
        if not isinstance(content, list):
            return data
        data["content"] = [_downgrade_unknown_block(block, KNOWN_CONTENT_BLOCK_TYPES) for block in content]
        return data


# ==================================================================================================
# Tool Models
# ==================================================================================================


class AnthropicTool(BaseModel):
    """
    Tool definition in Anthropic format.
    
    Supports both user-defined tools and server-side tools (Anthropic):
    - User-defined tools: require input_schema
    - Server-side tools: use type field (e.g., "web_search_20250305")
    
    Attributes:
        type: Tool type for server-side tools (e.g., "web_search_20250305")
        name: Tool name (must match pattern ^[a-zA-Z0-9_-]{1,64}$)
        description: Tool description (optional but recommended)
        input_schema: JSON Schema for tool parameters (required for user-defined tools)
        max_uses: Maximum uses per conversation (server-side tools, optional)
        allowed_domains: Allowed domains for web_search (optional)
        blocked_domains: Blocked domains for web_search (optional)
        user_location: User location for web_search (optional)
    """
    
    # Server-side tool fields (Anthropic spec)
    type: Optional[str] = None
    
    # Common fields
    name: Optional[str] = None  # Optional for server-side tools (validated below)
    description: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None  # Now optional for server-side tools
    
    # Server-side tool parameters (Anthropic spec - accepted but not enforced)
    max_uses: Optional[int] = None
    allowed_domains: Optional[List[str]] = None
    blocked_domains: Optional[List[str]] = None
    user_location: Optional[Dict[str, Any]] = None
    
    model_config = {"extra": "allow"}  # Forward compatibility
    
    @model_validator(mode="after")
    def validate_tool_consistency(self):
        """Validate that user-defined tools have both a name and input_schema."""
        is_server_side = self.type is not None

        if not is_server_side:
            # User-defined tool: name and input_schema are required.
            if not self.name:
                raise ValueError(
                    "name is required for user-defined tools "
                    "(those without a 'type' field)"
                )
            if self.input_schema is None:
                raise ValueError(
                    "input_schema is required for user-defined tools "
                    "(those without a 'type' field)"
                )
        return self


class ToolChoiceAuto(BaseModel):
    """Auto tool choice - model decides whether to use tools."""

    type: Literal["auto"] = "auto"


class ToolChoiceAny(BaseModel):
    """Any tool choice - model must use at least one tool."""

    type: Literal["any"] = "any"


class ToolChoiceTool(BaseModel):
    """Specific tool choice - model must use the specified tool."""

    type: Literal["tool"] = "tool"
    name: str


ToolChoice = Union[ToolChoiceAuto, ToolChoiceAny, ToolChoiceTool]


# ==================================================================================================
# Request Models
# ==================================================================================================


class SystemContentBlock(BaseModel):
    """
    System content block for prompt caching.

    Anthropic API supports system as a list of content blocks
    with optional cache_control for prompt caching.
    """

    type: Literal["text"] = "text"
    text: str
    cache_control: Optional[Dict[str, Any]] = None

    model_config = {"extra": "allow"}


# System can be a string or list of content blocks (for prompt caching)
SystemPrompt = Union[str, List[SystemContentBlock], List[Dict[str, Any]]]


class AnthropicMessagesRequest(BaseModel):
    """
    Request to Anthropic Messages API (/v1/messages).

    Attributes:
        model: Model ID (e.g., "claude-sonnet-4-5")
        messages: List of conversation messages
        max_tokens: Maximum tokens in response (required)
        system: System prompt (optional, string or list of content blocks for caching)
        stream: Whether to stream the response
        tools: List of available tools
        tool_choice: Tool selection strategy
        temperature: Sampling temperature (0-1)
        top_p: Top-p sampling
        top_k: Top-k sampling
        stop_sequences: Custom stop sequences
        metadata: Request metadata
    """

    model: str
    messages: List[AnthropicMessage] = Field(min_length=1)
    max_tokens: int

    # Optional parameters - system can be string or list of content blocks
    system: Optional[SystemPrompt] = None
    stream: bool = False

    # Extended thinking (official Anthropic parameter)
    thinking: Optional[Dict[str, Any]] = None

    # Tools
    tools: Optional[List[AnthropicTool]] = None
    tool_choice: Optional[Union[ToolChoice, Dict[str, Any]]] = None

    # Sampling parameters
    temperature: Optional[float] = Field(default=None, ge=0, le=1)
    top_p: Optional[float] = Field(default=None, ge=0, le=1)
    top_k: Optional[int] = Field(default=None, ge=0)

    # Other parameters
    stop_sequences: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

    model_config = {"extra": "allow"}


class AnthropicCountTokensRequest(BaseModel):
    """
    Request to Anthropic Count Tokens API (/v1/messages/count_tokens).
    
    Similar to AnthropicMessagesRequest but without generation parameters.
    Used to estimate token count before making actual request.
    
    Attributes:
        model: Model ID (e.g., "claude-sonnet-4-5")
        messages: List of conversation messages
        system: System prompt (optional, string or list of content blocks)
        tools: List of available tools
    """
    
    model: str
    messages: List[AnthropicMessage] = Field(min_length=1)
    
    # Optional parameters - only those that affect token count
    system: Optional[SystemPrompt] = None
    tools: Optional[List[AnthropicTool]] = None
    
    model_config = {"extra": "allow"}


# ==================================================================================================
# Response Models
# ==================================================================================================


class AnthropicUsage(BaseModel):
    """
    Token usage information in Anthropic format.

    Attributes:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        cache_read_input_tokens: Tokens read from prompt cache (only forwarded when explicitly returned by upstream Kiro API)
        cache_creation_input_tokens: Tokens used to create prompt cache (only forwarded when explicitly returned by upstream Kiro API)
    """

    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: Optional[int] = None
    cache_creation_input_tokens: Optional[int] = None

    model_config = {"extra": "allow"}


class AnthropicMessagesResponse(BaseModel):
    """
    Response from Anthropic Messages API (non-streaming).

    Attributes:
        id: Unique message ID
        type: Always "message"
        role: Always "assistant"
        content: List of content blocks (may include thinking, text, tool_use)
        model: Model used
        stop_reason: Why generation stopped
        stop_sequence: Stop sequence that triggered stop (if any)
        usage: Token usage information
    """

    id: str
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    content: List[Union[ThinkingContentBlock, TextContentBlock, ToolUseContentBlock]]
    model: str
    stop_reason: Optional[
        Literal["end_turn", "max_tokens", "stop_sequence", "tool_use"]
    ] = None
    stop_sequence: Optional[str] = None
    usage: AnthropicUsage


# ==================================================================================================
# Streaming Event Models
# ==================================================================================================


class MessageStartEvent(BaseModel):
    """
    Event sent at the start of a message stream.

    Contains the initial message object with empty content.
    """

    type: Literal["message_start"] = "message_start"
    message: Dict[str, Any]


class ContentBlockStartEvent(BaseModel):
    """
    Event sent at the start of a content block.

    Attributes:
        index: Index of the content block
        content_block: Initial content block (with empty text for text blocks)
    """

    type: Literal["content_block_start"] = "content_block_start"
    index: int
    content_block: Dict[str, Any]


class TextDelta(BaseModel):
    """Delta for text content."""

    type: Literal["text_delta"] = "text_delta"
    text: str


class ThinkingDelta(BaseModel):
    """Delta for thinking content."""

    type: Literal["thinking_delta"] = "thinking_delta"
    thinking: str


class InputJsonDelta(BaseModel):
    """Delta for tool input JSON."""

    type: Literal["input_json_delta"] = "input_json_delta"
    partial_json: str


class ContentBlockDeltaEvent(BaseModel):
    """
    Event sent when content block is updated.

    Attributes:
        index: Index of the content block being updated
        delta: The delta update (text_delta, thinking_delta, or input_json_delta)
    """

    type: Literal["content_block_delta"] = "content_block_delta"
    index: int
    delta: Union[TextDelta, ThinkingDelta, InputJsonDelta, Dict[str, Any]]


class ContentBlockStopEvent(BaseModel):
    """
    Event sent when a content block is complete.
    """

    type: Literal["content_block_stop"] = "content_block_stop"
    index: int


class MessageDeltaUsage(BaseModel):
    """Usage information in message_delta event."""

    output_tokens: int


class MessageDeltaEvent(BaseModel):
    """
    Event sent near the end of the stream with final message data.

    Attributes:
        delta: Contains stop_reason and stop_sequence
        usage: Output token count
    """

    type: Literal["message_delta"] = "message_delta"
    delta: Dict[str, Any]
    usage: MessageDeltaUsage


class MessageStopEvent(BaseModel):
    """
    Event sent at the end of the message stream.
    """

    type: Literal["message_stop"] = "message_stop"


class PingEvent(BaseModel):
    """
    Ping event sent periodically to keep connection alive.
    """

    type: Literal["ping"] = "ping"


class ErrorEvent(BaseModel):
    """
    Error event sent when an error occurs during streaming.
    """

    type: Literal["error"] = "error"
    error: Dict[str, Any]


# Union of all streaming events
StreamingEvent = Union[
    MessageStartEvent,
    ContentBlockStartEvent,
    ContentBlockDeltaEvent,
    ContentBlockStopEvent,
    MessageDeltaEvent,
    MessageStopEvent,
    PingEvent,
    ErrorEvent,
]


# ==================================================================================================
# Error Models
# ==================================================================================================


class AnthropicErrorDetail(BaseModel):
    """
    Error detail in Anthropic format.
    """

    type: str
    message: str


class AnthropicErrorResponse(BaseModel):
    """
    Error response in Anthropic format.
    """

    type: Literal["error"] = "error"
    error: AnthropicErrorDetail
