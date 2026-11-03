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
Streaming logic for converting Kiro stream to Anthropic Messages API format.

This module formats Kiro events into Anthropic SSE format:
- event: message_start
- event: content_block_start
- event: content_block_delta
- event: content_block_stop
- event: message_delta
- event: message_stop

Reference: https://docs.anthropic.com/en/api/messages-streaming
"""

import json
import time
import uuid
from contextlib import aclosing
from typing import TYPE_CHECKING, AsyncGenerator, Dict, List, Optional, Any

import httpx
from fastapi import HTTPException
from loguru import logger

from kiro.streaming_core import (
    parse_kiro_stream,
    collect_stream_to_result,
    FirstTokenTimeoutError,
    KiroEvent,
    calculate_tokens_from_context_usage,
    stream_with_first_token_retry,
    anthropic_error_type_for_status,
    ANTHROPIC_DEFAULT_ERROR_TYPE,
    create_stop_sequence_matcher,
    apply_stop_sequences,
    estimate_request_tokens_offloaded,
)
from kiro.tokenizer import count_tokens
from kiro.parsers import parse_bracket_tool_calls, deduplicate_tool_calls
from kiro.config import FIRST_TOKEN_TIMEOUT, FIRST_TOKEN_MAX_RETRIES, FAKE_REASONING_HANDLING

if TYPE_CHECKING:
    from kiro.auth import KiroAuthManager
    from kiro.cache import ModelInfoCache

# Import debug_logger for logging
try:
    from kiro.debug_logger import debug_logger
except ImportError:
    debug_logger = None


def generate_message_id() -> str:
    """Generate unique message ID in Anthropic format."""
    return f"msg_{uuid.uuid4().hex[:24]}"


def format_sse_event(event_type: str, data: Dict[str, Any]) -> str:
    """
    Format data as Anthropic SSE event.
    
    Anthropic SSE format:
    event: {event_type}
    data: {json_data}
    
    Args:
        event_type: Event type (message_start, content_block_delta, etc.)
        data: Event data dictionary
    
    Returns:
        Formatted SSE string
    """
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def generate_thinking_signature() -> str:
    """
    Generate a placeholder signature for thinking content blocks.
    
    In real Anthropic API, this is a cryptographic signature for verification.
    Since we're using fake reasoning via tag injection, we generate a placeholder.
    
    Returns:
        Placeholder signature string
    """
    return f"sig_{uuid.uuid4().hex[:32]}"


class AnthropicStreamError(Exception):
    """
    Error raised by the Anthropic streaming layer with Anthropic error metadata.

    str(error) is the Anthropic error JSON ({"type": "error", "error": {...}}),
    exactly as before this class existed, so existing callers that parse the
    message keep working. New callers can read status_code / error_type /
    message directly.

    Attributes:
        status_code: HTTP status code (upstream or gateway)
        error_type: Anthropic error type (e.g. "rate_limit_error")
        message: Human-readable error message
    """

    def __init__(self, status_code: int, error_type: str, message: str) -> None:
        """
        Initialize the error.

        Args:
            status_code: HTTP status code
            error_type: Anthropic error type
            message: Human-readable error message
        """
        self.status_code = status_code
        self.error_type = error_type
        self.message = message
        super().__init__(json.dumps({
            "type": "error",
            "error": {"type": error_type, "message": message}
        }))


def anthropic_error_type_for_exception(error: BaseException) -> str:
    """
    Pick the Anthropic error type for an exception raised mid-stream.

    Uses the HTTP status carried by the exception when there is one
    (AnthropicStreamError, FastAPI HTTPException, httpx.HTTPStatusError).
    Anything else is an internal failure and maps to "api_error".

    Args:
        error: Exception raised while streaming

    Returns:
        Anthropic error type string
    """
    if isinstance(error, AnthropicStreamError):
        return error.error_type
    if isinstance(error, HTTPException):
        return anthropic_error_type_for_status(error.status_code)
    if isinstance(error, httpx.HTTPStatusError):
        return anthropic_error_type_for_status(error.response.status_code)
    return ANTHROPIC_DEFAULT_ERROR_TYPE


def _resolve_stop_reason(
    content_was_truncated: bool,
    has_tool_use: bool,
    matched_stop_sequence: Optional[str],
) -> str:
    """
    Determine the Anthropic stop_reason (shared by streaming and non-streaming).

    Priority: truncation > tool_use > stop_sequence > end_turn.

    Args:
        content_was_truncated: Upstream ended without completion signals
        has_tool_use: At least one tool_use block was produced
        matched_stop_sequence: Stop sequence that ended the text, if any

    Returns:
        Anthropic stop_reason value
    """
    if content_was_truncated:
        return "max_tokens"
    if has_tool_use:
        return "tool_use"
    if matched_stop_sequence is not None:
        return "stop_sequence"
    return "end_turn"


async def _estimate_input_tokens(
    request_messages: Optional[list],
    request_tools: Optional[list],
    request_system: Optional[Any],
) -> int:
    """
    Estimate input tokens from the full request without blocking the event loop.

    Args:
        request_messages: Original request messages
        request_tools: Original request tools
        request_system: Original system prompt

    Returns:
        Estimated input token count (0 when there is nothing to count)
    """
    if not (request_messages or request_tools or request_system):
        return 0
    request_token_stats = await estimate_request_tokens_offloaded(
        messages=request_messages or [],
        tools=request_tools,
        system_prompt=request_system,
        apply_claude_correction=False
    )
    return request_token_stats["total_tokens"]


def _extract_cache_usage_fields(usage: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """
    Extract cache token fields from upstream usage (if present).

    Args:
        usage: Usage data from Kiro stream event

    Returns:
        Dict containing only available cache fields; missing fields are omitted
    """
    if not isinstance(usage, dict):
        return {}

    extracted: Dict[str, int] = {}
    key_map = {
        "cache_read_input_tokens": "cache_read_input_tokens",
        "cacheReadInputTokens": "cache_read_input_tokens",
        "cache_creation_input_tokens": "cache_creation_input_tokens",
        "cacheCreationInputTokens": "cache_creation_input_tokens",
    }
    for source_key, target_key in key_map.items():
        value = usage.get(source_key)
        if isinstance(value, (int, float)):
            extracted[target_key] = int(value)

    return extracted


async def stream_kiro_to_anthropic(
    response: httpx.Response,
    model: str,
    model_cache: "ModelInfoCache",
    auth_manager: "KiroAuthManager",
    first_token_timeout: float = FIRST_TOKEN_TIMEOUT,
    request_messages: Optional[list] = None,
    request_tools: Optional[list] = None,
    request_system: Optional[Any] = None,
    conversation_id: Optional[str] = None,
    stop_sequences: Optional[List[str]] = None,
) -> AsyncGenerator[str, None]:
    """
    Generator for converting Kiro stream to Anthropic SSE format.

    Parses Kiro AWS SSE stream and converts events to Anthropic format.
    Supports thinking content blocks when FAKE_REASONING_HANDLING=as_reasoning_content.

    If the stream fails after message_start, an `event: error` is emitted with
    the Anthropic error type mapped from the failure (see
    anthropic_error_type_for_exception), then the exception is re-raised.

    Args:
        response: HTTP response with data stream
        model: Model name to include in response
        model_cache: Model cache for getting token limits
        auth_manager: Authentication manager
        first_token_timeout: First token wait timeout (seconds)
        request_messages: Original request messages (for token counting)
        request_tools: Original request tools (for token counting)
        request_system: Original system prompt (for token counting)
        conversation_id: Stable conversation ID for truncation recovery (optional)
        stop_sequences: Optional gateway-side stop sequences, applied to text only.
                        On a match: stop_reason "stop_sequence" and stop_sequence set.
                        None = disabled (native behaviour).

    Yields:
        Strings in Anthropic SSE format

    Raises:
        FirstTokenTimeoutError: If first token not received within timeout
    """
    message_id = generate_message_id()
    input_tokens = 0
    output_tokens = 0
    full_content = ""
    full_thinking_content = ""
    
    # NOTE: Anthropic streaming spec requires input_tokens in message_start (beginning),
    # but Kiro API provides accurate context_usage at the end of stream.
    # This creates a fundamental limitation: we must use fallback estimation in message_start.
    # Accuracy: ~85-90% (acceptable trade-off for maintaining streaming capability).
    # See: https://docs.anthropic.com/en/api/messages-streaming
    
    # Fallback estimation must cover messages/tools/system to avoid significant undercount.
    # It runs off the event loop: tiktoken over a long history is CPU-bound.
    input_tokens = await _estimate_input_tokens(request_messages, request_tools, request_system)

    stop_matcher = create_stop_sequence_matcher(stop_sequences)

    # Track content blocks - thinking block is index 0, text block is index 1 (when thinking enabled)
    current_block_index = 0
    thinking_block_started = False
    thinking_block_index: Optional[int] = None
    text_block_started = False
    text_block_index: Optional[int] = None
    tool_blocks: List[Dict[str, Any]] = []
    tool_input_buffers: Dict[int, str] = {}  # index -> accumulated JSON
    
    # Generate signature for thinking block (used if thinking is present)
    thinking_signature = generate_thinking_signature()
    
    # Track context usage for token calculation
    context_usage_percentage: Optional[float] = None
    upstream_cache_usage: Dict[str, int] = {}
    
    # Track truncated tool calls for recovery
    truncated_tools: List[Dict[str, Any]] = []
    
    try:
        # Send message_start event
        yield format_sse_event("message_start", {
            "type": "message_start",
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": model,
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": 0
                }
            }
        })
        
        # apply_stop_sequences is a pure pass-through when stop_matcher is None
        event_stream = apply_stop_sequences(parse_kiro_stream(response, first_token_timeout), stop_matcher)
        async with aclosing(event_stream) as events:
            async for event in events:
                if event.type == "content":
                    content = event.content or ""
                    full_content += content
                
                    # Close thinking block if it was open and we're now getting regular content
                    if thinking_block_started and thinking_block_index is not None:
                        yield format_sse_event("content_block_stop", {
                            "type": "content_block_stop",
                            "index": thinking_block_index
                        })
                        thinking_block_started = False
                        current_block_index += 1
                
                    # Start text block if not started
                    if not text_block_started:
                        text_block_index = current_block_index
                        yield format_sse_event("content_block_start", {
                            "type": "content_block_start",
                            "index": text_block_index,
                            "content_block": {
                                "type": "text",
                                "text": ""
                            }
                        })
                        text_block_started = True
                
                    # Send content delta
                    if content:
                        yield format_sse_event("content_block_delta", {
                            "type": "content_block_delta",
                            "index": text_block_index,
                            "delta": {
                                "type": "text_delta",
                                "text": content
                            }
                        })
            
                elif event.type == "thinking":
                    thinking_content = event.thinking_content or ""
                    full_thinking_content += thinking_content
                
                    # Handle thinking content based on mode
                    if FAKE_REASONING_HANDLING == "as_reasoning_content":
                        # Use native Anthropic thinking content blocks
                        if not thinking_block_started:
                            thinking_block_index = current_block_index
                            yield format_sse_event("content_block_start", {
                                "type": "content_block_start",
                                "index": thinking_block_index,
                                "content_block": {
                                    "type": "thinking",
                                    "thinking": "",
                                    "signature": thinking_signature
                                }
                            })
                            thinking_block_started = True
                    
                        if thinking_content:
                            yield format_sse_event("content_block_delta", {
                                "type": "content_block_delta",
                                "index": thinking_block_index,
                                "delta": {
                                    "type": "thinking_delta",
                                    "thinking": thinking_content
                                }
                            })
                
                    elif FAKE_REASONING_HANDLING == "include_as_text":
                        # Include thinking as regular text content
                        # Close thinking block if it was open (shouldn't happen in this mode)
                        if thinking_block_started and thinking_block_index is not None:
                            yield format_sse_event("content_block_stop", {
                                "type": "content_block_stop",
                                "index": thinking_block_index
                            })
                            thinking_block_started = False
                            current_block_index += 1
                    
                        # Start text block if not started
                        if not text_block_started:
                            text_block_index = current_block_index
                            yield format_sse_event("content_block_start", {
                                "type": "content_block_start",
                                "index": text_block_index,
                                "content_block": {
                                    "type": "text",
                                    "text": ""
                                }
                            })
                            text_block_started = True
                    
                        if thinking_content:
                            yield format_sse_event("content_block_delta", {
                                "type": "content_block_delta",
                                "index": text_block_index,
                                "delta": {
                                    "type": "text_delta",
                                    "text": thinking_content
                                }
                            })
                    # For "strip" mode, we just skip the thinking content
            
                elif event.type == "tool_use" and event.tool_use:
                    # Close thinking block if open
                    if thinking_block_started and thinking_block_index is not None:
                        yield format_sse_event("content_block_stop", {
                            "type": "content_block_stop",
                            "index": thinking_block_index
                        })
                        thinking_block_started = False
                        current_block_index += 1
                
                    # Close text block if open
                    if text_block_started and text_block_index is not None:
                        yield format_sse_event("content_block_stop", {
                            "type": "content_block_stop",
                            "index": text_block_index
                        })
                        text_block_started = False
                        current_block_index += 1
                
                    tool = event.tool_use
                    tool_id = tool.get("id") or f"toolu_{uuid.uuid4().hex[:24]}"
                    tool_name = tool.get("function", {}).get("name", "") or tool.get("name", "")
                    tool_input = tool.get("function", {}).get("arguments", {}) or tool.get("input", {})
                
                    # ==============================================================================
                    # WebSearch Support - Path B: MCP Tool Emulation (Streaming Interception)
                    # ==============================================================================
                
                    # INTERCEPT web_search tool calls (Path B - MCP emulation)
                    if tool_name == "web_search":
                        from kiro.mcp_tools import call_kiro_mcp_api, generate_search_summary
                    
                        logger.info("Intercepted web_search tool call (Path B - MCP emulation)")
                    
                        # Parse tool_input if string
                        if isinstance(tool_input, str):
                            try:
                                tool_input = json.loads(tool_input)
                            except json.JSONDecodeError:
                                tool_input = {}
                    
                        # Extract query
                        query = tool_input.get("query", "")
                        if not query:
                            logger.warning("web_search called without query, skipping MCP call")
                            continue
                    
                        logger.debug(f"WebSearch query (Path B): {query}")
                    
                        # Call MCP API
                        mcp_tool_use_id, results = await call_kiro_mcp_api(query, auth_manager)
                    
                        if results is None:
                            logger.error("MCP API call failed for web_search")
                            # Continue with normal tool_use processing (will show error to user)
                        else:
                            # Emit server_tool_use + web_search_tool_result + text summary
                            # (full SSE sequence as in mcp_tools.py)
                        
                            # Event: content_block_start (server_tool_use)
                            yield format_sse_event("content_block_start", {
                                "type": "content_block_start",
                                "index": current_block_index,
                                "content_block": {
                                    "id": mcp_tool_use_id,
                                    "type": "server_tool_use",
                                    "name": "web_search",
                                    "input": {}
                                }
                            })
                        
                            # Event: content_block_delta (input_json_delta)
                            yield format_sse_event("content_block_delta", {
                                "type": "content_block_delta",
                                "index": current_block_index,
                                "delta": {
                                    "type": "input_json_delta",
                                    "partial_json": json.dumps({"query": query})
                                }
                            })
                        
                            # Event: content_block_stop (server_tool_use)
                            yield format_sse_event("content_block_stop", {
                                "type": "content_block_stop",
                                "index": current_block_index
                            })
                            current_block_index += 1
                        
                            # Event: content_block_start (web_search_tool_result)
                            search_content = []
                            for r in results.get("results", []):
                                search_content.append({
                                    "type": "web_search_result",
                                    "title": r.get("title", ""),
                                    "url": r.get("url", ""),
                                    "encrypted_content": r.get("snippet", ""),
                                    "page_age": None
                                })
                        
                            yield format_sse_event("content_block_start", {
                                "type": "content_block_start",
                                "index": current_block_index,
                                "content_block": {
                                    "type": "web_search_tool_result",
                                    "tool_use_id": mcp_tool_use_id,
                                    "content": search_content
                                }
                            })
                        
                            # Event: content_block_stop (web_search_tool_result)
                            yield format_sse_event("content_block_stop", {
                                "type": "content_block_stop",
                                "index": current_block_index
                            })
                            current_block_index += 1
                        
                            # Event: content_block_start (text)
                            yield format_sse_event("content_block_start", {
                                "type": "content_block_start",
                                "index": current_block_index,
                                "content_block": {"type": "text", "text": ""}
                            })
                        
                            # Events: content_block_delta (text_delta) - stream summary
                            summary = generate_search_summary(query, results)
                            chunk_size = 100
                            for i in range(0, len(summary), chunk_size):
                                chunk = summary[i:i + chunk_size]
                                yield format_sse_event("content_block_delta", {
                                    "type": "content_block_delta",
                                    "index": current_block_index,
                                    "delta": {"type": "text_delta", "text": chunk}
                                })
                        
                            # Event: content_block_stop (text)
                            yield format_sse_event("content_block_stop", {
                                "type": "content_block_stop",
                                "index": current_block_index
                            })
                            current_block_index += 1
                        
                            # Skip normal tool_use processing
                            continue
                
                    # Check if this tool was truncated
                    if tool.get('_truncation_detected'):
                        truncated_tools.append({
                            "id": tool_id,
                            "name": tool_name,
                            "truncation_info": tool.get('_truncation_info', {})
                        })
                
                    # Parse arguments if string
                    if isinstance(tool_input, str):
                        try:
                            tool_input = json.loads(tool_input)
                        except json.JSONDecodeError:
                            tool_input = {}
                
                    # Send tool_use block start
                    yield format_sse_event("content_block_start", {
                        "type": "content_block_start",
                        "index": current_block_index,
                        "content_block": {
                            "type": "tool_use",
                            "id": tool_id,
                            "name": tool_name,
                            "input": {}
                        }
                    })
                
                    # Send tool input as delta
                    input_json = json.dumps(tool_input, ensure_ascii=False)
                    yield format_sse_event("content_block_delta", {
                        "type": "content_block_delta",
                        "index": current_block_index,
                        "delta": {
                            "type": "input_json_delta",
                            "partial_json": input_json
                        }
                    })
                
                    # Close tool block
                    yield format_sse_event("content_block_stop", {
                        "type": "content_block_stop",
                        "index": current_block_index
                    })
                
                    tool_blocks.append({
                        "id": tool_id,
                        "name": tool_name,
                        "input": tool_input
                    })
                    current_block_index += 1
            
                elif event.type == "context_usage" and event.context_usage_percentage is not None:
                    context_usage_percentage = event.context_usage_percentage
                elif event.type == "usage" and event.usage:
                    upstream_cache_usage.update(_extract_cache_usage_fields(event.usage))
        
        # Track completion signals for truncation detection
        stream_completed_normally = context_usage_percentage is not None
        
        # Check for bracket-style tool calls in full content
        bracket_tool_calls = parse_bracket_tool_calls(full_content)
        if bracket_tool_calls:
            # Close thinking block if open
            if thinking_block_started and thinking_block_index is not None:
                yield format_sse_event("content_block_stop", {
                    "type": "content_block_stop",
                    "index": thinking_block_index
                })
                thinking_block_started = False
                current_block_index += 1
            
            # Close text block if open
            if text_block_started and text_block_index is not None:
                yield format_sse_event("content_block_stop", {
                    "type": "content_block_stop",
                    "index": text_block_index
                })
                text_block_started = False
                current_block_index += 1
            
            for tc in bracket_tool_calls:
                tool_id = tc.get("id") or f"toolu_{uuid.uuid4().hex[:24]}"
                tool_name = tc.get("function", {}).get("name", "")
                tool_input = tc.get("function", {}).get("arguments", {})
                
                if isinstance(tool_input, str):
                    try:
                        tool_input = json.loads(tool_input)
                    except json.JSONDecodeError:
                        tool_input = {}
                
                yield format_sse_event("content_block_start", {
                    "type": "content_block_start",
                    "index": current_block_index,
                    "content_block": {
                        "type": "tool_use",
                        "id": tool_id,
                        "name": tool_name,
                        "input": {}
                    }
                })
                
                input_json = json.dumps(tool_input, ensure_ascii=False)
                yield format_sse_event("content_block_delta", {
                    "type": "content_block_delta",
                    "index": current_block_index,
                    "delta": {
                        "type": "input_json_delta",
                        "partial_json": input_json
                    }
                })
                
                yield format_sse_event("content_block_stop", {
                    "type": "content_block_stop",
                    "index": current_block_index
                })
                
                tool_blocks.append({
                    "id": tool_id,
                    "name": tool_name,
                    "input": tool_input
                })
                current_block_index += 1
        
        # Close thinking block if still open
        if thinking_block_started and thinking_block_index is not None:
            yield format_sse_event("content_block_stop", {
                "type": "content_block_stop",
                "index": thinking_block_index
            })
            current_block_index += 1
        
        # Close text block if still open
        if text_block_started and text_block_index is not None:
            yield format_sse_event("content_block_stop", {
                "type": "content_block_stop",
                "index": text_block_index
            })
        
        matched_stop_sequence = stop_matcher.matched if stop_matcher is not None else None

        # Detect content truncation (missing completion signals).
        # A stop sequence match ends the stream on purpose before completion
        # signals arrive, so it is never treated as truncation.
        content_was_truncated = (
            matched_stop_sequence is None and
            not stream_completed_normally and
            len(full_content) > 0 and
            not tool_blocks  # Don't confuse with tool call truncation
        )

        if content_was_truncated:
            from kiro.config import TRUNCATION_RECOVERY
            logger.error(
                f"Content truncated by Kiro API: stream ended without completion signals, "
                f"length={len(full_content)} chars. "
                f"{'Model will be notified automatically about truncation.' if TRUNCATION_RECOVERY else 'Set TRUNCATION_RECOVERY=true in .env to auto-notify model about truncation.'}"
            )
        
        # Calculate output tokens
        output_tokens = count_tokens(full_content + full_thinking_content)
        
        # Calculate total tokens from context usage if available
        if context_usage_percentage is not None:
            prompt_tokens, _, prompt_source, _ = calculate_tokens_from_context_usage(
                context_usage_percentage, output_tokens, model_cache, model
            )
            # Don't override fallback when context_usage=0% (returns source="unknown")
            # Only override local estimate when upstream context usage is available
            if prompt_source != "unknown":
                input_tokens = prompt_tokens
        
        # Determine stop reason (truncation has highest priority)
        stop_reason = _resolve_stop_reason(content_was_truncated, bool(tool_blocks), matched_stop_sequence)
        reported_stop_sequence = matched_stop_sequence if stop_reason == "stop_sequence" else None
        if matched_stop_sequence is not None:
            logger.info(f"Generation ended by stop sequence {matched_stop_sequence!r} (stop_reason={stop_reason})")

        # Send message_delta with stop_reason and usage
        usage_payload = {
            "output_tokens": output_tokens
        }
        usage_payload.update(upstream_cache_usage)

        yield format_sse_event("message_delta", {
            "type": "message_delta",
            "delta": {
                "stop_reason": stop_reason,
                "stop_sequence": reported_stop_sequence
            },
            "usage": usage_payload
        })
        
        # Send message_stop
        yield format_sse_event("message_stop", {
            "type": "message_stop"
        })
        
        # Save truncation info for recovery (tracked by stable identifiers)
        from kiro.truncation_recovery import should_inject_recovery
        from kiro.truncation_state import save_tool_truncation, save_content_truncation
        
        if should_inject_recovery():
            # Save tool truncations (tracked by tool_call_id)
            if truncated_tools:
                for truncated_tool in truncated_tools:
                    save_tool_truncation(
                        tool_call_id=truncated_tool["id"],
                        tool_name=truncated_tool["name"],
                        truncation_info=truncated_tool["truncation_info"]
                    )
            
            # Save content truncation (tracked by content hash)
            if content_was_truncated:
                save_content_truncation(full_content)
            
            if truncated_tools or content_was_truncated:
                logger.info(
                    f"Truncation detected: {len(truncated_tools)} tool(s), "
                    f"content={content_was_truncated}. Will be handled when client sends next request."
                )
        
        logger.debug(
            f"[Anthropic Streaming] Completed: "
            f"input_tokens={input_tokens}, output_tokens={output_tokens}, "
            f"tool_blocks={len(tool_blocks)}, stop_reason={stop_reason}"
        )
        
    except FirstTokenTimeoutError:
        raise
    except GeneratorExit:
        logger.debug("Client disconnected (GeneratorExit)")
        raise
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e) if str(e) else "(empty message)"
        # Positional args: loguru treats curly braces in an f-string message
        # (e.g. an upstream JSON error body) as format fields and raises KeyError,
        # which would prevent the error event below from being sent.
        logger.error("Error during Anthropic streaming: [{}] {}", error_type, error_msg, exc_info=True)

        # Send error event with the Anthropic error type for this failure.
        # Errors with an HTTP status keep their message; anything else is an
        # internal gateway failure.
        anthropic_error_type = anthropic_error_type_for_exception(e)
        if isinstance(e, AnthropicStreamError):
            client_message = e.message
        elif isinstance(e, HTTPException):
            client_message = str(e.detail)
        else:
            client_message = f"Internal error: {error_msg}"
        yield format_sse_event("error", {
            "type": "error",
            "error": {
                "type": anthropic_error_type,
                "message": client_message
            }
        })
        raise
    finally:
        try:
            await response.aclose()
        except Exception as close_error:
            logger.debug(f"Error closing response: {close_error}")


async def collect_anthropic_response(
    response: httpx.Response,
    model: str,
    model_cache: "ModelInfoCache",
    auth_manager: "KiroAuthManager",
    request_messages: Optional[list] = None,
    request_tools: Optional[list] = None,
    request_system: Optional[Any] = None,
    stop_sequences: Optional[List[str]] = None,
) -> dict:
    """
    Collect full response from Kiro stream in Anthropic format.

    Used for non-streaming mode.

    Args:
        response: HTTP response with stream
        model: Model name
        model_cache: Model cache
        auth_manager: Authentication manager
        request_messages: Original request messages (for token counting)
        request_tools: Original request tools (for token counting)
        request_system: Original system prompt (for token counting)
        stop_sequences: Optional gateway-side stop sequences, applied to text only.
                        On a match: stop_reason "stop_sequence" and stop_sequence set.
                        None = disabled (native behaviour).

    Returns:
        Dictionary with full response in Anthropic Messages format
    """
    message_id = generate_message_id()

    # Non-streaming uses the same full-request estimation as streaming (off the event loop)
    input_tokens = await _estimate_input_tokens(request_messages, request_tools, request_system)

    # Collect stream result
    if stop_sequences is None:
        result = await collect_stream_to_result(response)
    else:
        result = await collect_stream_to_result(response, stop_sequences=stop_sequences)
    matched_stop_sequence = result.stop_sequence
    upstream_cache_usage = _extract_cache_usage_fields(result.usage)
    
    # Build content blocks
    content_blocks = []
    
    # Add thinking block FIRST if there's thinking content and mode is as_reasoning_content
    if result.thinking_content and FAKE_REASONING_HANDLING == "as_reasoning_content":
        content_blocks.append({
            "type": "thinking",
            "thinking": result.thinking_content,
            "signature": generate_thinking_signature()
        })
    
    # Add text block if there's content
    # For include_as_text mode, prepend thinking content to regular content
    text_content = result.content
    if result.thinking_content and FAKE_REASONING_HANDLING == "include_as_text":
        text_content = result.thinking_content + text_content
    
    if text_content:
        content_blocks.append({
            "type": "text",
            "text": text_content
        })
    
    # Add tool use blocks
    for tc in result.tool_calls:
        tool_id = tc.get("id") or f"toolu_{uuid.uuid4().hex[:24]}"
        tool_name = tc.get("function", {}).get("name", "") or tc.get("name", "")
        tool_input = tc.get("function", {}).get("arguments", {}) or tc.get("input", {})
        
        if isinstance(tool_input, str):
            try:
                tool_input = json.loads(tool_input)
            except json.JSONDecodeError:
                tool_input = {}
        
        content_blocks.append({
            "type": "tool_use",
            "id": tool_id,
            "name": tool_name,
            "input": tool_input
        })
    
    # Calculate output tokens
    output_tokens = count_tokens(result.content + result.thinking_content)
    
    # Calculate from context usage if available
    if result.context_usage_percentage is not None:
        prompt_tokens, _, prompt_source, _ = calculate_tokens_from_context_usage(
            result.context_usage_percentage, output_tokens, model_cache, model
        )
        # Don't override fallback when context_usage=0% (returns source="unknown")
        if prompt_source != "unknown":
            input_tokens = prompt_tokens
    
    # Detect content truncation (missing completion signals).
    # A stop sequence match ends collection on purpose, so it is never truncation.
    stream_completed_normally = result.context_usage_percentage is not None
    content_was_truncated = (
        matched_stop_sequence is None and
        not stream_completed_normally and
        len(result.content) > 0 and
        not result.tool_calls  # Don't confuse with tool call truncation
    )
    
    if content_was_truncated:
        from kiro.config import TRUNCATION_RECOVERY
        logger.error(
            f"Content truncated by Kiro API (non-streaming): stream ended without completion signals, "
            f"length={len(result.content)} chars. "
            f"{'Model will be notified automatically about truncation.' if TRUNCATION_RECOVERY else 'Set TRUNCATION_RECOVERY=true in .env to auto-notify model about truncation.'}"
        )
    
    # Determine stop reason (truncation has highest priority)
    stop_reason = _resolve_stop_reason(content_was_truncated, bool(result.tool_calls), matched_stop_sequence)
    reported_stop_sequence = matched_stop_sequence if stop_reason == "stop_sequence" else None
    if matched_stop_sequence is not None:
        logger.info(f"Generation ended by stop sequence {matched_stop_sequence!r} (stop_reason={stop_reason})")
    
    logger.debug(
        f"[Anthropic Non-Streaming] Completed: "
        f"input_tokens={input_tokens}, output_tokens={output_tokens}, "
        f"tool_calls={len(result.tool_calls)}, stop_reason={stop_reason}"
    )
    
    usage_payload: Dict[str, Any] = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens
    }
    usage_payload.update(upstream_cache_usage)

    return {
        "id": message_id,
        "type": "message",
        "role": "assistant",
        "content": content_blocks,
        "model": model,
        "stop_reason": stop_reason,
        "stop_sequence": reported_stop_sequence,
        "usage": usage_payload
    }


async def stream_with_first_token_retry_anthropic(
    make_request,
    model: str,
    model_cache: "ModelInfoCache",
    auth_manager: "KiroAuthManager",
    initial_response: Optional[httpx.Response] = None,
    max_retries: int = FIRST_TOKEN_MAX_RETRIES,
    first_token_timeout: float = FIRST_TOKEN_TIMEOUT,
    request_messages: Optional[list] = None,
    request_tools: Optional[list] = None,
    request_system: Optional[Any] = None,
    stop_sequences: Optional[List[str]] = None,
) -> AsyncGenerator[str, None]:
    """
    Streaming with automatic retry on first token timeout for Anthropic API.
    
    If model doesn't respond within the first token timeout,
    request is cancelled and a new one is made. Maximum max_retries attempts.
    The timeout grows per attempt: first_token_timeout * (attempt + 1).
    
    This is seamless for user - they just see a delay,
    but eventually get a response (or error after all attempts).
    
    Args:
        make_request: Function to create new HTTP request
        model: Model name
        model_cache: Model cache
        auth_manager: Authentication manager
        initial_response: Optional pre-validated response to use on first attempt.
                         If provided, make_request is only called on retries.
        max_retries: Maximum number of attempts
        first_token_timeout: First token wait timeout (seconds)
        request_messages: Original request messages (for fallback token counting)
        request_tools: Original request tools (for fallback token counting)
        request_system: Original system prompt (for fallback token counting)
        stop_sequences: Optional gateway-side stop sequences (None = disabled)
    
    Yields:
        Strings in Anthropic SSE format
    
    Raises:
        AnthropicStreamError: str() is the Anthropic error JSON. Raised on an
            upstream HTTP error (error type mapped from the status code) or after
            exhausting all attempts (type "timeout_error", status 504).
    """
    def create_http_error(status_code: int, error_text: str) -> Exception:
        """Create exception for HTTP errors in Anthropic format."""
        return AnthropicStreamError(
            status_code=status_code,
            error_type=anthropic_error_type_for_status(status_code),
            message=f"Upstream API error: {error_text}",
        )
    
    def create_timeout_error(retries: int, timeout: float) -> Exception:
        """Create exception for timeout errors in Anthropic format."""
        return AnthropicStreamError(
            status_code=504,
            error_type="timeout_error",
            message=f"Model did not respond within {timeout}s after {retries} attempts. Please try again.",
        )
    
    # Only forward stop_sequences when set, so the call stays identical to the
    # previous one when the feature is not used.
    extra_kwargs: Dict[str, Any] = {}
    if stop_sequences is not None:
        extra_kwargs["stop_sequences"] = stop_sequences
    
    async def stream_processor(response: httpx.Response, attempt_timeout: float) -> AsyncGenerator[str, None]:
        """Process response and yield Anthropic SSE chunks."""
        async with aclosing(stream_kiro_to_anthropic(
            response,
            model,
            model_cache,
            auth_manager,
            first_token_timeout=attempt_timeout,
            request_messages=request_messages,
            request_tools=request_tools,
            request_system=request_system,
            **extra_kwargs,
        )) as chunks:
            async for chunk in chunks:
                yield chunk
    
    async with aclosing(stream_with_first_token_retry(
        make_request=make_request,
        stream_processor=stream_processor,
        initial_response=initial_response,
        max_retries=max_retries,
        first_token_timeout=first_token_timeout,
        on_http_error=create_http_error,
        on_all_retries_failed=create_timeout_error,
        timeout_aware_processor=True,
    )) as chunks:
        async for chunk in chunks:
            yield chunk
