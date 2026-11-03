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
Exception handlers and error shaping for Kiro Gateway.

Every error the gateway produces is rendered in the shape the calling client expects:

- OpenAI-compatible paths: {"error": {"message", "type", "param", "code"}}
- Anthropic paths (/v1/messages*, or /v1/models* called with an
  anthropic-version header): {"type": "error", "error": {"type", "message"}}

Status codes and exception headers (e.g. Retry-After) are preserved.
"""

from typing import Any, Dict, List, Mapping, Optional

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException


# Paths served by the Anthropic-compatible router
ANTHROPIC_PATH_PREFIX: str = "/v1/messages"

# Paths serving both API families; the error shape follows the anthropic-version header
DUAL_FORMAT_PATH_PREFIX: str = "/v1/models"

# Anthropic error "type" by HTTP status (https://docs.anthropic.com/en/api/errors)
ANTHROPIC_ERROR_TYPES: Dict[int, str] = {
    400: "invalid_request_error",
    401: "authentication_error",
    403: "permission_error",
    404: "not_found_error",
    413: "request_too_large",
    422: "invalid_request_error",
    429: "rate_limit_error",
    503: "overloaded_error",
    529: "overloaded_error",
}

# All error types an Anthropic client can receive
ANTHROPIC_KNOWN_TYPES = frozenset(ANTHROPIC_ERROR_TYPES.values()) | {"api_error"}

# OpenAI error "type" by HTTP status
OPENAI_ERROR_TYPES: Dict[int, str] = {
    400: "invalid_request_error",
    401: "authentication_error",
    403: "permission_error",
    404: "not_found_error",
    422: "invalid_request_error",
    429: "rate_limit_error",
}

# Statuses for which an upstream Retry-After header is forwarded to the client
RETRY_AFTER_STATUSES = frozenset({429, 503})

# Upper bound for a forwarded Retry-After value (delta-seconds or HTTP-date fit easily)
MAX_RETRY_AFTER_LENGTH: int = 64

# Fallback message when an exception carries no usable detail
DEFAULT_ERROR_MESSAGE: str = "An error occurred while processing the request."

# Maximum number of validation errors listed in a 422 message
MAX_VALIDATION_ERRORS_IN_MESSAGE: int = 5


def anthropic_error_type(status_code: int) -> str:
    """
    Map an HTTP status to an Anthropic error type.

    Args:
        status_code: HTTP status code

    Returns:
        Anthropic error type, "api_error" for unmapped statuses
    """
    return ANTHROPIC_ERROR_TYPES.get(status_code, "api_error")


def openai_error_type(status_code: int) -> str:
    """
    Map an HTTP status to an OpenAI error type.

    Args:
        status_code: HTTP status code

    Returns:
        OpenAI error type: mapped value, "api_error" for other 5xx,
        "invalid_request_error" for other 4xx
    """
    if status_code in OPENAI_ERROR_TYPES:
        return OPENAI_ERROR_TYPES[status_code]
    return "api_error" if status_code >= 500 else "invalid_request_error"


def build_openai_error(
    message: str,
    status_code: int,
    error_type: Optional[str] = None,
    param: Optional[str] = None,
    code: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Build an OpenAI-shaped error body.

    Args:
        message: User-facing error message
        status_code: HTTP status (used to derive the type when not given)
        error_type: Explicit error type
        param: Offending request parameter
        code: Error code

    Returns:
        {"error": {"message", "type", "param", "code"}}
    """
    return {
        "error": {
            "message": message,
            "type": error_type or openai_error_type(status_code),
            "param": param,
            "code": code,
        }
    }


def build_anthropic_error(
    message: str,
    status_code: int,
    error_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build an Anthropic-shaped error body.

    Args:
        message: User-facing error message
        status_code: HTTP status (used to derive the type when not given)
        error_type: Explicit error type

    Returns:
        {"type": "error", "error": {"type", "message"}}
    """
    return {
        "type": "error",
        "error": {
            "type": error_type or anthropic_error_type(status_code),
            "message": message,
        },
    }


def _path_matches(path: str, prefix: str) -> bool:
    """
    Check whether a path equals a prefix or is nested under it.

    Args:
        path: Request URL path
        prefix: Path prefix without trailing slash

    Returns:
        True if path is prefix or prefix/...
    """
    return path == prefix or path.startswith(prefix + "/")


def wants_anthropic_errors(path: str, headers: Optional[Mapping[str, str]] = None) -> bool:
    """
    Decide whether an error for this request should use the Anthropic shape.

    Args:
        path: Request URL path
        headers: Request headers (case-insensitive mapping)

    Returns:
        True for /v1/messages paths, and for /v1/models paths called with an
        anthropic-version header; False otherwise
    """
    if not isinstance(path, str):
        return False
    if _path_matches(path, ANTHROPIC_PATH_PREFIX):
        return True
    if _path_matches(path, DUAL_FORMAT_PATH_PREFIX):
        return bool(headers is not None and headers.get("anthropic-version"))
    return False


def _extract_message(detail: Any) -> str:
    """
    Extract a human-readable message from an HTTPException detail.

    Args:
        detail: String, dict (possibly already an error envelope) or other value

    Returns:
        Message string
    """
    if detail is None:
        return DEFAULT_ERROR_MESSAGE
    if isinstance(detail, str):
        return detail or DEFAULT_ERROR_MESSAGE
    if isinstance(detail, dict):
        inner = detail.get("error")
        if isinstance(inner, dict) and inner.get("message"):
            return str(inner["message"])
        if detail.get("message"):
            return str(detail["message"])
    return str(detail)


def format_error_body(status_code: int, detail: Any, anthropic: bool) -> Dict[str, Any]:
    """
    Convert an exception detail into the target error shape without double-wrapping.

    A detail that is already a complete envelope of the target shape is returned
    unchanged. An envelope of the other shape is converted (message and type kept
    when the type is valid for the target API).

    Args:
        status_code: HTTP status code
        detail: HTTPException detail (string or dict)
        anthropic: True for the Anthropic shape, False for the OpenAI shape

    Returns:
        Error body in the requested shape
    """
    inner = detail.get("error") if isinstance(detail, dict) else None
    if not isinstance(inner, dict):
        inner = None
    message = _extract_message(detail)

    if anthropic:
        if inner is not None and detail.get("type") == "error" and "message" in inner and "type" in inner:
            return detail
        inner_type = inner.get("type") if inner is not None else None
        error_type = inner_type if inner_type in ANTHROPIC_KNOWN_TYPES else None
        return build_anthropic_error(message, status_code, error_type)

    if inner is not None and "message" in inner and detail.get("type") != "error":
        # Already OpenAI-shaped: normalize to the full four-field form
        return build_openai_error(
            str(inner["message"]),
            status_code,
            error_type=inner.get("type"),
            param=inner.get("param"),
            code=inner.get("code"),
        )
    return build_openai_error(message, status_code)


def error_response_for(
    path: str,
    headers: Optional[Mapping[str, str]],
    status_code: int,
    detail: Any,
    response_headers: Optional[Dict[str, str]] = None,
) -> JSONResponse:
    """
    Build a JSONResponse in the shape the client at `path` expects.

    Args:
        path: Request URL path
        headers: Request headers
        status_code: HTTP status code
        detail: Error detail (string or dict)
        response_headers: Extra response headers (e.g. Retry-After)

    Returns:
        JSONResponse with the shaped error body
    """
    body = format_error_body(status_code, detail, wants_anthropic_errors(path, headers))
    return JSONResponse(status_code=status_code, content=body, headers=response_headers)


def retry_after_headers(status_code: int, upstream_headers: Any) -> Optional[Dict[str, str]]:
    """
    Extract a Retry-After header from an upstream response for forwarding.

    Only forwarded for 429/503. Values that are not short single-line strings
    are ignored so an upstream cannot inject response headers.

    Args:
        status_code: Upstream HTTP status
        upstream_headers: Upstream headers mapping (httpx.Headers or dict-like)

    Returns:
        {"Retry-After": value}, or None when not applicable
    """
    if status_code not in RETRY_AFTER_STATUSES or upstream_headers is None:
        return None
    getter = getattr(upstream_headers, "get", None)
    if not callable(getter):
        return None
    try:
        value = getter("retry-after")
        if value is None:
            # Plain dicts are case-sensitive (e.g. a mapping we built ourselves)
            value = getter("Retry-After")
    except (TypeError, KeyError):
        return None
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > MAX_RETRY_AFTER_LENGTH or "\r" in value or "\n" in value:
        return None
    return {"Retry-After": value}


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """
    Render an HTTPException in the OpenAI or Anthropic error shape.

    Preserves the status code and any headers attached to the exception.

    Args:
        request: FastAPI Request object
        exc: Raised HTTPException

    Returns:
        JSONResponse with the shaped error
    """
    exc_headers = getattr(exc, "headers", None)
    return error_response_for(
        request.url.path,
        request.headers,
        exc.status_code,
        exc.detail,
        dict(exc_headers) if exc_headers else None,
    )


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


def validation_error_param(error: Dict[str, Any]) -> str:
    """
    Render a validation error location as a dotted parameter path.

    The leading "body" segment added by FastAPI is dropped.

    Args:
        error: Single sanitized validation error

    Returns:
        Parameter path such as "messages.0.role", or "" for the whole body
    """
    loc = list(error.get("loc") or [])
    if loc and loc[0] == "body":
        loc = loc[1:]
    return ".".join(str(part) for part in loc)


def summarize_validation_errors(errors: List[Dict[str, Any]]) -> str:
    """
    Build a short user-facing message from validation errors.

    Never includes the offending input values, which may contain user content.

    Args:
        errors: Sanitized validation errors

    Returns:
        Message such as "Invalid request: messages: Field required"
    """
    if not errors:
        return "Invalid request body."
    parts = []
    for error in errors[:MAX_VALIDATION_ERRORS_IN_MESSAGE]:
        location = validation_error_param(error)
        msg = str(error.get("msg") or "invalid value")
        parts.append(f"{location}: {msg}" if location else msg)
    extra = len(errors) - MAX_VALIDATION_ERRORS_IN_MESSAGE
    suffix = f" (and {extra} more)" if extra > 0 else ""
    return "Invalid request: " + "; ".join(parts) + suffix


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Pydantic validation error handler.

    Logs error details and returns a 422 in the OpenAI or Anthropic error shape.
    The request body is never echoed back to the client.
    Also flushes debug logs for validation errors when DEBUG_MODE is enabled.

    Args:
        request: FastAPI Request object
        exc: Validation exception from Pydantic

    Returns:
        JSONResponse with error details and status 422
    """
    # Sanitize errors for JSON serialization
    sanitized_errors = sanitize_validation_errors(exc.errors())

    logger.error(f"Validation error (422): {sanitized_errors}")

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

    message = summarize_validation_errors(sanitized_errors)
    if wants_anthropic_errors(request.url.path, request.headers):
        body = build_anthropic_error(message, 422)
    else:
        param = validation_error_param(sanitized_errors[0]) if sanitized_errors else ""
        body = build_openai_error(message, 422, param=param or None)

    return JSONResponse(status_code=422, content=body)
