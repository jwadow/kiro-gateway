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
Core streaming logic for parsing Kiro API responses.

This module contains shared logic used by both OpenAI and Anthropic streaming:
- KiroEvent dataclass for unified events
- Kiro SSE stream parsing
- Full response collection
- First token timeout handling

The core layer provides a unified interface that API-specific formatters use
to convert Kiro events to their respective SSE formats.
"""

import asyncio
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncGenerator, Callable, Awaitable, Dict, List, Optional, Sequence, Tuple, Union

import httpx
from loguru import logger

from kiro.parsers import AwsEventStreamParser, parse_bracket_tool_calls, deduplicate_tool_calls
from kiro.config import (
    FIRST_TOKEN_TIMEOUT,
    FIRST_TOKEN_MAX_RETRIES,
    FAKE_REASONING_ENABLED,
    FAKE_REASONING_HANDLING,
    STREAMING_READ_TIMEOUT,
)
from kiro.thinking_parser import ThinkingParser
from kiro import tokenizer as tokenizer_module

if TYPE_CHECKING:
    from kiro.cache import ModelInfoCache

# Import debug_logger for logging
try:
    from kiro.debug_logger import debug_logger
except ImportError:
    debug_logger = None


# ==================================================================================================
# Data Classes
# ==================================================================================================

@dataclass
class KiroEvent:
    """
    Unified event from Kiro API stream.
    
    This format is API-agnostic and can be converted to both OpenAI and Anthropic formats.
    
    Attributes:
        type: Event type (content, thinking, tool_use, usage, context_usage, error)
        content: Text content (for content events)
        thinking_content: Thinking/reasoning content (for thinking events)
        tool_use: Tool use data (for tool_use events)
        usage: Usage/metering data (for usage events)
        context_usage_percentage: Context usage percentage (for context_usage events)
        is_first_thinking_chunk: Whether this is the first thinking chunk
        is_last_thinking_chunk: Whether this is the last thinking chunk
    """
    type: str
    content: Optional[str] = None
    thinking_content: Optional[str] = None
    tool_use: Optional[Dict[str, Any]] = None
    usage: Optional[Dict[str, Any]] = None
    context_usage_percentage: Optional[float] = None
    is_first_thinking_chunk: bool = False
    is_last_thinking_chunk: bool = False


@dataclass
class StreamResult:
    """
    Result of collecting a complete stream response.
    
    Attributes:
        content: Full text content
        thinking_content: Full thinking/reasoning content
        tool_calls: List of tool calls
        usage: Usage information
        context_usage_percentage: Context usage percentage from Kiro API
        stop_sequence: Stop sequence that ended the text output (None if none matched)
    """
    content: str = ""
    thinking_content: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    usage: Optional[Dict[str, Any]] = None
    context_usage_percentage: Optional[float] = None
    stop_sequence: Optional[str] = None


class FirstTokenTimeoutError(Exception):
    """Exception raised when first token timeout occurs."""
    pass


# ==================================================================================================
# Anthropic Error Type Mapping
# ==================================================================================================

# HTTP status -> Anthropic error "type" field.
# Reference: https://docs.anthropic.com/en/api/errors
ANTHROPIC_ERROR_TYPES_BY_STATUS: Dict[int, str] = {
    400: "invalid_request_error",
    401: "authentication_error",
    403: "permission_error",
    404: "not_found_error",
    429: "rate_limit_error",
    503: "overloaded_error",
    529: "overloaded_error",
}

ANTHROPIC_DEFAULT_ERROR_TYPE = "api_error"


def anthropic_error_type_for_status(status: int) -> str:
    """
    Map an HTTP status code to the Anthropic API error type.

    Args:
        status: HTTP status code from upstream (or the gateway)

    Returns:
        Anthropic error type string ("api_error" for any unmapped status)

    Examples:
        >>> anthropic_error_type_for_status(429)
        'rate_limit_error'
        >>> anthropic_error_type_for_status(500)
        'api_error'
    """
    return ANTHROPIC_ERROR_TYPES_BY_STATUS.get(status, ANTHROPIC_DEFAULT_ERROR_TYPE)


# ==================================================================================================
# Stop Sequence Handling
# ==================================================================================================

def normalize_stop_sequences(stop_sequences: Optional[Union[str, Sequence[str]]]) -> List[str]:
    """
    Normalize client stop sequences into a de-duplicated list of non-empty strings.

    Accepts a single string as well (OpenAI allows `stop: "..."`).

    Args:
        stop_sequences: None, a string, or a sequence of strings

    Returns:
        List of unique non-empty stop sequences, in original order
    """
    if stop_sequences is None:
        return []
    if isinstance(stop_sequences, str):
        stop_sequences = [stop_sequences]
    result: List[str] = []
    for seq in stop_sequences:
        if isinstance(seq, str) and seq and seq not in result:
            result.append(seq)
    return result


class StopSequenceMatcher:
    """
    Incremental, chunk-boundary-safe stop sequence detector for text output.

    Kiro API has no native stop sequences, so the gateway enforces them on the
    text stream. Text is held back by (longest stop sequence length - 1) chars,
    so a sequence split across chunks is detected before any part of it reaches
    the client.

    The chosen match is the one that completes earliest in the text (ties go to
    the earliest start). The result does not depend on how upstream splits the
    text into chunks.

    Only regular text is fed here. Thinking content and tool calls are never
    matched against stop sequences.

    Attributes:
        stop_sequences: Non-empty stop sequences being matched
        matched: The stop sequence that matched, or None
    """

    def __init__(self, stop_sequences: Sequence[str]) -> None:
        """
        Initialize the matcher.

        Args:
            stop_sequences: Stop sequences to match (empty strings are ignored)

        Raises:
            ValueError: If no non-empty stop sequence is provided
        """
        self.stop_sequences: List[str] = normalize_stop_sequences(stop_sequences)
        if not self.stop_sequences:
            raise ValueError("StopSequenceMatcher requires at least one non-empty stop sequence")
        self._holdback = max(len(seq) for seq in self.stop_sequences) - 1
        self._buffer = ""
        self.matched: Optional[str] = None

    def feed(self, text: str) -> Tuple[str, Optional[str]]:
        """
        Feed a piece of text and get the part that is safe to emit.

        Args:
            text: Next piece of text from the stream

        Returns:
            Tuple (text_to_emit, matched_sequence). When matched_sequence is not
            None, text_to_emit is everything before the match and the text output
            must end. After a match, all further input is discarded.
        """
        if self.matched is not None:
            return "", self.matched
        if not text:
            return "", None

        self._buffer += text

        best: Optional[Tuple[int, int, str]] = None  # (end, start, sequence)
        for seq in self.stop_sequences:
            start = self._buffer.find(seq)
            if start == -1:
                continue
            candidate = (start + len(seq), start, seq)
            if best is None or candidate[:2] < best[:2]:
                best = candidate

        if best is not None:
            _, start, seq = best
            emit = self._buffer[:start]
            self._buffer = ""
            self.matched = seq
            logger.debug(f"Stop sequence matched: {seq!r}")
            return emit, seq

        safe_length = len(self._buffer) - self._holdback
        if safe_length <= 0:
            return "", None
        emit = self._buffer[:safe_length]
        self._buffer = self._buffer[safe_length:]
        return emit, None

    def flush(self) -> str:
        """
        Release held-back text (end of stream, or before non-text output).

        Held-back text never contains a complete stop sequence, because feed()
        checks the whole buffer each time.

        Returns:
            Held-back text (empty string after a match)
        """
        pending = self._buffer
        self._buffer = ""
        return pending


STOP_SEQUENCE_PASSTHROUGH_EVENT_TYPES = frozenset({"usage", "context_usage"})
"""Event types with no client-visible output; they never force a text flush."""


async def apply_stop_sequences(
    events: AsyncGenerator[KiroEvent, None],
    matcher: Optional[StopSequenceMatcher],
) -> AsyncGenerator[KiroEvent, None]:
    """
    Apply gateway-side stop sequences to a stream of KiroEvents.

    This is the single place where stop sequences are enforced. The OpenAI and
    Anthropic formatters use it in both streaming and non-streaming modes.

    Behaviour:
    - "content" events go through the matcher. Text that might be the start
      of a stop sequence is held back until it is safe to emit.
    - Before any other output event (thinking, tool_use) is passed on,
      held-back text is flushed, so output order is preserved. Thinking
      content and tool calls are never matched.
    - usage/context_usage events pass through unchanged.
    - On a match, the text before the match is emitted, the upstream stream
      is closed and iteration ends (generation is over). matcher.matched
      tells the caller which sequence matched.
    - At the end of the stream, held-back text is flushed.

    With matcher=None, events pass through untouched.

    Args:
        events: Upstream KiroEvent async generator (usually parse_kiro_stream)
        matcher: Stop sequence matcher, or None to disable stop sequences

    Yields:
        KiroEvent objects with stop sequences applied
    """
    async with aclosing(events) as upstream:
        if matcher is None:
            async for event in upstream:
                yield event
            return

        async for event in upstream:
            if event.type == "content":
                emitted, matched = matcher.feed(event.content or "")
                if emitted:
                    yield KiroEvent(type="content", content=emitted)
                if matched is not None:
                    return
                continue

            if event.type not in STOP_SEQUENCE_PASSTHROUGH_EVENT_TYPES:
                pending = matcher.flush()
                if pending:
                    yield KiroEvent(type="content", content=pending)
            yield event

        pending = matcher.flush()
        if pending:
            yield KiroEvent(type="content", content=pending)


def create_stop_sequence_matcher(
    stop_sequences: Optional[Union[str, Sequence[str]]]
) -> Optional[StopSequenceMatcher]:
    """
    Create a matcher if there is anything to match.

    Args:
        stop_sequences: Client stop sequences (None, a string, or a sequence of strings)

    Returns:
        StopSequenceMatcher, or None when no usable stop sequence was given.
        None means: behave exactly as without stop sequences.
    """
    normalized = normalize_stop_sequences(stop_sequences)
    if not normalized:
        return None
    return StopSequenceMatcher(normalized)


# ==================================================================================================
# Non-blocking Token Estimation
# ==================================================================================================

async def estimate_request_tokens_offloaded(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    system_prompt: Optional[Any] = None,
    apply_claude_correction: bool = True,
) -> Dict[str, int]:
    """
    Estimate request tokens without blocking the event loop.

    tiktoken over a full conversation history is CPU-bound and can stall every
    other stream on the loop. Uses tokenizer.estimate_request_tokens_async when
    it exists, otherwise runs tokenizer.estimate_request_tokens in a thread.

    Args:
        messages: Request messages
        tools: Request tools (optional)
        system_prompt: System prompt (optional)
        apply_claude_correction: Apply Claude correction coefficient

    Returns:
        Dict with messages_tokens, tools_tokens, system_tokens, total_tokens
    """
    async_estimator = getattr(tokenizer_module, "estimate_request_tokens_async", None)
    if async_estimator is not None:
        return await async_estimator(
            messages=messages,
            tools=tools,
            system_prompt=system_prompt,
            apply_claude_correction=apply_claude_correction,
        )
    return await asyncio.to_thread(
        tokenizer_module.estimate_request_tokens,
        messages,
        tools,
        system_prompt,
        apply_claude_correction,
    )


# ==================================================================================================
# Kiro Stream Parsing
# ==================================================================================================

async def parse_kiro_stream(
    response: httpx.Response,
    first_token_timeout: float = FIRST_TOKEN_TIMEOUT,
    enable_thinking_parser: bool = True
) -> AsyncGenerator[KiroEvent, None]:
    """
    Parses Kiro SSE stream and yields unified events.
    
    This is the core parsing function that converts Kiro's AWS SSE format
    into unified KiroEvent objects that can be formatted for any API.
    
    Args:
        response: HTTP response with data stream
        first_token_timeout: First token wait timeout (seconds)
        enable_thinking_parser: Whether to enable thinking block parsing
    
    Yields:
        KiroEvent objects representing stream events
    
    Raises:
        FirstTokenTimeoutError: If first token not received within timeout
    """
    parser = AwsEventStreamParser()
    first_token_received = False
    
    # Initialize thinking parser if fake reasoning is enabled
    thinking_parser: Optional[ThinkingParser] = None
    if FAKE_REASONING_ENABLED and enable_thinking_parser:
        thinking_parser = ThinkingParser(handling_mode=FAKE_REASONING_HANDLING)
        logger.debug(f"Thinking parser initialized with mode: {FAKE_REASONING_HANDLING}")
    
    try:
        # Create iterator for reading bytes
        byte_iterator = response.aiter_bytes()
        
        # Wait for first chunk with timeout
        try:
            logger.debug(f"Waiting for first token (timeout={first_token_timeout}s)...")
            first_byte_chunk = await asyncio.wait_for(
                byte_iterator.__anext__(),
                timeout=first_token_timeout
            )
            logger.debug("First token received")
        except asyncio.TimeoutError:
            logger.warning(f"[FirstTokenTimeout] Model did not respond within {first_token_timeout}s")
            raise FirstTokenTimeoutError(f"No response within {first_token_timeout} seconds")
        except StopAsyncIteration:
            # Empty response - this is normal, just finish
            logger.debug("Empty response from Kiro API")
            return
        
        # Process first chunk
        if debug_logger:
            debug_logger.log_raw_chunk(first_byte_chunk)
        
        for event in _process_chunk(parser, first_byte_chunk, thinking_parser):
            if event.type == "content" or event.type == "thinking":
                first_token_received = True
            yield event
        
        # Continue reading remaining chunks
        async for chunk in byte_iterator:
            if debug_logger:
                debug_logger.log_raw_chunk(chunk)
            
            for event in _process_chunk(parser, chunk, thinking_parser):
                yield event
        
        # Finalize thinking parser and yield any remaining content
        if thinking_parser:
            final_result = thinking_parser.finalize()
            
            if final_result.thinking_content:
                processed_thinking = thinking_parser.process_for_output(
                    final_result.thinking_content,
                    final_result.is_first_thinking_chunk,
                    final_result.is_last_thinking_chunk,
                )
                if processed_thinking:
                    yield KiroEvent(
                        type="thinking",
                        thinking_content=processed_thinking,
                        is_first_thinking_chunk=final_result.is_first_thinking_chunk,
                        is_last_thinking_chunk=final_result.is_last_thinking_chunk,
                    )
            
            if final_result.regular_content:
                yield KiroEvent(type="content", content=final_result.regular_content)
            
            if thinking_parser.found_thinking_block:
                logger.debug("Thinking block processing completed")
        
        # Check bracket-style tool calls in accumulated content
        all_tool_calls = parser.get_tool_calls()
        # Note: bracket tool calls are checked by the caller using full content
        
        # Yield tool calls if any
        for tc in all_tool_calls:
            yield KiroEvent(type="tool_use", tool_use=tc)
            
    except FirstTokenTimeoutError:
        raise
    except GeneratorExit:
        logger.debug("Client disconnected (GeneratorExit)")
        raise
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e) if str(e) else "(empty message)"
        # Positional args: with kwargs (exc_info) loguru formats the message and
        # braces in error_msg would raise KeyError, masking the real error.
        logger.error("Error during stream parsing: [{}] {}", error_type, error_msg, exc_info=True)
        raise


def _process_chunk(
    parser: AwsEventStreamParser,
    chunk: bytes,
    thinking_parser: Optional[ThinkingParser]
) -> List[KiroEvent]:
    """
    Process a single chunk from Kiro stream.
    
    This is a plain (synchronous) function: parsing a chunk never awaits,
    so building a list avoids creating an async generator per network chunk.
    
    Args:
        parser: AWS event stream parser
        chunk: Raw bytes chunk
        thinking_parser: Optional thinking parser for fake reasoning
    
    Returns:
        List of KiroEvent objects parsed from the chunk, in stream order
    """
    result: List[KiroEvent] = []
    
    for event in parser.feed(chunk):
        if event["type"] == "content":
            content = event["data"]
            
            # Process through thinking parser if enabled
            if thinking_parser:
                parse_result = thinking_parser.feed(content)
                
                # Thinking content if any
                if parse_result.thinking_content:
                    processed_thinking = thinking_parser.process_for_output(
                        parse_result.thinking_content,
                        parse_result.is_first_thinking_chunk,
                        parse_result.is_last_thinking_chunk,
                    )
                    if processed_thinking:
                        result.append(KiroEvent(
                            type="thinking",
                            thinking_content=processed_thinking,
                            is_first_thinking_chunk=parse_result.is_first_thinking_chunk,
                            is_last_thinking_chunk=parse_result.is_last_thinking_chunk,
                        ))
                
                # Regular content if any
                if parse_result.regular_content:
                    result.append(KiroEvent(type="content", content=parse_result.regular_content))
            else:
                # No thinking parser - pass through as-is
                result.append(KiroEvent(type="content", content=content))
        
        elif event["type"] == "usage":
            result.append(KiroEvent(type="usage", usage=event["data"]))
        
        elif event["type"] == "context_usage":
            result.append(KiroEvent(type="context_usage", context_usage_percentage=event["data"]))
    
    return result


# ==================================================================================================
# Full Response Collection
# ==================================================================================================

async def collect_stream_to_result(
    response: httpx.Response,
    first_token_timeout: float = FIRST_TOKEN_TIMEOUT,
    enable_thinking_parser: bool = True,
    stop_sequences: Optional[List[str]] = None,
) -> StreamResult:
    """
    Collects full response from Kiro stream.

    This function consumes the entire stream and returns a StreamResult
    with all accumulated data.

    Args:
        response: HTTP response with stream
        first_token_timeout: First token wait timeout
        enable_thinking_parser: Whether to enable thinking block parsing
        stop_sequences: Optional stop sequences, applied to regular text only.
                        On a match, text is cut before the sequence, the
                        rest of the stream is not read, and
                        result.stop_sequence is set. None disables matching.

    Returns:
        StreamResult with full content, thinking, tool calls, and usage
    """
    result = StreamResult()
    full_content_for_bracket_tools = ""
    matcher = create_stop_sequence_matcher(stop_sequences)
    events = apply_stop_sequences(
        parse_kiro_stream(response, first_token_timeout, enable_thinking_parser),
        matcher,
    )

    async with aclosing(events) as stream:
        async for event in stream:
            if event.type == "content" and event.content:
                result.content += event.content
                full_content_for_bracket_tools += event.content
            elif event.type == "thinking" and event.thinking_content:
                result.thinking_content += event.thinking_content
                full_content_for_bracket_tools += event.thinking_content
            elif event.type == "tool_use" and event.tool_use:
                result.tool_calls.append(event.tool_use)
            elif event.type == "usage" and event.usage:
                result.usage = event.usage
            elif event.type == "context_usage" and event.context_usage_percentage is not None:
                result.context_usage_percentage = event.context_usage_percentage

    if matcher is not None:
        result.stop_sequence = matcher.matched

    # Check for bracket-style tool calls in full content
    bracket_tool_calls = parse_bracket_tool_calls(full_content_for_bracket_tools)
    if bracket_tool_calls:
        result.tool_calls = deduplicate_tool_calls(result.tool_calls + bracket_tool_calls)
    
    return result


# ==================================================================================================
# Token Counting Utilities
# ==================================================================================================

def calculate_tokens_from_context_usage(
    context_usage_percentage: Optional[float],
    completion_tokens: int,
    model_cache: "ModelInfoCache",
    model: str
) -> Tuple[int, int, str, str]:
    """
    Calculate token counts from Kiro's context usage percentage.
    
    Args:
        context_usage_percentage: Context usage percentage from Kiro API
        completion_tokens: Number of completion tokens (counted via tiktoken)
        model_cache: Model cache for getting max input tokens
        model: Model name
    
    Returns:
        Tuple of (prompt_tokens, total_tokens, prompt_source, total_source)
    """
    if context_usage_percentage is not None and context_usage_percentage > 0:
        max_input_tokens = model_cache.get_max_input_tokens(model)
        total_tokens = int((context_usage_percentage / 100) * max_input_tokens)
        prompt_tokens = max(0, total_tokens - completion_tokens)
        return prompt_tokens, total_tokens, "subtraction", "API Kiro"
    
    # Fallback: no context usage data
    return 0, completion_tokens, "unknown", "tiktoken"


# ==================================================================================================
# First Token Retry Logic
# ==================================================================================================

def first_token_timeout_for_attempt(base_timeout: float, attempt: int) -> float:
    """
    Compute the first token timeout for a retry attempt.
    
    Grows linearly (base, 2*base, 3*base, ...) and never exceeds
    STREAMING_READ_TIMEOUT, the read timeout of the underlying HTTP client.
    
    Args:
        base_timeout: Configured first token timeout (seconds)
        attempt: Zero-based attempt number
    
    Returns:
        Timeout in seconds for this attempt
    """
    timeout = base_timeout * (max(attempt, 0) + 1)
    return min(timeout, max(base_timeout, STREAMING_READ_TIMEOUT))


async def stream_with_first_token_retry(
    make_request: Callable[[], Awaitable[httpx.Response]],
    stream_processor: Callable[[httpx.Response], AsyncGenerator[str, None]],
    initial_response: Optional[httpx.Response] = None,
    max_retries: int = FIRST_TOKEN_MAX_RETRIES,
    first_token_timeout: float = FIRST_TOKEN_TIMEOUT,
    on_http_error: Optional[Callable[[int, str], Exception]] = None,
    on_all_retries_failed: Optional[Callable[[int, float], Exception]] = None,
    timeout_aware_processor: bool = False,
) -> AsyncGenerator[str, None]:
    """
    Generic streaming with automatic retry on first token timeout.
    
    If model doesn't respond within the first token timeout,
    request is cancelled and a new one is made. Maximum max_retries attempts.
    
    The first token timeout grows with each attempt:
    first_token_timeout * (attempt + 1), capped at STREAMING_READ_TIMEOUT.
    A model that is slow (not stuck) gets more time instead of being cut off
    at the same deadline again, which reduces repeated upstream calls.
    Only processors created with timeout_aware_processor=True receive the
    per-attempt timeout; other processors keep their own fixed timeout.
    
    This is seamless for user - they just see a delay,
    but eventually get a response (or error after all attempts).
    
    Args:
        make_request: Function to create new HTTP request (returns httpx.Response)
        stream_processor: Function that processes response and yields SSE strings.
                         Must use parse_kiro_stream internally for timeout handling.
        initial_response: Optional pre-validated response to use on first attempt.
                         If provided, make_request is only called on retries.
                         This allows reusing an already-opened HTTP 200 response.
        max_retries: Maximum number of attempts
        first_token_timeout: First token wait timeout (seconds)
        on_http_error: Optional callback to create exception for HTTP errors.
                      Receives (status_code, error_text), returns Exception.
                      If None, raises generic Exception.
        on_all_retries_failed: Optional callback to create exception when all retries fail.
                              Receives (max_retries, timeout), returns Exception.
                              If None, raises generic Exception.
        timeout_aware_processor: If True, stream_processor is called as
                                 stream_processor(response, attempt_timeout) so the
                                 progressive per-attempt timeout is applied.
                                 If False, it is called as stream_processor(response).
    
    Yields:
        Strings in SSE format (format depends on stream_processor)
    
    Raises:
        Exception from on_http_error or on_all_retries_failed callbacks
    
    Example:
        >>> async def make_req():
        ...     return await http_client.request_with_retry("POST", url, payload, stream=True)
        >>> async def process(response):
        ...     async for chunk in stream_kiro_to_openai(response, ...):
        ...         yield chunk
        >>> # With initial response (reuse already-validated 200 response)
        >>> response = await make_req()
        >>> async for chunk in stream_with_first_token_retry(make_req, process, initial_response=response):
        ...     print(chunk)
    """
    last_error: Optional[Exception] = None
    
    for attempt in range(max_retries):
        response: Optional[httpx.Response] = None
        attempt_timeout = first_token_timeout_for_attempt(first_token_timeout, attempt)
        try:
            # Make request
            if attempt > 0:
                logger.warning(
                    f"Retry attempt {attempt + 1}/{max_retries} after first token timeout "
                    f"(first token timeout for this attempt: {attempt_timeout}s)"
                )
            
            # On first attempt, reuse initial_response if provided
            if attempt == 0 and initial_response is not None:
                response = initial_response
                logger.debug("Reusing initial response for first attempt")
            else:
                response = await make_request()
            
            if response.status_code != 200:
                # Error from API - close response and raise exception
                try:
                    error_content = await response.aread()
                    error_text = error_content.decode('utf-8', errors='replace')
                except Exception:
                    error_text = "Unknown error"
                
                try:
                    await response.aclose()
                except Exception:
                    pass
                
                logger.error(f"Error from Kiro API: {response.status_code} - {error_text}")
                
                if on_http_error:
                    raise on_http_error(response.status_code, error_text)
                else:
                    raise Exception(f"Upstream API error ({response.status_code}): {error_text}")
            
            # Try to stream with first token timeout
            if timeout_aware_processor:
                processor_stream = stream_processor(response, attempt_timeout)
            else:
                processor_stream = stream_processor(response)
            async with aclosing(processor_stream) as chunks:
                async for chunk in chunks:
                    yield chunk
            
            # Successfully completed - exit
            return
            
        except FirstTokenTimeoutError as e:
            last_error = e
            logger.warning(
                f"[FirstTokenTimeout] Attempt {attempt + 1}/{max_retries} failed - "
                f"model did not respond within {attempt_timeout if timeout_aware_processor else first_token_timeout}s"
            )
            
            # Close current response if open
            if response:
                try:
                    await response.aclose()
                except Exception:
                    pass
            
            # Continue to next attempt
            continue
            
        except Exception as e:
            # Other errors - no retry, propagate
            # Use positional argument to avoid loguru interpreting curly braces in error message as format placeholders
            # f-string with repr() doesn't work because loguru still sees {type} inside the string
            error_msg = str(e) if str(e) else "(empty message)"
            logger.error("Unexpected error during streaming: {}", error_msg, exc_info=True)
            if response:
                try:
                    await response.aclose()
                except Exception:
                    pass
            raise
    
    # All attempts exhausted - raise error
    logger.error(
        f"[FirstTokenTimeout] All {max_retries} attempts exhausted - "
        f"model never responded within {first_token_timeout}s per attempt"
    )
    
    if on_all_retries_failed:
        raise on_all_retries_failed(max_retries, first_token_timeout)
    else:
        raise Exception(
            f"Model did not respond within {first_token_timeout}s after {max_retries} attempts. "
            "Please try again."
        )