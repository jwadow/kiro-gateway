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
Streaming logic for converting Kiro stream to OpenAI format.

Contains generators for:
- Converting AWS SSE to OpenAI SSE
- Forming streaming chunks
- Processing tool calls in stream
- Gateway-side stop sequences
- Optional `stream_options.include_usage` final usage chunk

Uses streaming_core.py for parsing Kiro stream into unified KiroEvent objects.

Internally a single generator (_generate_openai_chunks) produces
chat.completion.chunk dictionaries. The SSE path serializes them and the
non-streaming path (collect_stream_response) accumulates them directly, so both
modes share one implementation without a JSON encode/decode round-trip.
"""

import json
import time
from contextlib import aclosing
from typing import TYPE_CHECKING, Any, AsyncGenerator, Callable, Awaitable, Dict, List, Optional

import httpx
from fastapi import HTTPException
from loguru import logger

from kiro.parsers import parse_bracket_tool_calls, deduplicate_tool_calls
from kiro.utils import generate_completion_id
from kiro.config import (
    FIRST_TOKEN_TIMEOUT,
    FIRST_TOKEN_MAX_RETRIES,
    FAKE_REASONING_HANDLING,
)
from kiro.tokenizer import count_tokens

# Import from streaming_core - reuse shared parsing logic
from kiro.streaming_core import (
    parse_kiro_stream,
    FirstTokenTimeoutError,
    KiroEvent,
    calculate_tokens_from_context_usage,
    create_stop_sequence_matcher,
    apply_stop_sequences,
    estimate_request_tokens_offloaded,
    stream_with_first_token_retry as stream_with_first_token_retry_core,
)

if TYPE_CHECKING:
    from kiro.auth import KiroAuthManager
    from kiro.cache import ModelInfoCache

# Import debug_logger for logging
try:
    from kiro.debug_logger import debug_logger
except ImportError:
    debug_logger = None


# Re-export FirstTokenTimeoutError for backward compatibility
__all__ = ['FirstTokenTimeoutError', 'stream_kiro_to_openai', 'stream_with_first_token_retry', 'collect_stream_response']


SSE_DONE = "data: [DONE]\n\n"

# Size of content pieces used when emitting a web_search summary
WEB_SEARCH_SUMMARY_CHUNK_SIZE = 100


def format_openai_sse_chunk(chunk: Dict[str, Any]) -> str:
    """
    Serialize an OpenAI chat.completion.chunk dict as an SSE data line.

    Args:
        chunk: chat.completion.chunk dictionary

    Returns:
        SSE string "data: {...}\\n\\n"
    """
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


def build_usage_only_chunk(final_chunk: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the OpenAI `stream_options.include_usage` chunk from the final chunk.

    Per OpenAI spec, when include_usage is true the last chunk before [DONE]
    has an empty `choices` list and carries the request usage.

    Args:
        final_chunk: The finish_reason chunk (must contain "usage")

    Returns:
        chat.completion.chunk dict with choices=[] and a copy of the usage
    """
    return {
        "id": final_chunk["id"],
        "object": "chat.completion.chunk",
        "created": final_chunk["created"],
        "model": final_chunk["model"],
        "choices": [],
        "usage": dict(final_chunk["usage"]),
    }


async def _generate_openai_chunks(
    response: httpx.Response,
    model: str,
    model_cache: "ModelInfoCache",
    auth_manager: "KiroAuthManager",
    first_token_timeout: float = FIRST_TOKEN_TIMEOUT,
    request_messages: Optional[list] = None,
    request_tools: Optional[list] = None,
    stop_sequences: Optional[List[str]] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Convert a Kiro stream into OpenAI chat.completion.chunk dictionaries.

    Single source of truth for OpenAI output, used by the SSE generator and by
    collect_stream_response(). The last item is always the final chunk with
    finish_reason and usage. Does not close the response (callers do).

    Args:
        response: HTTP response with data stream
        model: Model name to include in response
        model_cache: Model cache for getting token limits
        auth_manager: Authentication manager
        first_token_timeout: First token wait timeout (seconds)
        request_messages: Original request messages (for fallback token counting)
        request_tools: Original request tools (for fallback token counting)
        stop_sequences: Optional gateway-side stop sequences, applied to text
                        content only (not thinking, not tool calls).
                        None = disabled (native behaviour).

    Yields:
        chat.completion.chunk dictionaries

    Raises:
        FirstTokenTimeoutError: If first token not received within timeout
    """
    completion_id = generate_completion_id()
    created_time = int(time.time())
    first_chunk = True

    metering_data = None
    context_usage_percentage = None
    full_content = ""
    full_thinking_content = ""
    tool_calls_from_stream = []

    def make_delta_chunk(delta: Dict[str, Any]) -> Dict[str, Any]:
        """Wrap a delta into a chat.completion.chunk (adds role on the first chunk)."""
        nonlocal first_chunk
        if first_chunk:
            delta["role"] = "assistant"
            first_chunk = False
        return {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created_time,
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": None}]
        }

    stop_matcher = create_stop_sequence_matcher(stop_sequences)
    # apply_stop_sequences is a pure pass-through when stop_matcher is None
    events = apply_stop_sequences(parse_kiro_stream(response, first_token_timeout), stop_matcher)

    async with aclosing(events) as event_stream:
        async for event in event_stream:
            if event.type == "content" and event.content:
                # Accumulate content for bracket tool call detection
                full_content += event.content
                yield make_delta_chunk({"content": event.content})

            elif event.type == "thinking" and event.thinking_content:
                # Accumulate thinking content
                full_thinking_content += event.thinking_content

                # Send as reasoning_content or content based on mode
                if FAKE_REASONING_HANDLING == "as_reasoning_content":
                    delta = {"reasoning_content": event.thinking_content}
                else:
                    delta = {"content": event.thinking_content}
                yield make_delta_chunk(delta)

            elif event.type == "tool_use" and event.tool_use:
                tool = event.tool_use

                # Extract tool name safely (handle None/missing fields)
                tool_name = ""
                if tool:
                    tool_name = (tool.get("function") or {}).get("name", "") or tool.get("name", "")

                # ==============================================================================
                # WebSearch Support - Path B: MCP Tool Emulation (Streaming Interception)
                # ==============================================================================

                # INTERCEPT web_search tool calls (Path B - MCP emulation)
                if tool_name == "web_search":
                    from kiro.mcp_tools import call_kiro_mcp_api, generate_search_summary

                    logger.info("Intercepted web_search tool call (Path B - MCP emulation)")

                    # Parse tool_input
                    tool_input = tool.get("function", {}).get("arguments", {}) or tool.get("input", {})
                    if isinstance(tool_input, str):
                        try:
                            tool_input = json.loads(tool_input)
                        except json.JSONDecodeError:
                            tool_input = {}

                    # Extract query
                    query = tool_input.get("query", "")
                    if not query:
                        logger.warning("web_search called without query, skipping MCP call")
                        # Continue with normal tool_use processing
                    else:
                        logger.debug(f"WebSearch query (Path B): {query}")

                        # Call MCP API
                        mcp_tool_use_id, results = await call_kiro_mcp_api(query, auth_manager)

                        if results is None:
                            logger.error("MCP API call failed for web_search")
                            # Continue with normal tool_use processing (will show error to user)
                        else:
                            # Emit summary as content chunks (OpenAI format)
                            summary = generate_search_summary(query, results)
                            for i in range(0, len(summary), WEB_SEARCH_SUMMARY_CHUNK_SIZE):
                                content_piece = summary[i:i + WEB_SEARCH_SUMMARY_CHUNK_SIZE]
                                yield make_delta_chunk({"content": content_piece})

                            # Accumulate for token counting
                            full_content += summary

                            # Skip normal tool_use processing
                            continue

                # Collect tool calls from stream (normal tools, not web_search)
                tool_calls_from_stream.append(event.tool_use)

            elif event.type == "usage" and event.usage:
                metering_data = event.usage

            elif event.type == "context_usage" and event.context_usage_percentage is not None:
                context_usage_percentage = event.context_usage_percentage

    matched_stop_sequence = stop_matcher.matched if stop_matcher is not None else None

    # Track completion signals for truncation detection
    received_usage = metering_data is not None
    received_context_usage = context_usage_percentage is not None
    stream_completed_normally = received_usage or received_context_usage

    # Check bracket-style tool calls in full content
    bracket_tool_calls = parse_bracket_tool_calls(full_content)
    all_tool_calls = tool_calls_from_stream + bracket_tool_calls
    all_tool_calls = deduplicate_tool_calls(all_tool_calls)

    # Detect content truncation (missing completion signals).
    # A stop sequence match ends the stream on purpose before completion
    # signals arrive, so it is never treated as truncation.
    content_was_truncated = (
        matched_stop_sequence is None and
        not stream_completed_normally and
        len(full_content) > 0 and
        not all_tool_calls  # Don't confuse with tool call truncation
    )

    if content_was_truncated:
        from kiro.config import TRUNCATION_RECOVERY
        logger.error(
            f"Content truncated by Kiro API: stream ended without completion signals, "
            f"length={len(full_content)} chars. "
            f"{'Model will be notified automatically about truncation.' if TRUNCATION_RECOVERY else 'Set TRUNCATION_RECOVERY=true in .env to auto-notify model about truncation.'}"
        )

    # Determine finish_reason (truncation has highest priority).
    # A stop sequence match maps to "stop" (OpenAI spec); tool calls received
    # before the match keep "tool_calls".
    if content_was_truncated:
        finish_reason = "length"
    elif all_tool_calls:
        finish_reason = "tool_calls"
    else:
        finish_reason = "stop"

    if matched_stop_sequence is not None:
        logger.info(f"Generation ended by stop sequence {matched_stop_sequence!r} (finish_reason={finish_reason})")

    # Count completion_tokens (output) using tiktoken
    completion_tokens = count_tokens(full_content + full_thinking_content)

    # Calculate total_tokens based on context_usage_percentage from Kiro API
    # context_usage shows TOTAL percentage of context usage (input + output)
    prompt_tokens, total_tokens, prompt_source, total_source = calculate_tokens_from_context_usage(
        context_usage_percentage, completion_tokens, model_cache, model
    )

    # Fallback: Kiro API didn't return context_usage, use tiktoken.
    # Counting the whole history is CPU-bound, so it runs off the event loop.
    # IMPORTANT: Don't apply correction coefficient for prompt_tokens,
    # as it was calibrated for completion_tokens
    if prompt_source == "unknown" and request_messages:
        request_token_stats = await estimate_request_tokens_offloaded(
            messages=request_messages,
            tools=request_tools,
            system_prompt=None,
            apply_claude_correction=False,
        )
        prompt_tokens = request_token_stats["total_tokens"]
        total_tokens = prompt_tokens + completion_tokens
        prompt_source = "tiktoken"
        total_source = "tiktoken"

    # Send tool calls if present
    if all_tool_calls:
        logger.debug(f"Processing {len(all_tool_calls)} tool calls for streaming response")

        # Add required index field to each tool_call
        # according to OpenAI API specification for streaming
        indexed_tool_calls = []
        for idx, tc in enumerate(all_tool_calls):
            # Extract function with None protection
            func = tc.get("function") or {}
            # Use "or" for protection against explicit None in values
            tool_name = func.get("name") or ""
            tool_args = func.get("arguments") or "{}"

            logger.debug(f"Tool call [{idx}] '{tool_name}': id={tc.get('id')}, args_length={len(tool_args)}")

            indexed_tool_calls.append({
                "index": idx,
                "id": tc.get("id"),
                "type": tc.get("type", "function"),
                "function": {
                    "name": tool_name,
                    "arguments": tool_args
                }
            })

        yield {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created_time,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"tool_calls": indexed_tool_calls},
                "finish_reason": None
            }]
        }

    # Save truncation info for recovery (tracked by stable identifiers)
    from kiro.truncation_recovery import should_inject_recovery
    from kiro.truncation_state import save_tool_truncation, save_content_truncation

    if should_inject_recovery():
        # Save tool truncations (tracked by tool_call_id)
        truncated_count = 0
        for tc in all_tool_calls:
            if tc.get('_truncation_detected'):
                save_tool_truncation(
                    tool_call_id=tc['id'],
                    tool_name=tc['function']['name'],
                    truncation_info=tc['_truncation_info']
                )
                truncated_count += 1

        # Save content truncation (tracked by content hash)
        if content_was_truncated:
            save_content_truncation(full_content)

        if truncated_count > 0 or content_was_truncated:
            logger.info(
                f"Truncation detected: {truncated_count} tool(s), "
                f"content={content_was_truncated}. Will be handled when client sends next request."
            )

    # Final chunk with usage
    final_chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created_time,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
    }

    if metering_data:
        final_chunk["usage"]["credits_used"] = metering_data

    # Log final token values being sent to client
    logger.debug(
        f"[Usage] {model}: "
        f"prompt_tokens={prompt_tokens} ({prompt_source}), "
        f"completion_tokens={completion_tokens} (tiktoken), "
        f"total_tokens={total_tokens} ({total_source})"
    )

    yield final_chunk


async def stream_kiro_to_openai_internal(
    client: httpx.AsyncClient,
    response: httpx.Response,
    model: str,
    model_cache: "ModelInfoCache",
    auth_manager: "KiroAuthManager",
    first_token_timeout: float = FIRST_TOKEN_TIMEOUT,
    request_messages: Optional[list] = None,
    request_tools: Optional[list] = None,
    conversation_id: Optional[str] = None,
    include_usage: bool = False,
    stop_sequences: Optional[List[str]] = None,
) -> AsyncGenerator[str, None]:
    """
    Internal generator for converting Kiro stream to OpenAI format.

    Parses AWS SSE stream and converts events to OpenAI chat.completion.chunk.
    Supports tool calls and usage calculation.

    IMPORTANT: This function raises FirstTokenTimeoutError if first token
    is not received within first_token_timeout seconds.

    Args:
        client: HTTP client (for connection management)
        response: HTTP response with data stream
        model: Model name to include in response
        model_cache: Model cache for getting token limits
        auth_manager: Authentication manager
        first_token_timeout: First token wait timeout (seconds)
        request_messages: Original request messages (for fallback token counting)
        request_tools: Original request tools (for fallback token counting)
        conversation_id: Stable conversation ID for truncation recovery (optional)
        include_usage: Value of request `stream_options.include_usage`. Usage is
                       always attached to the finish_reason chunk (backward
                       compatible). When True, an extra final chunk with
                       `choices: []` and `usage` is sent before [DONE] (OpenAI spec).
        stop_sequences: Optional gateway-side stop sequences (None = disabled)

    Yields:
        Strings in SSE format: "data: {...}\\n\\n" or "data: [DONE]\\n\\n"

    Raises:
        FirstTokenTimeoutError: If first token not received within timeout

    Example:
        >>> async for chunk in stream_kiro_to_openai_internal(client, response, "claude-sonnet-4", cache, auth):
        ...     print(chunk)
        data: {"id":"chatcmpl-...","object":"chat.completion.chunk",...}

        data: [DONE]
    """
    streaming_error_occurred = False

    try:
        chunk_generator = _generate_openai_chunks(
            response,
            model,
            model_cache,
            auth_manager,
            first_token_timeout=first_token_timeout,
            request_messages=request_messages,
            request_tools=request_tools,
            stop_sequences=stop_sequences,
        )
        final_chunk: Optional[Dict[str, Any]] = None
        async with aclosing(chunk_generator) as chunks:
            async for chunk in chunks:
                chunk_text = format_openai_sse_chunk(chunk)
                if debug_logger:
                    debug_logger.log_modified_chunk(chunk_text.encode('utf-8'))
                if "usage" in chunk:
                    final_chunk = chunk
                yield chunk_text

        if include_usage and final_chunk is not None:
            usage_chunk_text = format_openai_sse_chunk(build_usage_only_chunk(final_chunk))
            if debug_logger:
                debug_logger.log_modified_chunk(usage_chunk_text.encode('utf-8'))
            yield usage_chunk_text

        yield SSE_DONE

    except FirstTokenTimeoutError:
        # Propagate timeout up for retry
        raise
    except GeneratorExit:
        # Client disconnected - this is normal, don't log as error
        logger.debug("Client disconnected (GeneratorExit)")
        streaming_error_occurred = True
    except Exception as e:
        streaming_error_occurred = True
        # Log exception type and message for better diagnostics
        error_type = type(e).__name__
        error_msg = str(e) if str(e) else "(empty message)"
        # Positional args: with kwargs (exc_info) loguru formats the message and
        # braces in error_msg would raise KeyError, masking the real error.
        logger.error(
            "Error during streaming: [{}] {}", error_type, error_msg,
            exc_info=True
        )
        # Propagate error up for proper handling in routes_openai.py
        raise
    finally:
        # Always close response
        try:
            await response.aclose()
        except Exception as close_error:
            logger.debug(f"Error closing response: {close_error}")

        if streaming_error_occurred:
            logger.debug("Streaming completed with error")
        else:
            logger.debug("Streaming completed successfully")


async def stream_kiro_to_openai(
    client: httpx.AsyncClient,
    response: httpx.Response,
    model: str,
    model_cache: "ModelInfoCache",
    auth_manager: "KiroAuthManager",
    request_messages: Optional[list] = None,
    request_tools: Optional[list] = None,
    include_usage: bool = False,
    stop_sequences: Optional[List[str]] = None,
) -> AsyncGenerator[str, None]:
    """
    Generator for converting Kiro stream to OpenAI format.

    This is a wrapper over stream_kiro_to_openai_internal that does NOT retry.
    Retry logic is implemented in stream_with_first_token_retry.

    Args:
        client: HTTP client (for connection management)
        response: HTTP response with data stream
        model: Model name to include in response
        model_cache: Model cache for getting token limits
        auth_manager: Authentication manager
        request_messages: Original request messages (for fallback token counting)
        request_tools: Original request tools (for fallback token counting)
        include_usage: Request `stream_options.include_usage` (adds a choices=[] usage chunk)
        stop_sequences: Optional gateway-side stop sequences (None = disabled)

    Yields:
        Strings in SSE format: "data: {...}\\n\\n" or "data: [DONE]\\n\\n"
    """
    async with aclosing(stream_kiro_to_openai_internal(
        client, response, model, model_cache, auth_manager,
        request_messages=request_messages,
        request_tools=request_tools,
        include_usage=include_usage,
        stop_sequences=stop_sequences,
    )) as chunks:
        async for chunk in chunks:
            yield chunk


async def stream_with_first_token_retry(
    make_request: Callable[[], Awaitable[httpx.Response]],
    client: httpx.AsyncClient,
    model: str,
    model_cache: "ModelInfoCache",
    auth_manager: "KiroAuthManager",
    initial_response: Optional[httpx.Response] = None,
    max_retries: int = FIRST_TOKEN_MAX_RETRIES,
    first_token_timeout: float = FIRST_TOKEN_TIMEOUT,
    request_messages: Optional[list] = None,
    request_tools: Optional[list] = None,
    include_usage: bool = False,
    stop_sequences: Optional[List[str]] = None,
) -> AsyncGenerator[str, None]:
    """
    Streaming with automatic retry on first token timeout.

    If model doesn't respond within the first token timeout,
    request is cancelled and a new one is made. Maximum max_retries attempts.
    The timeout grows per attempt: first_token_timeout * (attempt + 1).

    This is seamless for user - they just see a delay,
    but eventually get a response (or error after all attempts).

    Uses generic stream_with_first_token_retry from streaming_core.py.

    Args:
        make_request: Function to create new HTTP request
        client: HTTP client
        model: Model name
        model_cache: Model cache
        auth_manager: Authentication manager
        initial_response: Optional pre-validated response to use on first attempt.
                         If provided, make_request is only called on retries.
        max_retries: Maximum number of attempts
        first_token_timeout: Base first token wait timeout (seconds)
        request_messages: Original request messages (for fallback token counting)
        request_tools: Original request tools (for fallback token counting)
        include_usage: Request `stream_options.include_usage` (adds a choices=[] usage chunk)
        stop_sequences: Optional gateway-side stop sequences (None = disabled)

    Yields:
        Strings in SSE format

    Raises:
        HTTPException: After exhausting all attempts

    Example:
        >>> async def make_req():
        ...     return await http_client.request_with_retry("POST", url, payload, stream=True)
        >>> response = await make_req()
        >>> async for chunk in stream_with_first_token_retry(
        ...     make_req, client, model, cache, auth, initial_response=response
        ... ):
        ...     print(chunk)
    """
    def create_http_error(status_code: int, error_text: str) -> HTTPException:
        """Create HTTPException for HTTP errors."""
        return HTTPException(
            status_code=status_code,
            detail=f"Upstream API error: {error_text}"
        )

    def create_timeout_error(retries: int, timeout: float) -> HTTPException:
        """Create HTTPException for timeout errors."""
        return HTTPException(
            status_code=504,
            detail=f"Model did not respond within {timeout}s after {retries} attempts. Please try again."
        )

    async def stream_processor(response: httpx.Response, attempt_timeout: float) -> AsyncGenerator[str, None]:
        """Process response and yield OpenAI SSE chunks."""
        async with aclosing(stream_kiro_to_openai_internal(
            client,
            response,
            model,
            model_cache,
            auth_manager,
            first_token_timeout=attempt_timeout,
            request_messages=request_messages,
            request_tools=request_tools,
            include_usage=include_usage,
            stop_sequences=stop_sequences,
        )) as chunks:
            async for chunk in chunks:
                yield chunk

    async with aclosing(stream_with_first_token_retry_core(
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


async def collect_stream_response(
    client: httpx.AsyncClient,
    response: httpx.Response,
    model: str,
    model_cache: "ModelInfoCache",
    auth_manager: "KiroAuthManager",
    request_messages: Optional[list] = None,
    request_tools: Optional[list] = None,
    stop_sequences: Optional[List[str]] = None,
) -> dict:
    """
    Collect full response from streaming stream.

    Used for non-streaming mode. Consumes the same chunk dictionaries as the
    streaming path (so output is identical) and accumulates them directly,
    without serializing to SSE and parsing back.

    Args:
        client: HTTP client
        response: HTTP response with stream
        model: Model name
        model_cache: Model cache
        auth_manager: Authentication manager
        request_messages: Original request messages (for fallback token counting)
        request_tools: Original request tools (for fallback token counting)
        stop_sequences: Optional gateway-side stop sequences (None = disabled)

    Returns:
        Dictionary with full response in OpenAI chat.completion format
    """
    content_parts: List[str] = []
    reasoning_parts: List[str] = []
    final_usage = None
    tool_calls = []
    finish_reason = "stop"  # Default fallback
    completion_id = generate_completion_id()

    try:
        chunk_generator = _generate_openai_chunks(
            response,
            model,
            model_cache,
            auth_manager,
            request_messages=request_messages,
            request_tools=request_tools,
            stop_sequences=stop_sequences,
        )
        async with aclosing(chunk_generator) as chunks:
            async for chunk_data in chunks:
                choice = (chunk_data.get("choices") or [{}])[0]
                delta = choice.get("delta", {})
                if "content" in delta:
                    content_parts.append(delta["content"])
                if "reasoning_content" in delta:
                    reasoning_parts.append(delta["reasoning_content"])
                if "tool_calls" in delta:
                    tool_calls.extend(delta["tool_calls"])

                # finish_reason was already calculated by the chunk generator
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]

                if "usage" in chunk_data:
                    final_usage = chunk_data["usage"]
    finally:
        # Always close response (same guarantee as the streaming path)
        try:
            await response.aclose()
        except Exception as close_error:
            logger.debug(f"Error closing response: {close_error}")

    # Form final response
    message = {"role": "assistant", "content": "".join(content_parts)}
    full_reasoning_content = "".join(reasoning_parts)
    if full_reasoning_content:
        message["reasoning_content"] = full_reasoning_content
    if tool_calls:
        # For non-streaming response remove index field from tool_calls,
        # as it's only required for streaming chunks
        cleaned_tool_calls = []
        for tc in tool_calls:
            # Extract function with None protection
            func = tc.get("function") or {}
            cleaned_tool_calls.append({
                "id": tc.get("id"),
                "type": tc.get("type", "function"),
                "function": {
                    "name": func.get("name", ""),
                    "arguments": func.get("arguments", "{}")
                }
            })
        message["tool_calls"] = cleaned_tool_calls

    # Form usage for response
    usage = final_usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": finish_reason
        }],
        "usage": usage
    }
