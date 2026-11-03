# -*- coding: utf-8 -*-

"""
Unit tests for exception handlers.
Tests validation error handling and debug logging integration.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request
from fastapi.exceptions import RequestValidationError


class TestSanitizeValidationErrors:
    """Tests for sanitize_validation_errors function."""
    
    def test_sanitizes_bytes_in_input_field(self):
        """
        What it does: Verifies that bytes in 'input' field are converted to strings.
        Purpose: Ensure JSON serialization works for bytes objects.
        """
        print("Setup: Creating error with bytes in input field...")
        from kiro.exceptions import sanitize_validation_errors
        
        errors = [
            {
                "type": "json_invalid",
                "loc": ["body", 0],
                "msg": "Invalid JSON",
                "input": b'{"invalid": json}'
            }
        ]
        
        print("Action: Calling sanitize_validation_errors...")
        result = sanitize_validation_errors(errors)
        
        print(f"Comparing input type: Expected str, Got {type(result[0]['input'])}")
        assert isinstance(result[0]["input"], str)
        assert result[0]["input"] == '{"invalid": json}'
    
    def test_sanitizes_bytes_in_list_values(self):
        """
        What it does: Verifies that bytes in list values are converted to strings.
        Purpose: Ensure nested bytes are handled.
        """
        print("Setup: Creating error with bytes in list...")
        from kiro.exceptions import sanitize_validation_errors
        
        errors = [
            {
                "type": "value_error",
                "loc": ["body", "messages"],
                "msg": "Invalid value",
                "input": [b'bytes1', "string", b'bytes2']
            }
        ]
        
        print("Action: Calling sanitize_validation_errors...")
        result = sanitize_validation_errors(errors)
        
        print(f"Checking list values are converted...")
        assert result[0]["input"] == ["bytes1", "string", "bytes2"]
    
    def test_preserves_non_bytes_values(self):
        """
        What it does: Verifies that non-bytes values are preserved.
        Purpose: Ensure normal values are not modified.
        """
        print("Setup: Creating error with normal values...")
        from kiro.exceptions import sanitize_validation_errors
        
        errors = [
            {
                "type": "missing",
                "loc": ["body", "model"],
                "msg": "Field required",
                "input": {"messages": []}
            }
        ]
        
        print("Action: Calling sanitize_validation_errors...")
        result = sanitize_validation_errors(errors)
        
        print(f"Checking values are preserved...")
        assert result[0]["input"] == {"messages": []}
        assert result[0]["type"] == "missing"


class TestValidationExceptionHandler:
    """Tests for validation_exception_handler function."""
    
    @pytest.mark.asyncio
    async def test_returns_422_status_code(self):
        """
        What it does: Verifies that handler returns 422 status code.
        Purpose: Ensure proper HTTP status for validation errors.
        """
        print("Setup: Creating mock request and exception...")
        from kiro.exceptions import validation_exception_handler
        
        mock_request = MagicMock(spec=Request)
        mock_request.body = AsyncMock(return_value=b'{"invalid": json}')
        
        mock_exc = MagicMock(spec=RequestValidationError)
        mock_exc.errors.return_value = [
            {"type": "json_invalid", "loc": ["body"], "msg": "Invalid JSON", "input": {}}
        ]
        
        # Patch debug_logger at the source module
        with patch('kiro.debug_logger.debug_logger') as mock_logger:
            print("Action: Calling validation_exception_handler...")
            response = await validation_exception_handler(mock_request, mock_exc)
            
            print(f"Comparing status_code: Expected 422, Got {response.status_code}")
            assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_calls_flush_on_error_with_422(self):
        """
        What it does: Verifies that handler calls flush_on_error(422).
        Purpose: Ensure debug logs are flushed for validation errors.
        """
        print("Setup: Creating mock request and exception...")
        from kiro.exceptions import validation_exception_handler
        
        mock_request = MagicMock(spec=Request)
        mock_request.body = AsyncMock(return_value=b'{"test": "data"}')
        
        mock_exc = MagicMock(spec=RequestValidationError)
        mock_exc.errors.return_value = [
            {"type": "missing", "loc": ["body", "model"], "msg": "Field required", "input": {}}
        ]
        
        # Patch debug_logger at the source module
        with patch('kiro.debug_logger.debug_logger') as mock_logger:
            print("Action: Calling validation_exception_handler...")
            await validation_exception_handler(mock_request, mock_exc)
            
            print("Verifying flush_on_error was called with 422...")
            mock_logger.flush_on_error.assert_called_once()
            call_args = mock_logger.flush_on_error.call_args
            assert call_args[0][0] == 422  # First positional argument is status_code
    
    @pytest.mark.asyncio
    async def test_includes_sanitized_errors_in_response(self):
        """
        What it does: Verifies that response includes sanitized errors.
        Purpose: Ensure error details are returned to client.
        """
        print("Setup: Creating mock request and exception...")
        from kiro.exceptions import validation_exception_handler
        import json
        
        mock_request = MagicMock(spec=Request)
        mock_request.body = AsyncMock(return_value=b'{"test": "data"}')
        
        mock_exc = MagicMock(spec=RequestValidationError)
        mock_exc.errors.return_value = [
            {"type": "missing", "loc": ["body", "model"], "msg": "Field required", "input": {}}
        ]
        
        with patch('kiro.debug_logger.debug_logger'):
            print("Action: Calling validation_exception_handler...")
            response = await validation_exception_handler(mock_request, mock_exc)
            
            print("Parsing response body...")
            body = json.loads(response.body.decode())
            
            print("Verifying OpenAI error shape with the field location...")
            assert set(body) == {"error"}
            assert body["error"]["type"] == "invalid_request_error"
            assert body["error"]["param"] == "model"
            assert "model: Field required" in body["error"]["message"]
    
    @pytest.mark.asyncio
    async def test_does_not_echo_request_body(self):
        """
        What it does: Verifies the request body is never echoed in the 422 response.
        Purpose: Avoid leaking user content (and bloating responses) in error bodies.
        """
        print("Setup: Creating mock request with large body...")
        from kiro.exceptions import validation_exception_handler
        import json
        
        large_body = b'{"data": "' + b'x' * 1000 + b'"}'
        
        mock_request = MagicMock(spec=Request)
        mock_request.body = AsyncMock(return_value=large_body)
        
        mock_exc = MagicMock(spec=RequestValidationError)
        mock_exc.errors.return_value = [
            {"type": "json_invalid", "loc": ["body"], "msg": "Invalid", "input": {}}
        ]
        
        with patch('kiro.debug_logger.debug_logger'):
            print("Action: Calling validation_exception_handler...")
            response = await validation_exception_handler(mock_request, mock_exc)
            
            print("Parsing response body...")
            body = json.loads(response.body.decode())
            
            print("Verifying body is not echoed...")
            assert "body" not in body
            assert "xxxx" not in response.body.decode()
            mock_request.body.assert_not_called()


class TestValidationExceptionHandlerLogging:
    """Tests for logging behavior in validation_exception_handler."""
    
    @pytest.mark.asyncio
    async def test_logs_error_at_error_level(self):
        """
        What it does: Verifies that validation error is logged at ERROR level.
        Purpose: Ensure errors are visible in logs.
        """
        print("Setup: Creating mock request and exception...")
        from kiro.exceptions import validation_exception_handler
        
        mock_request = MagicMock(spec=Request)
        mock_request.body = AsyncMock(return_value=b'{"test": "data"}')
        
        mock_exc = MagicMock(spec=RequestValidationError)
        mock_exc.errors.return_value = [
            {"type": "missing", "loc": ["body", "model"], "msg": "Field required", "input": {}}
        ]
        
        with patch('kiro.debug_logger.debug_logger'):
            with patch('kiro.exceptions.logger') as mock_logger:
                print("Action: Calling validation_exception_handler...")
                await validation_exception_handler(mock_request, mock_exc)
                
                print("Verifying logger.error was called...")
                mock_logger.error.assert_called()


class TestValidationExceptionHandlerEdgeCases:
    """Tests for edge cases in validation_exception_handler."""
    
    @pytest.mark.asyncio
    async def test_handles_empty_errors_list(self):
        """
        What it does: Verifies that handler works with empty errors list.
        Purpose: Ensure edge case doesn't cause crash.
        """
        print("Setup: Creating mock request with empty errors...")
        from kiro.exceptions import validation_exception_handler
        import json
        
        mock_request = MagicMock(spec=Request)
        mock_request.body = AsyncMock(return_value=b'{}')
        
        mock_exc = MagicMock(spec=RequestValidationError)
        mock_exc.errors.return_value = []
        
        with patch('kiro.debug_logger.debug_logger'):
            print("Action: Calling validation_exception_handler...")
            response = await validation_exception_handler(mock_request, mock_exc)
            
            print(f"Verifying response is valid...")
            assert response.status_code == 422
            
            body = json.loads(response.body.decode())
            assert body["error"]["message"] == "Invalid request body."
            assert body["error"]["param"] is None
    
    @pytest.mark.asyncio
    async def test_handles_unicode_in_body(self):
        """
        What it does: Verifies that handler works with unicode in body.
        Purpose: Ensure international characters are handled.
        """
        print("Setup: Creating mock request with unicode body...")
        from kiro.exceptions import validation_exception_handler
        import json
        
        unicode_body = '{"message": "Привет мир 🌍"}'.encode('utf-8')
        
        mock_request = MagicMock(spec=Request)
        mock_request.body = AsyncMock(return_value=unicode_body)
        
        mock_exc = MagicMock(spec=RequestValidationError)
        mock_exc.errors.return_value = [
            {"type": "missing", "loc": ["body", "model"], "msg": "Field required", "input": {}}
        ]
        
        with patch('kiro.debug_logger.debug_logger'):
            print("Action: Calling validation_exception_handler...")
            response = await validation_exception_handler(mock_request, mock_exc)
            
            print(f"Verifying response is valid...")
            assert response.status_code == 422
            
            body = json.loads(response.body.decode())
            assert "Привет мир" not in response.body.decode("utf-8")
            assert body["error"]["type"] == "invalid_request_error"


# =============================================================================
# Error shaping (OpenAI / Anthropic) - HTTPException handler, mapping helpers
# =============================================================================

import json as _json

from fastapi import FastAPI, HTTPException as FastAPIHTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel


def _make_error_app() -> FastAPI:
    """Minimal app wired with the gateway's error handlers (no lifespan)."""
    from kiro.exceptions import http_exception_handler, validation_exception_handler
    from starlette.exceptions import HTTPException as StarletteHTTPException

    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)

    class Body(BaseModel):
        model: str
        max_tokens: int

    @app.get("/v1/chat/completions/raise/{status}")
    async def raise_openai(status: int):
        raise FastAPIHTTPException(status_code=status, detail="boom")

    @app.get("/v1/messages/raise/{status}")
    async def raise_anthropic(status: int):
        raise FastAPIHTTPException(status_code=status, detail="boom")

    @app.get("/v1/messages/raise_enveloped")
    async def raise_enveloped():
        raise FastAPIHTTPException(status_code=401, detail={
            "type": "error", "error": {"type": "authentication_error", "message": "bad key"}})

    @app.get("/v1/chat/completions/raise_openai_enveloped")
    async def raise_openai_enveloped():
        raise FastAPIHTTPException(status_code=402, detail={
            "error": {"message": "pay", "type": "billing", "code": "x"}})

    @app.get("/v1/chat/completions/raise_with_headers")
    async def raise_with_headers():
        raise FastAPIHTTPException(status_code=429, detail="slow", headers={"Retry-After": "7"})

    @app.post("/v1/messages")
    async def post_messages(body: Body):
        return {"ok": True}

    @app.post("/v1/chat/completions")
    async def post_chat(body: Body):
        return {"ok": True}

    @app.get("/v1/models")
    async def models():
        raise FastAPIHTTPException(status_code=401, detail="Invalid or missing API Key")

    return app


@pytest.fixture
def error_client() -> TestClient:
    """TestClient over the minimal error app."""
    return TestClient(_make_error_app())


class TestErrorTypeMapping:
    """Tests for status -> error type mapping."""

    @pytest.mark.parametrize("status,expected", [
        (400, "invalid_request_error"),
        (401, "authentication_error"),
        (403, "permission_error"),
        (404, "not_found_error"),
        (413, "request_too_large"),
        (429, "rate_limit_error"),
        (503, "overloaded_error"),
        (529, "overloaded_error"),
        (500, "api_error"),
        (502, "api_error"),
        (504, "api_error"),
        (402, "api_error"),
        (418, "api_error"),
    ])
    def test_anthropic_error_type(self, status, expected):
        """
        What it does: Maps every documented status to its Anthropic error type.
        Purpose: Anthropic SDKs dispatch exception classes on error.type.
        """
        from kiro.exceptions import anthropic_error_type
        assert anthropic_error_type(status) == expected

    @pytest.mark.parametrize("status,expected", [
        (400, "invalid_request_error"),
        (401, "authentication_error"),
        (404, "not_found_error"),
        (429, "rate_limit_error"),
        (422, "invalid_request_error"),
        (402, "invalid_request_error"),
        (500, "api_error"),
        (503, "api_error"),
    ])
    def test_openai_error_type(self, status, expected):
        """
        What it does: Maps statuses to OpenAI error types (other 4xx invalid_request_error, 5xx api_error).
        Purpose: Keep OpenAI error types meaningful for clients.
        """
        from kiro.exceptions import openai_error_type
        assert openai_error_type(status) == expected


class TestWantsAnthropicErrors:
    """Tests for path/header-based shape selection."""

    @pytest.mark.parametrize("path,headers,expected", [
        ("/v1/messages", {}, True),
        ("/v1/messages/count_tokens", {}, True),
        ("/v1/messagesX", {}, False),
        ("/v1/chat/completions", {}, False),
        ("/v1/chat/completions", {"anthropic-version": "2023-06-01"}, False),
        ("/v1/models", {}, False),
        ("/v1/models", {"anthropic-version": "2023-06-01"}, True),
        ("/v1/models/claude-x", {"anthropic-version": "2023-06-01"}, True),
        ("/v1/models", {"anthropic-version": ""}, False),
        ("/v1/modelsX", {"anthropic-version": "2023-06-01"}, False),
        ("/", None, False),
    ])
    def test_selection(self, path, headers, expected):
        """
        What it does: Checks which requests get the Anthropic error shape.
        Purpose: Only Anthropic surfaces get Anthropic-shaped errors.
        """
        from kiro.exceptions import wants_anthropic_errors
        assert wants_anthropic_errors(path, headers) is expected

    def test_non_string_path_is_openai(self):
        """
        What it does: Passes a non-string path (e.g. a mock).
        Purpose: Never crash while rendering an error.
        """
        from kiro.exceptions import wants_anthropic_errors
        assert wants_anthropic_errors(MagicMock(), {}) is False


class TestFormatErrorBody:
    """Tests for format_error_body (no double-wrapping)."""

    def test_string_detail_openai(self):
        """
        What it does: Wraps a plain string detail.
        Purpose: OpenAI shape has all four fields.
        """
        from kiro.exceptions import format_error_body
        assert format_error_body(401, "nope", anthropic=False) == {
            "error": {"message": "nope", "type": "authentication_error", "param": None, "code": None}}

    def test_string_detail_anthropic(self):
        """
        What it does: Wraps a plain string detail.
        Purpose: Anthropic shape has top-level type=error.
        """
        from kiro.exceptions import format_error_body
        assert format_error_body(429, "slow", anthropic=True) == {
            "type": "error", "error": {"type": "rate_limit_error", "message": "slow"}}

    def test_anthropic_envelope_not_double_wrapped(self):
        """
        What it does: Passes a detail already in Anthropic shape.
        Purpose: Must be returned unchanged, not nested.
        """
        from kiro.exceptions import format_error_body
        detail = {"type": "error", "error": {"type": "authentication_error", "message": "m"}}
        assert format_error_body(401, detail, anthropic=True) is detail

    def test_openai_envelope_normalized_not_double_wrapped(self):
        """
        What it does: Passes a detail already in (partial) OpenAI shape.
        Purpose: Keep message/type/code and add param, without nesting.
        """
        from kiro.exceptions import format_error_body
        body = format_error_body(402, {"error": {"message": "pay", "type": "billing", "code": 7}}, anthropic=False)
        assert body == {"error": {"message": "pay", "type": "billing", "param": None, "code": 7}}

    def test_anthropic_envelope_converted_for_openai_path(self):
        """
        What it does: Anthropic-shaped detail rendered for an OpenAI client.
        Purpose: Cross-shape details are converted, message kept.
        """
        from kiro.exceptions import format_error_body
        detail = {"type": "error", "error": {"type": "authentication_error", "message": "bad"}}
        body = format_error_body(401, detail, anthropic=False)
        assert body == {"error": {"message": "bad", "type": "authentication_error", "param": None, "code": None}}

    def test_openai_envelope_converted_for_anthropic_path_unknown_type(self):
        """
        What it does: OpenAI-shaped detail with a non-Anthropic type rendered for Anthropic.
        Purpose: Unknown types are replaced by the status mapping.
        """
        from kiro.exceptions import format_error_body
        body = format_error_body(429, {"error": {"message": "m", "type": "kiro_api_error"}}, anthropic=True)
        assert body == {"type": "error", "error": {"type": "rate_limit_error", "message": "m"}}

    def test_incomplete_anthropic_envelope_is_rebuilt(self):
        """
        What it does: Anthropic-like detail missing error.type.
        Purpose: Output always has a valid type.
        """
        from kiro.exceptions import format_error_body
        body = format_error_body(403, {"type": "error", "error": {"message": "m"}}, anthropic=True)
        assert body == {"type": "error", "error": {"type": "permission_error", "message": "m"}}

    @pytest.mark.parametrize("detail", [None, "", {}, {"foo": 1}, ["a"], 42, {"error": "flat"}])
    def test_odd_details_never_crash(self, detail):
        """
        What it does: Feeds empty/odd details.
        Purpose: Error rendering must always produce a valid body with a message.
        """
        from kiro.exceptions import format_error_body
        for anthropic in (True, False):
            body = format_error_body(500, detail, anthropic=anthropic)
            assert body["error"]["message"]
            _json.dumps(body)

    def test_message_key_without_envelope(self):
        """
        What it does: Detail dict with a top-level "message".
        Purpose: Message is extracted instead of str(dict).
        """
        from kiro.exceptions import format_error_body
        body = format_error_body(400, {"message": "clean"}, anthropic=False)
        assert body["error"]["message"] == "clean"


class TestRetryAfterHeaders:
    """Tests for retry_after_headers."""

    @pytest.mark.parametrize("status", [429, 503])
    def test_forwarded_on_retryable_status(self, status):
        """
        What it does: Upstream 429/503 with Retry-After.
        Purpose: Clients can back off as the upstream asked.
        """
        import httpx
        from kiro.exceptions import retry_after_headers
        assert retry_after_headers(status, httpx.Headers({"Retry-After": "12"})) == {"Retry-After": "12"}

    @pytest.mark.parametrize("status", [200, 400, 500, 502])
    def test_not_forwarded_on_other_status(self, status):
        """
        What it does: Retry-After on non-retryable status.
        Purpose: Only 429/503 forward the header.
        """
        from kiro.exceptions import retry_after_headers
        assert retry_after_headers(status, {"retry-after": "3"}) is None

    @pytest.mark.parametrize("headers", [
        None, {}, {"retry-after": ""}, {"retry-after": "  "},
        {"retry-after": "1\r\nX-Evil: 1"}, {"retry-after": "9" * 100},
        {"retry-after": 5}, MagicMock(get=MagicMock(return_value=MagicMock())),
        object(),
    ])
    def test_rejects_missing_or_unsafe_values(self, headers):
        """
        What it does: Missing, empty, oversized, non-string or CRLF values.
        Purpose: No header injection and no crash on odd upstream objects.
        """
        from kiro.exceptions import retry_after_headers
        assert retry_after_headers(429, headers) is None

    def test_plain_dict_with_canonical_case(self):
        """
        What it does: Plain dict keyed "Retry-After" (as produced by retry_after_headers itself).
        Purpose: Output of one call can be fed back in (the failover loop re-uses it).
        """
        from kiro.exceptions import retry_after_headers
        first = retry_after_headers(429, {"retry-after": "8"})
        assert retry_after_headers(429, first) == {"Retry-After": "8"}

    def test_strips_whitespace(self):
        """
        What it does: Value with surrounding whitespace.
        Purpose: Forward a clean value.
        """
        from kiro.exceptions import retry_after_headers
        assert retry_after_headers(503, {"retry-after": " 4 "}) == {"Retry-After": "4"}

    def test_getter_raising_type_error(self):
        """
        What it does: Headers object whose get() raises TypeError.
        Purpose: Never crash while building an error response.
        """
        from kiro.exceptions import retry_after_headers
        bad = MagicMock()
        bad.get.side_effect = TypeError("nope")
        assert retry_after_headers(429, bad) is None


class TestHttpExceptionHandlerIntegration:
    """End-to-end tests of http_exception_handler through a FastAPI app."""

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 503])
    def test_openai_path_shape_and_status(self, error_client, status):
        """
        What it does: Raises HTTPException on an OpenAI path.
        Purpose: Status preserved, body in OpenAI shape, no "detail".
        """
        from kiro.exceptions import openai_error_type
        resp = error_client.get(f"/v1/chat/completions/raise/{status}")
        assert resp.status_code == status
        assert resp.json() == {"error": {"message": "boom", "type": openai_error_type(status), "param": None, "code": None}}

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 413, 429, 500, 503, 529])
    def test_anthropic_path_shape_and_status(self, error_client, status):
        """
        What it does: Raises HTTPException on an Anthropic path.
        Purpose: Status preserved, body in Anthropic shape with mapped type.
        """
        from kiro.exceptions import anthropic_error_type
        resp = error_client.get(f"/v1/messages/raise/{status}")
        assert resp.status_code == status
        assert resp.json() == {"type": "error", "error": {"type": anthropic_error_type(status), "message": "boom"}}

    def test_enveloped_anthropic_detail_passthrough(self, error_client):
        """
        What it does: Raises with a detail that is already an Anthropic envelope.
        Purpose: No {"detail": {...}} nesting (the old 401 bug).
        """
        resp = error_client.get("/v1/messages/raise_enveloped")
        assert resp.status_code == 401
        assert resp.json() == {"type": "error", "error": {"type": "authentication_error", "message": "bad key"}}

    def test_enveloped_openai_detail_passthrough(self, error_client):
        """
        What it does: Raises with a detail already in OpenAI shape.
        Purpose: No double-wrapping on OpenAI paths.
        """
        resp = error_client.get("/v1/chat/completions/raise_openai_enveloped")
        assert resp.json() == {"error": {"message": "pay", "type": "billing", "param": None, "code": "x"}}

    def test_exception_headers_preserved(self, error_client):
        """
        What it does: HTTPException carrying Retry-After.
        Purpose: Headers on the exception reach the client.
        """
        resp = error_client.get("/v1/chat/completions/raise_with_headers")
        assert resp.status_code == 429
        assert resp.headers["retry-after"] == "7"

    def test_unknown_route_404_is_openai_shaped(self, error_client):
        """
        What it does: Requests an unknown path.
        Purpose: Starlette's own 404 also uses the gateway error shape.
        """
        resp = error_client.get("/v1/does-not-exist")
        assert resp.status_code == 404
        assert resp.json()["error"]["type"] == "not_found_error"

    def test_unknown_anthropic_subpath_404_is_anthropic_shaped(self, error_client):
        """
        What it does: Unknown path under /v1/messages.
        Purpose: Anthropic clients get Anthropic errors even for routing errors.
        """
        resp = error_client.get("/v1/messages/nope/nope")
        assert resp.status_code == 404
        assert resp.json() == {"type": "error", "error": {"type": "not_found_error", "message": "Not Found"}}

    def test_method_not_allowed_preserves_405_and_allow(self, error_client):
        """
        What it does: GET on a POST-only route.
        Purpose: 405 status and Allow header kept, body shaped.
        """
        resp = error_client.get("/v1/chat/completions")
        assert resp.status_code == 405
        assert "allow" in resp.headers
        assert resp.json()["error"]["message"] == "Method Not Allowed"

    def test_models_with_anthropic_version_gets_anthropic_401(self, error_client):
        """
        What it does: /v1/models 401 with anthropic-version header.
        Purpose: Anthropic SDK listing models sees an Anthropic error.
        """
        resp = error_client.get("/v1/models", headers={"anthropic-version": "2023-06-01"})
        assert resp.json()["type"] == "error"
        assert resp.json()["error"]["type"] == "authentication_error"

    def test_models_without_anthropic_version_gets_openai_401(self, error_client):
        """
        What it does: /v1/models 401 without anthropic-version.
        Purpose: OpenAI clients keep OpenAI shape.
        """
        resp = error_client.get("/v1/models")
        assert resp.json()["error"]["type"] == "authentication_error"
        assert "type" not in resp.json()


class TestValidationHandlerShapes:
    """Tests for 422 shapes through a FastAPI app."""

    def test_anthropic_422_shape(self, error_client):
        """
        What it does: Invalid body on /v1/messages.
        Purpose: 422 with Anthropic invalid_request_error, no body echo.
        """
        resp = error_client.post("/v1/messages", json={"model": "secret-content-xyz"})
        assert resp.status_code == 422
        body = resp.json()
        assert body["type"] == "error"
        assert body["error"]["type"] == "invalid_request_error"
        assert "max_tokens" in body["error"]["message"]
        assert "secret-content-xyz" not in resp.text

    def test_openai_422_shape_with_param(self, error_client):
        """
        What it does: Invalid body on /v1/chat/completions.
        Purpose: 422 with OpenAI shape, param names the first bad field.
        """
        resp = error_client.post("/v1/chat/completions", json={"model": "secret-content-xyz"})
        assert resp.status_code == 422
        body = resp.json()
        assert set(body["error"]) == {"message", "type", "param", "code"}
        assert body["error"]["param"] == "max_tokens"
        assert "secret-content-xyz" not in resp.text

    def test_malformed_json_422(self, error_client):
        """
        What it does: Sends a non-JSON body.
        Purpose: Still a shaped 422, body not echoed.
        """
        resp = error_client.post("/v1/messages", content=b"{not json PRIVATE",
                                 headers={"content-type": "application/json"})
        assert resp.status_code == 422
        assert resp.json()["type"] == "error"
        assert "PRIVATE" not in resp.text


class TestSummarizeValidationErrors:
    """Tests for summarize_validation_errors and validation_error_param."""

    def test_limits_listed_errors(self):
        """
        What it does: Seven errors.
        Purpose: Message lists five and counts the rest.
        """
        from kiro.exceptions import summarize_validation_errors
        errors = [{"loc": ["body", f"f{i}"], "msg": "bad"} for i in range(7)]
        message = summarize_validation_errors(errors)
        assert "f4: bad" in message
        assert "f5" not in message
        assert "(and 2 more)" in message

    def test_exactly_five_has_no_suffix(self):
        """
        What it does: Exactly five errors (boundary).
        Purpose: No "(and 0 more)" suffix.
        """
        from kiro.exceptions import summarize_validation_errors
        message = summarize_validation_errors([{"loc": ["body", "a"], "msg": "bad"}] * 5)
        assert "more" not in message

    def test_never_includes_input(self):
        """
        What it does: Error with an "input" value.
        Purpose: User content is never put into the message.
        """
        from kiro.exceptions import summarize_validation_errors
        message = summarize_validation_errors([{"loc": ["body"], "msg": "bad", "input": "TOPSECRET"}])
        assert "TOPSECRET" not in message
        assert message == "Invalid request: bad"

    @pytest.mark.parametrize("error,expected", [
        ({"loc": ["body", "messages", 0, "role"]}, "messages.0.role"),
        ({"loc": ["body"]}, ""),
        ({"loc": ["query", "x"]}, "query.x"),
        ({}, ""),
        ({"loc": None}, ""),
    ])
    def test_param_path(self, error, expected):
        """
        What it does: Renders error locations.
        Purpose: param is a readable dotted path without the "body" prefix.
        """
        from kiro.exceptions import validation_error_param
        assert validation_error_param(error) == expected
