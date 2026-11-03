# -*- coding: utf-8 -*-

"""
Unit tests for DebugLoggerMiddleware.
Tests debug logging initialization at the middleware level.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request
from starlette.responses import Response


class TestDebugLoggerMiddlewareEndpointFiltering:
    """Tests for endpoint filtering in middleware."""
    
    @pytest.mark.asyncio
    async def test_skips_health_endpoint(self):
        """
        What it does: Verifies that middleware skips /health endpoint.
        Purpose: Ensure health checks are not logged.
        """
        print("Setup: Creating mock request for /health...")
        
        with patch('kiro.debug_middleware.DEBUG_MODE', 'all'):
            from kiro.debug_middleware import DebugLoggerMiddleware
            
            middleware = DebugLoggerMiddleware(app=MagicMock())
            
            # Mock request
            mock_request = MagicMock(spec=Request)
            mock_request.url.path = "/health"
            
            # Mock call_next
            mock_response = MagicMock(spec=Response)
            mock_call_next = AsyncMock(return_value=mock_response)
            
            # Mock debug_logger at the source module
            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                print("Action: Calling dispatch for /health...")
                response = await middleware.dispatch(mock_request, mock_call_next)
                
                print("Verifying prepare_new_request was NOT called...")
                mock_logger.prepare_new_request.assert_not_called()
                
                print("Verifying call_next was called...")
                mock_call_next.assert_called_once_with(mock_request)
                
                print(f"Comparing response: Expected {mock_response}, Got {response}")
                assert response == mock_response
    
    @pytest.mark.asyncio
    async def test_skips_docs_endpoint(self):
        """
        What it does: Verifies that middleware skips /docs endpoint.
        Purpose: Ensure documentation is not logged.
        """
        print("Setup: Creating mock request for /docs...")
        
        with patch('kiro.debug_middleware.DEBUG_MODE', 'all'):
            from kiro.debug_middleware import DebugLoggerMiddleware
            
            middleware = DebugLoggerMiddleware(app=MagicMock())
            
            mock_request = MagicMock(spec=Request)
            mock_request.url.path = "/docs"
            
            mock_response = MagicMock(spec=Response)
            mock_call_next = AsyncMock(return_value=mock_response)
            
            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                print("Action: Calling dispatch for /docs...")
                response = await middleware.dispatch(mock_request, mock_call_next)
                
                print("Verifying prepare_new_request was NOT called...")
                mock_logger.prepare_new_request.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_skips_root_endpoint(self):
        """
        What it does: Verifies that middleware skips / endpoint.
        Purpose: Ensure root endpoint is not logged.
        """
        print("Setup: Creating mock request for /...")
        
        with patch('kiro.debug_middleware.DEBUG_MODE', 'all'):
            from kiro.debug_middleware import DebugLoggerMiddleware
            
            middleware = DebugLoggerMiddleware(app=MagicMock())
            
            mock_request = MagicMock(spec=Request)
            mock_request.url.path = "/"
            
            mock_response = MagicMock(spec=Response)
            mock_call_next = AsyncMock(return_value=mock_response)
            
            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                print("Action: Calling dispatch for /...")
                await middleware.dispatch(mock_request, mock_call_next)
                
                print("Verifying prepare_new_request was NOT called...")
                mock_logger.prepare_new_request.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_processes_chat_completions_endpoint(self):
        """
        What it does: Verifies that middleware processes /v1/chat/completions.
        Purpose: Ensure OpenAI endpoint is logged.
        """
        print("Setup: Creating mock request for /v1/chat/completions...")
        
        with patch('kiro.debug_middleware.DEBUG_MODE', 'all'):
            from kiro.debug_middleware import DebugLoggerMiddleware
            
            middleware = DebugLoggerMiddleware(app=MagicMock())
            
            mock_request = MagicMock(spec=Request)
            mock_request.url.path = "/v1/chat/completions"
            mock_request.body = AsyncMock(return_value=b'{"model": "test"}')
            
            mock_response = MagicMock(spec=Response)
            mock_call_next = AsyncMock(return_value=mock_response)
            
            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                print("Action: Calling dispatch for /v1/chat/completions...")
                await middleware.dispatch(mock_request, mock_call_next)
                
                print("Verifying prepare_new_request was called...")
                mock_logger.prepare_new_request.assert_called_once()
                
                print("Verifying log_request_body was called...")
                mock_logger.log_request_body.assert_called_once_with(b'{"model": "test"}')
    
    @pytest.mark.asyncio
    async def test_processes_messages_endpoint(self):
        """
        What it does: Verifies that middleware processes /v1/messages.
        Purpose: Ensure Anthropic endpoint is logged.
        """
        print("Setup: Creating mock request for /v1/messages...")
        
        with patch('kiro.debug_middleware.DEBUG_MODE', 'all'):
            from kiro.debug_middleware import DebugLoggerMiddleware
            
            middleware = DebugLoggerMiddleware(app=MagicMock())
            
            mock_request = MagicMock(spec=Request)
            mock_request.url.path = "/v1/messages"
            mock_request.body = AsyncMock(return_value=b'{"model": "claude"}')
            
            mock_response = MagicMock(spec=Response)
            mock_call_next = AsyncMock(return_value=mock_response)
            
            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                print("Action: Calling dispatch for /v1/messages...")
                await middleware.dispatch(mock_request, mock_call_next)
                
                print("Verifying prepare_new_request was called...")
                mock_logger.prepare_new_request.assert_called_once()


class TestDebugLoggerMiddlewareModeHandling:
    """Tests for DEBUG_MODE handling in middleware."""
    
    @pytest.mark.asyncio
    async def test_skips_when_debug_mode_off(self):
        """
        What it does: Verifies that middleware skips requests when DEBUG_MODE=off.
        Purpose: Ensure logging is disabled in off mode.
        """
        print("Setup: DEBUG_MODE=off...")
        
        with patch('kiro.debug_middleware.DEBUG_MODE', 'off'):
            from kiro.debug_middleware import DebugLoggerMiddleware
            
            middleware = DebugLoggerMiddleware(app=MagicMock())
            
            mock_request = MagicMock(spec=Request)
            mock_request.url.path = "/v1/chat/completions"
            
            mock_response = MagicMock(spec=Response)
            mock_call_next = AsyncMock(return_value=mock_response)
            
            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                print("Action: Calling dispatch with DEBUG_MODE=off...")
                response = await middleware.dispatch(mock_request, mock_call_next)
                
                print("Verifying prepare_new_request was NOT called...")
                mock_logger.prepare_new_request.assert_not_called()
                
                print("Verifying call_next was called...")
                mock_call_next.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_processes_when_debug_mode_errors(self):
        """
        What it does: Verifies that middleware works when DEBUG_MODE=errors.
        Purpose: Ensure errors mode activates logging.
        """
        print("Setup: DEBUG_MODE=errors...")
        
        with patch('kiro.debug_middleware.DEBUG_MODE', 'errors'):
            from kiro.debug_middleware import DebugLoggerMiddleware
            
            middleware = DebugLoggerMiddleware(app=MagicMock())
            
            mock_request = MagicMock(spec=Request)
            mock_request.url.path = "/v1/chat/completions"
            mock_request.body = AsyncMock(return_value=b'{"test": "data"}')
            
            mock_response = MagicMock(spec=Response)
            mock_call_next = AsyncMock(return_value=mock_response)
            
            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                print("Action: Calling dispatch with DEBUG_MODE=errors...")
                await middleware.dispatch(mock_request, mock_call_next)
                
                print("Verifying prepare_new_request was called...")
                mock_logger.prepare_new_request.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_processes_when_debug_mode_all(self):
        """
        What it does: Verifies that middleware works when DEBUG_MODE=all.
        Purpose: Ensure all mode activates logging.
        """
        print("Setup: DEBUG_MODE=all...")
        
        with patch('kiro.debug_middleware.DEBUG_MODE', 'all'):
            from kiro.debug_middleware import DebugLoggerMiddleware
            
            middleware = DebugLoggerMiddleware(app=MagicMock())
            
            mock_request = MagicMock(spec=Request)
            mock_request.url.path = "/v1/messages"
            mock_request.body = AsyncMock(return_value=b'{"test": "data"}')
            
            mock_response = MagicMock(spec=Response)
            mock_call_next = AsyncMock(return_value=mock_response)
            
            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                print("Action: Calling dispatch with DEBUG_MODE=all...")
                await middleware.dispatch(mock_request, mock_call_next)
                
                print("Verifying prepare_new_request was called...")
                mock_logger.prepare_new_request.assert_called_once()


class TestDebugLoggerMiddlewareErrorHandling:
    """Tests for error handling in middleware."""
    
    @pytest.mark.asyncio
    async def test_handles_body_read_error_gracefully(self):
        """
        What it does: Verifies that middleware handles body read errors gracefully.
        Purpose: Ensure body read errors don't break the request.
        """
        print("Setup: Simulating body read error...")
        
        with patch('kiro.debug_middleware.DEBUG_MODE', 'all'):
            from kiro.debug_middleware import DebugLoggerMiddleware
            
            middleware = DebugLoggerMiddleware(app=MagicMock())
            
            mock_request = MagicMock(spec=Request)
            mock_request.url.path = "/v1/chat/completions"
            mock_request.body = AsyncMock(side_effect=Exception("Body read error"))
            
            mock_response = MagicMock(spec=Response)
            mock_call_next = AsyncMock(return_value=mock_response)
            
            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                print("Action: Calling dispatch with body read error...")
                response = await middleware.dispatch(mock_request, mock_call_next)
                
                print("Verifying prepare_new_request was called...")
                mock_logger.prepare_new_request.assert_called_once()
                
                print("Verifying log_request_body was NOT called (due to error)...")
                mock_logger.log_request_body.assert_not_called()
                
                print("Verifying call_next was called (request continued)...")
                mock_call_next.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_skips_empty_body(self):
        """
        What it does: Verifies that middleware doesn't log empty body.
        Purpose: Ensure empty requests don't create unnecessary logs.
        """
        print("Setup: Creating request with empty body...")
        
        with patch('kiro.debug_middleware.DEBUG_MODE', 'all'):
            from kiro.debug_middleware import DebugLoggerMiddleware
            
            middleware = DebugLoggerMiddleware(app=MagicMock())
            
            mock_request = MagicMock(spec=Request)
            mock_request.url.path = "/v1/chat/completions"
            mock_request.body = AsyncMock(return_value=b'')  # Empty body
            
            mock_response = MagicMock(spec=Response)
            mock_call_next = AsyncMock(return_value=mock_response)
            
            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                print("Action: Calling dispatch with empty body...")
                await middleware.dispatch(mock_request, mock_call_next)
                
                print("Verifying prepare_new_request was called...")
                mock_logger.prepare_new_request.assert_called_once()
                
                print("Verifying log_request_body was NOT called (body is empty)...")
                mock_logger.log_request_body.assert_not_called()


class TestDebugLoggerMiddlewareResponsePassthrough:
    """Tests for transparent response passthrough."""
    
    @pytest.mark.asyncio
    async def test_returns_response_from_call_next(self):
        """
        What it does: Verifies that middleware returns response from call_next.
        Purpose: Ensure middleware doesn't modify the response.
        """
        print("Setup: Creating mock response...")
        
        with patch('kiro.debug_middleware.DEBUG_MODE', 'all'):
            from kiro.debug_middleware import DebugLoggerMiddleware
            
            middleware = DebugLoggerMiddleware(app=MagicMock())
            
            mock_request = MagicMock(spec=Request)
            mock_request.url.path = "/v1/chat/completions"
            mock_request.body = AsyncMock(return_value=b'{"test": "data"}')
            
            expected_response = MagicMock(spec=Response)
            expected_response.status_code = 200
            mock_call_next = AsyncMock(return_value=expected_response)
            
            with patch('kiro.debug_logger.debug_logger'):
                print("Action: Calling dispatch...")
                actual_response = await middleware.dispatch(mock_request, mock_call_next)
                
                print(f"Comparing response: Expected {expected_response}, Got {actual_response}")
                assert actual_response == expected_response
                assert actual_response.status_code == 200


class TestLoggedEndpointsConstant:
    """Tests for LOGGED_ENDPOINTS constant."""
    
    def test_logged_endpoints_contains_chat_completions(self):
        """
        What it does: Verifies that LOGGED_ENDPOINTS contains /v1/chat/completions.
        Purpose: Ensure OpenAI endpoint is included in logging.
        """
        print("Checking LOGGED_ENDPOINTS...")
        from kiro.debug_middleware import LOGGED_ENDPOINTS
        
        print(f"LOGGED_ENDPOINTS contents: {LOGGED_ENDPOINTS}")
        assert "/v1/chat/completions" in LOGGED_ENDPOINTS
    
    def test_logged_endpoints_contains_messages(self):
        """
        What it does: Verifies that LOGGED_ENDPOINTS contains /v1/messages.
        Purpose: Ensure Anthropic endpoint is included in logging.
        """
        print("Checking LOGGED_ENDPOINTS...")
        from kiro.debug_middleware import LOGGED_ENDPOINTS
        
        print(f"LOGGED_ENDPOINTS contents: {LOGGED_ENDPOINTS}")
        assert "/v1/messages" in LOGGED_ENDPOINTS
    
    def test_logged_endpoints_is_frozenset(self):
        """
        What it does: Verifies that LOGGED_ENDPOINTS is a frozenset.
        Purpose: Ensure the constant is immutable.
        """
        print("Checking LOGGED_ENDPOINTS type...")
        from kiro.debug_middleware import LOGGED_ENDPOINTS
        
        print(f"LOGGED_ENDPOINTS type: {type(LOGGED_ENDPOINTS)}")
        assert isinstance(LOGGED_ENDPOINTS, frozenset)


# =============================================================================
# RequestIdMiddleware (pure ASGI)
# =============================================================================

import re as _re

from fastapi import FastAPI as _FastAPI
from fastapi.responses import StreamingResponse as _StreamingResponse, JSONResponse as _JSONResponse
from fastapi.testclient import TestClient as _TestClient


REQUEST_ID_PATTERN = _re.compile(r"^req_[0-9a-f]{32}$")


def _request_id_app() -> _FastAPI:
    """Minimal app wrapped with RequestIdMiddleware."""
    from kiro.debug_middleware import RequestIdMiddleware

    app = _FastAPI()

    @app.get("/json")
    async def json_route(request: Request):
        return {"seen": request.state.request_id}

    @app.get("/stream")
    async def stream_route():
        async def gen():
            for i in range(3):
                yield f"data: {i}\n\n"
        return _StreamingResponse(gen(), media_type="text/event-stream")

    @app.get("/preset")
    async def preset_route():
        return _JSONResponse({"ok": True}, headers={"x-request-id": "upstream-id"})

    @app.get("/boom")
    async def boom_route():
        from fastapi import HTTPException
        raise HTTPException(status_code=418, detail="teapot")

    app.add_middleware(RequestIdMiddleware)
    return app


class TestRequestIdMiddleware:
    """Tests for request-id / x-request-id response headers."""

    def test_headers_present_and_equal(self):
        """
        What it does: Calls a JSON route.
        Purpose: Both headers set, same id, expected format.
        """
        resp = _TestClient(_request_id_app()).get("/json")
        assert REQUEST_ID_PATTERN.match(resp.headers["request-id"])
        assert resp.headers["request-id"] == resp.headers["x-request-id"]

    def test_id_exposed_on_request_state(self):
        """
        What it does: Route echoes request.state.request_id.
        Purpose: Handlers can log the same id the client sees.
        """
        resp = _TestClient(_request_id_app()).get("/json")
        assert resp.json()["seen"] == resp.headers["request-id"]

    def test_unique_per_request(self):
        """
        What it does: Sends several requests.
        Purpose: Ids never repeat.
        """
        client = _TestClient(_request_id_app())
        ids = {client.get("/json").headers["request-id"] for _ in range(20)}
        assert len(ids) == 20

    def test_streaming_body_untouched(self):
        """
        What it does: Calls an SSE route.
        Purpose: Headers added without buffering or altering chunks.
        """
        resp = _TestClient(_request_id_app()).get("/stream")
        assert resp.text == "data: 0\n\ndata: 1\n\ndata: 2\n\n"
        assert REQUEST_ID_PATTERN.match(resp.headers["x-request-id"])
        assert resp.headers["content-type"].startswith("text/event-stream")

    def test_existing_header_replaced_not_duplicated(self):
        """
        What it does: Route already sets x-request-id.
        Purpose: Exactly one value per header (no duplicates confusing clients).
        """
        resp = _TestClient(_request_id_app()).get("/preset")
        assert resp.headers.get_list("x-request-id") == [resp.headers["request-id"]]

    def test_error_responses_tagged(self):
        """
        What it does: Route raises HTTPException; also an unknown path.
        Purpose: Error responses carry ids for support/debugging.
        """
        client = _TestClient(_request_id_app())
        assert "request-id" in client.get("/boom").headers
        assert "request-id" in client.get("/nope").headers

    @pytest.mark.asyncio
    async def test_non_http_scope_passthrough(self):
        """
        What it does: Sends a lifespan scope through the middleware.
        Purpose: Only HTTP traffic is touched.
        """
        from kiro.debug_middleware import RequestIdMiddleware
        inner = AsyncMock()
        middleware = RequestIdMiddleware(inner)
        scope = {"type": "lifespan"}
        receive, send = AsyncMock(), AsyncMock()
        await middleware(scope, receive, send)
        inner.assert_awaited_once_with(scope, receive, send)
        assert "state" not in scope

    @pytest.mark.asyncio
    async def test_body_messages_forwarded_unchanged(self):
        """
        What it does: Drives the ASGI send wrapper with start + body messages.
        Purpose: Only http.response.start is modified.
        """
        from kiro.debug_middleware import RequestIdMiddleware
        sent = []

        async def inner(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"hi", "more_body": False})

        async def send(message):
            sent.append(message)

        await RequestIdMiddleware(inner)({"type": "http"}, AsyncMock(), send)
        start_headers = dict(sent[0]["headers"])
        assert start_headers[b"content-type"] == b"text/plain"
        assert start_headers[b"request-id"] == start_headers[b"x-request-id"]
        assert sent[1] == {"type": "http.response.body", "body": b"hi", "more_body": False}

    def test_generate_request_id_format(self):
        """
        What it does: Generates an id directly.
        Purpose: Stable, header-safe format.
        """
        from kiro.debug_middleware import generate_request_id
        assert REQUEST_ID_PATTERN.match(generate_request_id())
