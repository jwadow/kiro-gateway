# -*- coding: utf-8 -*-

"""
Unit tests for streaming_responses module.

Tests for:
- Chat Completions response conversion to Responses API objects
- Responses API semantic streaming events
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kiro.streaming_responses import chat_completion_to_response, stream_kiro_to_responses


@pytest.fixture
def mock_model_cache():
    """Mock for ModelInfoCache."""
    cache = MagicMock()
    cache.get_max_input_tokens.return_value = 200000
    return cache


@pytest.fixture
def mock_auth_manager():
    """Mock for KiroAuthManager."""
    return MagicMock()


@pytest.fixture
def mock_http_client():
    """Mock for httpx.AsyncClient."""
    return AsyncMock()


@pytest.fixture
def mock_response():
    """Mock for httpx.Response."""
    response = AsyncMock()
    response.status_code = 200
    response.aclose = AsyncMock()
    return response


class TestChatCompletionToResponse:
    """Tests for chat_completion_to_response."""

    def test_converts_text_message_to_response_object(self):
        """
        What it does: Converts a normal chat completion into a Responses object.
        Purpose: Ensure non-streaming /v1/responses returns the expected shape.
        """
        print("Setup: Chat completion with text...")
        chat_response = {
            "id": "chatcmpl_123",
            "created": 123,
            "model": "claude-sonnet-4-5",
            "choices": [{
                "message": {"role": "assistant", "content": "Hello there"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        }

        print("Action: Converting to Responses object...")
        response = chat_completion_to_response(chat_response, response_id="resp_test")

        assert response["id"] == "resp_test"
        assert response["object"] == "response"
        assert response["status"] == "completed"
        assert response["output_text"] == "Hello there"
        assert response["output"][0]["type"] == "message"
        assert response["output"][0]["content"][0]["type"] == "output_text"
        assert response["usage"]["input_tokens"] == 3
        assert response["usage"]["output_tokens"] == 2

    def test_converts_tool_calls_to_function_call_items(self):
        """
        What it does: Converts chat tool_calls into Responses function_call output items.
        Purpose: Ensure Codex can receive tool requests from /v1/responses.
        """
        print("Setup: Chat completion with tool call...")
        chat_response = {
            "created": 123,
            "model": "claude-sonnet-4-5",
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "call_123",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path":"README.md"}'},
                    }],
                },
            }],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        }

        print("Action: Converting to Responses object...")
        response = chat_completion_to_response(chat_response, response_id="resp_test")

        assert response["output_text"] == ""
        assert len(response["output"]) == 1
        assert response["output"][0]["type"] == "function_call"
        assert response["output"][0]["call_id"] == "call_123"
        assert response["output"][0]["name"] == "read_file"


class TestStreamKiroToResponses:
    """Tests for Responses API streaming events."""

    @pytest.mark.asyncio
    async def test_yields_responses_text_delta_events(self, mock_http_client, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Converts chat stream chunks into Responses API text delta events.
        Purpose: Ensure streaming clients receive semantic Responses events.
        """
        print("Setup: Mock chat stream with text and usage...")

        async def mock_stream_kiro_to_openai(*args, **kwargs):
            yield 'data: {"choices":[{"delta":{"role":"assistant","content":"Hel"},"finish_reason":null}]}\n\n'
            yield 'data: {"choices":[{"delta":{"content":"lo"},"finish_reason":null}]}\n\n'
            yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":2,"total_tokens":3}}\n\n'
            yield "data: [DONE]\n\n"

        print("Action: Streaming to Responses format...")
        chunks = []
        with patch("kiro.streaming_responses.stream_kiro_to_openai", mock_stream_kiro_to_openai):
            async for chunk in stream_kiro_to_responses(
                mock_http_client,
                mock_response,
                "claude-sonnet-4-5",
                mock_model_cache,
                mock_auth_manager,
            ):
                chunks.append(chunk)

        assert any("event: response.created" in chunk for chunk in chunks)
        assert any("event: response.output_text.delta" in chunk and '"delta": "Hel"' in chunk for chunk in chunks)
        assert any("event: response.output_text.done" in chunk and '"text": "Hello"' in chunk for chunk in chunks)
        assert any("event: response.completed" in chunk and '"output_text": "Hello"' in chunk for chunk in chunks)
        assert chunks[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_yields_function_call_items_for_tool_calls(self, mock_http_client, mock_response, mock_model_cache, mock_auth_manager):
        """
        What it does: Converts chat stream tool calls into Responses output items.
        Purpose: Ensure streaming /v1/responses exposes function calls.
        """
        print("Setup: Mock chat stream with tool call...")

        async def mock_stream_kiro_to_openai(*args, **kwargs):
            payload = {
                "choices": [{
                    "delta": {
                        "tool_calls": [{
                            "id": "call_123",
                            "type": "function",
                            "function": {"name": "shell", "arguments": '{"cmd":"ls"}'},
                        }]
                    },
                    "finish_reason": None,
                }]
            }
            yield f"data: {json.dumps(payload)}\n\n"
            yield 'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}\n\n'
            yield "data: [DONE]\n\n"

        print("Action: Streaming to Responses format...")
        chunks = []
        with patch("kiro.streaming_responses.stream_kiro_to_openai", mock_stream_kiro_to_openai):
            async for chunk in stream_kiro_to_responses(
                mock_http_client,
                mock_response,
                "claude-sonnet-4-5",
                mock_model_cache,
                mock_auth_manager,
            ):
                chunks.append(chunk)

        tool_item_chunks = [chunk for chunk in chunks if '"type": "function_call"' in chunk]
        assert len(tool_item_chunks) >= 1
        assert any('"call_id": "call_123"' in chunk for chunk in tool_item_chunks)
        assert any('"name": "shell"' in chunk for chunk in tool_item_chunks)
        assert any("event: response.function_call_arguments.delta" in chunk for chunk in chunks)
        assert any("event: response.function_call_arguments.done" in chunk for chunk in chunks)
