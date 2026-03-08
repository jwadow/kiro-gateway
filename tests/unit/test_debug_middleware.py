# -*- coding: utf-8 -*-

"""
Unit tests for DebugLoggerMiddleware.
Tests debug logging initialization at the middleware level.
"""

import asyncio

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
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


class TestDebugLoggerMiddlewareRequestBodyPreservation:
    """Tests for preserving request bodies for downstream handlers."""

    @pytest.mark.asyncio
    async def test_preserves_request_body_for_downstream_handler(self):
        """
        What it does: Verifies that the middleware does not consume the request body.
        Purpose: Ensure downstream FastAPI handlers can still parse JSON bodies.
        """
        print("Setup: Creating FastAPI app with DebugLoggerMiddleware...")

        with patch('kiro.debug_middleware.DEBUG_MODE', 'all'):
            from kiro.debug_middleware import DebugLoggerMiddleware

            app = FastAPI()
            app.add_middleware(DebugLoggerMiddleware)

            @app.post("/v1/chat/completions")
            async def chat_completions(payload: dict):
                return payload

            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as client:
                    print("Action: Sending JSON request through middleware...")
                    response = await asyncio.wait_for(
                        client.post(
                            "/v1/chat/completions",
                            json={"model": "test", "messages": [{"role": "user", "content": "ping"}]},
                        ),
                        timeout=1.0,
                    )

            print("Verifying downstream handler received the full JSON body...")
            assert response.status_code == 200
            assert response.json() == {
                "model": "test",
                "messages": [{"role": "user", "content": "ping"}],
            }
            mock_logger.prepare_new_request.assert_called_once()
            mock_logger.log_request_body.assert_called_once()

    @pytest.mark.asyncio
    async def test_preserves_empty_request_body_for_downstream_handler(self):
        """
        What it does: Verifies that empty request bodies do not hang downstream handlers.
        Purpose: Ensure the middleware replays EOF semantics even for empty bodies.
        """
        print("Setup: Creating FastAPI app for empty body request...")

        with patch('kiro.debug_middleware.DEBUG_MODE', 'all'):
            from kiro.debug_middleware import DebugLoggerMiddleware

            app = FastAPI()
            app.add_middleware(DebugLoggerMiddleware)

            @app.post("/v1/chat/completions")
            async def chat_completions(request: Request):
                return {"body": (await request.body()).decode("utf-8")}

            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as client:
                    print("Action: Sending empty request body through middleware...")
                    response = await asyncio.wait_for(
                        client.post(
                            "/v1/chat/completions",
                            content=b"",
                        ),
                        timeout=1.0,
                    )

            print("Verifying downstream handler completed without hanging...")
            assert response.status_code == 200
            assert response.json() == {"body": ""}
            mock_logger.prepare_new_request.assert_called_once()
            mock_logger.log_request_body.assert_not_called()


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
