
# -*- coding: utf-8 -*-

"""
Unit tests for streaming_anthropic module.

Tests for:
- generate_message_id() function
- format_sse_event() function
- stream_kiro_to_anthropic() generator
- collect_anthropic_response() function
"""

import pytest
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from kiro.streaming_anthropic import (
    generate_message_id,
    generate_thinking_signature,
    format_sse_event,
    stream_kiro_to_anthropic,
    collect_anthropic_response,
    stream_with_first_token_retry_anthropic,
)
from kiro.streaming_core import KiroEvent, StreamResult


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
def mock_auth_manager():
    """Mock for KiroAuthManager."""
    manager = MagicMock()
    return manager


@pytest.fixture
def mock_response():
    """Mock for httpx.Response."""
    response = AsyncMock()
    response.status_code = 200
    response.aclose = AsyncMock()
    return response


# ==================================================================================================
# Tests for generate_message_id()
# ==================================================================================================

class TestGenerateMessageId:
    """Tests for generate_message_id() function."""
    
    def test_generates_message_id_with_prefix(self):
        """
        What it does: Generates message ID with 'msg_' prefix.
        Goal: Verify Anthropic message ID format.
        """
        print("Action: Generating message ID...")
        message_id = generate_message_id()
        
        print(f"Generated ID: {message_id}")
        assert message_id.startswith("msg_")
        print("✓ Message ID has correct prefix")
    
    def test_generates_unique_ids(self):
        """
        What it does: Generates unique message IDs.
        Goal: Verify IDs are unique.
        """
        print("Action: Generating multiple message IDs...")
        ids = [generate_message_id() for _ in range(100)]
        
        print(f"Generated {len(ids)} IDs")
        unique_ids = set(ids)
        print(f"Unique IDs: {len(unique_ids)}")
        
        assert len(unique_ids) == 100
        print("✓ All message IDs are unique")
    
    def test_message_id_has_correct_length(self):
        """
        What it does: Verifies message ID length.
        Goal: Ensure ID format matches Anthropic spec.
        """
        print("Action: Generating message ID...")
        message_id = generate_message_id()
        
        # Format: msg_ + 24 hex chars
        print(f"Generated ID: {message_id}, length: {len(message_id)}")
        assert len(message_id) == 4 + 24  # "msg_" + 24 chars
        print("✓ Message ID has correct length")


# ==================================================================================================
# Tests for format_sse_event()
# ==================================================================================================

class TestFormatSseEvent:
    """Tests for format_sse_event() function."""
    
    def test_formats_message_start_event(self):
        """
        What it does: Formats message_start event.
        Goal: Verify Anthropic SSE format.
        """
        print("Action: Formatting message_start event...")
        data = {
            "type": "message_start",
            "message": {
                "id": "msg_123",
                "type": "message",
                "role": "assistant"
            }
        }
        
        result = format_sse_event("message_start", data)
        
        print(f"Formatted event:\n{result}")
        assert result.startswith("event: message_start\n")
        assert "data: " in result
        assert result.endswith("\n\n")
        print("✓ Event formatted correctly")
    
    def test_formats_content_block_delta_event(self):
        """
        What it does: Formats content_block_delta event.
        Goal: Verify delta event format.
        """
        print("Action: Formatting content_block_delta event...")
        data = {
            "type": "content_block_delta",
            "index": 0,
            "delta": {
                "type": "text_delta",
                "text": "Hello"
            }
        }
        
        result = format_sse_event("content_block_delta", data)
        
        print(f"Formatted event:\n{result}")
        assert "event: content_block_delta\n" in result
        assert '"text": "Hello"' in result
        print("✓ Delta event formatted correctly")
    
    def test_formats_message_stop_event(self):
        """
        What it does: Formats message_stop event.
        Goal: Verify stop event format.
        """
        print("Action: Formatting message_stop event...")
        data = {"type": "message_stop"}
        
        result = format_sse_event("message_stop", data)
        
        print(f"Formatted event:\n{result}")
        assert "event: message_stop\n" in result
        print("✓ Stop event formatted correctly")
    
    def test_handles_unicode_content(self):
        """
        What it does: Handles Unicode content in events.
        Goal: Verify non-ASCII characters are preserved.
        """
        print("Action: Formatting event with Unicode...")
        data = {
            "type": "content_block_delta",
            "delta": {"text": "Привет мир! 🌍"}
        }
        
        result = format_sse_event("content_block_delta", data)
        
        print(f"Formatted event:\n{result}")
        assert "Привет мир!" in result
        assert "🌍" in result
        print("✓ Unicode content preserved")
    
    def test_json_data_is_valid(self):
        """
        What it does: Verifies JSON data is valid.
        Goal: Ensure data can be parsed back.
        """
        print("Action: Formatting and parsing event...")
        data = {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": 100}
        }
        
        result = format_sse_event("message_delta", data)
        
        # Extract JSON from result
        lines = result.strip().split("\n")
        data_line = [l for l in lines if l.startswith("data: ")][0]
        json_str = data_line[6:]  # Remove "data: " prefix
        
        print(f"JSON string: {json_str}")
        parsed = json.loads(json_str)
        
        assert parsed["type"] == "message_delta"
        assert parsed["delta"]["stop_reason"] == "end_turn"
        print("✓ JSON data is valid and parseable")


# ==================================================================================================
# Tests for stream_kiro_to_anthropic()
# ==================================================================================================

class TestStreamKiroToAnthropic:
    """Tests for stream_kiro_to_anthropic() generator."""
    
    @pytest.mark.asyncio
    async def test_yields_message_start_event(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Yields message_start event at beginning.
        Goal: Verify Anthropic streaming protocol.
        """
        print("Setup: Mock empty stream...")
        
        async def mock_parse_kiro_stream(*args, **kwargs):
            return
            yield  # Make it a generator
        
        print("Action: Streaming to Anthropic format...")
        events = []
        
        with patch('kiro.streaming_anthropic.parse_kiro_stream', mock_parse_kiro_stream):
            async for event in stream_kiro_to_anthropic(
                mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
            ):
                events.append(event)
        
        print(f"Received {len(events)} events")
        
        # First event should be message_start
        assert len(events) > 0
        assert "event: message_start" in events[0]
        print("✓ message_start event yielded first")
    
    @pytest.mark.asyncio
    async def test_yields_content_block_start_on_first_content(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Yields content_block_start before first content.
        Goal: Verify content block lifecycle.
        """
        print("Setup: Mock stream with content...")
        
        async def mock_parse_kiro_stream(*args, **kwargs):
            yield KiroEvent(type="content", content="Hello")
        
        print("Action: Streaming to Anthropic format...")
        events = []
        
        with patch('kiro.streaming_anthropic.parse_kiro_stream', mock_parse_kiro_stream):
            with patch('kiro.streaming_anthropic.parse_bracket_tool_calls', return_value=[]):
                async for event in stream_kiro_to_anthropic(
                    mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
                ):
                    events.append(event)
        
        print(f"Received {len(events)} events")
        
        # Should have content_block_start
        content_block_start_found = any("content_block_start" in e for e in events)
        assert content_block_start_found
        print("✓ content_block_start event yielded")
    
    @pytest.mark.asyncio
    async def test_yields_content_block_delta_for_content(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Yields content_block_delta for content events.
        Goal: Verify content streaming.
        """
        print("Setup: Mock stream with content...")
        
        async def mock_parse_kiro_stream(*args, **kwargs):
            yield KiroEvent(type="content", content="Hello")
            yield KiroEvent(type="content", content=" World")
        
        print("Action: Streaming to Anthropic format...")
        events = []
        
        with patch('kiro.streaming_anthropic.parse_kiro_stream', mock_parse_kiro_stream):
            with patch('kiro.streaming_anthropic.parse_bracket_tool_calls', return_value=[]):
                async for event in stream_kiro_to_anthropic(
                    mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
                ):
                    events.append(event)
        
        print(f"Received {len(events)} events")
        
        # Should have content_block_delta events
        delta_events = [e for e in events if "content_block_delta" in e]
        print(f"Delta events: {len(delta_events)}")
        
        assert len(delta_events) >= 2
        assert "Hello" in delta_events[0]
        assert "World" in delta_events[1]
        print("✓ content_block_delta events yielded for content")
    
    @pytest.mark.asyncio
    async def test_yields_tool_use_block_for_tool_calls(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Yields tool_use block for tool calls.
        Goal: Verify tool use streaming.
        """
        print("Setup: Mock stream with tool call...")
        
        tool_use_data = {
            "id": "toolu_123",
            "function": {
                "name": "get_weather",
                "arguments": '{"city": "Moscow"}'
            }
        }
        
        async def mock_parse_kiro_stream(*args, **kwargs):
            yield KiroEvent(type="content", content="Let me check")
            yield KiroEvent(type="tool_use", tool_use=tool_use_data)
        
        print("Action: Streaming to Anthropic format...")
        events = []
        
        with patch('kiro.streaming_anthropic.parse_kiro_stream', mock_parse_kiro_stream):
            with patch('kiro.streaming_anthropic.parse_bracket_tool_calls', return_value=[]):
                async for event in stream_kiro_to_anthropic(
                    mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
                ):
                    events.append(event)
        
        print(f"Received {len(events)} events")
        
        # Should have tool_use content block
        tool_use_events = [e for e in events if "tool_use" in e and "content_block_start" in e]
        print(f"Tool use events: {len(tool_use_events)}")
        
        assert len(tool_use_events) >= 1
        assert "get_weather" in tool_use_events[0]
        print("✓ tool_use block yielded for tool calls")
    
    @pytest.mark.asyncio
    async def test_yields_message_delta_with_stop_reason(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Yields message_delta with stop_reason.
        Goal: Verify message completion.
        """
        print("Setup: Mock stream with content...")
        
        async def mock_parse_kiro_stream(*args, **kwargs):
            yield KiroEvent(type="content", content="Hello")
        
        print("Action: Streaming to Anthropic format...")
        events = []
        
        with patch('kiro.streaming_anthropic.parse_kiro_stream', mock_parse_kiro_stream):
            with patch('kiro.streaming_anthropic.parse_bracket_tool_calls', return_value=[]):
                async for event in stream_kiro_to_anthropic(
                    mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
                ):
                    events.append(event)
        
        print(f"Received {len(events)} events")
        
        # Should have message_delta with stop_reason
        message_delta_events = [e for e in events if "message_delta" in e]
        assert len(message_delta_events) >= 1
        assert "end_turn" in message_delta_events[0]
        print("✓ message_delta with stop_reason yielded")
    
    @pytest.mark.asyncio
    async def test_yields_message_stop_at_end(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Yields message_stop at end.
        Goal: Verify stream termination.
        """
        print("Setup: Mock stream with content...")
        
        async def mock_parse_kiro_stream(*args, **kwargs):
            yield KiroEvent(type="content", content="Hello")
        
        print("Action: Streaming to Anthropic format...")
        events = []
        
        with patch('kiro.streaming_anthropic.parse_kiro_stream', mock_parse_kiro_stream):
            with patch('kiro.streaming_anthropic.parse_bracket_tool_calls', return_value=[]):
                async for event in stream_kiro_to_anthropic(
                    mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
                ):
                    events.append(event)
        
        print(f"Received {len(events)} events")
        
        # Last event should be message_stop
        assert "message_stop" in events[-1]
        print("✓ message_stop yielded at end")
    
    @pytest.mark.asyncio
    async def test_stop_reason_is_tool_use_when_tools_present(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Sets stop_reason to tool_use when tools are present.
        Goal: Verify correct stop reason for tool calls.
        """
        print("Setup: Mock stream with tool call...")
        
        tool_use_data = {
            "id": "toolu_123",
            "function": {"name": "func1", "arguments": "{}"}
        }
        
        async def mock_parse_kiro_stream(*args, **kwargs):
            yield KiroEvent(type="tool_use", tool_use=tool_use_data)
        
        print("Action: Streaming to Anthropic format...")
        events = []
        
        with patch('kiro.streaming_anthropic.parse_kiro_stream', mock_parse_kiro_stream):
            with patch('kiro.streaming_anthropic.parse_bracket_tool_calls', return_value=[]):
                async for event in stream_kiro_to_anthropic(
                    mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
                ):
                    events.append(event)
        
        print(f"Received {len(events)} events")
        
        # message_delta should have stop_reason: tool_use
        message_delta_events = [e for e in events if "message_delta" in e]
        assert len(message_delta_events) >= 1
        assert "tool_use" in message_delta_events[0]
        print("✓ stop_reason is tool_use when tools present")
    
    @pytest.mark.asyncio
    async def test_handles_bracket_tool_calls(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Handles bracket-style tool calls in content.
        Goal: Verify bracket tool call detection.
        """
        print("Setup: Mock stream with bracket tool calls...")
        
        async def mock_parse_kiro_stream(*args, **kwargs):
            yield KiroEvent(type="content", content="[tool_call: func1]")
        
        bracket_tool_calls = [
            {"id": "call_1", "function": {"name": "func1", "arguments": "{}"}}
        ]
        
        print("Action: Streaming to Anthropic format...")
        events = []
        
        with patch('kiro.streaming_anthropic.parse_kiro_stream', mock_parse_kiro_stream):
            with patch('kiro.streaming_anthropic.parse_bracket_tool_calls', return_value=bracket_tool_calls):
                async for event in stream_kiro_to_anthropic(
                    mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
                ):
                    events.append(event)
        
        print(f"Received {len(events)} events")
        
        # Should have tool_use block from bracket tool calls
        tool_use_events = [e for e in events if "tool_use" in e and "content_block_start" in e]
        assert len(tool_use_events) >= 1
        print("✓ Bracket tool calls handled correctly")
    
    @pytest.mark.asyncio
    async def test_closes_response_on_completion(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Closes response on completion.
        Goal: Verify resource cleanup.
        """
        print("Setup: Mock stream...")
        
        async def mock_parse_kiro_stream(*args, **kwargs):
            yield KiroEvent(type="content", content="Hello")
        
        print("Action: Streaming to Anthropic format...")
        
        with patch('kiro.streaming_anthropic.parse_kiro_stream', mock_parse_kiro_stream):
            with patch('kiro.streaming_anthropic.parse_bracket_tool_calls', return_value=[]):
                async for event in stream_kiro_to_anthropic(
                    mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
                ):
                    pass
        
        print("Check: response.aclose() should be called...")
        mock_response.aclose.assert_called()
        print("✓ Response closed on completion")
    
    @pytest.mark.asyncio
    async def test_closes_response_on_error(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Closes response on error.
        Goal: Verify resource cleanup on error.
        """
        print("Setup: Mock stream that raises error...")
        
        async def mock_parse_kiro_stream(*args, **kwargs):
            yield KiroEvent(type="content", content="Hello")
            raise RuntimeError("Test error")
        
        print("Action: Streaming to Anthropic format with error...")
        
        with patch('kiro.streaming_anthropic.parse_kiro_stream', mock_parse_kiro_stream):
            with patch('kiro.streaming_anthropic.parse_bracket_tool_calls', return_value=[]):
                try:
                    async for event in stream_kiro_to_anthropic(
                        mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
                    ):
                        pass
                except RuntimeError:
                    pass
        
        print("Check: response.aclose() should be called...")
        mock_response.aclose.assert_called()
        print("✓ Response closed on error")


# ==================================================================================================
# Tests for collect_anthropic_response()
# ==================================================================================================

class TestCollectAnthropicResponse:
    """Tests for collect_anthropic_response() function."""
    
    @pytest.mark.asyncio
    async def test_collects_text_content(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Collects text content into response.
        Goal: Verify content collection.
        """
        print("Setup: Mock stream result with content...")
        
        mock_result = StreamResult(
            content="Hello, world!",
            thinking_content="",
            tool_calls=[],
            usage=None,
            context_usage_percentage=None
        )
        
        print("Action: Collecting Anthropic response...")
        
        with patch('kiro.streaming_anthropic.collect_stream_to_result', return_value=mock_result):
            result = await collect_anthropic_response(
                mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
            )
        
        print(f"Result: {result}")
        
        assert result["type"] == "message"
        assert result["role"] == "assistant"
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "Hello, world!"
        print("✓ Text content collected correctly")
    
    @pytest.mark.asyncio
    async def test_collects_tool_use_content(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Collects tool use into response.
        Goal: Verify tool use collection.
        """
        print("Setup: Mock stream result with tool calls...")
        
        mock_result = StreamResult(
            content="Let me check",
            thinking_content="",
            tool_calls=[
                {
                    "id": "toolu_123",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"city": "Moscow"}'
                    }
                }
            ],
            usage=None,
            context_usage_percentage=None
        )
        
        print("Action: Collecting Anthropic response...")
        
        with patch('kiro.streaming_anthropic.collect_stream_to_result', return_value=mock_result):
            result = await collect_anthropic_response(
                mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
            )
        
        print(f"Result: {result}")
        
        # Should have text and tool_use blocks
        assert len(result["content"]) == 2
        
        text_block = result["content"][0]
        assert text_block["type"] == "text"
        
        tool_block = result["content"][1]
        assert tool_block["type"] == "tool_use"
        assert tool_block["name"] == "get_weather"
        assert tool_block["input"] == {"city": "Moscow"}
        print("✓ Tool use content collected correctly")
    
    @pytest.mark.asyncio
    async def test_sets_stop_reason_end_turn(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Sets stop_reason to end_turn for normal completion.
        Goal: Verify stop reason.
        """
        print("Setup: Mock stream result without tool calls...")
        
        mock_result = StreamResult(
            content="Hello",
            thinking_content="",
            tool_calls=[],
            usage=None,
            context_usage_percentage=None
        )
        
        print("Action: Collecting Anthropic response...")
        
        with patch('kiro.streaming_anthropic.collect_stream_to_result', return_value=mock_result):
            result = await collect_anthropic_response(
                mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
            )
        
        print(f"stop_reason: {result['stop_reason']}")
        assert result["stop_reason"] == "end_turn"
        print("✓ stop_reason is end_turn")
    
    @pytest.mark.asyncio
    async def test_sets_stop_reason_tool_use(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Sets stop_reason to tool_use when tools present.
        Goal: Verify stop reason for tool calls.
        """
        print("Setup: Mock stream result with tool calls...")
        
        mock_result = StreamResult(
            content="",
            thinking_content="",
            tool_calls=[{"id": "call_1", "function": {"name": "func1", "arguments": "{}"}}],
            usage=None,
            context_usage_percentage=None
        )
        
        print("Action: Collecting Anthropic response...")
        
        with patch('kiro.streaming_anthropic.collect_stream_to_result', return_value=mock_result):
            result = await collect_anthropic_response(
                mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
            )
        
        print(f"stop_reason: {result['stop_reason']}")
        assert result["stop_reason"] == "tool_use"
        print("✓ stop_reason is tool_use")
    
    @pytest.mark.asyncio
    async def test_includes_usage_info(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Includes usage information in response.
        Goal: Verify usage is included.
        """
        print("Setup: Mock stream result...")
        
        mock_result = StreamResult(
            content="Hello, world!",
            thinking_content="",
            tool_calls=[],
            usage=None,
            context_usage_percentage=None
        )
        
        print("Action: Collecting Anthropic response...")
        
        with patch('kiro.streaming_anthropic.collect_stream_to_result', return_value=mock_result):
            with patch('kiro.streaming_anthropic.estimate_request_tokens', return_value={"total_tokens": 10}):
                with patch('kiro.streaming_anthropic.count_tokens', return_value=5):
                    result = await collect_anthropic_response(
                        mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager,
                        request_messages=[{"role": "user", "content": "Hi"}]
                    )
        
        print(f"Usage: {result['usage']}")
        assert "input_tokens" in result["usage"]
        assert "output_tokens" in result["usage"]
        print("✓ Usage info included")
    
    @pytest.mark.asyncio
    async def test_generates_message_id(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Generates message ID for response.
        Goal: Verify message ID is present.
        """
        print("Setup: Mock stream result...")
        
        mock_result = StreamResult(
            content="Hello",
            thinking_content="",
            tool_calls=[],
            usage=None,
            context_usage_percentage=None
        )
        
        print("Action: Collecting Anthropic response...")
        
        with patch('kiro.streaming_anthropic.collect_stream_to_result', return_value=mock_result):
            result = await collect_anthropic_response(
                mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
            )
        
        print(f"Message ID: {result['id']}")
        assert result["id"].startswith("msg_")
        print("✓ Message ID generated")
    
    @pytest.mark.asyncio
    async def test_includes_model_name(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Includes model name in response.
        Goal: Verify model is included.
        """
        print("Setup: Mock stream result...")
        
        mock_result = StreamResult(
            content="Hello",
            thinking_content="",
            tool_calls=[],
            usage=None,
            context_usage_percentage=None
        )
        
        print("Action: Collecting Anthropic response...")
        
        with patch('kiro.streaming_anthropic.collect_stream_to_result', return_value=mock_result):
            result = await collect_anthropic_response(
                mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
            )
        
        print(f"Model: {result['model']}")
        assert result["model"] == "claude-sonnet-4"
        print("✓ Model name included")
    
    @pytest.mark.asyncio
    async def test_parses_tool_arguments_from_string(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Parses tool arguments from JSON string.
        Goal: Verify arguments are parsed to dict.
        """
        print("Setup: Mock stream result with string arguments...")
        
        mock_result = StreamResult(
            content="",
            thinking_content="",
            tool_calls=[
                {
                    "id": "call_1",
                    "function": {
                        "name": "func1",
                        "arguments": '{"key": "value"}'  # String, not dict
                    }
                }
            ],
            usage=None,
            context_usage_percentage=None
        )
        
        print("Action: Collecting Anthropic response...")
        
        with patch('kiro.streaming_anthropic.collect_stream_to_result', return_value=mock_result):
            result = await collect_anthropic_response(
                mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
            )
        
        print(f"Result: {result}")
        
        # Tool input should be parsed to dict
        tool_block = result["content"][0]  # Only tool_use since content is empty
        assert tool_block["type"] == "tool_use"
        assert tool_block["input"] == {"key": "value"}
        assert isinstance(tool_block["input"], dict)
        print("✓ Tool arguments parsed from string to dict")
    
    @pytest.mark.asyncio
    async def test_handles_invalid_json_arguments(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Handles invalid JSON in tool arguments.
        Goal: Verify graceful handling of invalid JSON.
        """
        print("Setup: Mock stream result with invalid JSON arguments...")
        
        mock_result = StreamResult(
            content="",
            thinking_content="",
            tool_calls=[
                {
                    "id": "call_1",
                    "function": {
                        "name": "func1",
                        "arguments": "not valid json"  # Invalid JSON
                    }
                }
            ],
            usage=None,
            context_usage_percentage=None
        )
        
        print("Action: Collecting Anthropic response...")
        
        with patch('kiro.streaming_anthropic.collect_stream_to_result', return_value=mock_result):
            result = await collect_anthropic_response(
                mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
            )
        
        print(f"Result: {result}")
        
        # Should handle gracefully with empty dict
        tool_block = result["content"][0]
        assert tool_block["type"] == "tool_use"
        assert tool_block["input"] == {}
        print("✓ Invalid JSON arguments handled gracefully")
    
    @pytest.mark.asyncio
    async def test_handles_empty_content(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Handles empty content in response.
        Goal: Verify empty content is handled.
        """
        print("Setup: Mock stream result with empty content...")
        
        mock_result = StreamResult(
            content="",
            thinking_content="",
            tool_calls=[],
            usage=None,
            context_usage_percentage=None
        )
        
        print("Action: Collecting Anthropic response...")
        
        with patch('kiro.streaming_anthropic.collect_stream_to_result', return_value=mock_result):
            result = await collect_anthropic_response(
                mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
            )
        
        print(f"Result: {result}")
        
        # Content should be empty list
        assert result["content"] == []
        print("✓ Empty content handled correctly")


# ==================================================================================================
# Tests for error handling
# ==================================================================================================

class TestStreamingAnthropicErrorHandling:
    """Tests for error handling in streaming_anthropic."""
    
    @pytest.mark.asyncio
    async def test_propagates_first_token_timeout_error(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Propagates FirstTokenTimeoutError.
        Goal: Verify timeout error is not caught internally.
        """
        from kiro.streaming_core import FirstTokenTimeoutError
        
        print("Setup: Mock stream that raises timeout...")
        
        async def mock_parse_kiro_stream(*args, **kwargs):
            raise FirstTokenTimeoutError("Timeout!")
            yield  # Make it a generator
        
        print("Action: Streaming to Anthropic format with timeout...")
        
        with patch('kiro.streaming_anthropic.parse_kiro_stream', mock_parse_kiro_stream):
            with pytest.raises(FirstTokenTimeoutError):
                async for event in stream_kiro_to_anthropic(
                    mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
                ):
                    pass
        
        print("✓ FirstTokenTimeoutError propagated correctly")
    
    @pytest.mark.asyncio
    async def test_propagates_generator_exit(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Propagates GeneratorExit.
        Goal: Verify client disconnect is handled.
        """
        print("Setup: Mock stream that raises GeneratorExit...")
        
        async def mock_parse_kiro_stream(*args, **kwargs):
            yield KiroEvent(type="content", content="Hello")
            raise GeneratorExit()
        
        print("Action: Streaming to Anthropic format with GeneratorExit...")
        
        with patch('kiro.streaming_anthropic.parse_kiro_stream', mock_parse_kiro_stream):
            with patch('kiro.streaming_anthropic.parse_bracket_tool_calls', return_value=[]):
                with pytest.raises(GeneratorExit):
                    async for event in stream_kiro_to_anthropic(
                        mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
                    ):
                        pass
        
        print("✓ GeneratorExit propagated correctly")
    
    @pytest.mark.asyncio
    async def test_yields_error_event_on_exception(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Yields error event on exception.
        Goal: Verify error event is sent to client.
        """
        print("Setup: Mock stream that raises RuntimeError...")
        
        async def mock_parse_kiro_stream(*args, **kwargs):
            yield KiroEvent(type="content", content="Hello")
            raise RuntimeError("Test error")
        
        print("Action: Streaming to Anthropic format with error...")
        events = []
        
        with patch('kiro.streaming_anthropic.parse_kiro_stream', mock_parse_kiro_stream):
            with patch('kiro.streaming_anthropic.parse_bracket_tool_calls', return_value=[]):
                try:
                    async for event in stream_kiro_to_anthropic(
                        mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
                    ):
                        events.append(event)
                except RuntimeError:
                    pass
        
        print(f"Received {len(events)} events")
        
        # Should have error event
        error_events = [e for e in events if "event: error" in e]
        assert len(error_events) >= 1
        assert "Test error" in error_events[0]
        print("✓ Error event yielded on exception")
    
    @pytest.mark.asyncio
    async def test_closes_response_in_finally(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Closes response in finally block.
        Goal: Verify resource cleanup always happens.
        """
        print("Setup: Mock stream that raises error...")
        
        async def mock_parse_kiro_stream(*args, **kwargs):
            raise ValueError("Test error")
            yield  # Make it a generator
        
        print("Action: Streaming to Anthropic format with error...")
        
        with patch('kiro.streaming_anthropic.parse_kiro_stream', mock_parse_kiro_stream):
            try:
                async for event in stream_kiro_to_anthropic(
                    mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
                ):
                    pass
            except ValueError:
                pass
        
        print("Check: response.aclose() should be called...")
        mock_response.aclose.assert_called()
        print("✓ Response closed in finally block")


# ==================================================================================================
# Tests for thinking content handling
# ==================================================================================================

class TestStreamingAnthropicThinkingContent:
    """Tests for thinking content handling in Anthropic streaming."""
    
    @pytest.mark.asyncio
    async def test_includes_thinking_as_text_when_configured(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Includes thinking content as text when configured.
        Goal: Verify thinking content handling.
        """
        print("Setup: Mock stream with thinking content...")
        
        async def mock_parse_kiro_stream(*args, **kwargs):
            yield KiroEvent(type="thinking", thinking_content="Let me think...")
            yield KiroEvent(type="content", content="Here is my answer")
        
        print("Action: Streaming to Anthropic format with thinking...")
        events = []
        
        with patch('kiro.streaming_anthropic.parse_kiro_stream', mock_parse_kiro_stream):
            with patch('kiro.streaming_anthropic.parse_bracket_tool_calls', return_value=[]):
                with patch('kiro.streaming_anthropic.FAKE_REASONING_HANDLING', 'include_as_text'):
                    async for event in stream_kiro_to_anthropic(
                        mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
                    ):
                        events.append(event)
        
        print(f"Received {len(events)} events")
        
        # Should have thinking content as text delta
        delta_events = [e for e in events if "content_block_delta" in e]
        thinking_found = any("Let me think" in e for e in delta_events)
        assert thinking_found
        print("✓ Thinking content included as text")
    
    @pytest.mark.asyncio
    async def test_strips_thinking_when_configured(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Strips thinking content when configured.
        Goal: Verify thinking content is stripped.
        """
        print("Setup: Mock stream with thinking content...")
        
        async def mock_parse_kiro_stream(*args, **kwargs):
            yield KiroEvent(type="thinking", thinking_content="Let me think...")
            yield KiroEvent(type="content", content="Here is my answer")
        
        print("Action: Streaming to Anthropic format with strip mode...")
        events = []
        
        with patch('kiro.streaming_anthropic.parse_kiro_stream', mock_parse_kiro_stream):
            with patch('kiro.streaming_anthropic.parse_bracket_tool_calls', return_value=[]):
                with patch('kiro.streaming_anthropic.FAKE_REASONING_HANDLING', 'strip'):
                    async for event in stream_kiro_to_anthropic(
                        mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
                    ):
                        events.append(event)
        
        print(f"Received {len(events)} events")
        
        # Should NOT have thinking content
        delta_events = [e for e in events if "content_block_delta" in e]
        thinking_found = any("Let me think" in e for e in delta_events)
        assert not thinking_found
        print("✓ Thinking content stripped")


# ==================================================================================================
# Tests for context usage calculation
# ==================================================================================================

class TestStreamingAnthropicContextUsage:
    """Tests for context usage calculation in Anthropic streaming."""
    
    @pytest.mark.asyncio
    async def test_calculates_tokens_from_context_usage(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Calculates tokens from context usage percentage.
        Goal: Verify token calculation.
        """
        print("Setup: Mock stream with context usage...")
        
        async def mock_parse_kiro_stream(*args, **kwargs):
            yield KiroEvent(type="content", content="Hello")
            yield KiroEvent(type="context_usage", context_usage_percentage=5.0)
        
        print("Action: Streaming to Anthropic format...")
        events = []
        
        with patch('kiro.streaming_anthropic.parse_kiro_stream', mock_parse_kiro_stream):
            with patch('kiro.streaming_anthropic.parse_bracket_tool_calls', return_value=[]):
                async for event in stream_kiro_to_anthropic(
                    mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
                ):
                    events.append(event)
        
        print(f"Received {len(events)} events")
        
        # message_delta should have usage with output_tokens
        message_delta_events = [e for e in events if "message_delta" in e]
        assert len(message_delta_events) >= 1
        assert "output_tokens" in message_delta_events[0]
        print("✓ Tokens calculated from context usage")
    
    @pytest.mark.asyncio
    async def test_uses_request_messages_for_input_tokens(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Uses request messages for input token count.
        Goal: Verify input tokens are counted from request.
        """
        print("Setup: Mock stream...")
        
        async def mock_parse_kiro_stream(*args, **kwargs):
            yield KiroEvent(type="content", content="Hello")
        
        request_messages = [
            {"role": "user", "content": "Hi there!"}
        ]
        
        print("Action: Streaming to Anthropic format with request messages...")
        events = []
        
        with patch('kiro.streaming_anthropic.parse_kiro_stream', mock_parse_kiro_stream):
            with patch('kiro.streaming_anthropic.parse_bracket_tool_calls', return_value=[]):
                with patch('kiro.streaming_anthropic.estimate_request_tokens', return_value={"total_tokens": 10}) as mock_estimate:
                    async for event in stream_kiro_to_anthropic(
                        mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager,
                        request_messages=request_messages
                    ):
                        events.append(event)
                    
                    # Verify estimate_request_tokens was called
                    mock_estimate.assert_called_once_with(
                        messages=request_messages,
                        tools=None,
                        system_prompt=None,
                        apply_claude_correction=False
                    )
        
        print("✓ Request messages used for input token count")

    @pytest.mark.asyncio
    async def test_uses_tools_and_system_for_input_tokens(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Includes request tools and system in input token estimation.
        Goal: Verify Anthropic fallback token counting uses full request.
        """
        print("Setup: Mock stream...")

        async def mock_parse_kiro_stream(*args, **kwargs):
            yield KiroEvent(type="content", content="Hello")

        request_messages = [{"role": "user", "content": "Hi"}]
        request_tools = [{"name": "get_weather", "input_schema": {"type": "object"}}]
        request_system = [{"type": "text", "text": "你是助手"}]

        with patch('kiro.streaming_anthropic.parse_kiro_stream', mock_parse_kiro_stream):
            with patch('kiro.streaming_anthropic.parse_bracket_tool_calls', return_value=[]):
                with patch('kiro.streaming_anthropic.estimate_request_tokens', return_value={"total_tokens": 12}) as mock_estimate:
                    events = []
                    async for event in stream_kiro_to_anthropic(
                        mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager,
                        request_messages=request_messages,
                        request_tools=request_tools,
                        request_system=request_system,
                    ):
                        events.append(event)

                    assert events, "Should produce streaming events"
                    mock_estimate.assert_called_once_with(
                        messages=request_messages,
                        tools=request_tools,
                        system_prompt=request_system,
                        apply_claude_correction=False
                    )
        print("✓ Request tools and system included in token count")

    @pytest.mark.asyncio
    async def test_context_usage_zero_keeps_fallback_estimate(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Keeps fallback estimate when context usage is 0.
        Goal: Prevent overriding with zero prompt tokens.
        """
        async def mock_parse_kiro_stream(*args, **kwargs):
            yield KiroEvent(type="content", content="Hello")
            yield KiroEvent(type="context_usage", context_usage_percentage=0.0)

        events = []
        with patch('kiro.streaming_anthropic.parse_kiro_stream', mock_parse_kiro_stream):
            with patch('kiro.streaming_anthropic.parse_bracket_tool_calls', return_value=[]):
                with patch('kiro.streaming_anthropic.estimate_request_tokens', return_value={"total_tokens": 99}):
                    async for event in stream_kiro_to_anthropic(
                        mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager,
                        request_messages=[{"role": "user", "content": "hi"}]
                    ):
                        events.append(event)

        message_start_event = next(e for e in events if "event: message_start" in e)
        assert '"input_tokens": 99' in message_start_event

    @pytest.mark.asyncio
    async def test_non_streaming_passes_upstream_cache_usage_fields(self, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Passes through upstream cache usage fields when available.
        Goal: Ensure no fake values, only real upstream usage keys.
        """
        mock_result = MagicMock(
            content="done",
            thinking_content="",
            tool_calls=[],
            context_usage_percentage=None,
            usage={"cacheReadInputTokens": 12, "cacheCreationInputTokens": 34},
        )

        with patch('kiro.streaming_anthropic.collect_stream_to_result', return_value=mock_result):
            with patch('kiro.streaming_anthropic.generate_message_id', return_value="msg_test"):
                response_data = await collect_anthropic_response(
                    mock_response, "claude-sonnet-4", mock_model_cache, mock_auth_manager
                )

        usage = response_data["usage"]
        assert usage["cache_read_input_tokens"] == 12
        assert usage["cache_creation_input_tokens"] == 34


# ==================================================================================================
# Tests for generate_thinking_signature()
# ==================================================================================================

class TestGenerateThinkingSignature:
    """
    Tests for generate_thinking_signature() function.
    
    This function generates placeholder signatures for thinking content blocks.
    In real Anthropic API, this is a cryptographic signature for verification.
    Since we use fake reasoning via tag injection, we generate a placeholder.
    """
    
    def test_generates_signature_with_prefix(self):
        """
        What it does: Generates signature with 'sig_' prefix.
        Goal: Verify signature format matches expected pattern.
        """
        print("Action: Generating thinking signature...")
        signature = generate_thinking_signature()
        
        print(f"Generated signature: {signature}")
        assert signature.startswith("sig_")
        print("✓ Signature has correct prefix")
    
    def test_generates_unique_signatures(self):
        """
        What it does: Generates unique signatures.
        Goal: Verify signatures are unique across multiple calls.
        """
        print("Action: Generating multiple signatures...")
        signatures = [generate_thinking_signature() for _ in range(100)]
        
        print(f"Generated {len(signatures)} signatures")
        unique_signatures = set(signatures)
        print(f"Unique signatures: {len(unique_signatures)}")
        
        assert len(unique_signatures) == 100
        print("✓ All signatures are unique")
    
    def test_signature_has_correct_length(self):
        """
        What it does: Verifies signature length.
        Goal: Ensure signature format is consistent.
        """
        print("Action: Generating signature...")
        signature = generate_thinking_signature()
        
        # Format: sig_ + 32 hex chars
        print(f"Generated signature: {signature}, length: {len(signature)}")
        assert len(signature) == 4 + 32  # "sig_" + 32 chars
        print("✓ Signature has correct length")
    
    def test_signature_contains_only_valid_characters(self):
        """
        What it does: Verifies signature contains only valid hex characters.
        Goal: Ensure signature is properly formatted.
        """
        print("Action: Generating signature...")
        signature = generate_thinking_signature()
        
        print(f"Generated signature: {signature}")
        # Remove prefix and check remaining chars are hex
        hex_part = signature[4:]  # Remove "sig_"
        assert all(c in '0123456789abcdef' for c in hex_part)
        print("✓ Signature contains only valid hex characters")


# ==================================================================================================
# Tests for stream_with_first_token_retry_anthropic()
# ==================================================================================================

class TestStreamWithFirstTokenRetryAnthropic:
    """
    Tests for stream_with_first_token_retry_anthropic() function.
    
    This function wraps stream_kiro_to_anthropic with automatic retry
    on first token timeout. It uses the generic stream_with_first_token_retry
    from streaming_core.py with Anthropic-specific error formatting.
    """
    
    @pytest.mark.asyncio
    async def test_yields_chunks_on_success(self, mock_model_cache, mock_auth_manager):
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
        
        async def mock_parse_kiro_stream(*args, **kwargs):
            yield KiroEvent(type="content", content="Hello")
        
        print("Action: Streaming with retry wrapper...")
        chunks = []
        
        with patch('kiro.streaming_anthropic.parse_kiro_stream', mock_parse_kiro_stream):
            with patch('kiro.streaming_anthropic.parse_bracket_tool_calls', return_value=[]):
                async for chunk in stream_with_first_token_retry_anthropic(
                    make_request=mock_make_request,
                    model="claude-sonnet-4",
                    model_cache=mock_model_cache,
                    auth_manager=mock_auth_manager,
                    max_retries=3,
                    first_token_timeout=30
                ):
                    chunks.append(chunk)
        
        print(f"Received {len(chunks)} chunks")
        assert len(chunks) > 0
        assert any("message_start" in c for c in chunks)
        print("✓ Chunks yielded on success")
    
    @pytest.mark.asyncio
    async def test_retries_on_first_token_timeout(self, mock_model_cache, mock_auth_manager):
        """
        What it does: Retries on first token timeout.
        Goal: Verify retry logic is triggered.
        """
        from kiro.streaming_core import FirstTokenTimeoutError
        
        print("Setup: Mock request that times out then succeeds...")
        
        call_count = 0
        
        async def mock_make_request():
            nonlocal call_count
            call_count += 1
            response = AsyncMock()
            response.status_code = 200
            response.aclose = AsyncMock()
            return response
        
        async def mock_stream_kiro_to_anthropic(*args, **kwargs):
            nonlocal call_count
            if call_count == 1:
                raise FirstTokenTimeoutError("Timeout on first attempt")
            yield "event: message_start\ndata: {}\n\n"
            yield "event: message_stop\ndata: {}\n\n"
        
        print("Action: Streaming with retry on timeout...")
        chunks = []
        
        with patch('kiro.streaming_anthropic.stream_kiro_to_anthropic', mock_stream_kiro_to_anthropic):
            async for chunk in stream_with_first_token_retry_anthropic(
                make_request=mock_make_request,
                model="claude-sonnet-4",
                model_cache=mock_model_cache,
                auth_manager=mock_auth_manager,
                max_retries=3,
                first_token_timeout=30
            ):
                chunks.append(chunk)
        
        print(f"Call count: {call_count}")
        print(f"Received {len(chunks)} chunks")
        
        assert call_count == 2  # First timeout, second success
        assert len(chunks) > 0
        print("✓ Retry on timeout works correctly")
    
    @pytest.mark.asyncio
    async def test_raises_anthropic_error_after_all_retries(self, mock_model_cache, mock_auth_manager):
        """
        What it does: Raises Anthropic-formatted error after all retries exhausted.
        Goal: Verify error format matches Anthropic API.
        """
        from kiro.streaming_core import FirstTokenTimeoutError
        
        print("Setup: Mock request that always times out...")
        
        async def mock_make_request():
            response = AsyncMock()
            response.status_code = 200
            response.aclose = AsyncMock()
            return response
        
        async def mock_stream_kiro_to_anthropic(*args, **kwargs):
            raise FirstTokenTimeoutError("Timeout!")
            yield  # Make it a generator
        
        print("Action: Streaming with all retries failing...")
        
        with patch('kiro.streaming_anthropic.stream_kiro_to_anthropic', mock_stream_kiro_to_anthropic):
            with pytest.raises(Exception) as exc_info:
                async for chunk in stream_with_first_token_retry_anthropic(
                    make_request=mock_make_request,
                    model="claude-sonnet-4",
                    model_cache=mock_model_cache,
                    auth_manager=mock_auth_manager,
                    max_retries=2,
                    first_token_timeout=30
                ):
                    pass
        
        print(f"Exception: {exc_info.value}")
        
        # Error should be in Anthropic format (JSON)
        error_json = json.loads(str(exc_info.value))
        assert error_json["type"] == "error"
        assert error_json["error"]["type"] == "timeout_error"
        assert "30" in error_json["error"]["message"]
        print("✓ Anthropic-formatted error raised after all retries")
    
    @pytest.mark.asyncio
    async def test_raises_anthropic_error_on_http_error(self, mock_model_cache, mock_auth_manager):
        """
        What it does: Raises Anthropic-formatted error on HTTP error.
        Goal: Verify HTTP errors are formatted correctly.
        """
        print("Setup: Mock request that returns HTTP error...")
        
        async def mock_make_request():
            response = AsyncMock()
            response.status_code = 500
            response.aread = AsyncMock(return_value=b"Internal Server Error")
            response.aclose = AsyncMock()
            return response
        
        print("Action: Streaming with HTTP error...")
        
        with pytest.raises(Exception) as exc_info:
            async for chunk in stream_with_first_token_retry_anthropic(
                make_request=mock_make_request,
                model="claude-sonnet-4",
                model_cache=mock_model_cache,
                auth_manager=mock_auth_manager,
                max_retries=2,
                first_token_timeout=30
            ):
                pass
        
        print(f"Exception: {exc_info.value}")
        
        # Error should be in Anthropic format (JSON)
        error_json = json.loads(str(exc_info.value))
        assert error_json["type"] == "error"
        assert error_json["error"]["type"] == "api_error"
        assert "Upstream API error" in error_json["error"]["message"]
        print("✓ Anthropic-formatted error raised on HTTP error")
    
    @pytest.mark.asyncio
    async def test_passes_request_messages_to_stream(self, mock_model_cache, mock_auth_manager):
        """
        What it does: Passes request_messages to underlying stream function.
        Goal: Verify token counting parameters are forwarded.
        """
        print("Setup: Mock request with messages...")
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.aclose = AsyncMock()
        
        async def mock_make_request():
            return mock_response
        
        captured_kwargs = {}
        
        async def mock_stream_kiro_to_anthropic(*args, **kwargs):
            captured_kwargs.update(kwargs)
            yield "event: message_start\ndata: {}\n\n"
            yield "event: message_stop\ndata: {}\n\n"
        
        request_messages = [{"role": "user", "content": "Hello"}]
        
        print("Action: Streaming with request_messages...")
        
        with patch('kiro.streaming_anthropic.stream_kiro_to_anthropic', mock_stream_kiro_to_anthropic):
            async for chunk in stream_with_first_token_retry_anthropic(
                make_request=mock_make_request,
                model="claude-sonnet-4",
                model_cache=mock_model_cache,
                auth_manager=mock_auth_manager,
                request_messages=request_messages
            ):
                pass
        
        print(f"Captured kwargs: {captured_kwargs}")
        assert captured_kwargs.get("request_messages") == request_messages
        print("✓ request_messages passed to stream function")
    
    @pytest.mark.asyncio
    async def test_uses_configured_max_retries(self, mock_model_cache, mock_auth_manager):
        """
        What it does: Uses configured max_retries value.
        Goal: Verify max_retries parameter is respected.
        """
        from kiro.streaming_core import FirstTokenTimeoutError
        
        print("Setup: Mock request that always times out...")
        
        call_count = 0
        
        async def mock_make_request():
            nonlocal call_count
            call_count += 1
            response = AsyncMock()
            response.status_code = 200
            response.aclose = AsyncMock()
            return response
        
        async def mock_stream_kiro_to_anthropic(*args, **kwargs):
            raise FirstTokenTimeoutError("Timeout!")
            yield  # Make it a generator
        
        print("Action: Streaming with max_retries=5...")
        
        with patch('kiro.streaming_anthropic.stream_kiro_to_anthropic', mock_stream_kiro_to_anthropic):
            try:
                async for chunk in stream_with_first_token_retry_anthropic(
                    make_request=mock_make_request,
                    model="claude-sonnet-4",
                    model_cache=mock_model_cache,
                    auth_manager=mock_auth_manager,
                    max_retries=5,
                    first_token_timeout=30
                ):
                    pass
            except Exception:
                pass
        
        print(f"Call count: {call_count}")
        assert call_count == 5  # Should try exactly 5 times
        print("✓ max_retries parameter respected")
