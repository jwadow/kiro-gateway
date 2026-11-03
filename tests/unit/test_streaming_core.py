
# -*- coding: utf-8 -*-

"""
Unit tests for streaming_core module.

Tests for:
- KiroEvent dataclass
- StreamResult dataclass
- FirstTokenTimeoutError exception
- parse_kiro_stream() function
- collect_stream_to_result() function
- calculate_tokens_from_context_usage() function
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import asdict

from kiro.streaming_core import (
    KiroEvent,
    StreamResult,
    FirstTokenTimeoutError,
    parse_kiro_stream,
    collect_stream_to_result,
    calculate_tokens_from_context_usage,
    stream_with_first_token_retry,
    _process_chunk,
    anthropic_error_type_for_status,
    normalize_stop_sequences,
    create_stop_sequence_matcher,
    StopSequenceMatcher,
    apply_stop_sequences,
    estimate_request_tokens_offloaded,
    first_token_timeout_for_attempt,
)


# ==================================================================================================
# Fixtures
# ==================================================================================================

@pytest.fixture
def mock_model_cache():
    """Mock for ModelInfoCache."""
    cache = MagicMock()
    cache.get_max_input_tokens.return_value = 200000
    return cache


@pytest.fixture
def mock_response():
    """Mock for httpx.Response."""
    response = AsyncMock()
    response.status_code = 200
    response.aclose = AsyncMock()
    return response


@pytest.fixture
def mock_parser():
    """Mock for AwsEventStreamParser."""
    parser = MagicMock()
    parser.feed.return_value = []
    parser.get_tool_calls.return_value = []
    return parser


# ==================================================================================================
# Tests for KiroEvent dataclass
# ==================================================================================================

class TestKiroEvent:
    """Tests for KiroEvent dataclass."""
    
    def test_creates_content_event(self):
        """
        What it does: Creates a content event with text.
        Goal: Verify KiroEvent can represent content events.
        """
        print("Action: Creating content event...")
        event = KiroEvent(type="content", content="Hello, world!")
        
        print(f"Comparing type: Expected 'content', Got '{event.type}'")
        assert event.type == "content"
        print(f"Comparing content: Expected 'Hello, world!', Got '{event.content}'")
        assert event.content == "Hello, world!"
        assert event.thinking_content is None
        assert event.tool_use is None
        print("✓ Content event created correctly")
    
    def test_creates_thinking_event(self):
        """
        What it does: Creates a thinking event with reasoning content.
        Goal: Verify KiroEvent can represent thinking events.
        """
        print("Action: Creating thinking event...")
        event = KiroEvent(
            type="thinking",
            thinking_content="Let me think...",
            is_first_thinking_chunk=True,
            is_last_thinking_chunk=False
        )
        
        print(f"Comparing type: Expected 'thinking', Got '{event.type}'")
        assert event.type == "thinking"
        print(f"Comparing thinking_content: Expected 'Let me think...', Got '{event.thinking_content}'")
        assert event.thinking_content == "Let me think..."
        assert event.is_first_thinking_chunk is True
        assert event.is_last_thinking_chunk is False
        print("✓ Thinking event created correctly")
    
    def test_creates_tool_use_event(self):
        """
        What it does: Creates a tool_use event with tool data.
        Goal: Verify KiroEvent can represent tool use events.
        """
        print("Action: Creating tool_use event...")
        tool_data = {
            "id": "call_123",
            "type": "function",
            "function": {"name": "get_weather", "arguments": '{"city": "Moscow"}'}
        }
        event = KiroEvent(type="tool_use", tool_use=tool_data)
        
        print(f"Comparing type: Expected 'tool_use', Got '{event.type}'")
        assert event.type == "tool_use"
        print(f"Comparing tool_use: Expected {tool_data}, Got {event.tool_use}")
        assert event.tool_use == tool_data
        print("✓ Tool use event created correctly")
    
    def test_creates_usage_event(self):
        """
        What it does: Creates a usage event with metering data.
        Goal: Verify KiroEvent can represent usage events.
        """
        print("Action: Creating usage event...")
        usage_data = {"credits": 0.001}
        event = KiroEvent(type="usage", usage=usage_data)
        
        print(f"Comparing type: Expected 'usage', Got '{event.type}'")
        assert event.type == "usage"
        print(f"Comparing usage: Expected {usage_data}, Got {event.usage}")
        assert event.usage == usage_data
        print("✓ Usage event created correctly")
    
    def test_creates_context_usage_event(self):
        """
        What it does: Creates a context_usage event with percentage.
        Goal: Verify KiroEvent can represent context usage events.
        """
        print("Action: Creating context_usage event...")
        event = KiroEvent(type="context_usage", context_usage_percentage=5.5)
        
        print(f"Comparing type: Expected 'context_usage', Got '{event.type}'")
        assert event.type == "context_usage"
        print(f"Comparing context_usage_percentage: Expected 5.5, Got {event.context_usage_percentage}")
        assert event.context_usage_percentage == 5.5
        print("✓ Context usage event created correctly")
    
    def test_default_values(self):
        """
        What it does: Verifies default values for optional fields.
        Goal: Ensure all optional fields default to None/False.
        """
        print("Action: Creating minimal event...")
        event = KiroEvent(type="content")
        
        print("Checking default values...")
        assert event.content is None
        assert event.thinking_content is None
        assert event.tool_use is None
        assert event.usage is None
        assert event.context_usage_percentage is None
        assert event.is_first_thinking_chunk is False
        assert event.is_last_thinking_chunk is False
        print("✓ All default values are correct")


# ==================================================================================================
# Tests for StreamResult dataclass
# ==================================================================================================

class TestStreamResult:
    """Tests for StreamResult dataclass."""
    
    def test_creates_empty_result(self):
        """
        What it does: Creates an empty StreamResult.
        Goal: Verify default values are correct.
        """
        print("Action: Creating empty StreamResult...")
        result = StreamResult()
        
        print("Checking default values...")
        assert result.content == ""
        assert result.thinking_content == ""
        assert result.tool_calls == []
        assert result.usage is None
        assert result.context_usage_percentage is None
        print("✓ Empty StreamResult created correctly")
    
    def test_creates_result_with_content(self):
        """
        What it does: Creates StreamResult with content.
        Goal: Verify content is stored correctly.
        """
        print("Action: Creating StreamResult with content...")
        result = StreamResult(content="Hello, world!")
        
        print(f"Comparing content: Expected 'Hello, world!', Got '{result.content}'")
        assert result.content == "Hello, world!"
        print("✓ StreamResult with content created correctly")
    
    def test_creates_result_with_tool_calls(self):
        """
        What it does: Creates StreamResult with tool calls.
        Goal: Verify tool calls are stored correctly.
        """
        print("Action: Creating StreamResult with tool calls...")
        tool_calls = [
            {"id": "call_1", "function": {"name": "func1"}},
            {"id": "call_2", "function": {"name": "func2"}}
        ]
        result = StreamResult(tool_calls=tool_calls)
        
        print(f"Comparing tool_calls count: Expected 2, Got {len(result.tool_calls)}")
        assert len(result.tool_calls) == 2
        assert result.tool_calls[0]["id"] == "call_1"
        print("✓ StreamResult with tool calls created correctly")
    
    def test_creates_result_with_usage(self):
        """
        What it does: Creates StreamResult with usage data.
        Goal: Verify usage is stored correctly.
        """
        print("Action: Creating StreamResult with usage...")
        usage = {"credits": 0.002}
        result = StreamResult(usage=usage)
        
        print(f"Comparing usage: Expected {usage}, Got {result.usage}")
        assert result.usage == usage
        print("✓ StreamResult with usage created correctly")
    
    def test_creates_full_result(self):
        """
        What it does: Creates StreamResult with all fields.
        Goal: Verify all fields work together.
        """
        print("Action: Creating full StreamResult...")
        result = StreamResult(
            content="Response text",
            thinking_content="Thinking...",
            tool_calls=[{"id": "call_1"}],
            usage={"credits": 0.001},
            context_usage_percentage=3.5
        )
        
        print("Checking all fields...")
        assert result.content == "Response text"
        assert result.thinking_content == "Thinking..."
        assert len(result.tool_calls) == 1
        assert result.usage == {"credits": 0.001}
        assert result.context_usage_percentage == 3.5
        print("✓ Full StreamResult created correctly")


# ==================================================================================================
# Tests for FirstTokenTimeoutError
# ==================================================================================================

class TestFirstTokenTimeoutError:
    """Tests for FirstTokenTimeoutError exception."""
    
    def test_creates_exception_with_message(self):
        """
        What it does: Creates exception with custom message.
        Goal: Verify exception message is stored correctly.
        """
        print("Action: Creating FirstTokenTimeoutError...")
        error = FirstTokenTimeoutError("No response within 30 seconds")
        
        print(f"Comparing message: Expected 'No response within 30 seconds', Got '{str(error)}'")
        assert str(error) == "No response within 30 seconds"
        print("✓ Exception created correctly")
    
    def test_exception_is_catchable(self):
        """
        What it does: Verifies exception can be caught.
        Goal: Ensure exception inherits from Exception.
        """
        print("Action: Raising and catching FirstTokenTimeoutError...")
        
        with pytest.raises(FirstTokenTimeoutError) as exc_info:
            raise FirstTokenTimeoutError("Timeout!")
        
        print(f"Caught exception: {exc_info.value}")
        assert "Timeout!" in str(exc_info.value)
        print("✓ Exception is catchable")
    
    def test_exception_inherits_from_exception(self):
        """
        What it does: Verifies inheritance chain.
        Goal: Ensure proper exception hierarchy.
        """
        print("Action: Checking inheritance...")
        error = FirstTokenTimeoutError("Test")
        
        assert isinstance(error, Exception)
        print("✓ FirstTokenTimeoutError inherits from Exception")


# ==================================================================================================
# Tests for parse_kiro_stream()
# ==================================================================================================

class TestParseKiroStream:
    """Tests for parse_kiro_stream() function."""
    
    @pytest.mark.asyncio
    async def test_parses_content_events(self, mock_response, mock_parser):
        """
        What it does: Parses content events from Kiro stream.
        Goal: Verify content events are yielded correctly.
        """
        print("Setup: Mock parser to return content events...")
        mock_parser.feed.return_value = [
            {"type": "content", "data": "Hello"},
            {"type": "content", "data": " World"}
        ]
        
        async def mock_aiter_bytes():
            yield b'chunk1'
        
        mock_response.aiter_bytes = mock_aiter_bytes
        
        print("Action: Parsing stream...")
        events = []
        
        with patch('kiro.streaming_core.AwsEventStreamParser', return_value=mock_parser):
            with patch('kiro.streaming_core.FAKE_REASONING_ENABLED', False):
                async for event in parse_kiro_stream(mock_response, first_token_timeout=30):
                    events.append(event)
        
        print(f"Received {len(events)} events")
        content_events = [e for e in events if e.type == "content"]
        print(f"Content events: {len(content_events)}")
        
        assert len(content_events) == 2
        assert content_events[0].content == "Hello"
        assert content_events[1].content == " World"
        print("✓ Content events parsed correctly")
    
    @pytest.mark.asyncio
    async def test_parses_usage_events(self, mock_response, mock_parser):
        """
        What it does: Parses usage events from Kiro stream.
        Goal: Verify usage events are yielded correctly.
        """
        print("Setup: Mock parser to return usage event...")
        mock_parser.feed.return_value = [
            {"type": "usage", "data": {"credits": 0.001}}
        ]
        
        async def mock_aiter_bytes():
            yield b'chunk1'
        
        mock_response.aiter_bytes = mock_aiter_bytes
        
        print("Action: Parsing stream...")
        events = []
        
        with patch('kiro.streaming_core.AwsEventStreamParser', return_value=mock_parser):
            with patch('kiro.streaming_core.FAKE_REASONING_ENABLED', False):
                async for event in parse_kiro_stream(mock_response, first_token_timeout=30):
                    events.append(event)
        
        print(f"Received {len(events)} events")
        usage_events = [e for e in events if e.type == "usage"]
        
        assert len(usage_events) == 1
        assert usage_events[0].usage == {"credits": 0.001}
        print("✓ Usage events parsed correctly")
    
    @pytest.mark.asyncio
    async def test_parses_context_usage_events(self, mock_response, mock_parser):
        """
        What it does: Parses context_usage events from Kiro stream.
        Goal: Verify context usage percentage is yielded correctly.
        """
        print("Setup: Mock parser to return context_usage event...")
        mock_parser.feed.return_value = [
            {"type": "context_usage", "data": 5.5}
        ]
        
        async def mock_aiter_bytes():
            yield b'chunk1'
        
        mock_response.aiter_bytes = mock_aiter_bytes
        
        print("Action: Parsing stream...")
        events = []
        
        with patch('kiro.streaming_core.AwsEventStreamParser', return_value=mock_parser):
            with patch('kiro.streaming_core.FAKE_REASONING_ENABLED', False):
                async for event in parse_kiro_stream(mock_response, first_token_timeout=30):
                    events.append(event)
        
        print(f"Received {len(events)} events")
        context_events = [e for e in events if e.type == "context_usage"]
        
        assert len(context_events) == 1
        assert context_events[0].context_usage_percentage == 5.5
        print("✓ Context usage events parsed correctly")
    
    @pytest.mark.asyncio
    async def test_yields_tool_calls_at_end(self, mock_response, mock_parser):
        """
        What it does: Yields tool calls collected during parsing.
        Goal: Verify tool calls are yielded as events.
        """
        print("Setup: Mock parser with tool calls...")
        mock_parser.feed.return_value = [{"type": "content", "data": "text"}]
        mock_parser.get_tool_calls.return_value = [
            {"id": "call_1", "function": {"name": "func1", "arguments": "{}"}}
        ]
        
        async def mock_aiter_bytes():
            yield b'chunk1'
        
        mock_response.aiter_bytes = mock_aiter_bytes
        
        print("Action: Parsing stream...")
        events = []
        
        with patch('kiro.streaming_core.AwsEventStreamParser', return_value=mock_parser):
            with patch('kiro.streaming_core.FAKE_REASONING_ENABLED', False):
                async for event in parse_kiro_stream(mock_response, first_token_timeout=30):
                    events.append(event)
        
        print(f"Received {len(events)} events")
        tool_events = [e for e in events if e.type == "tool_use"]
        
        assert len(tool_events) == 1
        assert tool_events[0].tool_use["id"] == "call_1"
        print("✓ Tool calls yielded correctly")
    
    @pytest.mark.asyncio
    async def test_raises_timeout_on_first_token(self, mock_response):
        """
        What it does: Raises FirstTokenTimeoutError on timeout.
        Goal: Verify timeout handling for first token.
        """
        print("Setup: Mock response that times out...")
        
        async def mock_aiter_bytes():
            yield b'chunk'
        
        mock_response.aiter_bytes = mock_aiter_bytes
        
        async def mock_wait_for_timeout(*args, **kwargs):
            raise asyncio.TimeoutError()
        
        print("Action: Parsing stream with timeout...")
        
        with patch('kiro.streaming_core.asyncio.wait_for', side_effect=mock_wait_for_timeout):
            with pytest.raises(FirstTokenTimeoutError) as exc_info:
                async for event in parse_kiro_stream(mock_response, first_token_timeout=30):
                    pass
        
        print(f"Caught exception: {exc_info.value}")
        assert "30" in str(exc_info.value)
        print("✓ FirstTokenTimeoutError raised on timeout")
    
    @pytest.mark.asyncio
    async def test_handles_empty_response(self, mock_response):
        """
        What it does: Handles empty response gracefully.
        Goal: Verify no events yielded for empty response.
        """
        print("Setup: Mock empty response...")
        
        async def mock_aiter_bytes():
            return
            yield  # Make it a generator
        
        mock_response.aiter_bytes = mock_aiter_bytes
        
        # Mock wait_for to raise StopAsyncIteration (empty response)
        async def mock_wait_for_empty(*args, **kwargs):
            raise StopAsyncIteration()
        
        print("Action: Parsing empty stream...")
        events = []
        
        with patch('kiro.streaming_core.asyncio.wait_for', side_effect=mock_wait_for_empty):
            async for event in parse_kiro_stream(mock_response, first_token_timeout=30):
                events.append(event)
        
        print(f"Received {len(events)} events")
        assert len(events) == 0
        print("✓ Empty response handled correctly")
    
    @pytest.mark.asyncio
    async def test_handles_generator_exit(self, mock_response, mock_parser):
        """
        What it does: Handles GeneratorExit gracefully.
        Goal: Verify client disconnect is handled.
        """
        print("Setup: Mock response that raises GeneratorExit...")
        
        async def mock_aiter_bytes():
            yield b'chunk1'
            raise GeneratorExit()
        
        mock_response.aiter_bytes = mock_aiter_bytes
        mock_parser.feed.return_value = [{"type": "content", "data": "Hello"}]
        
        print("Action: Parsing stream with GeneratorExit...")
        events = []
        generator_exit_raised = False
        
        with patch('kiro.streaming_core.AwsEventStreamParser', return_value=mock_parser):
            with patch('kiro.streaming_core.FAKE_REASONING_ENABLED', False):
                try:
                    async for event in parse_kiro_stream(mock_response, first_token_timeout=30):
                        events.append(event)
                except GeneratorExit:
                    generator_exit_raised = True
        
        print(f"GeneratorExit raised: {generator_exit_raised}")
        assert generator_exit_raised
        print("✓ GeneratorExit handled correctly")


# ==================================================================================================
# Tests for _process_chunk()
# ==================================================================================================

class TestProcessChunk:
    """Tests for _process_chunk() helper function."""
    
    @pytest.mark.asyncio
    async def test_processes_content_event(self, mock_parser):
        """
        What it does: Processes content event from chunk.
        Goal: Verify content is converted to KiroEvent.
        """
        print("Setup: Mock parser with content event...")
        mock_parser.feed.return_value = [{"type": "content", "data": "Hello"}]
        
        print("Action: Processing chunk...")
        events = []
        for event in _process_chunk(mock_parser, b'chunk', None):
            events.append(event)
        
        print(f"Received {len(events)} events")
        assert len(events) == 1
        assert events[0].type == "content"
        assert events[0].content == "Hello"
        print("✓ Content event processed correctly")
    
    @pytest.mark.asyncio
    async def test_processes_usage_event(self, mock_parser):
        """
        What it does: Processes usage event from chunk.
        Goal: Verify usage is converted to KiroEvent.
        """
        print("Setup: Mock parser with usage event...")
        mock_parser.feed.return_value = [{"type": "usage", "data": {"credits": 0.001}}]
        
        print("Action: Processing chunk...")
        events = []
        for event in _process_chunk(mock_parser, b'chunk', None):
            events.append(event)
        
        print(f"Received {len(events)} events")
        assert len(events) == 1
        assert events[0].type == "usage"
        assert events[0].usage == {"credits": 0.001}
        print("✓ Usage event processed correctly")
    
    @pytest.mark.asyncio
    async def test_processes_context_usage_event(self, mock_parser):
        """
        What it does: Processes context_usage event from chunk.
        Goal: Verify context usage is converted to KiroEvent.
        """
        print("Setup: Mock parser with context_usage event...")
        mock_parser.feed.return_value = [{"type": "context_usage", "data": 7.5}]
        
        print("Action: Processing chunk...")
        events = []
        for event in _process_chunk(mock_parser, b'chunk', None):
            events.append(event)
        
        print(f"Received {len(events)} events")
        assert len(events) == 1
        assert events[0].type == "context_usage"
        assert events[0].context_usage_percentage == 7.5
        print("✓ Context usage event processed correctly")
    
    @pytest.mark.asyncio
    async def test_processes_multiple_events(self, mock_parser):
        """
        What it does: Processes multiple events from single chunk.
        Goal: Verify all events are yielded.
        """
        print("Setup: Mock parser with multiple events...")
        mock_parser.feed.return_value = [
            {"type": "content", "data": "Hello"},
            {"type": "content", "data": " World"},
            {"type": "usage", "data": {"credits": 0.001}}
        ]
        
        print("Action: Processing chunk...")
        events = []
        for event in _process_chunk(mock_parser, b'chunk', None):
            events.append(event)
        
        print(f"Received {len(events)} events")
        assert len(events) == 3
        assert events[0].type == "content"
        assert events[1].type == "content"
        assert events[2].type == "usage"
        print("✓ Multiple events processed correctly")
    
    @pytest.mark.asyncio
    async def test_processes_with_thinking_parser(self, mock_parser):
        """
        What it does: Processes content through thinking parser.
        Goal: Verify thinking parser integration.
        """
        print("Setup: Mock parser and thinking parser...")
        mock_parser.feed.return_value = [{"type": "content", "data": "Hello"}]
        
        mock_thinking_parser = MagicMock()
        mock_thinking_parser.feed.return_value = MagicMock(
            thinking_content=None,
            regular_content="Hello",
            is_first_thinking_chunk=False,
            is_last_thinking_chunk=False
        )
        
        print("Action: Processing chunk with thinking parser...")
        events = []
        for event in _process_chunk(mock_parser, b'chunk', mock_thinking_parser):
            events.append(event)
        
        print(f"Received {len(events)} events")
        assert len(events) == 1
        assert events[0].type == "content"
        assert events[0].content == "Hello"
        print("✓ Thinking parser integration works correctly")
    
    @pytest.mark.asyncio
    async def test_yields_thinking_content(self, mock_parser):
        """
        What it does: Yields thinking content from thinking parser.
        Goal: Verify thinking events are created.
        """
        print("Setup: Mock parser and thinking parser with thinking content...")
        mock_parser.feed.return_value = [{"type": "content", "data": "<thinking>Let me think</thinking>"}]
        
        mock_thinking_parser = MagicMock()
        mock_thinking_parser.feed.return_value = MagicMock(
            thinking_content="Let me think",
            regular_content=None,
            is_first_thinking_chunk=True,
            is_last_thinking_chunk=True
        )
        mock_thinking_parser.process_for_output.return_value = "Let me think"
        
        print("Action: Processing chunk with thinking content...")
        events = []
        for event in _process_chunk(mock_parser, b'chunk', mock_thinking_parser):
            events.append(event)
        
        print(f"Received {len(events)} events")
        thinking_events = [e for e in events if e.type == "thinking"]
        assert len(thinking_events) == 1
        assert thinking_events[0].thinking_content == "Let me think"
        print("✓ Thinking content yielded correctly")


# ==================================================================================================
# Tests for collect_stream_to_result()
# ==================================================================================================

class TestCollectStreamToResult:
    """Tests for collect_stream_to_result() function."""
    
    @pytest.mark.asyncio
    async def test_collects_content(self, mock_response, mock_parser):
        """
        What it does: Collects content from stream.
        Goal: Verify content is accumulated correctly.
        """
        print("Setup: Mock parser with content events...")
        mock_parser.feed.return_value = [
            {"type": "content", "data": "Hello"},
            {"type": "content", "data": " World"}
        ]
        mock_parser.get_tool_calls.return_value = []
        
        async def mock_aiter_bytes():
            yield b'chunk1'
        
        mock_response.aiter_bytes = mock_aiter_bytes
        
        print("Action: Collecting stream...")
        
        with patch('kiro.streaming_core.AwsEventStreamParser', return_value=mock_parser):
            with patch('kiro.streaming_core.FAKE_REASONING_ENABLED', False):
                with patch('kiro.streaming_core.parse_bracket_tool_calls', return_value=[]):
                    result = await collect_stream_to_result(mock_response, first_token_timeout=30)
        
        print(f"Collected content: '{result.content}'")
        assert result.content == "Hello World"
        print("✓ Content collected correctly")
    
    @pytest.mark.asyncio
    async def test_collects_tool_calls(self, mock_response, mock_parser):
        """
        What it does: Collects tool calls from stream.
        Goal: Verify tool calls are accumulated correctly.
        """
        print("Setup: Mock parser with tool calls...")
        mock_parser.feed.return_value = [{"type": "content", "data": "text"}]
        mock_parser.get_tool_calls.return_value = [
            {"id": "call_1", "function": {"name": "func1", "arguments": "{}"}}
        ]
        
        async def mock_aiter_bytes():
            yield b'chunk1'
        
        mock_response.aiter_bytes = mock_aiter_bytes
        
        print("Action: Collecting stream...")
        
        with patch('kiro.streaming_core.AwsEventStreamParser', return_value=mock_parser):
            with patch('kiro.streaming_core.FAKE_REASONING_ENABLED', False):
                with patch('kiro.streaming_core.parse_bracket_tool_calls', return_value=[]):
                    result = await collect_stream_to_result(mock_response, first_token_timeout=30)
        
        print(f"Collected tool calls: {len(result.tool_calls)}")
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["id"] == "call_1"
        print("✓ Tool calls collected correctly")
    
    @pytest.mark.asyncio
    async def test_collects_usage(self, mock_response, mock_parser):
        """
        What it does: Collects usage from stream.
        Goal: Verify usage is stored correctly.
        """
        print("Setup: Mock parser with usage event...")
        mock_parser.feed.return_value = [
            {"type": "content", "data": "text"},
            {"type": "usage", "data": {"credits": 0.002}}
        ]
        mock_parser.get_tool_calls.return_value = []
        
        async def mock_aiter_bytes():
            yield b'chunk1'
        
        mock_response.aiter_bytes = mock_aiter_bytes
        
        print("Action: Collecting stream...")
        
        with patch('kiro.streaming_core.AwsEventStreamParser', return_value=mock_parser):
            with patch('kiro.streaming_core.FAKE_REASONING_ENABLED', False):
                with patch('kiro.streaming_core.parse_bracket_tool_calls', return_value=[]):
                    result = await collect_stream_to_result(mock_response, first_token_timeout=30)
        
        print(f"Collected usage: {result.usage}")
        assert result.usage == {"credits": 0.002}
        print("✓ Usage collected correctly")
    
    @pytest.mark.asyncio
    async def test_collects_context_usage_percentage(self, mock_response, mock_parser):
        """
        What it does: Collects context usage percentage from stream.
        Goal: Verify context usage is stored correctly.
        """
        print("Setup: Mock parser with context_usage event...")
        mock_parser.feed.return_value = [
            {"type": "content", "data": "text"},
            {"type": "context_usage", "data": 8.5}
        ]
        mock_parser.get_tool_calls.return_value = []
        
        async def mock_aiter_bytes():
            yield b'chunk1'
        
        mock_response.aiter_bytes = mock_aiter_bytes
        
        print("Action: Collecting stream...")
        
        with patch('kiro.streaming_core.AwsEventStreamParser', return_value=mock_parser):
            with patch('kiro.streaming_core.FAKE_REASONING_ENABLED', False):
                with patch('kiro.streaming_core.parse_bracket_tool_calls', return_value=[]):
                    result = await collect_stream_to_result(mock_response, first_token_timeout=30)
        
        print(f"Collected context_usage_percentage: {result.context_usage_percentage}")
        assert result.context_usage_percentage == 8.5
        print("✓ Context usage percentage collected correctly")
    
    @pytest.mark.asyncio
    async def test_collects_thinking_content(self, mock_response, mock_parser):
        """
        What it does: Collects thinking content from stream.
        Goal: Verify thinking content is accumulated correctly.
        """
        print("Setup: Mock parser with thinking content...")
        # We need to mock the thinking parser behavior
        mock_parser.feed.return_value = [{"type": "content", "data": "thinking text"}]
        mock_parser.get_tool_calls.return_value = []
        
        async def mock_aiter_bytes():
            yield b'chunk1'
        
        mock_response.aiter_bytes = mock_aiter_bytes
        
        # Create mock events that include thinking
        mock_events = [
            KiroEvent(type="thinking", thinking_content="Let me think..."),
            KiroEvent(type="content", content="Here is my answer")
        ]
        
        async def mock_parse_kiro_stream(*args, **kwargs):
            for event in mock_events:
                yield event
        
        print("Action: Collecting stream with thinking...")
        
        with patch('kiro.streaming_core.parse_kiro_stream', mock_parse_kiro_stream):
            with patch('kiro.streaming_core.parse_bracket_tool_calls', return_value=[]):
                result = await collect_stream_to_result(mock_response, first_token_timeout=30)
        
        print(f"Collected thinking_content: '{result.thinking_content}'")
        print(f"Collected content: '{result.content}'")
        assert result.thinking_content == "Let me think..."
        assert result.content == "Here is my answer"
        print("✓ Thinking content collected correctly")
    
    @pytest.mark.asyncio
    async def test_deduplicates_bracket_tool_calls(self, mock_response, mock_parser):
        """
        What it does: Deduplicates bracket-style tool calls.
        Goal: Verify duplicate tool calls are removed.
        """
        print("Setup: Mock parser with tool calls and bracket tool calls...")
        mock_parser.feed.return_value = [{"type": "content", "data": "text"}]
        mock_parser.get_tool_calls.return_value = [
            {"id": "call_1", "function": {"name": "func1", "arguments": "{}"}}
        ]
        
        bracket_tool_calls = [
            {"id": "call_1", "function": {"name": "func1", "arguments": "{}"}},  # Duplicate
            {"id": "call_2", "function": {"name": "func2", "arguments": "{}"}}   # New
        ]
        
        async def mock_aiter_bytes():
            yield b'chunk1'
        
        mock_response.aiter_bytes = mock_aiter_bytes
        
        print("Action: Collecting stream with duplicates...")
        
        with patch('kiro.streaming_core.AwsEventStreamParser', return_value=mock_parser):
            with patch('kiro.streaming_core.FAKE_REASONING_ENABLED', False):
                with patch('kiro.streaming_core.parse_bracket_tool_calls', return_value=bracket_tool_calls):
                    with patch('kiro.streaming_core.deduplicate_tool_calls') as mock_dedup:
                        mock_dedup.return_value = [
                            {"id": "call_1", "function": {"name": "func1", "arguments": "{}"}},
                            {"id": "call_2", "function": {"name": "func2", "arguments": "{}"}}
                        ]
                        result = await collect_stream_to_result(mock_response, first_token_timeout=30)
        
        print(f"Collected tool calls: {len(result.tool_calls)}")
        assert len(result.tool_calls) == 2
        print("✓ Tool calls deduplicated correctly")


# ==================================================================================================
# Tests for calculate_tokens_from_context_usage()
# ==================================================================================================

class TestCalculateTokensFromContextUsage:
    """Tests for calculate_tokens_from_context_usage() function."""
    
    def test_calculates_tokens_from_percentage(self, mock_model_cache):
        """
        What it does: Calculates tokens from context usage percentage.
        Goal: Verify token calculation is correct.
        """
        print("Setup: Context usage 10% with 200000 max tokens...")
        context_usage_percentage = 10.0
        completion_tokens = 100
        
        print("Action: Calculating tokens...")
        prompt_tokens, total_tokens, prompt_source, total_source = calculate_tokens_from_context_usage(
            context_usage_percentage, completion_tokens, mock_model_cache, "claude-sonnet-4"
        )
        
        # 10% of 200000 = 20000 total tokens
        # prompt_tokens = 20000 - 100 = 19900
        print(f"Comparing total_tokens: Expected 20000, Got {total_tokens}")
        assert total_tokens == 20000
        print(f"Comparing prompt_tokens: Expected 19900, Got {prompt_tokens}")
        assert prompt_tokens == 19900
        assert prompt_source == "subtraction"
        assert total_source == "API Kiro"
        print("✓ Tokens calculated correctly")
    
    def test_handles_zero_percentage(self, mock_model_cache):
        """
        What it does: Handles zero context usage percentage.
        Goal: Verify fallback behavior for zero percentage.
        """
        print("Setup: Context usage 0%...")
        context_usage_percentage = 0.0
        completion_tokens = 100
        
        print("Action: Calculating tokens...")
        prompt_tokens, total_tokens, prompt_source, total_source = calculate_tokens_from_context_usage(
            context_usage_percentage, completion_tokens, mock_model_cache, "claude-sonnet-4"
        )
        
        print(f"Comparing prompt_tokens: Expected 0, Got {prompt_tokens}")
        assert prompt_tokens == 0
        print(f"Comparing total_tokens: Expected 100, Got {total_tokens}")
        assert total_tokens == 100
        assert prompt_source == "unknown"
        assert total_source == "tiktoken"
        print("✓ Zero percentage handled correctly")
    
    def test_handles_none_percentage(self, mock_model_cache):
        """
        What it does: Handles None context usage percentage.
        Goal: Verify fallback behavior for None percentage.
        """
        print("Setup: Context usage None...")
        context_usage_percentage = None
        completion_tokens = 100
        
        print("Action: Calculating tokens...")
        prompt_tokens, total_tokens, prompt_source, total_source = calculate_tokens_from_context_usage(
            context_usage_percentage, completion_tokens, mock_model_cache, "claude-sonnet-4"
        )
        
        print(f"Comparing prompt_tokens: Expected 0, Got {prompt_tokens}")
        assert prompt_tokens == 0
        print(f"Comparing total_tokens: Expected 100, Got {total_tokens}")
        assert total_tokens == 100
        assert prompt_source == "unknown"
        assert total_source == "tiktoken"
        print("✓ None percentage handled correctly")
    
    def test_prevents_negative_prompt_tokens(self, mock_model_cache):
        """
        What it does: Prevents negative prompt tokens.
        Goal: Verify prompt_tokens is never negative.
        """
        print("Setup: Very small context usage with large completion...")
        context_usage_percentage = 0.01  # 0.01% of 200000 = 20 total tokens
        completion_tokens = 100  # More than total!
        
        print("Action: Calculating tokens...")
        prompt_tokens, total_tokens, prompt_source, total_source = calculate_tokens_from_context_usage(
            context_usage_percentage, completion_tokens, mock_model_cache, "claude-sonnet-4"
        )
        
        print(f"Comparing prompt_tokens: Expected >= 0, Got {prompt_tokens}")
        assert prompt_tokens >= 0
        print("✓ Negative prompt tokens prevented")
    
    def test_uses_model_specific_max_tokens(self, mock_model_cache):
        """
        What it does: Uses model-specific max input tokens.
        Goal: Verify model cache is queried correctly.
        """
        print("Setup: Different max tokens for model...")
        mock_model_cache.get_max_input_tokens.return_value = 100000  # Different from default
        context_usage_percentage = 10.0
        completion_tokens = 100
        
        print("Action: Calculating tokens...")
        prompt_tokens, total_tokens, prompt_source, total_source = calculate_tokens_from_context_usage(
            context_usage_percentage, completion_tokens, mock_model_cache, "claude-haiku-3"
        )
        
        # 10% of 100000 = 10000 total tokens
        print(f"Comparing total_tokens: Expected 10000, Got {total_tokens}")
        assert total_tokens == 10000
        
        # Verify model cache was called with correct model
        mock_model_cache.get_max_input_tokens.assert_called_with("claude-haiku-3")
        print("✓ Model-specific max tokens used correctly")
    
    def test_small_percentage_calculation(self, mock_model_cache):
        """
        What it does: Calculates tokens for small percentage.
        Goal: Verify precision for small percentages.
        """
        print("Setup: Context usage 0.5%...")
        context_usage_percentage = 0.5
        completion_tokens = 50
        
        print("Action: Calculating tokens...")
        prompt_tokens, total_tokens, prompt_source, total_source = calculate_tokens_from_context_usage(
            context_usage_percentage, completion_tokens, mock_model_cache, "claude-sonnet-4"
        )
        
        # 0.5% of 200000 = 1000 total tokens
        # prompt_tokens = 1000 - 50 = 950
        print(f"Comparing total_tokens: Expected 1000, Got {total_tokens}")
        assert total_tokens == 1000
        print(f"Comparing prompt_tokens: Expected 950, Got {prompt_tokens}")
        assert prompt_tokens == 950
        print("✓ Small percentage calculated correctly")
    
    def test_large_percentage_calculation(self, mock_model_cache):
        """
        What it does: Calculates tokens for large percentage.
        Goal: Verify calculation for high context usage.
        """
        print("Setup: Context usage 95%...")
        context_usage_percentage = 95.0
        completion_tokens = 1000
        
        print("Action: Calculating tokens...")
        prompt_tokens, total_tokens, prompt_source, total_source = calculate_tokens_from_context_usage(
            context_usage_percentage, completion_tokens, mock_model_cache, "claude-sonnet-4"
        )
        
        # 95% of 200000 = 190000 total tokens
        # prompt_tokens = 190000 - 1000 = 189000
        print(f"Comparing total_tokens: Expected 190000, Got {total_tokens}")
        assert total_tokens == 190000
        print(f"Comparing prompt_tokens: Expected 189000, Got {prompt_tokens}")
        assert prompt_tokens == 189000
        print("✓ Large percentage calculated correctly")


# ==================================================================================================
# Tests for thinking parser integration
# ==================================================================================================

class TestThinkingParserIntegration:
    """Tests for thinking parser integration in streaming."""
    
    @pytest.mark.asyncio
    async def test_thinking_parser_enabled_when_fake_reasoning_on(self, mock_response, mock_parser):
        """
        What it does: Enables thinking parser when FAKE_REASONING_ENABLED is True.
        Goal: Verify thinking parser is created.
        """
        print("Setup: Enable fake reasoning...")
        mock_parser.feed.return_value = [{"type": "content", "data": "Hello"}]
        mock_parser.get_tool_calls.return_value = []
        
        async def mock_aiter_bytes():
            yield b'chunk1'
        
        mock_response.aiter_bytes = mock_aiter_bytes
        
        print("Action: Parsing stream with fake reasoning enabled...")
        events = []
        
        with patch('kiro.streaming_core.AwsEventStreamParser', return_value=mock_parser):
            with patch('kiro.streaming_core.FAKE_REASONING_ENABLED', True):
                with patch('kiro.streaming_core.ThinkingParser') as mock_thinking_parser_class:
                    mock_thinking_parser = MagicMock()
                    mock_thinking_parser.feed.return_value = MagicMock(
                        thinking_content=None,
                        regular_content="Hello",
                        is_first_thinking_chunk=False,
                        is_last_thinking_chunk=False
                    )
                    mock_thinking_parser.finalize.return_value = MagicMock(
                        thinking_content=None,
                        regular_content=None,
                        is_first_thinking_chunk=False,
                        is_last_thinking_chunk=False
                    )
                    mock_thinking_parser.found_thinking_block = False
                    mock_thinking_parser_class.return_value = mock_thinking_parser
                    
                    async for event in parse_kiro_stream(mock_response, first_token_timeout=30):
                        events.append(event)
                    
                    # Verify ThinkingParser was instantiated
                    mock_thinking_parser_class.assert_called_once()
        
        print("✓ Thinking parser enabled when fake reasoning is on")
    
    @pytest.mark.asyncio
    async def test_thinking_parser_disabled_when_fake_reasoning_off(self, mock_response, mock_parser):
        """
        What it does: Disables thinking parser when FAKE_REASONING_ENABLED is False.
        Goal: Verify thinking parser is not created.
        """
        print("Setup: Disable fake reasoning...")
        mock_parser.feed.return_value = [{"type": "content", "data": "Hello"}]
        mock_parser.get_tool_calls.return_value = []
        
        async def mock_aiter_bytes():
            yield b'chunk1'
        
        mock_response.aiter_bytes = mock_aiter_bytes
        
        print("Action: Parsing stream with fake reasoning disabled...")
        events = []
        
        with patch('kiro.streaming_core.AwsEventStreamParser', return_value=mock_parser):
            with patch('kiro.streaming_core.FAKE_REASONING_ENABLED', False):
                with patch('kiro.streaming_core.ThinkingParser') as mock_thinking_parser_class:
                    async for event in parse_kiro_stream(mock_response, first_token_timeout=30):
                        events.append(event)
                    
                    # Verify ThinkingParser was NOT instantiated
                    mock_thinking_parser_class.assert_not_called()
        
        print("✓ Thinking parser disabled when fake reasoning is off")
    
    @pytest.mark.asyncio
    async def test_thinking_parser_can_be_disabled_via_parameter(self, mock_response, mock_parser):
        """
        What it does: Disables thinking parser via enable_thinking_parser parameter.
        Goal: Verify parameter overrides config.
        """
        print("Setup: Enable fake reasoning but disable via parameter...")
        mock_parser.feed.return_value = [{"type": "content", "data": "Hello"}]
        mock_parser.get_tool_calls.return_value = []
        
        async def mock_aiter_bytes():
            yield b'chunk1'
        
        mock_response.aiter_bytes = mock_aiter_bytes
        
        print("Action: Parsing stream with thinking parser disabled via parameter...")
        events = []
        
        with patch('kiro.streaming_core.AwsEventStreamParser', return_value=mock_parser):
            with patch('kiro.streaming_core.FAKE_REASONING_ENABLED', True):
                with patch('kiro.streaming_core.ThinkingParser') as mock_thinking_parser_class:
                    async for event in parse_kiro_stream(
                        mock_response,
                        first_token_timeout=30,
                        enable_thinking_parser=False
                    ):
                        events.append(event)
                    
                    # Verify ThinkingParser was NOT instantiated
                    mock_thinking_parser_class.assert_not_called()
        
        print("✓ Thinking parser disabled via parameter")


# ==================================================================================================
# Tests for error handling
# ==================================================================================================

class TestStreamingCoreErrorHandling:
    """Tests for error handling in streaming_core."""
    
    @pytest.mark.asyncio
    async def test_propagates_first_token_timeout_error(self, mock_response):
        """
        What it does: Propagates FirstTokenTimeoutError.
        Goal: Verify timeout error is not caught internally.
        """
        print("Setup: Mock response that times out...")
        
        async def mock_aiter_bytes():
            yield b'chunk'
        
        mock_response.aiter_bytes = mock_aiter_bytes
        
        async def mock_wait_for_timeout(*args, **kwargs):
            raise asyncio.TimeoutError()
        
        print("Action: Parsing stream with timeout...")
        
        with patch('kiro.streaming_core.asyncio.wait_for', side_effect=mock_wait_for_timeout):
            with pytest.raises(FirstTokenTimeoutError):
                async for event in parse_kiro_stream(mock_response, first_token_timeout=30):
                    pass
        
        print("✓ FirstTokenTimeoutError propagated correctly")
    
    @pytest.mark.asyncio
    async def test_propagates_generator_exit(self, mock_response, mock_parser):
        """
        What it does: Propagates GeneratorExit.
        Goal: Verify client disconnect is handled.
        """
        print("Setup: Mock response that raises GeneratorExit...")
        
        async def mock_aiter_bytes():
            yield b'chunk1'
            raise GeneratorExit()
        
        mock_response.aiter_bytes = mock_aiter_bytes
        mock_parser.feed.return_value = [{"type": "content", "data": "Hello"}]
        
        print("Action: Parsing stream with GeneratorExit...")
        
        with patch('kiro.streaming_core.AwsEventStreamParser', return_value=mock_parser):
            with patch('kiro.streaming_core.FAKE_REASONING_ENABLED', False):
                with pytest.raises(GeneratorExit):
                    async for event in parse_kiro_stream(mock_response, first_token_timeout=30):
                        pass
        
        print("✓ GeneratorExit propagated correctly")
    
    @pytest.mark.asyncio
    async def test_propagates_other_exceptions(self, mock_response, mock_parser):
        """
        What it does: Propagates other exceptions.
        Goal: Verify errors are not swallowed.
        """
        print("Setup: Mock response that raises RuntimeError...")
        
        async def mock_aiter_bytes():
            yield b'chunk1'
            raise RuntimeError("Test error")
        
        mock_response.aiter_bytes = mock_aiter_bytes
        mock_parser.feed.return_value = [{"type": "content", "data": "Hello"}]
        
        print("Action: Parsing stream with RuntimeError...")
        
        with patch('kiro.streaming_core.AwsEventStreamParser', return_value=mock_parser):
            with patch('kiro.streaming_core.FAKE_REASONING_ENABLED', False):
                with pytest.raises(RuntimeError) as exc_info:
                    async for event in parse_kiro_stream(mock_response, first_token_timeout=30):
                        pass
        
        print(f"Caught exception: {exc_info.value}")
        assert "Test error" in str(exc_info.value)
        print("✓ RuntimeError propagated correctly")


# ==================================================================================================
# Tests for stream_with_first_token_retry()
# ==================================================================================================

class TestStreamWithFirstTokenRetryCore:
    """
    Tests for stream_with_first_token_retry() generic function.
    
    This function provides automatic retry logic on first token timeout.
    It is used by both OpenAI and Anthropic streaming implementations.
    """
    
    @pytest.mark.asyncio
    async def test_yields_chunks_on_success(self):
        """
        What it does: Yields chunks on successful streaming.
        Goal: Verify normal operation without retries.
        """
        print("Setup: Mock successful request...")
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.aclose = AsyncMock()
        
        async def mock_make_request():
            return mock_response
        
        async def mock_stream_processor(response):
            yield "chunk1"
            yield "chunk2"
            yield "chunk3"
        
        print("Action: Streaming with retry wrapper...")
        chunks = []
        
        async for chunk in stream_with_first_token_retry(
            make_request=mock_make_request,
            stream_processor=mock_stream_processor,
            max_retries=3,
            first_token_timeout=30
        ):
            chunks.append(chunk)
        
        print(f"Received {len(chunks)} chunks")
        assert len(chunks) == 3
        assert chunks == ["chunk1", "chunk2", "chunk3"]
        print("✓ Chunks yielded on success")
    
    @pytest.mark.asyncio
    async def test_retries_on_first_token_timeout(self):
        """
        What it does: Retries on first token timeout.
        Goal: Verify retry logic is triggered.
        """
        print("Setup: Mock request that times out then succeeds...")
        
        call_count = 0
        
        async def mock_make_request():
            nonlocal call_count
            call_count += 1
            response = AsyncMock()
            response.status_code = 200
            response.aclose = AsyncMock()
            return response
        
        async def mock_stream_processor(response):
            nonlocal call_count
            if call_count == 1:
                raise FirstTokenTimeoutError("Timeout on first attempt")
            yield "success_chunk"
        
        print("Action: Streaming with retry on timeout...")
        chunks = []
        
        async for chunk in stream_with_first_token_retry(
            make_request=mock_make_request,
            stream_processor=mock_stream_processor,
            max_retries=3,
            first_token_timeout=30
        ):
            chunks.append(chunk)
        
        print(f"Call count: {call_count}")
        print(f"Received {len(chunks)} chunks")
        
        assert call_count == 2  # First timeout, second success
        assert len(chunks) == 1
        assert chunks[0] == "success_chunk"
        print("✓ Retry on timeout works correctly")
    
    @pytest.mark.asyncio
    async def test_raises_exception_after_all_retries(self):
        """
        What it does: Raises exception after all retries exhausted.
        Goal: Verify error handling when all retries fail.
        """
        print("Setup: Mock request that always times out...")
        
        call_count = 0
        
        async def mock_make_request():
            nonlocal call_count
            call_count += 1
            response = AsyncMock()
            response.status_code = 200
            response.aclose = AsyncMock()
            return response
        
        async def mock_stream_processor(response):
            raise FirstTokenTimeoutError("Timeout!")
            yield  # Make it a generator
        
        print("Action: Streaming with all retries failing...")
        
        with pytest.raises(Exception) as exc_info:
            async for chunk in stream_with_first_token_retry(
                make_request=mock_make_request,
                stream_processor=mock_stream_processor,
                max_retries=3,
                first_token_timeout=30
            ):
                pass
        
        print(f"Call count: {call_count}")
        print(f"Exception: {exc_info.value}")
        
        assert call_count == 3  # Should try exactly 3 times
        assert "30" in str(exc_info.value)  # Timeout value in message
        assert "3" in str(exc_info.value)  # Retry count in message
        print("✓ Exception raised after all retries")
    
    @pytest.mark.asyncio
    async def test_uses_custom_error_callbacks(self):
        """
        What it does: Uses custom error callbacks.
        Goal: Verify on_http_error and on_all_retries_failed callbacks.
        """
        print("Setup: Mock request that always times out with custom callbacks...")
        
        async def mock_make_request():
            response = AsyncMock()
            response.status_code = 200
            response.aclose = AsyncMock()
            return response
        
        async def mock_stream_processor(response):
            raise FirstTokenTimeoutError("Timeout!")
            yield  # Make it a generator
        
        def custom_all_retries_failed(max_retries, timeout):
            return ValueError(f"Custom error: {max_retries} retries, {timeout}s timeout")
        
        print("Action: Streaming with custom callback...")
        
        with pytest.raises(ValueError) as exc_info:
            async for chunk in stream_with_first_token_retry(
                make_request=mock_make_request,
                stream_processor=mock_stream_processor,
                max_retries=2,
                first_token_timeout=15,
                on_all_retries_failed=custom_all_retries_failed
            ):
                pass
        
        print(f"Exception: {exc_info.value}")
        assert "Custom error" in str(exc_info.value)
        assert "2 retries" in str(exc_info.value)
        assert "15" in str(exc_info.value)
        print("✓ Custom callback used correctly")
    
    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        """
        What it does: Handles HTTP error from API.
        Goal: Verify HTTP errors are handled correctly.
        """
        print("Setup: Mock request that returns HTTP error...")
        
        async def mock_make_request():
            response = AsyncMock()
            response.status_code = 500
            response.aread = AsyncMock(return_value=b"Internal Server Error")
            response.aclose = AsyncMock()
            return response
        
        async def mock_stream_processor(response):
            yield "should not reach"
        
        print("Action: Streaming with HTTP error...")
        
        with pytest.raises(Exception) as exc_info:
            async for chunk in stream_with_first_token_retry(
                make_request=mock_make_request,
                stream_processor=mock_stream_processor,
                max_retries=3,
                first_token_timeout=30
            ):
                pass
        
        print(f"Exception: {exc_info.value}")
        assert "500" in str(exc_info.value)
        assert "Internal Server Error" in str(exc_info.value)
        print("✓ HTTP error handled correctly")
    
    @pytest.mark.asyncio
    async def test_uses_custom_http_error_callback(self):
        """
        What it does: Uses custom HTTP error callback.
        Goal: Verify on_http_error callback is used.
        """
        print("Setup: Mock request with custom HTTP error callback...")
        
        async def mock_make_request():
            response = AsyncMock()
            response.status_code = 429
            response.aread = AsyncMock(return_value=b"Rate limited")
            response.aclose = AsyncMock()
            return response
        
        async def mock_stream_processor(response):
            yield "should not reach"
        
        def custom_http_error(status_code, error_text):
            return RuntimeError(f"Custom HTTP error: {status_code} - {error_text}")
        
        print("Action: Streaming with custom HTTP error callback...")
        
        with pytest.raises(RuntimeError) as exc_info:
            async for chunk in stream_with_first_token_retry(
                make_request=mock_make_request,
                stream_processor=mock_stream_processor,
                max_retries=3,
                first_token_timeout=30,
                on_http_error=custom_http_error
            ):
                pass
        
        print(f"Exception: {exc_info.value}")
        assert "Custom HTTP error" in str(exc_info.value)
        assert "429" in str(exc_info.value)
        assert "Rate limited" in str(exc_info.value)
        print("✓ Custom HTTP error callback used correctly")
    
    @pytest.mark.asyncio
    async def test_closes_response_on_timeout(self):
        """
        What it does: Closes response on timeout.
        Goal: Verify response is properly closed after timeout.
        """
        print("Setup: Mock request that times out...")
        
        responses = []
        
        async def mock_make_request():
            response = AsyncMock()
            response.status_code = 200
            response.aclose = AsyncMock()
            responses.append(response)
            return response
        
        async def mock_stream_processor(response):
            raise FirstTokenTimeoutError("Timeout!")
            yield  # Make it a generator
        
        print("Action: Streaming with timeout...")
        
        try:
            async for chunk in stream_with_first_token_retry(
                make_request=mock_make_request,
                stream_processor=mock_stream_processor,
                max_retries=2,
                first_token_timeout=30
            ):
                pass
        except Exception:
            pass
        
        print(f"Created {len(responses)} responses")
        
        # All responses should have been closed
        for i, response in enumerate(responses):
            print(f"Response {i} aclose called: {response.aclose.called}")
            response.aclose.assert_called()
        
        print("✓ Responses closed on timeout")
    
    @pytest.mark.asyncio
    async def test_propagates_non_timeout_exceptions(self):
        """
        What it does: Propagates non-timeout exceptions without retry.
        Goal: Verify other exceptions are not retried.
        """
        print("Setup: Mock request that raises RuntimeError...")
        
        call_count = 0
        
        async def mock_make_request():
            nonlocal call_count
            call_count += 1
            response = AsyncMock()
            response.status_code = 200
            response.aclose = AsyncMock()
            return response
        
        async def mock_stream_processor(response):
            raise RuntimeError("Not a timeout error")
            yield  # Make it a generator
        
        print("Action: Streaming with non-timeout error...")
        
        with pytest.raises(RuntimeError) as exc_info:
            async for chunk in stream_with_first_token_retry(
                make_request=mock_make_request,
                stream_processor=mock_stream_processor,
                max_retries=3,
                first_token_timeout=30
            ):
                pass
        
        print(f"Call count: {call_count}")
        print(f"Exception: {exc_info.value}")
        
        assert call_count == 1  # Should NOT retry
        assert "Not a timeout error" in str(exc_info.value)
        print("✓ Non-timeout exceptions propagated without retry")
    
    @pytest.mark.asyncio
    async def test_uses_configured_max_retries(self):
        """
        What it does: Uses configured max_retries value.
        Goal: Verify max_retries parameter is respected.
        """
        print("Setup: Mock request that always times out...")
        
        call_count = 0
        
        async def mock_make_request():
            nonlocal call_count
            call_count += 1
            response = AsyncMock()
            response.status_code = 200
            response.aclose = AsyncMock()
            return response
        
        async def mock_stream_processor(response):
            raise FirstTokenTimeoutError("Timeout!")
            yield  # Make it a generator
        
        print("Action: Streaming with max_retries=5...")
        
        try:
            async for chunk in stream_with_first_token_retry(
                make_request=mock_make_request,
                stream_processor=mock_stream_processor,
                max_retries=5,
                first_token_timeout=30
            ):
                pass
        except Exception:
            pass
        
        print(f"Call count: {call_count}")
        assert call_count == 5  # Should try exactly 5 times
        print("✓ max_retries parameter respected")
    
    @pytest.mark.asyncio
    async def test_multiple_retries_then_success(self):
        """
        What it does: Succeeds after multiple retries.
        Goal: Verify recovery after multiple failures.
        """
        print("Setup: Mock request that fails twice then succeeds...")
        
        call_count = 0
        
        async def mock_make_request():
            nonlocal call_count
            call_count += 1
            response = AsyncMock()
            response.status_code = 200
            response.aclose = AsyncMock()
            return response
        
        async def mock_stream_processor(response):
            nonlocal call_count
            if call_count < 3:
                raise FirstTokenTimeoutError(f"Timeout on attempt {call_count}")
            yield "finally_success"
        
        print("Action: Streaming with multiple retries...")
        chunks = []
        
        async for chunk in stream_with_first_token_retry(
            make_request=mock_make_request,
            stream_processor=mock_stream_processor,
            max_retries=5,
            first_token_timeout=30
        ):
            chunks.append(chunk)
        
        print(f"Call count: {call_count}")
        print(f"Received {len(chunks)} chunks")
        
        assert call_count == 3  # Failed twice, succeeded on third
        assert len(chunks) == 1
        assert chunks[0] == "finally_success"
        print("✓ Multiple retries then success works correctly")
    
    @pytest.mark.asyncio
    async def test_closes_response_on_http_error(self):
        """
        What it does: Closes response on HTTP error.
        Goal: Verify response is properly closed after HTTP error.
        """
        print("Setup: Mock request that returns HTTP error...")
        
        response = AsyncMock()
        response.status_code = 503
        response.aread = AsyncMock(return_value=b"Service Unavailable")
        response.aclose = AsyncMock()
        
        async def mock_make_request():
            return response
        
        async def mock_stream_processor(resp):
            yield "should not reach"
        
        print("Action: Streaming with HTTP error...")
        
        try:
            async for chunk in stream_with_first_token_retry(
                make_request=mock_make_request,
                stream_processor=mock_stream_processor,
                max_retries=3,
                first_token_timeout=30
            ):
                pass
        except Exception:
            pass
        
        print(f"Response aclose called: {response.aclose.called}")
        response.aclose.assert_called()
        print("✓ Response closed on HTTP error")
    
    @pytest.mark.asyncio
    async def test_reuses_initial_response_on_first_attempt(self):
        """
        What it does: Reuses initial_response on first attempt.
        Goal: Verify initial_response is used instead of calling make_request.
        """
        print("Setup: Mock initial response...")
        
        initial_response = AsyncMock()
        initial_response.status_code = 200
        initial_response.aclose = AsyncMock()
        
        make_request_called = False
        
        async def mock_make_request():
            nonlocal make_request_called
            make_request_called = True
            response = AsyncMock()
            response.status_code = 200
            response.aclose = AsyncMock()
            return response
        
        async def mock_stream_processor(response):
            # Verify we got the initial response
            assert response is initial_response
            yield "chunk_from_initial"
        
        print("Action: Streaming with initial_response...")
        chunks = []
        
        async for chunk in stream_with_first_token_retry(
            make_request=mock_make_request,
            stream_processor=mock_stream_processor,
            initial_response=initial_response,
            max_retries=3,
            first_token_timeout=30
        ):
            chunks.append(chunk)
        
        print(f"make_request called: {make_request_called}")
        print(f"Received {len(chunks)} chunks")
        
        # make_request should NOT be called on first attempt
        assert not make_request_called
        assert len(chunks) == 1
        assert chunks[0] == "chunk_from_initial"
        print("✓ initial_response reused on first attempt")
    
    @pytest.mark.asyncio
    async def test_calls_make_request_on_retry(self):
        """
        What it does: Calls make_request on retry attempts.
        Goal: Verify make_request is called when retrying after timeout.
        """
        print("Setup: Mock initial response that times out...")
        
        initial_response = AsyncMock()
        initial_response.status_code = 200
        initial_response.aclose = AsyncMock()
        
        make_request_call_count = 0
        
        async def mock_make_request():
            nonlocal make_request_call_count
            make_request_call_count += 1
            print(f"make_request called (retry attempt {make_request_call_count})")
            response = AsyncMock()
            response.status_code = 200
            response.aclose = AsyncMock()
            return response
        
        attempt_count = 0
        
        async def mock_stream_processor(response):
            nonlocal attempt_count
            attempt_count += 1
            
            if attempt_count == 1:
                # First attempt with initial_response - timeout
                assert response is initial_response
                raise FirstTokenTimeoutError("Timeout on first attempt")
            else:
                # Retry attempts - should get response from make_request
                assert response is not initial_response
                yield "success_chunk"
        
        print("Action: Streaming with initial_response that times out...")
        chunks = []
        
        async for chunk in stream_with_first_token_retry(
            make_request=mock_make_request,
            stream_processor=mock_stream_processor,
            initial_response=initial_response,
            max_retries=3,
            first_token_timeout=30
        ):
            chunks.append(chunk)
        
        print(f"make_request call count: {make_request_call_count}")
        print(f"Total attempts: {attempt_count}")
        print(f"Received {len(chunks)} chunks")
        
        # make_request should be called once (on retry)
        assert make_request_call_count == 1
        assert attempt_count == 2  # First with initial_response, second with make_request
        assert len(chunks) == 1
        print("✓ make_request called on retry")
    
    @pytest.mark.asyncio
    async def test_initial_response_none_calls_make_request_immediately(self):
        """
        What it does: Calls make_request immediately when initial_response is None.
        Goal: Verify backward compatibility (old behavior).
        """
        print("Setup: No initial_response (None)...")
        
        make_request_call_count = 0
        
        async def mock_make_request():
            nonlocal make_request_call_count
            make_request_call_count += 1
            print(f"make_request called (attempt {make_request_call_count})")
            response = AsyncMock()
            response.status_code = 200
            response.aclose = AsyncMock()
            return response
        
        async def mock_stream_processor(response):
            yield "chunk"
        
        print("Action: Streaming without initial_response...")
        chunks = []
        
        async for chunk in stream_with_first_token_retry(
            make_request=mock_make_request,
            stream_processor=mock_stream_processor,
            initial_response=None,  # Explicitly None
            max_retries=3,
            first_token_timeout=30
        ):
            chunks.append(chunk)
        
        print(f"make_request call count: {make_request_call_count}")
        print(f"Received {len(chunks)} chunks")
        
        # make_request should be called immediately (old behavior)
        assert make_request_call_count == 1
        assert len(chunks) == 1
        print("✓ make_request called immediately when initial_response is None")



# ==================================================================================================
# Tests for _process_chunk() being a plain function (perf: no async generator per chunk)
# ==================================================================================================

class TestProcessChunkIsPlainFunction:
    """Tests that _process_chunk() is synchronous and returns a list."""

    def test_returns_list_not_async_generator(self, mock_parser):
        """
        What it does: Calls _process_chunk() without awaiting.
        Purpose: Ensure no async generator object is created per network chunk.
        """
        import inspect
        mock_parser.feed.return_value = [{"type": "content", "data": "x"}]

        result = _process_chunk(mock_parser, b"chunk", None)

        assert isinstance(result, list)
        assert not inspect.isasyncgenfunction(_process_chunk)
        assert not inspect.iscoroutinefunction(_process_chunk)

    def test_returns_empty_list_for_no_events(self, mock_parser):
        """
        What it does: Processes a chunk that yields no parser events.
        Purpose: Ensure an empty list (not None) is returned.
        """
        mock_parser.feed.return_value = []
        assert _process_chunk(mock_parser, b"", None) == []

    def test_ignores_unknown_event_types(self, mock_parser):
        """
        What it does: Feeds an unknown parser event type.
        Purpose: Ensure unknown events are dropped instead of crashing.
        """
        mock_parser.feed.return_value = [{"type": "something_new", "data": 1}, {"type": "content", "data": "ok"}]
        events = _process_chunk(mock_parser, b"chunk", None)
        assert [e.type for e in events] == ["content"]

    def test_preserves_event_order(self, mock_parser):
        """
        What it does: Processes mixed events in one chunk.
        Purpose: Ensure the returned list keeps stream order.
        """
        mock_parser.feed.return_value = [
            {"type": "content", "data": "a"},
            {"type": "usage", "data": {"credits": 1}},
            {"type": "content", "data": "b"},
            {"type": "context_usage", "data": 3.5},
        ]
        events = _process_chunk(mock_parser, b"chunk", None)
        assert [e.type for e in events] == ["content", "usage", "content", "context_usage"]
        assert events[2].content == "b"
        assert events[3].context_usage_percentage == 3.5

    def test_thinking_parser_empty_processed_thinking_is_dropped(self, mock_parser):
        """
        What it does: Thinking parser returns thinking that process_for_output drops.
        Purpose: Ensure no empty thinking event is produced.
        """
        mock_parser.feed.return_value = [{"type": "content", "data": "<thinking>x"}]
        thinking_parser = MagicMock()
        parse_result = MagicMock()
        parse_result.thinking_content = "x"
        parse_result.regular_content = ""
        parse_result.is_first_thinking_chunk = True
        parse_result.is_last_thinking_chunk = False
        thinking_parser.feed.return_value = parse_result
        thinking_parser.process_for_output.return_value = None

        assert _process_chunk(mock_parser, b"chunk", thinking_parser) == []


# ==================================================================================================
# Tests for anthropic_error_type_for_status()
# ==================================================================================================

class TestAnthropicErrorTypeForStatus:
    """Tests for the HTTP status -> Anthropic error type mapping."""

    @pytest.mark.parametrize("status,expected", [
        (400, "invalid_request_error"),
        (401, "authentication_error"),
        (403, "permission_error"),
        (404, "not_found_error"),
        (429, "rate_limit_error"),
        (503, "overloaded_error"),
        (529, "overloaded_error"),
    ])
    def test_maps_known_statuses(self, status, expected):
        """
        What it does: Maps each documented status code.
        Purpose: Ensure Anthropic error types match the Anthropic API spec.
        """
        assert anthropic_error_type_for_status(status) == expected

    @pytest.mark.parametrize("status", [500, 502, 504, 418, 422, 413, 200, 0, -1, 999])
    def test_unknown_statuses_map_to_api_error(self, status):
        """
        What it does: Maps statuses outside the table, including nonsense values.
        Purpose: Ensure the fallback is always api_error.
        """
        assert anthropic_error_type_for_status(status) == "api_error"


# ==================================================================================================
# Tests for stop sequence handling
# ==================================================================================================

def _feed_all(matcher, pieces):
    """Feed pieces into matcher; return (emitted_text, matched), flushing when nothing matched."""
    out = ""
    matched = None
    for piece in pieces:
        emitted, matched = matcher.feed(piece)
        out += emitted
        if matched is not None:
            return out, matched
    return out + matcher.flush(), None


class TestNormalizeStopSequences:
    """Tests for normalize_stop_sequences()."""

    def test_none_returns_empty(self):
        """What it does: None input. Purpose: No stop sequences."""
        assert normalize_stop_sequences(None) == []

    def test_single_string_is_wrapped(self):
        """What it does: OpenAI allows stop as a string. Purpose: Accept it."""
        assert normalize_stop_sequences("END") == ["END"]

    def test_empty_string_and_non_strings_dropped(self):
        """What it does: Malformed entries. Purpose: Ignore them instead of matching everything."""
        assert normalize_stop_sequences(["", None, 5, "A", ""]) == ["A"]

    def test_duplicates_removed_order_kept(self):
        """What it does: Duplicate sequences. Purpose: De-duplicate, keep order."""
        assert normalize_stop_sequences(["b", "a", "b"]) == ["b", "a"]

    def test_empty_list(self):
        """What it does: Empty list. Purpose: No stop sequences."""
        assert normalize_stop_sequences([]) == []


class TestCreateStopSequenceMatcher:
    """Tests for create_stop_sequence_matcher()."""

    @pytest.mark.parametrize("value", [None, [], [""], ""])
    def test_returns_none_when_nothing_to_match(self, value):
        """
        What it does: Creates a matcher from empty inputs.
        Purpose: None keeps native behaviour exactly (no buffering).
        """
        assert create_stop_sequence_matcher(value) is None

    def test_returns_matcher(self):
        """What it does: Valid sequences. Purpose: Matcher is created."""
        assert isinstance(create_stop_sequence_matcher(["x"]), StopSequenceMatcher)

    def test_matcher_rejects_empty_list(self):
        """What it does: Direct construction with nothing usable. Purpose: Fail loudly."""
        with pytest.raises(ValueError):
            StopSequenceMatcher(["", ""])


class TestStopSequenceMatcher:
    """Tests for StopSequenceMatcher incremental matching."""

    def test_not_present_emits_everything(self):
        """
        What it does: Text without the sequence.
        Purpose: All text is emitted after flush, nothing lost.
        """
        out, matched = _feed_all(StopSequenceMatcher(["STOP"]), ["Hello ", "wor", "ld"])
        assert out == "Hello world"
        assert matched is None

    def test_match_in_single_chunk(self):
        """What it does: Sequence inside one chunk. Purpose: Cut before it."""
        out, matched = _feed_all(StopSequenceMatcher(["STOP"]), ["abcSTOPdef"])
        assert (out, matched) == ("abc", "STOP")

    def test_match_split_across_chunks(self):
        """
        What it does: Sequence split over three chunks.
        Purpose: No part of the sequence leaks to the client.
        """
        out, matched = _feed_all(StopSequenceMatcher(["STOP"]), ["abcS", "T", "OPdef"])
        assert (out, matched) == ("abc", "STOP")

    def test_match_split_one_char_per_chunk(self):
        """What it does: Worst-case char-by-char stream. Purpose: Still detected."""
        out, matched = _feed_all(StopSequenceMatcher(["</end>"]), list("hello</end>tail"))
        assert (out, matched) == ("hello", "</end>")

    def test_match_at_very_start(self):
        """What it does: Output starts with the sequence. Purpose: Nothing emitted."""
        out, matched = _feed_all(StopSequenceMatcher(["STOP"]), ["STOP and more"])
        assert (out, matched) == ("", "STOP")

    def test_match_at_very_start_split(self):
        """What it does: Sequence at start, split. Purpose: Nothing emitted."""
        out, matched = _feed_all(StopSequenceMatcher(["STOP"]), ["ST", "OP"])
        assert (out, matched) == ("", "STOP")

    def test_match_at_very_end(self):
        """What it does: Sequence is the last text. Purpose: Detected, text before kept."""
        out, matched = _feed_all(StopSequenceMatcher(["STOP"]), ["abc", "STOP"])
        assert (out, matched) == ("abc", "STOP")

    def test_partial_prefix_at_end_is_flushed(self):
        """
        What it does: Stream ends with a prefix of the sequence.
        Purpose: Held-back prefix is released by flush (not lost).
        """
        out, matched = _feed_all(StopSequenceMatcher(["STOP"]), ["abcST"])
        assert (out, matched) == ("abcST", None)

    def test_holdback_never_exceeds_max_len_minus_one(self):
        """
        What it does: Checks what is emitted before the stream ends.
        Purpose: Latency bound - only (max_len - 1) chars are held back.
        """
        matcher = StopSequenceMatcher(["ABCDE"])
        assert matcher.feed("0123456789") == ("012345", None)
        assert matcher.flush() == "6789"

    def test_single_char_sequence_has_no_holdback(self):
        """What it does: One-char sequence. Purpose: Nothing is buffered."""
        matcher = StopSequenceMatcher(["\n"])
        assert matcher.feed("abc") == ("abc", None)
        assert matcher.feed("d\ne") == ("d", "\n")

    def test_multiple_sequences_earliest_wins(self):
        """What it does: Two sequences present. Purpose: The one that completes first wins."""
        out, matched = _feed_all(StopSequenceMatcher(["world", "lo"]), ["hello world"])
        assert (out, matched) == ("hel", "lo")

    def test_multiple_sequences_order_in_list_irrelevant(self):
        """What it does: Same text, reversed list. Purpose: Result depends on text only."""
        out, matched = _feed_all(StopSequenceMatcher(["lo", "world"]), ["hello world"])
        assert (out, matched) == ("hel", "lo")

    def test_multiple_sequences_result_independent_of_chunking(self):
        """
        What it does: Same text fed whole and char by char.
        Purpose: Chunk boundaries never change the outcome.
        """
        text = "the quick brown fox ends here"
        seqs = ["fox ends", "brown", "n f"]
        whole = _feed_all(StopSequenceMatcher(seqs), [text])
        chars = _feed_all(StopSequenceMatcher(seqs), list(text))
        assert whole == chars == ("the quick ", "brown")

    def test_overlapping_sequences_shorter_completing_first(self):
        """What it does: "ab" vs "abc". Purpose: "ab" completes first and wins."""
        out, matched = _feed_all(StopSequenceMatcher(["abc", "ab"]), ["xa", "bc"])
        assert (out, matched) == ("x", "ab")

    def test_input_after_match_is_ignored(self):
        """What it does: Feeds after a match. Purpose: Nothing more is emitted."""
        matcher = StopSequenceMatcher(["X"])
        matcher.feed("aXb")
        assert matcher.feed("more") == ("", "X")
        assert matcher.flush() == ""
        assert matcher.matched == "X"

    def test_empty_feed_is_noop(self):
        """What it does: Empty string fed. Purpose: No output, no state change."""
        matcher = StopSequenceMatcher(["STOP"])
        assert matcher.feed("") == ("", None)
        assert matcher.matched is None

    def test_unicode_sequences(self):
        """What it does: Non-ASCII sequence split across chunks. Purpose: Works per character."""
        out, matched = _feed_all(StopSequenceMatcher(["конец"]), ["текст ко", "нец дальше"])
        assert (out, matched) == ("текст ", "конец")

    def test_repeated_prefix_does_not_confuse(self):
        """What it does: Text "aaab" with sequence "aab". Purpose: Overlapping prefix is handled."""
        out, matched = _feed_all(StopSequenceMatcher(["aab"]), ["a", "a", "a", "b"])
        assert (out, matched) == ("a", "aab")


async def _events_from(items):
    """Async generator yielding the given KiroEvents."""
    for item in items:
        yield item


async def _collect_events(gen):
    """Collect all events from an async generator."""
    return [event async for event in gen]


class TestApplyStopSequences:
    """Tests for apply_stop_sequences() KiroEvent filter."""

    @pytest.mark.asyncio
    async def test_none_matcher_is_pass_through(self):
        """
        What it does: Filter with matcher=None.
        Purpose: Default behaviour is identical (same objects, same order).
        """
        items = [
            KiroEvent(type="content", content="a"),
            KiroEvent(type="thinking", thinking_content="t"),
            KiroEvent(type="usage", usage={"x": 1}),
        ]
        result = await _collect_events(apply_stop_sequences(_events_from(items), None))
        assert result == items
        assert all(a is b for a, b in zip(result, items))

    @pytest.mark.asyncio
    async def test_stops_stream_and_closes_upstream(self):
        """
        What it does: Match occurs while upstream has more events.
        Purpose: Later events (including tool calls) are not produced; upstream is closed.
        """
        closed = False

        async def upstream():
            nonlocal closed
            try:
                yield KiroEvent(type="content", content="hello ST")
                yield KiroEvent(type="content", content="OP world")
                yield KiroEvent(type="tool_use", tool_use={"id": "t1"})
            finally:
                closed = True

        matcher = StopSequenceMatcher(["STOP"])
        result = await _collect_events(apply_stop_sequences(upstream(), matcher))

        assert "".join(e.content for e in result if e.type == "content") == "hello "
        assert not any(e.type == "tool_use" for e in result)
        assert matcher.matched == "STOP"
        assert closed

    @pytest.mark.asyncio
    async def test_thinking_not_matched(self):
        """
        What it does: Stop sequence appears in thinking content.
        Purpose: Thinking is never cut and does not end the stream.
        """
        items = [
            KiroEvent(type="thinking", thinking_content="I will say STOP now"),
            KiroEvent(type="content", content="answer"),
        ]
        matcher = StopSequenceMatcher(["STOP"])
        result = await _collect_events(apply_stop_sequences(_events_from(items), matcher))

        assert result[0].thinking_content == "I will say STOP now"
        assert "".join(e.content for e in result if e.type == "content") == "answer"
        assert matcher.matched is None

    @pytest.mark.asyncio
    async def test_tool_use_not_matched_and_flushes_pending_text_first(self):
        """
        What it does: Held-back text followed by a tool call containing the sequence.
        Purpose: Text is flushed before the tool call (order kept); tool input untouched.
        """
        tool = {"id": "t1", "function": {"name": "f", "arguments": '{"q": "STOP"}'}}
        items = [
            KiroEvent(type="content", content="abcST"),
            KiroEvent(type="tool_use", tool_use=tool),
        ]
        matcher = StopSequenceMatcher(["STOP"])
        result = await _collect_events(apply_stop_sequences(_events_from(items), matcher))

        assert [e.type for e in result] == ["content", "content", "tool_use"]
        assert result[0].content + result[1].content == "abcST"
        assert result[2].tool_use is tool
        assert matcher.matched is None

    @pytest.mark.asyncio
    async def test_usage_events_do_not_flush(self):
        """
        What it does: Usage event arrives between two halves of the sequence.
        Purpose: Usage must not force a flush that leaks a partial sequence.
        """
        items = [
            KiroEvent(type="content", content="xST"),
            KiroEvent(type="context_usage", context_usage_percentage=1.0),
            KiroEvent(type="content", content="OPy"),
        ]
        matcher = StopSequenceMatcher(["STOP"])
        result = await _collect_events(apply_stop_sequences(_events_from(items), matcher))

        assert "".join(e.content for e in result if e.type == "content") == "x"
        assert matcher.matched == "STOP"

    @pytest.mark.asyncio
    async def test_flushes_tail_at_end(self):
        """What it does: No match, held-back tail. Purpose: Tail emitted at end."""
        items = [KiroEvent(type="content", content="abcS")]
        result = await _collect_events(apply_stop_sequences(_events_from(items), StopSequenceMatcher(["STOP"])))
        assert "".join(e.content for e in result) == "abcS"

    @pytest.mark.asyncio
    async def test_no_empty_content_events(self):
        """What it does: Chunks fully held back. Purpose: No empty content events are produced."""
        items = [KiroEvent(type="content", content="S"), KiroEvent(type="content", content="T")]
        result = await _collect_events(apply_stop_sequences(_events_from(items), StopSequenceMatcher(["STOP"])))
        assert all(e.content for e in result)
        assert "".join(e.content for e in result) == "ST"

    @pytest.mark.asyncio
    async def test_propagates_first_token_timeout(self):
        """What it does: Upstream raises timeout. Purpose: Retry logic still sees it."""
        async def upstream():
            raise FirstTokenTimeoutError("t")
            yield  # pragma: no cover

        with pytest.raises(FirstTokenTimeoutError):
            await _collect_events(apply_stop_sequences(upstream(), StopSequenceMatcher(["x"])))


class TestCollectStreamToResultStopSequences:
    """Tests for stop_sequences in collect_stream_to_result()."""

    @pytest.mark.asyncio
    async def test_cuts_content_and_sets_stop_sequence(self, mock_response):
        """
        What it does: Non-streaming collection with a split stop sequence.
        Purpose: Content is cut, thinking untouched, later tool calls dropped, stop_sequence set.
        """
        async def mock_parse(*args, **kwargs):
            yield KiroEvent(type="thinking", thinking_content="think END")
            yield KiroEvent(type="content", content="Hello E")
            yield KiroEvent(type="content", content="ND tail")
            yield KiroEvent(type="tool_use", tool_use={"id": "late"})

        with patch('kiro.streaming_core.parse_kiro_stream', mock_parse):
            with patch('kiro.streaming_core.parse_bracket_tool_calls', return_value=[]):
                result = await collect_stream_to_result(mock_response, stop_sequences=["END"])

        assert result.content == "Hello "
        assert result.thinking_content == "think END"
        assert result.stop_sequence == "END"
        assert result.tool_calls == []

    @pytest.mark.asyncio
    async def test_not_present_keeps_full_content(self, mock_response):
        """What it does: Sequence absent. Purpose: Full content, stop_sequence None."""
        async def mock_parse(*args, **kwargs):
            yield KiroEvent(type="content", content="Hello ")
            yield KiroEvent(type="content", content="world E")

        with patch('kiro.streaming_core.parse_kiro_stream', mock_parse):
            with patch('kiro.streaming_core.parse_bracket_tool_calls', return_value=[]):
                result = await collect_stream_to_result(mock_response, stop_sequences=["END"])

        assert result.content == "Hello world E"
        assert result.stop_sequence is None

    @pytest.mark.asyncio
    async def test_default_none_unchanged(self, mock_response):
        """What it does: No stop_sequences. Purpose: Exactly the old behaviour."""
        async def mock_parse(*args, **kwargs):
            yield KiroEvent(type="content", content="a END b")

        with patch('kiro.streaming_core.parse_kiro_stream', mock_parse):
            with patch('kiro.streaming_core.parse_bracket_tool_calls', return_value=[]):
                result = await collect_stream_to_result(mock_response)

        assert result.content == "a END b"
        assert result.stop_sequence is None


# ==================================================================================================
# Tests for non-blocking token estimation
# ==================================================================================================

class TestEstimateRequestTokensOffloaded:
    """Tests for estimate_request_tokens_offloaded()."""

    @pytest.mark.asyncio
    async def test_uses_async_tokenizer_when_available(self):
        """
        What it does: tokenizer has estimate_request_tokens_async.
        Purpose: The async variant is used with the same arguments.
        """
        fake_async = AsyncMock(return_value={"total_tokens": 7})
        with patch('kiro.streaming_core.tokenizer_module') as tok:
            tok.estimate_request_tokens_async = fake_async
            result = await estimate_request_tokens_offloaded(
                messages=[{"role": "user", "content": "hi"}], tools=None,
                system_prompt="s", apply_claude_correction=False,
            )
        assert result == {"total_tokens": 7}
        fake_async.assert_awaited_once_with(
            messages=[{"role": "user", "content": "hi"}], tools=None,
            system_prompt="s", apply_claude_correction=False,
        )

    @pytest.mark.asyncio
    async def test_falls_back_to_thread_when_async_missing(self):
        """
        What it does: tokenizer lacks the async variant.
        Purpose: Sync estimator runs in a worker thread, not on the event loop thread.
        """
        import threading
        loop_thread = threading.get_ident()
        seen_thread = {}

        def fake_sync(messages, tools, system_prompt, apply_claude_correction):
            seen_thread["id"] = threading.get_ident()
            return {"total_tokens": len(messages)}

        fake_module = MagicMock(spec=["estimate_request_tokens"])
        fake_module.estimate_request_tokens = fake_sync
        with patch('kiro.streaming_core.tokenizer_module', fake_module):
            result = await estimate_request_tokens_offloaded(messages=[{}, {}])

        assert result == {"total_tokens": 2}
        assert seen_thread["id"] != loop_thread

    @pytest.mark.asyncio
    async def test_real_tokenizer_matches_sync_result(self):
        """
        What it does: Uses the real tokenizer module.
        Purpose: Offloading does not change the numbers.
        """
        from kiro.tokenizer import estimate_request_tokens
        messages = [{"role": "user", "content": "Hello there, how are you?"}]
        expected = estimate_request_tokens(messages, None, "sys", False)
        result = await estimate_request_tokens_offloaded(messages, None, "sys", False)
        assert result == expected


# ==================================================================================================
# Tests for progressive first token timeout (bounded retries)
# ==================================================================================================

class TestFirstTokenTimeoutForAttempt:
    """Tests for first_token_timeout_for_attempt()."""

    def test_grows_linearly(self):
        """What it does: attempts 0..2. Purpose: timeout * (attempt + 1)."""
        assert [first_token_timeout_for_attempt(15, a) for a in range(3)] == [15, 30, 45]

    def test_capped_by_streaming_read_timeout(self):
        """What it does: Large attempt number. Purpose: Never above STREAMING_READ_TIMEOUT."""
        with patch('kiro.streaming_core.STREAMING_READ_TIMEOUT', 100.0):
            assert first_token_timeout_for_attempt(40, 5) == 100.0

    def test_cap_never_below_base(self):
        """What it does: Base already above the cap. Purpose: Base is kept (no shrinking)."""
        with patch('kiro.streaming_core.STREAMING_READ_TIMEOUT', 10.0):
            assert first_token_timeout_for_attempt(20, 0) == 20
            assert first_token_timeout_for_attempt(20, 3) == 20

    def test_negative_attempt_treated_as_first(self):
        """What it does: Invalid attempt. Purpose: Treated as attempt 0."""
        assert first_token_timeout_for_attempt(15, -2) == 15


class TestStreamWithFirstTokenRetryProgressiveTimeout:
    """Tests for timeout_aware_processor in stream_with_first_token_retry()."""

    @pytest.mark.asyncio
    async def test_processor_receives_growing_timeouts(self):
        """
        What it does: Every attempt times out with a timeout-aware processor.
        Purpose: Attempt N gets base * (N + 1); number of attempts stays max_retries.
        """
        seen_timeouts = []
        make_calls = 0

        async def make_request():
            nonlocal make_calls
            make_calls += 1
            response = AsyncMock()
            response.status_code = 200
            return response

        async def processor(response, attempt_timeout):
            seen_timeouts.append(attempt_timeout)
            raise FirstTokenTimeoutError("t")
            yield  # pragma: no cover

        with pytest.raises(Exception):
            async for _ in stream_with_first_token_retry(
                make_request=make_request,
                stream_processor=processor,
                max_retries=3,
                first_token_timeout=10,
                timeout_aware_processor=True,
            ):
                pass

        assert seen_timeouts == [10, 20, 30]
        assert make_calls == 3

    @pytest.mark.asyncio
    async def test_initial_response_counts_as_first_attempt(self):
        """
        What it does: initial_response given, all attempts time out.
        Purpose: Only max_retries - 1 extra requests are made.
        """
        make_calls = 0

        async def make_request():
            nonlocal make_calls
            make_calls += 1
            response = AsyncMock()
            response.status_code = 200
            return response

        async def processor(response, attempt_timeout):
            raise FirstTokenTimeoutError("t")
            yield  # pragma: no cover

        initial = AsyncMock()
        initial.status_code = 200
        with pytest.raises(Exception):
            async for _ in stream_with_first_token_retry(
                make_request=make_request,
                stream_processor=processor,
                initial_response=initial,
                max_retries=3,
                first_token_timeout=5,
                timeout_aware_processor=True,
            ):
                pass

        assert make_calls == 2

    @pytest.mark.asyncio
    async def test_legacy_processor_called_with_response_only(self):
        """
        What it does: Default timeout_aware_processor=False.
        Purpose: Existing one-argument processors keep working.
        """
        calls = []

        async def make_request():
            response = AsyncMock()
            response.status_code = 200
            return response

        async def processor(response):
            calls.append(response)
            yield "ok"

        chunks = [c async for c in stream_with_first_token_retry(
            make_request=make_request, stream_processor=processor, max_retries=2, first_token_timeout=5,
        )]
        assert chunks == ["ok"]
        assert len(calls) == 1
