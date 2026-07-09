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


class MissingProfileArnError(ValueError):
    """
    Raised when no profileArn can be resolved for a Kiro API request.

    The Kiro runtime (`runtime.kiro.dev`) rejects `generateAssistantResponse`
    requests without a `profileArn` with an opaque HTTP 400
    ("profileArn is required for this request."). The Gateway detects this
    condition before contacting the Kiro API and surfaces this actionable
    error instead.

    This subclasses ``ValueError`` so that the existing ``except ValueError``
    handlers in both the OpenAI and Anthropic routes (streaming and
    non-streaming paths) translate it into an HTTP 400 response in the
    correct per-API error format.

    The error message intentionally references the ``PROFILE_ARN``
    configuration key and never includes any credential, token, or
    access-key value.
    """

    #: Default user-facing message. Contains the literal ``PROFILE_ARN`` key
    #: and a statement that the value is required. Contains no secrets.
    DEFAULT_MESSAGE: str = (
        "profileArn is required but could not be resolved. Set the PROFILE_ARN "
        "configuration value (for example, in your .env file) to your AWS "
        "CodeWhisperer profile ARN, or use credentials that provide one."
    )

    def __init__(self, message: str = "") -> None:
        """
        Initialize the error.

        Args:
            message: Optional override for the user-facing message. When empty,
                ``DEFAULT_MESSAGE`` is used.
        """
        super().__init__(message or self.DEFAULT_MESSAGE)


class MalformedProfileArnError(ValueError):
    """
    Raised when a profileArn is present but is not a valid CodeWhisperer ARN.

    The most common cause is leaving the documentation placeholder
    ``arn:aws:codewhisperer:us-east-1:...`` in the configuration (the ``...``
    is never replaced with a real AWS account ID and profile). The Kiro runtime
    accepts that *some* profileArn is present but then rejects the malformed
    value during body validation with an opaque
    ``HTTP 400 "Improperly formed request." (reason: REQUEST_BODY_INVALID)``.

    Detecting this in the Gateway lets us return an actionable error instead of
    the cryptic upstream one (AGENTS.md §9 "User Experience First").

    Subclasses ``ValueError`` so existing route handlers translate it to HTTP
    400 in the correct per-API error format. The message references the
    ``PROFILE_ARN`` key and never includes credential values.
    """

    def __init__(self, profile_arn: str = "") -> None:
        """
        Initialize the error.

        Args:
            profile_arn: The offending profileArn value. Only the
                non-sensitive ARN string is echoed (an ARN is an identifier,
                not a secret); it helps the user spot the placeholder.
        """
        detail = (
            f"PROFILE_ARN is set to an invalid value ('{profile_arn}'). "
            if profile_arn
            else "PROFILE_ARN is set to an invalid value. "
        )
        message = (
            f"{detail}It must be a real AWS CodeWhisperer profile ARN of the form "
            "'arn:aws:codewhisperer:<region>:<aws-account-id>:profile/<profile-id>'. "
            "The default '...' placeholder must be replaced with your actual AWS "
            "account ID and profile ID. You can find this ARN in your Kiro IDE "
            "request traffic, in the Amazon Q Developer console, or via kiro-cli."
        )
        super().__init__(message)


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