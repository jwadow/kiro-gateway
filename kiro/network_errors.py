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
Network error classification and user-friendly message formatting.

This module provides a centralized system for classifying network errors
and converting them into actionable, user-friendly messages with troubleshooting steps.

Architecture:
- ErrorCategory: Enum of all possible network error types
- NetworkErrorInfo: Structured information about an error
- classify_network_error(): Analyzes exceptions and returns NetworkErrorInfo
- format_error_for_user(): Formats errors for API responses (OpenAI/Anthropic)
"""

import socket
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Any, Optional

import httpx
from loguru import logger


class ErrorCategory(str, Enum):
    """
    Categories of network errors.
    
    Each category represents a distinct type of network failure
    with specific troubleshooting steps.
    """
    DNS_RESOLUTION = "dns_resolution"
    CONNECTION_REFUSED = "connection_refused"
    CONNECTION_RESET = "connection_reset"
    NETWORK_UNREACHABLE = "network_unreachable"
    TIMEOUT_CONNECT = "timeout_connect"
    TIMEOUT_READ = "timeout_read"
    SSL_ERROR = "ssl_error"
    PROXY_ERROR = "proxy_error"
    TOO_MANY_REDIRECTS = "too_many_redirects"
    UNKNOWN = "unknown"


@dataclass
class NetworkErrorInfo:
    """
    Structured information about a network error.
    
    Attributes:
        category: Error category for classification
        user_message: Clear, non-technical message for end users
        troubleshooting_steps: List of actionable steps to resolve the issue
        technical_details: Technical error details for logging and debugging
        is_retryable: Whether retrying the request might succeed
        suggested_http_code: Appropriate HTTP status code (502, 504, etc.)
    """
    category: ErrorCategory
    user_message: str
    troubleshooting_steps: List[str]
    technical_details: str
    is_retryable: bool
    suggested_http_code: int


def classify_network_error(error: Exception) -> NetworkErrorInfo:
    """
    Classifies a network error and returns structured information.
    
    Analyzes the exception type, error message, and underlying cause
    to determine the specific type of network failure and provide
    appropriate user-facing messages and troubleshooting steps.
    
    Args:
        error: The exception that occurred (typically httpx.RequestError)
    
    Returns:
        NetworkErrorInfo with classification and user-friendly details
    
    Example:
        >>> try:
        ...     response = await client.get("https://example.com")
        ... except httpx.RequestError as e:
        ...     error_info = classify_network_error(e)
        ...     logger.error(f"[{error_info.category}] {error_info.user_message}")
    """
    error_type = type(error).__name__
    error_str = str(error)
    
    # Extract technical details for logging
    technical_details = f"{error_type}: {error_str}"
    
    # Analyze httpx.ConnectError (connection establishment failures)
    if isinstance(error, httpx.ConnectError):
        return _classify_connect_error(error, technical_details)
    
    # Analyze httpx.TimeoutException (various timeout types)
    if isinstance(error, httpx.TimeoutException):
        return _classify_timeout_error(error, technical_details)
    
    # Analyze httpx.TooManyRedirects
    if isinstance(error, httpx.TooManyRedirects):
        return NetworkErrorInfo(
            category=ErrorCategory.TOO_MANY_REDIRECTS,
            user_message="Too many redirects - the server is redirecting in a loop.",
            troubleshooting_steps=[
                "This is likely a server-side configuration issue",
                "Try accessing the service directly without the gateway",
                "Contact the service provider if the issue persists"
            ],
            technical_details=technical_details,
            is_retryable=False,
            suggested_http_code=502
        )
    
    # Analyze httpx.ProxyError
    if isinstance(error, httpx.ProxyError):
        return NetworkErrorInfo(
            category=ErrorCategory.PROXY_ERROR,
            user_message="Proxy connection failed - cannot connect through the configured proxy.",
            troubleshooting_steps=[
                "Check proxy configuration (HTTP_PROXY, HTTPS_PROXY environment variables)",
                "Verify proxy server is accessible",
                "Try disabling proxy temporarily",
                "Check proxy authentication credentials if required"
            ],
            technical_details=technical_details,
            is_retryable=True,
            suggested_http_code=502
        )
    
    # Generic httpx.RequestError (catch-all)
    if isinstance(error, httpx.RequestError):
        return NetworkErrorInfo(
            category=ErrorCategory.UNKNOWN,
            user_message="Network request failed due to an unexpected error.",
            troubleshooting_steps=[
                "Check your internet connection",
                "Verify firewall/antivirus settings",
                "Try again in a few moments",
                "Check the debug logs for more details"
            ],
            technical_details=technical_details,
            is_retryable=True,
            suggested_http_code=502
        )
    
    # Non-httpx errors (shouldn't happen, but handle gracefully)
    return NetworkErrorInfo(
        category=ErrorCategory.UNKNOWN,
        user_message="An unexpected error occurred.",
        troubleshooting_steps=[
            "Check the debug logs for details",
            "Try again in a few moments",
            "Report this issue if it persists"
        ],
        technical_details=technical_details,
        is_retryable=True,
        suggested_http_code=500
    )


def _classify_connect_error(error: httpx.ConnectError, technical_details: str) -> NetworkErrorInfo:
    """
    Classifies httpx.ConnectError into specific subcategories.
    
    Args:
        error: The ConnectError exception
        technical_details: Technical error string for logging
    
    Returns:
        NetworkErrorInfo with specific classification
    """
    error_str = str(error)
    
    # Check underlying cause chain for more specific errors
    cause = error.__cause__
    
    # Check for DNS errors (socket.gaierror)
    if cause and isinstance(cause, socket.gaierror):
        # DNS resolution failed
        # Common errno values:
        # - 11001 (Windows): WSAHOST_NOT_FOUND
        # - -2, -3, -5 (Unix): EAI_NONAME, EAI_AGAIN, EAI_NODATA
        errno = getattr(cause, 'errno', None)
        
        return NetworkErrorInfo(
            category=ErrorCategory.DNS_RESOLUTION,
            user_message="DNS resolution failed - cannot resolve the provider's domain name.",
            troubleshooting_steps=[
                "Check your internet connection",
                "Try changing DNS servers to Google DNS (8.8.8.8, 8.8.4.4) or Cloudflare (1.1.1.1, 1.0.0.1)",
                "Temporarily disable VPN if you're using one",
                "Check if firewall/antivirus is blocking DNS requests",
                "Verify the domain name is correct and the service is operational"
            ],
            technical_details=f"{technical_details} (errno: {errno})",
            is_retryable=True,
            suggested_http_code=502
        )
    
    # Check for connection refused
    if "Connection refused" in error_str or "ECONNREFUSED" in error_str:
        return NetworkErrorInfo(
            category=ErrorCategory.CONNECTION_REFUSED,
            user_message="Connection refused - the server is not accepting connections.",
            troubleshooting_steps=[
                "The service may be temporarily down",
                "Check if the service is running and accessible",
                "Verify firewall is not blocking the connection",
                "Try again in a few moments"
            ],
            technical_details=technical_details,
            is_retryable=True,
            suggested_http_code=502
        )
    
    # Check for connection reset
    if "Connection reset" in error_str or "ECONNRESET" in error_str:
        return NetworkErrorInfo(
            category=ErrorCategory.CONNECTION_RESET,
            user_message="Connection reset - the server closed the connection unexpectedly.",
            troubleshooting_steps=[
                "This is usually a temporary server issue",
                "Try again in a few moments",
                "Check if VPN/proxy is interfering with the connection",
                "Verify network stability"
            ],
            technical_details=technical_details,
            is_retryable=True,
            suggested_http_code=502
        )
    
    # Check for network unreachable
    if "Network is unreachable" in error_str or "No route to host" in error_str or "ENETUNREACH" in error_str:
        return NetworkErrorInfo(
            category=ErrorCategory.NETWORK_UNREACHABLE,
            user_message="Network unreachable - cannot reach the server's network.",
            troubleshooting_steps=[
                "Check your internet connection",
                "Verify network adapter is enabled and working",
                "Check routing table if using VPN",
                "Try disabling VPN temporarily",
                "Restart network adapter or router"
            ],
            technical_details=technical_details,
            is_retryable=True,
            suggested_http_code=502
        )
    
    # Check for SSL/TLS errors
    if "SSL" in error_str or "TLS" in error_str or "certificate" in error_str.lower():
        return NetworkErrorInfo(
            category=ErrorCategory.SSL_ERROR,
            user_message="SSL/TLS error - secure connection could not be established.",
            troubleshooting_steps=[
                "Check system date and time (incorrect time causes SSL errors)",
                "Update SSL certificates on your system",
                "Check if antivirus/firewall is intercepting HTTPS traffic",
                "Verify the server's SSL certificate is valid"
            ],
            technical_details=technical_details,
            is_retryable=False,
            suggested_http_code=502
        )
    
    # Generic connection error
    return NetworkErrorInfo(
        category=ErrorCategory.UNKNOWN,
        user_message="Connection failed - unable to establish connection to the server.",
        troubleshooting_steps=[
            "Check your internet connection",
            "Verify firewall/antivirus settings",
            "Try disabling VPN temporarily",
            "Check if the service is accessible from other devices"
        ],
        technical_details=technical_details,
        is_retryable=True,
        suggested_http_code=502
    )


def _classify_timeout_error(error: httpx.TimeoutException, technical_details: str) -> NetworkErrorInfo:
    """
    Classifies httpx.TimeoutException into specific subcategories.
    
    Args:
        error: The TimeoutException
        technical_details: Technical error string for logging
    
    Returns:
        NetworkErrorInfo with specific classification
    """
    # ConnectTimeout: TCP handshake timeout
    if isinstance(error, httpx.ConnectTimeout):
        return NetworkErrorInfo(
            category=ErrorCategory.TIMEOUT_CONNECT,
            user_message="Connection timeout - server did not respond to connection attempt.",
            troubleshooting_steps=[
                "Check your internet connection speed",
                "The server may be overloaded or slow to respond",
                "Try again in a few moments",
                "Check if firewall is delaying connections"
            ],
            technical_details=technical_details,
            is_retryable=True,
            suggested_http_code=504
        )
    
    # ReadTimeout: Server stopped sending data
    if isinstance(error, httpx.ReadTimeout):
        return NetworkErrorInfo(
            category=ErrorCategory.TIMEOUT_READ,
            user_message="Read timeout - server stopped responding during data transfer.",
            troubleshooting_steps=[
                "The server may be processing a complex request",
                "Check your internet connection stability",
                "Try again with a simpler request",
                "The service may be experiencing high load"
            ],
            technical_details=technical_details,
            is_retryable=True,
            suggested_http_code=504
        )
    
    # Generic timeout
    return NetworkErrorInfo(
        category=ErrorCategory.TIMEOUT_READ,
        user_message="Request timeout - operation took too long to complete.",
        troubleshooting_steps=[
            "Check your internet connection",
            "The server may be slow or overloaded",
            "Try again in a few moments"
        ],
        technical_details=technical_details,
        is_retryable=True,
        suggested_http_code=504
    )


def format_error_for_user(
    error_info: NetworkErrorInfo,
    format_type: str = "openai",
    include_troubleshooting: bool = True
) -> Dict[str, Any]:
    """
    Formats NetworkErrorInfo for API response.
    
    Converts structured error information into the appropriate format
    for OpenAI or Anthropic API responses.
    
    Args:
        error_info: The classified error information
        format_type: "openai" or "anthropic" format
        include_troubleshooting: Whether to include troubleshooting steps
    
    Returns:
        Dictionary formatted for API response
    
    Example:
        >>> error_info = classify_network_error(exception)
        >>> response = format_error_for_user(error_info, format_type="openai")
        >>> return JSONResponse(status_code=502, content=response)
    """
    # Build the message
    message = error_info.user_message
    
    if include_troubleshooting and error_info.troubleshooting_steps:
        message += "\n\nTroubleshooting steps:\n"
        for i, step in enumerate(error_info.troubleshooting_steps, 1):
            message += f"{i}. {step}\n"
    
    # Format for OpenAI API
    if format_type == "openai":
        return {
            "error": {
                "message": message.strip(),
                "type": "connectivity_error",
                "code": error_info.category.value,
                "param": None
            }
        }
    
    # Format for Anthropic API
    elif format_type == "anthropic":
        return {
            "type": "error",
            "error": {
                "type": "connectivity_error",
                "message": message.strip()
            }
        }
    
    # Generic format (fallback)
    else:
        return {
            "error": {
                "type": "connectivity_error",
                "category": error_info.category.value,
                "message": message.strip(),
                "technical_details": error_info.technical_details
            }
        }


def get_short_error_message(error_info: NetworkErrorInfo) -> str:
    """
    Returns a short, single-line error message for logging.
    
    Args:
        error_info: The classified error information
    
    Returns:
        Short error message suitable for log files
    
    Example:
        >>> error_info = classify_network_error(exception)
        >>> logger.warning(get_short_error_message(error_info))
    """
    return error_info.user_message


def build_http_error_detail(error_info: NetworkErrorInfo) -> str:
    """
    Builds a detailed, user-friendly error string for an HTTPException detail.

    Combines the user-facing message, numbered troubleshooting steps, and the
    technical details into a single multi-line string. This is the standard
    representation used when raising an HTTPException for a classified network
    error, so that connectivity failures surface the same actionable guidance
    everywhere in the gateway (HTTP client retries and mid-stream body drops).

    Args:
        error_info: The classified network error information.

    Returns:
        A formatted, stripped multi-line error message suitable for use as an
        HTTPException `detail`.

    Example:
        >>> error_info = classify_network_error(exception)
        >>> raise HTTPException(
        ...     status_code=error_info.suggested_http_code,
        ...     detail=build_http_error_detail(error_info),
        ... )
    """
    detail = error_info.user_message

    if error_info.troubleshooting_steps:
        detail += "\n\nTroubleshooting:\n"
        for i, step in enumerate(error_info.troubleshooting_steps, 1):
            detail += f"{i}. {step}\n"

    detail += f"\nTechnical details: {error_info.technical_details}"

    return detail.strip()
