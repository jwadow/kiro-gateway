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
from typing import TYPE_CHECKING, AsyncGenerator, Dict, List, Optional, Any

import httpx
from loguru import logger

from kiro.streaming_core import (
    parse_kiro_stream,
    collect_stream_to_result,
    FirstTokenTimeoutError,
    KiroEvent,
    stream_with_first_token_retry,
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


async def stream_kiro_to_anthropic(
    response: httpx.Response,
    model: str,
    model_cache: "ModelInfoCache",
    auth_manager: "KiroAuthManager",
    first_token_timeout: float = FIRST_TOKEN_TIMEOUT,
    prompt_tokens: int = 0,
    conversation_id: Optional[str] = None
) -> AsyncGenerator[str, None]:
    """
    Generator for converting Kiro stream to Anthropic SSE format.

    Parses Kiro AWS SSE stream and converts events to Anthropic format.
    Supports thinking content blocks when FAKE_REASONING_HANDLING=as_reasoning_content.

    Args:
        response: HTTP response with data stream
        model: Model name to include in response
        model_cache: Model cache for getting token limits
        auth_manager: Authentication manager
        first_token_timeout: First token wait timeout (seconds)
        prompt_tokens: Pre-counted prompt tokens (from full Kiro payload)
        conversation_id: Stable conversation ID for truncation recovery (optional)

    Yields:
        Strings in Anthropic SSE format

    Raises:
        FirstTokenTimeoutError: If first token not received within timeout
    """
    message_id = generate_message_id()
    input_tokens = prompt_tokens
    output_tokens = 0
    full_content = ""
    full_thinking_content = ""
    
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
        
        async for event in parse_kiro_stream(response, first_token_timeout):
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
        
        # Detect content truncation (missing completion signals)
        content_was_truncated = (
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

        # input_tokens already set from pre-counted prompt_tokens (full Kiro payload).
        # Don't override with contextUsagePercentage — it's unreliable.
        
        # Determine stop reason
        stop_reason = "tool_use" if tool_blocks else "end_turn"
        
        # Send message_delta with stop_reason and usage
        yield format_sse_event("message_delta", {
            "type": "message_delta",
            "delta": {
                "stop_reason": stop_reason,
                "stop_sequence": None
            },
            "usage": {
                "output_tokens": output_tokens
            }
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
        logger.error(f"Error during Anthropic streaming: [{error_type}] {error_msg}", exc_info=True)
        
        # Send error event
        yield format_sse_event("error", {
            "type": "error",
            "error": {
                "type": "api_error",
                "message": f"Internal error: {error_msg}"
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
    prompt_tokens: int = 0
) -> dict:
    """
    Collect full response from Kiro stream in Anthropic format.

    Used for non-streaming mode.

    Args:
        response: HTTP response with stream
        model: Model name
        model_cache: Model cache
        auth_manager: Authentication manager
        prompt_tokens: Pre-counted prompt tokens (from full Kiro payload)

    Returns:
        Dictionary with full response in Anthropic Messages format
    """
    message_id = generate_message_id()

    # Use pre-counted prompt tokens
    input_tokens = prompt_tokens
    
    # Collect stream result
    result = await collect_stream_to_result(response)
    
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
    
    # input_tokens already set from pre-counted prompt_tokens (full Kiro payload).
    # Don't override with contextUsagePercentage — it's unreliable.
    
    # Determine stop reason
    stop_reason = "tool_use" if result.tool_calls else "end_turn"
    
    logger.debug(
        f"[Anthropic Non-Streaming] Completed: "
        f"input_tokens={input_tokens}, output_tokens={output_tokens}, "
        f"tool_calls={len(result.tool_calls)}, stop_reason={stop_reason}"
    )
    
    return {
        "id": message_id,
        "type": "message",
        "role": "assistant",
        "content": content_blocks,
        "model": model,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens
        }
    }


async def stream_with_first_token_retry_anthropic(
    make_request,
    model: str,
    model_cache: "ModelInfoCache",
    auth_manager: "KiroAuthManager",
    max_retries: int = FIRST_TOKEN_MAX_RETRIES,
    first_token_timeout: float = FIRST_TOKEN_TIMEOUT,
    prompt_tokens: int = 0
) -> AsyncGenerator[str, None]:
    """
    Streaming with automatic retry on first token timeout for Anthropic API.

    If model doesn't respond within first_token_timeout seconds,
    request is cancelled and a new one is made. Maximum max_retries attempts.

    This is seamless for user - they just see a delay,
    but eventually get a response (or error after all attempts).

    Args:
        make_request: Function to create new HTTP request
        model: Model name
        model_cache: Model cache
        auth_manager: Authentication manager
        max_retries: Maximum number of attempts
        first_token_timeout: First token wait timeout (seconds)
        prompt_tokens: Pre-counted prompt tokens (from full Kiro payload)

    Yields:
        Strings in Anthropic SSE format

    Raises:
        Exception with Anthropic error format after exhausting all attempts
    """
    def create_http_error(status_code: int, error_text: str) -> Exception:
        """Create exception for HTTP errors in Anthropic format."""
        return Exception(json.dumps({
            "type": "error",
            "error": {
                "type": "api_error",
                "message": f"Upstream API error: {error_text}"
            }
        }))
    
    def create_timeout_error(retries: int, timeout: float) -> Exception:
        """Create exception for timeout errors in Anthropic format."""
        return Exception(json.dumps({
            "type": "error",
            "error": {
                "type": "timeout_error",
                "message": f"Model did not respond within {timeout}s after {retries} attempts. Please try again."
            }
        }))
    
    async def stream_processor(response: httpx.Response) -> AsyncGenerator[str, None]:
        """Process response and yield Anthropic SSE chunks."""
        async for chunk in stream_kiro_to_anthropic(
            response,
            model,
            model_cache,
            auth_manager,
            first_token_timeout=first_token_timeout,
            prompt_tokens=prompt_tokens
        ):
            yield chunk
    
    async for chunk in stream_with_first_token_retry(
        make_request=make_request,
        stream_processor=stream_processor,
        max_retries=max_retries,
        first_token_timeout=first_token_timeout,
        on_http_error=create_http_error,
        on_all_retries_failed=create_timeout_error,
    ):
        yield chunk