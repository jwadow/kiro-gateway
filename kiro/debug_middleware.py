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
Debug logging middleware for Kiro Gateway.

This middleware initializes debug logging BEFORE Pydantic validation,
which allows capturing validation errors (422) in debug logs.

The middleware:
1. Intercepts requests to API endpoints (/v1/chat/completions, /v1/messages)
2. Calls prepare_new_request() to initialize buffers and loguru sink
3. Reads and logs the raw request body
4. Passes the request to the next handler

Flush/discard operations are handled by:
- Route handlers (for successful requests and Kiro API errors)
- Exception handlers (for validation errors and other exceptions)

Also provides RequestIdMiddleware, a pure ASGI middleware that tags every
response with request-id / x-request-id headers.
"""

import uuid
from typing import Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from loguru import logger

from kiro.config import DEBUG_MODE


# API endpoints that should have debug logging enabled
# These are the main API endpoints that process user requests
LOGGED_ENDPOINTS = frozenset({
    "/v1/chat/completions",  # OpenAI-compatible endpoint
    "/v1/messages",          # Anthropic-compatible endpoint
    "/v1/responses",         # OpenAI Responses API endpoint
})


class DebugLoggerMiddleware(BaseHTTPMiddleware):
    """
    Middleware for initializing debug logging on API requests.
    
    This middleware runs BEFORE Pydantic validation, which means it can
    capture the raw request body even for requests that fail validation.
    
    The middleware only activates for API endpoints defined in LOGGED_ENDPOINTS.
    Health checks, documentation, and other endpoints are not logged.
    
    Lifecycle:
    - prepare_new_request(): Called here (before validation)
    - log_request_body(): Called here (raw body from client)
    - log_kiro_request_body(): Called in route handlers (transformed payload)
    - flush_on_error() / discard_buffers(): Called in routes or exception handlers
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process the request and initialize debug logging if needed.
        
        Args:
            request: The incoming HTTP request
            call_next: The next middleware or route handler
            
        Returns:
            The response from the next handler
        """
        # Skip logging for non-API endpoints (health, docs, etc.)
        if request.url.path not in LOGGED_ENDPOINTS:
            return await call_next(request)
        
        # Skip if debug mode is disabled
        if DEBUG_MODE == "off":
            return await call_next(request)
        
        # Import here to avoid circular imports and allow graceful degradation
        try:
            from kiro.debug_logger import debug_logger
        except ImportError:
            logger.warning("debug_logger not available, skipping debug logging")
            return await call_next(request)
        
        # Initialize debug logging for this request
        # This sets up buffers and creates a loguru sink to capture app logs
        debug_logger.prepare_new_request()
        
        # Read and log the raw request body
        # FastAPI caches the body after first read, so this is safe
        try:
            body = await request.body()
            if body:
                debug_logger.log_request_body(body)
        except Exception as e:
            logger.warning(f"Failed to read request body for debug logging: {e}")
        
        # Continue to validation and route handler
        # flush_on_error() or discard_buffers() will be called by:
        # - Route handlers (for successful requests and Kiro API errors)
        # - validation_exception_handler (for 422 validation errors)
        # - Generic exception handlers (for other errors)
        response = await call_next(request)
        
        return response


# Response headers carrying the per-request id (Anthropic uses "request-id", OpenAI "x-request-id")
REQUEST_ID_HEADERS: Tuple[bytes, ...] = (b"request-id", b"x-request-id")

# Prefix of generated request ids (mirrors Anthropic's "req_..." format)
REQUEST_ID_PREFIX: str = "req_"


def generate_request_id() -> str:
    """
    Generate a unique request id.

    Returns:
        Id such as "req_3f2b...", 32 hex chars after the prefix
    """
    return f"{REQUEST_ID_PREFIX}{uuid.uuid4().hex}"


class RequestIdMiddleware:
    """
    Pure ASGI middleware adding request-id and x-request-id headers to every HTTP response.

    Implemented without BaseHTTPMiddleware so streaming (SSE) bodies pass through
    untouched: only the http.response.start message is modified. The id is also
    stored in scope["state"]["request_id"] for handlers that want to log it.
    """

    def __init__(self, app: ASGIApp) -> None:
        """
        Args:
            app: Wrapped ASGI application
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Handle one ASGI connection.

        Args:
            scope: ASGI scope
            receive: ASGI receive callable
            send: ASGI send callable
        """
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_id = generate_request_id()
        scope.setdefault("state", {})["request_id"] = request_id
        encoded_id = request_id.encode("latin-1")

        async def send_with_request_id(message: Message) -> None:
            if message.get("type") == "http.response.start":
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() not in REQUEST_ID_HEADERS
                ]
                headers.extend((name, encoded_id) for name in REQUEST_ID_HEADERS)
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_request_id)
