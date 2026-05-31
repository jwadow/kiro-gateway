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
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from loguru import logger

from kiro.config import DEBUG_MODE


# API endpoints that should have debug logging enabled
# These are the main API endpoints that process user requests
LOGGED_ENDPOINTS = frozenset({
    "/v1/chat/completions",  # OpenAI-compatible endpoint
    "/v1/responses",         # OpenAI Responses-compatible endpoint
    "/v1/messages",          # Anthropic-compatible endpoint
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
