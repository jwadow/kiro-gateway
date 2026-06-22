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
Exception handlers for Kiro Gateway.

Contains functions for handling validation errors and other exceptions
in a JSON-serialization compatible format.
"""

from typing import Any, List, Dict

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger


def sanitize_validation_errors(errors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Converts validation errors to JSON-serializable format.
    
    Pydantic may include bytes objects in the 'input' field, which
    are not JSON-serializable. This function converts them to strings.
    
    Args:
        errors: List of validation errors from Pydantic
    
    Returns:
        List of errors with bytes converted to strings
    """
    sanitized = []
    for error in errors:
        sanitized_error = {}
        for key, value in error.items():
            if isinstance(value, bytes):
                # Convert bytes to string
                sanitized_error[key] = value.decode("utf-8", errors="replace")
            elif isinstance(value, (list, tuple)):
                # Recursively process lists
                sanitized_error[key] = [
                    v.decode("utf-8", errors="replace") if isinstance(v, bytes) else v
                    for v in value
                ]
            else:
                sanitized_error[key] = value
        sanitized.append(sanitized_error)
    return sanitized


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Pydantic validation error handler.
    
    Logs error details and returns an informative response.
    Correctly handles bytes objects in errors by converting them to strings.
    Also flushes debug logs for validation errors when DEBUG_MODE is enabled.
    
    Args:
        request: FastAPI Request object
        exc: Validation exception from Pydantic
    
    Returns:
        JSONResponse with error details and status 422
    """
    body = await request.body()
    body_str = body.decode("utf-8", errors="replace")
    
    # Sanitize errors for JSON serialization
    sanitized_errors = sanitize_validation_errors(exc.errors())
    
    logger.error(f"Validation error (422): {sanitized_errors}")
    # Log body at DEBUG level to avoid cluttering console with potentially large payloads
    # logger.debug(f"Request body: {body_str[:500]}...")
    
    # Flush debug logs for validation errors
    # This is called AFTER middleware has initialized debug logging,
    # so all app logs during request processing will be captured
    try:
        from kiro.debug_logger import debug_logger
        if debug_logger:
            error_message = f"Validation error: {sanitized_errors}"
            debug_logger.flush_on_error(422, error_message)
    except ImportError:
        pass  # debug_logger not available
    
    return JSONResponse(
        status_code=422,
        content={"detail": sanitized_errors, "body": body_str[:500]},
    )