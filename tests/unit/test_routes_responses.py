# -*- coding: utf-8 -*-

"""
Unit tests for the Responses API route (routes_responses.py, POST /v1/responses).

The router is mounted on a fresh FastAPI app so the main app lifespan
(credentials loading) is not needed. The chat pipeline is either mocked at
the chat_completions boundary or exercised with mocked Kiro HTTP/streaming.
"""

import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient

from kiro.config import PROXY_API_KEY
from kiro.routes_responses import router


AUTH = {"Authorization": f"Bearer {PROXY_API_KEY}"}


@pytest.fixture
def app() -> FastAPI:
    """Fresh app with only the Responses router."""
    application = FastAPI()
    application.include_router(router)
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """TestClient without lifespan."""
    return TestClient(app)


def chat_json(message: Dict[str, Any], finish_reason: str = "stop") -> JSONResponse:
    """Chat completion JSONResponse as returned by chat_completions."""
    return JSONResponse(content={
        "id": "chatcmpl-1", "object": "chat.completion", "created": 1700000000, "model": "m",
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
    })


def parse_events(text: str) -> List[Dict[str, Any]]:
    """Parse Responses SSE body into events."""
    events = []
    for frame in text.split("\n\n"):
        if frame.strip():
            event_line, data_line = frame.split("\n")[:2]
            event = json.loads(data_line[len("data: "):])
            assert event["type"] == event_line[len("event: "):]
            events.append(event)
    return events


class TestResponsesAuth:
    """Authentication tests."""

    def test_missing_api_key_returns_401(self, client):
        """
        What it does: Calls endpoint without Authorization.
        Purpose: Endpoint must require the proxy API key.
        """
        resp = client.post("/v1/responses", json={"model": "m", "input": "hi"})
        assert resp.status_code == 401

    def test_wrong_api_key_returns_401(self, client):
        """
        What it does: Calls endpoint with a wrong key.
        Purpose: Invalid keys must be rejected.
        """
        resp = client.post("/v1/responses", json={"model": "m", "input": "hi"},
                           headers={"Authorization": "Bearer nope"})
        assert resp.status_code == 401

    def test_auth_checked_before_pipeline(self, client):
        """
        What it does: Ensures pipeline is not called on auth failure.
        Purpose: No upstream work for unauthenticated requests.
        """
        with patch("kiro.routes_responses.chat_completions", new=AsyncMock()) as mock_chat:
            client.post("/v1/responses", json={"model": "m", "input": "hi"})
        mock_chat.assert_not_called()


class TestResponsesValidation:
    """Request validation tests."""

    def test_previous_response_id_returns_400_openai_error(self, client):
        """
        What it does: Sends previous_response_id.
        Purpose: Stateless gateway must reject it with an OpenAI-shaped error.
        """
        with patch("kiro.routes_responses.chat_completions", new=AsyncMock()) as mock_chat:
            resp = client.post("/v1/responses", headers=AUTH,
                               json={"model": "m", "input": "hi", "previous_response_id": "resp_1"})
        assert resp.status_code == 400
        error = resp.json()["error"]
        assert set(error) == {"message", "type", "param", "code"}
        assert error["type"] == "invalid_request_error"
        assert error["param"] == "previous_response_id"
        mock_chat.assert_not_called()

    def test_malformed_item_returns_400(self, client):
        """
        What it does: Sends an unsupported item type.
        Purpose: Translation errors become 400 with the item path.
        """
        resp = client.post("/v1/responses", headers=AUTH,
                           json={"model": "m", "input": [{"type": "computer_call"}]})
        assert resp.status_code == 400
        assert resp.json()["error"]["param"] == "input[0].type"

    @pytest.mark.parametrize("body", [
        {"input": "hi"},
        {"model": "m"},
        {"model": "m", "input": 5},
        {"model": "m", "input": "hi", "tools": "bad"},
    ])
    def test_schema_violations_return_422(self, client, body):
        """
        What it does: Sends bodies violating the request schema.
        Purpose: Pydantic validation must reject them.
        """
        resp = client.post("/v1/responses", headers=AUTH, json=body)
        assert resp.status_code == 422


class TestResponsesNonStreaming:
    """Non-streaming tests with chat_completions mocked."""

    def test_translates_request_and_response(self, client):
        """
        What it does: Full non-streaming round trip.
        Purpose: Chat request built correctly and response converted.
        """
        mock_chat = AsyncMock(return_value=chat_json({"role": "assistant", "content": "Hello!"}))
        with patch("kiro.routes_responses.chat_completions", new=mock_chat):
            resp = client.post("/v1/responses", headers=AUTH, json={
                "model": "claude-sonnet-4.5", "instructions": "be nice", "input": "hi",
                "max_output_tokens": 50,
                "tools": [{"type": "function", "name": "f", "parameters": {"type": "object"}}],
            })
        assert resp.status_code == 200
        chat_request = mock_chat.call_args.args[1]
        assert [m.role for m in chat_request.messages] == ["system", "user"]
        assert chat_request.max_tokens == 50
        assert chat_request.stream is False
        assert chat_request.tools[0].function.name == "f"

        body = resp.json()
        assert body["object"] == "response"
        assert body["status"] == "completed"
        assert body["output"][0]["content"][0]["text"] == "Hello!"
        assert body["usage"] == {
            "input_tokens": 4, "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": 2, "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": 6,
        }

    def test_tool_call_response(self, client):
        """
        What it does: Converts a tool-call chat response.
        Purpose: function_call items reach the client.
        """
        mock_chat = AsyncMock(return_value=chat_json({
            "role": "assistant", "content": "",
            "tool_calls": [{"id": "call_9", "type": "function", "function": {"name": "f", "arguments": "{}"}}],
        }, finish_reason="tool_calls"))
        with patch("kiro.routes_responses.chat_completions", new=mock_chat):
            body = client.post("/v1/responses", headers=AUTH, json={"model": "m", "input": "x"}).json()
        assert body["output"] == [{
            "type": "function_call", "id": body["output"][0]["id"], "call_id": "call_9",
            "name": "f", "arguments": "{}", "status": "completed",
        }]

    def test_upstream_error_response_is_normalized(self, client):
        """
        What it does: chat_completions returns a Kiro error JSONResponse.
        Purpose: Status preserved, error gains type/param/code fields.
        """
        upstream = JSONResponse(status_code=429, content={"error": {"message": "slow down", "type": "kiro_api_error", "code": 429}})
        with patch("kiro.routes_responses.chat_completions", new=AsyncMock(return_value=upstream)):
            resp = client.post("/v1/responses", headers=AUTH, json={"model": "m", "input": "x"})
        assert resp.status_code == 429
        assert resp.json() == {"error": {"message": "slow down", "type": "kiro_api_error", "param": None, "code": 429}}

    def test_upstream_error_without_error_object(self, client):
        """
        What it does: chat_completions returns an error body without "error".
        Purpose: Still produce an OpenAI-shaped error.
        """
        upstream = JSONResponse(status_code=500, content={"detail": "boom"})
        with patch("kiro.routes_responses.chat_completions", new=AsyncMock(return_value=upstream)):
            resp = client.post("/v1/responses", headers=AUTH, json={"model": "m", "input": "x"})
        assert resp.status_code == 500
        assert resp.json()["error"]["type"] == "api_error"

    @pytest.mark.parametrize("status,error_type", [(503, "api_error"), (400, "invalid_request_error"), (403, "permission_error")])
    def test_http_exception_becomes_openai_error(self, client, status, error_type):
        """
        What it does: chat_completions raises HTTPException.
        Purpose: Errors are returned in OpenAI shape, not FastAPI's {"detail"}.
        """
        with patch("kiro.routes_responses.chat_completions",
                   new=AsyncMock(side_effect=HTTPException(status_code=status, detail="No available accounts"))):
            resp = client.post("/v1/responses", headers=AUTH, json={"model": "m", "input": "x"})
        assert resp.status_code == status
        assert resp.json()["error"]["message"] == "No available accounts"
        assert resp.json()["error"]["type"] == error_type


class TestResponsesStreaming:
    """Streaming tests with chat_completions mocked."""

    def test_streaming_text(self, client):
        """
        What it does: Streams a text response.
        Purpose: Chat SSE is re-emitted as Responses SSE.
        """
        async def chat_stream():
            yield 'data: {"choices":[{"index":0,"delta":{"role":"assistant","content":"Hi"},"finish_reason":null}]}\n\n'
            yield 'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}\n\n'
            yield "data: [DONE]\n\n"

        mock_chat = AsyncMock(return_value=StreamingResponse(chat_stream(), media_type="text/event-stream"))
        with patch("kiro.routes_responses.chat_completions", new=mock_chat):
            resp = client.post("/v1/responses", headers=AUTH, json={"model": "m", "input": "x", "stream": True})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert mock_chat.call_args.args[1].stream is True
        events = parse_events(resp.text)
        assert events[0]["type"] == "response.created"
        assert events[-1]["type"] == "response.completed"
        assert events[-1]["response"]["output"][0]["content"][0]["text"] == "Hi"
        assert events[-1]["response"]["usage"]["total_tokens"] == 2

    def test_streaming_error_emits_response_failed(self, client):
        """
        What it does: Upstream stream raises mid-way.
        Purpose: Client receives response.failed as terminal event.
        """
        async def chat_stream():
            yield 'data: {"choices":[{"index":0,"delta":{"content":"par"},"finish_reason":null}]}\n\n'
            raise RuntimeError("stream broke")

        mock_chat = AsyncMock(return_value=StreamingResponse(chat_stream(), media_type="text/event-stream"))
        with patch("kiro.routes_responses.chat_completions", new=mock_chat):
            resp = client.post("/v1/responses", headers=AUTH, json={"model": "m", "input": "x", "stream": True})
        events = parse_events(resp.text)
        assert events[-1]["type"] == "response.failed"
        assert events[-1]["response"]["error"]["message"] == "stream broke"


class TestResponsesPipelineIntegration:
    """Runs the real chat_completions handler with mocked Kiro I/O (legacy single-account mode)."""

    @pytest.fixture
    def pipeline_app(self, app: FastAPI) -> FastAPI:
        """App state with a mocked legacy account."""
        auth_manager = MagicMock()
        auth_manager.profile_arn = "arn:aws:codewhisperer:us-east-1:1:profile/x"
        auth_manager.api_host = "https://kiro.invalid"
        account = MagicMock(auth_manager=auth_manager, model_cache=MagicMock(), model_resolver=MagicMock())
        app.state.account_system = False
        app.state.account_manager = MagicMock()
        app.state.account_manager.get_first_account.return_value = account
        app.state.http_client = MagicMock()
        return app

    @staticmethod
    def mock_http_client() -> MagicMock:
        """KiroHttpClient mock returning a 200 response."""
        http_client = MagicMock()
        http_client.request_with_retry = AsyncMock(return_value=MagicMock(status_code=200))
        http_client.close = AsyncMock()
        return http_client

    def test_non_streaming_through_real_chat_pipeline(self, pipeline_app):
        """
        What it does: Non-streaming request through routes_openai.chat_completions.
        Purpose: Verify the adapter wiring with the real handler, payload builder included.
        """
        collected = {
            "id": "c", "object": "chat.completion", "created": 1, "model": "m",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "pong"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
        }
        http_client = self.mock_http_client()
        with patch("kiro.routes_openai.KiroHttpClient", return_value=http_client), \
             patch("kiro.routes_openai.collect_stream_response", new=AsyncMock(return_value=collected)):
            resp = TestClient(pipeline_app).post("/v1/responses", headers=AUTH, json={
                "model": "claude-sonnet-4.5",
                "input": [
                    {"role": "user", "content": "ping"},
                    {"type": "function_call", "call_id": "c1", "name": "f", "arguments": "{}"},
                    {"type": "function_call_output", "call_id": "c1", "output": "ok"},
                ],
                "tools": [{"type": "function", "name": "f", "parameters": {"type": "object", "properties": {}}}],
            })
        assert resp.status_code == 200, resp.text
        assert resp.json()["output"][0]["content"][0]["text"] == "pong"
        kiro_payload = http_client.request_with_retry.call_args.args[2]
        assert "conversationState" in kiro_payload
        http_client.close.assert_awaited()

    def test_streaming_through_real_chat_pipeline(self, pipeline_app):
        """
        What it does: Streaming request through routes_openai.chat_completions.
        Purpose: Verify real stream wrapper output is translated and cleaned up.
        """
        async def fake_stream(**kwargs):
            yield 'data: {"choices":[{"index":0,"delta":{"content":"yo"},"finish_reason":null}]}\n\n'
            yield 'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}\n\n'
            yield "data: [DONE]\n\n"

        http_client = self.mock_http_client()
        with patch("kiro.routes_openai.KiroHttpClient", return_value=http_client), \
             patch("kiro.routes_openai.stream_with_first_token_retry", new=fake_stream):
            resp = TestClient(pipeline_app).post("/v1/responses", headers=AUTH,
                                                 json={"model": "claude-sonnet-4.5", "input": "hi", "stream": True})
        events = parse_events(resp.text)
        assert events[-1]["type"] == "response.completed"
        assert events[-1]["response"]["output"][0]["content"][0]["text"] == "yo"
        http_client.close.assert_awaited()

    def test_upstream_kiro_error_through_real_pipeline(self, pipeline_app):
        """
        What it does: Kiro returns 400 through the real handler.
        Purpose: Error is propagated with status and OpenAI error shape.
        """
        http_client = self.mock_http_client()
        error_response = MagicMock(status_code=400)
        error_response.aread = AsyncMock(return_value=b'{"message":"Improperly formed request."}')
        http_client.request_with_retry = AsyncMock(return_value=error_response)
        with patch("kiro.routes_openai.KiroHttpClient", return_value=http_client):
            resp = TestClient(pipeline_app).post("/v1/responses", headers=AUTH,
                                                 json={"model": "claude-sonnet-4.5", "input": "hi"})
        assert resp.status_code == 400
        assert set(resp.json()["error"]) == {"message", "type", "param", "code"}
