# -*- coding: utf-8 -*-

"""
Unit tests for network error classification system.
Tests classify_network_error(), format_error_for_user(), and get_short_error_message().
"""

import socket
import pytest

import httpx

from kiro.network_errors import (
    ErrorCategory,
    NetworkErrorInfo,
    classify_network_error,
    format_error_for_user,
    get_short_error_message,
    build_http_error_detail,
)


class TestClassifyNetworkErrorDNS:
    """Tests for DNS resolution error classification."""
    
    def test_dns_error_with_socket_gaierror_windows(self):
        """
        What it does: Verifies DNS errors are classified correctly on Windows.
        Purpose: Ensure socket.gaierror with errno 11001 is detected as DNS_RESOLUTION (issue #53).
        """
        print("Setup: Creating ConnectError with socket.gaierror (Windows errno 11001)...")
        dns_error = socket.gaierror(11001, "getaddrinfo failed")
        connect_error = httpx.ConnectError("All connection attempts failed")
        connect_error.__cause__ = dns_error
        
        print("Action: Classifying error...")
        error_info = classify_network_error(connect_error)
        
        print("Verification: Category is DNS_RESOLUTION...")
        print(f"Comparing category: Expected {ErrorCategory.DNS_RESOLUTION}, Got {error_info.category}")
        assert error_info.category == ErrorCategory.DNS_RESOLUTION
        assert "DNS resolution failed" in error_info.user_message
        assert "cannot resolve" in error_info.user_message.lower()
        assert error_info.is_retryable is True
        assert error_info.suggested_http_code == 502
        assert "11001" in error_info.technical_details
    
    def test_dns_error_with_socket_gaierror_unix(self):
        """
        What it does: Verifies DNS errors are classified correctly on Unix.
        Purpose: Ensure socket.gaierror with Unix errno is detected as DNS_RESOLUTION.
        """
        print("Setup: Creating ConnectError with socket.gaierror (Unix errno -2)...")
        dns_error = socket.gaierror(-2, "Name or service not known")
        connect_error = httpx.ConnectError("Connection failed")
        connect_error.__cause__ = dns_error
        
        print("Action: Classifying error...")
        error_info = classify_network_error(connect_error)
        
        print("Verification: Category is DNS_RESOLUTION...")
        assert error_info.category == ErrorCategory.DNS_RESOLUTION
        assert "DNS" in error_info.user_message
        assert "-2" in error_info.technical_details
    
    def test_dns_error_includes_troubleshooting_steps(self):
        """
        What it does: Verifies DNS errors include actionable troubleshooting steps.
        Purpose: Ensure users get clear guidance on fixing DNS issues.
        """
        print("Setup: Creating DNS error...")
        dns_error = socket.gaierror(11001, "getaddrinfo failed")
        connect_error = httpx.ConnectError("Connection failed")
        connect_error.__cause__ = dns_error
        
        print("Action: Classifying error...")
        error_info = classify_network_error(connect_error)
        
        print("Verification: Troubleshooting steps present...")
        steps = error_info.troubleshooting_steps
        assert len(steps) >= 3
        assert any("DNS" in step for step in steps)
        assert any("8.8.8.8" in step or "1.1.1.1" in step for step in steps)
        assert any("VPN" in step for step in steps)
        assert any("firewall" in step.lower() or "antivirus" in step.lower() for step in steps)
    
    def test_dns_error_technical_details_include_errno(self):
        """
        What it does: Verifies technical details include errno for debugging.
        Purpose: Ensure developers can identify specific DNS error codes.
        """
        print("Setup: Creating DNS error with specific errno...")
        dns_error = socket.gaierror(11001, "getaddrinfo failed")
        connect_error = httpx.ConnectError("Failed")
        connect_error.__cause__ = dns_error
        
        print("Action: Classifying error...")
        error_info = classify_network_error(connect_error)
        
        print("Verification: Technical details include errno...")
        assert "errno" in error_info.technical_details.lower()
        assert "11001" in error_info.technical_details


class TestClassifyNetworkErrorConnection:
    """Tests for connection error classification."""
    
    def test_connection_refused_error(self):
        """
        What it does: Verifies connection refused errors are classified correctly.
        Purpose: Ensure "Connection refused" is detected as CONNECTION_REFUSED.
        """
        print("Setup: Creating ConnectError with 'Connection refused'...")
        connect_error = httpx.ConnectError("Connection refused")
        
        print("Action: Classifying error...")
        error_info = classify_network_error(connect_error)
        
        print("Verification: Category is CONNECTION_REFUSED...")
        print(f"Comparing category: Expected {ErrorCategory.CONNECTION_REFUSED}, Got {error_info.category}")
        assert error_info.category == ErrorCategory.CONNECTION_REFUSED
        assert "Connection refused" in error_info.user_message
        assert "not accepting connections" in error_info.user_message
        assert error_info.is_retryable is True
        assert error_info.suggested_http_code == 502
    
    def test_connection_refused_with_econnrefused(self):
        """
        What it does: Verifies ECONNREFUSED is detected as CONNECTION_REFUSED.
        Purpose: Ensure Unix-style error codes are recognized.
        """
        print("Setup: Creating ConnectError with ECONNREFUSED...")
        connect_error = httpx.ConnectError("[Errno 111] ECONNREFUSED")
        
        print("Action: Classifying error...")
        error_info = classify_network_error(connect_error)
        
        print("Verification: Category is CONNECTION_REFUSED...")
        assert error_info.category == ErrorCategory.CONNECTION_REFUSED
    
    def test_connection_reset_error(self):
        """
        What it does: Verifies connection reset errors are classified correctly.
        Purpose: Ensure "Connection reset" is detected as CONNECTION_RESET.
        """
        print("Setup: Creating ConnectError with 'Connection reset'...")
        connect_error = httpx.ConnectError("Connection reset by peer")
        
        print("Action: Classifying error...")
        error_info = classify_network_error(connect_error)
        
        print("Verification: Category is CONNECTION_RESET...")
        print(f"Comparing category: Expected {ErrorCategory.CONNECTION_RESET}, Got {error_info.category}")
        assert error_info.category == ErrorCategory.CONNECTION_RESET
        assert "Connection reset" in error_info.user_message
        assert "closed the connection" in error_info.user_message
        assert error_info.is_retryable is True
    
    def test_connection_reset_with_econnreset(self):
        """
        What it does: Verifies ECONNRESET is detected as CONNECTION_RESET.
        Purpose: Ensure Unix-style error codes are recognized.
        """
        print("Setup: Creating ConnectError with ECONNRESET...")
        connect_error = httpx.ConnectError("[Errno 104] ECONNRESET")
        
        print("Action: Classifying error...")
        error_info = classify_network_error(connect_error)
        
        print("Verification: Category is CONNECTION_RESET...")
        assert error_info.category == ErrorCategory.CONNECTION_RESET
    
    def test_network_unreachable_error(self):
        """
        What it does: Verifies network unreachable errors are classified correctly.
        Purpose: Ensure "Network is unreachable" is detected as NETWORK_UNREACHABLE.
        """
        print("Setup: Creating ConnectError with 'Network is unreachable'...")
        connect_error = httpx.ConnectError("Network is unreachable")
        
        print("Action: Classifying error...")
        error_info = classify_network_error(connect_error)
        
        print("Verification: Category is NETWORK_UNREACHABLE...")
        print(f"Comparing category: Expected {ErrorCategory.NETWORK_UNREACHABLE}, Got {error_info.category}")
        assert error_info.category == ErrorCategory.NETWORK_UNREACHABLE
        assert "Network unreachable" in error_info.user_message
        assert error_info.is_retryable is True
    
    def test_network_unreachable_with_no_route_to_host(self):
        """
        What it does: Verifies "No route to host" is detected as NETWORK_UNREACHABLE.
        Purpose: Ensure alternative error messages are recognized.
        """
        print("Setup: Creating ConnectError with 'No route to host'...")
        connect_error = httpx.ConnectError("No route to host")
        
        print("Action: Classifying error...")
        error_info = classify_network_error(connect_error)
        
        print("Verification: Category is NETWORK_UNREACHABLE...")
        assert error_info.category == ErrorCategory.NETWORK_UNREACHABLE
    
    def test_network_unreachable_with_enetunreach(self):
        """
        What it does: Verifies ENETUNREACH is detected as NETWORK_UNREACHABLE.
        Purpose: Ensure Unix-style error codes are recognized.
        """
        print("Setup: Creating ConnectError with ENETUNREACH...")
        connect_error = httpx.ConnectError("[Errno 101] ENETUNREACH")
        
        print("Action: Classifying error...")
        error_info = classify_network_error(connect_error)
        
        print("Verification: Category is NETWORK_UNREACHABLE...")
        assert error_info.category == ErrorCategory.NETWORK_UNREACHABLE
    
    def test_generic_connect_error_classified_as_unknown(self):
        """
        What it does: Verifies generic connection errors fall back to UNKNOWN.
        Purpose: Ensure unrecognized errors have a fallback category.
        """
        print("Setup: Creating generic ConnectError...")
        connect_error = httpx.ConnectError("All connection attempts failed")
        
        print("Action: Classifying error...")
        error_info = classify_network_error(connect_error)
        
        print("Verification: Category is UNKNOWN...")
        print(f"Comparing category: Expected {ErrorCategory.UNKNOWN}, Got {error_info.category}")
        assert error_info.category == ErrorCategory.UNKNOWN
        assert "Connection failed" in error_info.user_message
        assert error_info.is_retryable is True
        assert error_info.suggested_http_code == 502


class TestClassifyNetworkErrorTimeout:
    """Tests for timeout error classification."""
    
    def test_connect_timeout_error(self):
        """
        What it does: Verifies ConnectTimeout is classified correctly.
        Purpose: Ensure TCP handshake timeouts are detected as TIMEOUT_CONNECT.
        """
        print("Setup: Creating ConnectTimeout...")
        timeout_error = httpx.ConnectTimeout("Connection timeout")
        
        print("Action: Classifying error...")
        error_info = classify_network_error(timeout_error)
        
        print("Verification: Category is TIMEOUT_CONNECT...")
        print(f"Comparing category: Expected {ErrorCategory.TIMEOUT_CONNECT}, Got {error_info.category}")
        assert error_info.category == ErrorCategory.TIMEOUT_CONNECT
        assert "Connection timeout" in error_info.user_message
        assert "did not respond" in error_info.user_message
        assert error_info.is_retryable is True
        assert error_info.suggested_http_code == 504
    
    def test_connect_timeout_includes_troubleshooting(self):
        """
        What it does: Verifies connect timeout includes troubleshooting steps.
        Purpose: Ensure users get guidance on fixing timeout issues.
        """
        print("Setup: Creating ConnectTimeout...")
        timeout_error = httpx.ConnectTimeout("Timeout")
        
        print("Action: Classifying error...")
        error_info = classify_network_error(timeout_error)
        
        print("Verification: Troubleshooting steps present...")
        steps = error_info.troubleshooting_steps
        assert len(steps) >= 2
        assert any("internet connection" in step.lower() for step in steps)
        assert any("server" in step.lower() or "overloaded" in step.lower() for step in steps)
    
    def test_read_timeout_error(self):
        """
        What it does: Verifies ReadTimeout is classified correctly.
        Purpose: Ensure read timeouts are detected as TIMEOUT_READ.
        """
        print("Setup: Creating ReadTimeout...")
        timeout_error = httpx.ReadTimeout("Read timeout")
        
        print("Action: Classifying error...")
        error_info = classify_network_error(timeout_error)
        
        print("Verification: Category is TIMEOUT_READ...")
        print(f"Comparing category: Expected {ErrorCategory.TIMEOUT_READ}, Got {error_info.category}")
        assert error_info.category == ErrorCategory.TIMEOUT_READ
        assert "Read timeout" in error_info.user_message
        assert "stopped responding" in error_info.user_message
        assert error_info.is_retryable is True
        assert error_info.suggested_http_code == 504
    
    def test_read_timeout_includes_troubleshooting(self):
        """
        What it does: Verifies read timeout includes troubleshooting steps.
        Purpose: Ensure users get guidance on fixing read timeout issues.
        """
        print("Setup: Creating ReadTimeout...")
        timeout_error = httpx.ReadTimeout("Timeout")
        
        print("Action: Classifying error...")
        error_info = classify_network_error(timeout_error)
        
        print("Verification: Troubleshooting steps present...")
        steps = error_info.troubleshooting_steps
        assert len(steps) >= 2
        assert any("server" in step.lower() or "processing" in step.lower() for step in steps)
    
    def test_generic_timeout_error(self):
        """
        What it does: Verifies generic TimeoutException is classified as TIMEOUT_READ.
        Purpose: Ensure unspecified timeouts have a fallback.
        """
        print("Setup: Creating generic TimeoutException...")
        timeout_error = httpx.TimeoutException("Timeout")
        
        print("Action: Classifying error...")
        error_info = classify_network_error(timeout_error)
        
        print("Verification: Category is TIMEOUT_READ...")
        print(f"Comparing category: Expected {ErrorCategory.TIMEOUT_READ}, Got {error_info.category}")
        assert error_info.category == ErrorCategory.TIMEOUT_READ
        assert "timeout" in error_info.user_message.lower()
        assert error_info.is_retryable is True


class TestClassifyNetworkErrorSSL:
    """Tests for SSL/TLS error classification."""
    
    def test_ssl_error_detection(self):
        """
        What it does: Verifies SSL errors are classified correctly.
        Purpose: Ensure SSL/TLS errors are detected as SSL_ERROR.
        """
        print("Setup: Creating ConnectError with SSL in message...")
        connect_error = httpx.ConnectError("SSL handshake failed")
        
        print("Action: Classifying error...")
        error_info = classify_network_error(connect_error)
        
        print("Verification: Category is SSL_ERROR...")
        print(f"Comparing category: Expected {ErrorCategory.SSL_ERROR}, Got {error_info.category}")
        assert error_info.category == ErrorCategory.SSL_ERROR
        assert "SSL/TLS error" in error_info.user_message
        assert "secure connection" in error_info.user_message
        assert error_info.is_retryable is False
        assert error_info.suggested_http_code == 502
    
    def test_tls_error_detection(self):
        """
        What it does: Verifies TLS errors are detected as SSL_ERROR.
        Purpose: Ensure TLS keyword is recognized.
        """
        print("Setup: Creating ConnectError with TLS in message...")
        connect_error = httpx.ConnectError("TLS connection failed")
        
        print("Action: Classifying error...")
        error_info = classify_network_error(connect_error)
        
        print("Verification: Category is SSL_ERROR...")
        assert error_info.category == ErrorCategory.SSL_ERROR
    
    def test_certificate_error_detection(self):
        """
        What it does: Verifies certificate errors are detected as SSL_ERROR.
        Purpose: Ensure certificate keyword is recognized.
        """
        print("Setup: Creating ConnectError with certificate in message...")
        connect_error = httpx.ConnectError("Certificate verification failed")
        
        print("Action: Classifying error...")
        error_info = classify_network_error(connect_error)
        
        print("Verification: Category is SSL_ERROR...")
        assert error_info.category == ErrorCategory.SSL_ERROR
    
    def test_ssl_error_includes_troubleshooting(self):
        """
        What it does: Verifies SSL errors include troubleshooting steps.
        Purpose: Ensure users get guidance on fixing SSL issues.
        """
        print("Setup: Creating SSL error...")
        connect_error = httpx.ConnectError("SSL error")
        
        print("Action: Classifying error...")
        error_info = classify_network_error(connect_error)
        
        print("Verification: Troubleshooting steps present...")
        steps = error_info.troubleshooting_steps
        assert len(steps) >= 2
        assert any("certificate" in step.lower() for step in steps)
        assert any("date" in step.lower() or "time" in step.lower() for step in steps)


class TestClassifyNetworkErrorProxy:
    """Tests for proxy error classification."""
    
    def test_proxy_error_detection(self):
        """
        What it does: Verifies proxy errors are classified correctly.
        Purpose: Ensure ProxyError is detected as PROXY_ERROR.
        """
        print("Setup: Creating ProxyError...")
        proxy_error = httpx.ProxyError("Proxy connection failed")
        
        print("Action: Classifying error...")
        error_info = classify_network_error(proxy_error)
        
        print("Verification: Category is PROXY_ERROR...")
        print(f"Comparing category: Expected {ErrorCategory.PROXY_ERROR}, Got {error_info.category}")
        assert error_info.category == ErrorCategory.PROXY_ERROR
        assert "Proxy" in error_info.user_message
        assert "cannot connect through" in error_info.user_message
        assert error_info.is_retryable is True
        assert error_info.suggested_http_code == 502
    
    def test_proxy_error_includes_troubleshooting(self):
        """
        What it does: Verifies proxy errors include troubleshooting steps.
        Purpose: Ensure users get guidance on fixing proxy issues.
        """
        print("Setup: Creating ProxyError...")
        proxy_error = httpx.ProxyError("Proxy failed")
        
        print("Action: Classifying error...")
        error_info = classify_network_error(proxy_error)
        
        print("Verification: Troubleshooting steps present...")
        steps = error_info.troubleshooting_steps
        assert len(steps) >= 2
        assert any("HTTP_PROXY" in step or "HTTPS_PROXY" in step for step in steps)
        assert any("proxy" in step.lower() for step in steps)


class TestClassifyNetworkErrorRedirects:
    """Tests for redirect error classification."""
    
    def test_too_many_redirects_error(self):
        """
        What it does: Verifies TooManyRedirects is classified correctly.
        Purpose: Ensure redirect loops are detected as TOO_MANY_REDIRECTS.
        """
        print("Setup: Creating TooManyRedirects...")
        redirect_error = httpx.TooManyRedirects("Too many redirects")
        
        print("Action: Classifying error...")
        error_info = classify_network_error(redirect_error)
        
        print("Verification: Category is TOO_MANY_REDIRECTS...")
        print(f"Comparing category: Expected {ErrorCategory.TOO_MANY_REDIRECTS}, Got {error_info.category}")
        assert error_info.category == ErrorCategory.TOO_MANY_REDIRECTS
        assert "redirect" in error_info.user_message.lower()
        assert "loop" in error_info.user_message.lower()
        assert error_info.is_retryable is False
        assert error_info.suggested_http_code == 502


class TestClassifyNetworkErrorGeneric:
    """Tests for generic error classification."""
    
    def test_generic_request_error_classified_as_unknown(self):
        """
        What it does: Verifies generic RequestError falls back to UNKNOWN.
        Purpose: Ensure unrecognized httpx errors have a fallback.
        """
        print("Setup: Creating generic RequestError...")
        request_error = httpx.RequestError("Unknown network error")
        
        print("Action: Classifying error...")
        error_info = classify_network_error(request_error)
        
        print("Verification: Category is UNKNOWN...")
        print(f"Comparing category: Expected {ErrorCategory.UNKNOWN}, Got {error_info.category}")
        assert error_info.category == ErrorCategory.UNKNOWN
        assert "unexpected error" in error_info.user_message.lower()
        assert error_info.is_retryable is True
        assert error_info.suggested_http_code == 502
    
    def test_non_httpx_error_classified_as_unknown(self):
        """
        What it does: Verifies non-httpx errors fall back to UNKNOWN.
        Purpose: Ensure graceful handling of unexpected exception types.
        """
        print("Setup: Creating generic Exception...")
        generic_error = Exception("Something went wrong")
        
        print("Action: Classifying error...")
        error_info = classify_network_error(generic_error)
        
        print("Verification: Category is UNKNOWN...")
        print(f"Comparing category: Expected {ErrorCategory.UNKNOWN}, Got {error_info.category}")
        assert error_info.category == ErrorCategory.UNKNOWN
        assert error_info.suggested_http_code == 500


class TestFormatErrorForUser:
    """Tests for format_error_for_user() function."""
    
    def test_format_openai_includes_troubleshooting(self):
        """
        What it does: Verifies OpenAI format includes troubleshooting steps.
        Purpose: Ensure users get actionable guidance in API responses.
        """
        print("Setup: Creating NetworkErrorInfo...")
        error_info = NetworkErrorInfo(
            category=ErrorCategory.DNS_RESOLUTION,
            user_message="DNS failed",
            troubleshooting_steps=["Step 1", "Step 2"],
            technical_details="Technical info",
            is_retryable=True,
            suggested_http_code=502
        )
        
        print("Action: Formatting for OpenAI...")
        formatted = format_error_for_user(error_info, format_type="openai", include_troubleshooting=True)
        
        print("Verification: OpenAI format structure...")
        assert "error" in formatted
        assert "message" in formatted["error"]
        assert "type" in formatted["error"]
        assert "code" in formatted["error"]
        assert formatted["error"]["type"] == "connectivity_error"
        assert formatted["error"]["code"] == "dns_resolution"
        assert "Step 1" in formatted["error"]["message"]
        assert "Step 2" in formatted["error"]["message"]
    
    def test_format_openai_without_troubleshooting(self):
        """
        What it does: Verifies OpenAI format can exclude troubleshooting.
        Purpose: Ensure flexibility in error message verbosity.
        """
        print("Setup: Creating NetworkErrorInfo...")
        error_info = NetworkErrorInfo(
            category=ErrorCategory.TIMEOUT_CONNECT,
            user_message="Connection timeout",
            troubleshooting_steps=["Step 1"],
            technical_details="Technical info",
            is_retryable=True,
            suggested_http_code=504
        )
        
        print("Action: Formatting for OpenAI without troubleshooting...")
        formatted = format_error_for_user(error_info, format_type="openai", include_troubleshooting=False)
        
        print("Verification: No troubleshooting steps in message...")
        assert "Step 1" not in formatted["error"]["message"]
        assert formatted["error"]["message"] == "Connection timeout"
    
    def test_format_anthropic_structure(self):
        """
        What it does: Verifies Anthropic format structure.
        Purpose: Ensure compatibility with Anthropic API error format.
        """
        print("Setup: Creating NetworkErrorInfo...")
        error_info = NetworkErrorInfo(
            category=ErrorCategory.CONNECTION_REFUSED,
            user_message="Connection refused",
            troubleshooting_steps=["Step 1"],
            technical_details="Technical info",
            is_retryable=True,
            suggested_http_code=502
        )
        
        print("Action: Formatting for Anthropic...")
        formatted = format_error_for_user(error_info, format_type="anthropic")
        
        print("Verification: Anthropic format structure...")
        assert "type" in formatted
        assert formatted["type"] == "error"
        assert "error" in formatted
        assert "type" in formatted["error"]
        assert "message" in formatted["error"]
        assert formatted["error"]["type"] == "connectivity_error"
    
    def test_format_generic_includes_technical_details(self):
        """
        What it does: Verifies generic format includes technical details.
        Purpose: Ensure debugging information is available in generic format.
        """
        print("Setup: Creating NetworkErrorInfo...")
        error_info = NetworkErrorInfo(
            category=ErrorCategory.SSL_ERROR,
            user_message="SSL error",
            troubleshooting_steps=[],
            technical_details="ConnectError: SSL handshake failed",
            is_retryable=False,
            suggested_http_code=502
        )
        
        print("Action: Formatting with generic format...")
        formatted = format_error_for_user(error_info, format_type="generic")
        
        print("Verification: Technical details present...")
        assert "technical_details" in formatted["error"]
        assert formatted["error"]["technical_details"] == "ConnectError: SSL handshake failed"


class TestGetShortErrorMessage:
    """Tests for get_short_error_message() function."""
    
    def test_short_message_no_brackets(self):
        """
        What it does: Verifies short message doesn't include brackets.
        Purpose: Ensure clean log output without category brackets.
        """
        print("Setup: Creating NetworkErrorInfo...")
        error_info = NetworkErrorInfo(
            category=ErrorCategory.DNS_RESOLUTION,
            user_message="DNS resolution failed",
            troubleshooting_steps=[],
            technical_details="Technical info",
            is_retryable=True,
            suggested_http_code=502
        )
        
        print("Action: Getting short message...")
        short_msg = get_short_error_message(error_info)
        
        print("Verification: No brackets in message...")
        print(f"Short message: {short_msg}")
        assert short_msg == "DNS resolution failed"
        assert "[" not in short_msg
        assert "]" not in short_msg
    
    def test_short_message_different_categories(self):
        """
        What it does: Verifies short messages for different error categories.
        Purpose: Ensure consistent format across all error types.
        """
        print("Setup: Creating multiple NetworkErrorInfo instances...")
        errors = [
            NetworkErrorInfo(ErrorCategory.TIMEOUT_CONNECT, "Timeout", [], "Tech", True, 504),
            NetworkErrorInfo(ErrorCategory.CONNECTION_REFUSED, "Refused", [], "Tech", True, 502),
            NetworkErrorInfo(ErrorCategory.UNKNOWN, "Unknown", [], "Tech", True, 502),
        ]
        
        print("Action: Getting short messages...")
        for error_info in errors:
            short_msg = get_short_error_message(error_info)
            
            print(f"Verification: {error_info.category} -> {short_msg}")
            assert short_msg == error_info.user_message
            assert "[" not in short_msg


class TestNetworkErrorInfoDataclass:
    """Tests for NetworkErrorInfo dataclass."""
    
    def test_network_error_info_creation(self):
        """
        What it does: Verifies NetworkErrorInfo can be created with all fields.
        Purpose: Ensure dataclass structure is correct.
        """
        print("Setup: Creating NetworkErrorInfo...")
        error_info = NetworkErrorInfo(
            category=ErrorCategory.DNS_RESOLUTION,
            user_message="Test message",
            troubleshooting_steps=["Step 1", "Step 2"],
            technical_details="Technical details",
            is_retryable=True,
            suggested_http_code=502
        )
        
        print("Verification: All fields accessible...")
        assert error_info.category == ErrorCategory.DNS_RESOLUTION
        assert error_info.user_message == "Test message"
        assert len(error_info.troubleshooting_steps) == 2
        assert error_info.technical_details == "Technical details"
        assert error_info.is_retryable is True
        assert error_info.suggested_http_code == 502


class TestBuildHttpErrorDetail:
    """Tests for build_http_error_detail() - the shared HTTPException detail formatter."""

    def _make_info(self, steps):
        return NetworkErrorInfo(
            category=ErrorCategory.CONNECTION_RESET,
            user_message="Connection reset - the server closed the connection unexpectedly.",
            troubleshooting_steps=steps,
            technical_details="RemoteProtocolError: peer closed connection (incomplete chunked read)",
            is_retryable=True,
            suggested_http_code=502,
        )

    def test_includes_user_message_steps_and_technical_details(self):
        """
        What it does: Verifies the detail string contains the user message,
                      numbered troubleshooting steps, and technical details.
        Goal: Ensure the classified error is fully actionable for the client.
        """
        info = self._make_info(["Try again in a few moments", "Check network stability"])
        detail = build_http_error_detail(info)

        assert "Connection reset" in detail
        assert "Troubleshooting:" in detail
        assert "1. Try again in a few moments" in detail
        assert "2. Check network stability" in detail
        assert "Technical details:" in detail
        assert "incomplete chunked read" in detail

    def test_omits_troubleshooting_section_when_no_steps(self):
        """
        What it does: Verifies the 'Troubleshooting:' header is not present when
                      there are no steps.
        Goal: Avoid an empty, confusing section.
        """
        info = self._make_info([])
        detail = build_http_error_detail(info)

        assert "Troubleshooting:" not in detail
        assert "Technical details:" in detail

    def test_result_is_stripped(self):
        """
        What it does: Verifies the returned string has no leading/trailing whitespace.
        Goal: Keep client-facing error messages clean.
        """
        info = self._make_info(["Step one"])
        detail = build_http_error_detail(info)

        assert detail == detail.strip()

    def test_matches_classified_remote_protocol_error(self):
        """
        What it does: End-to-end - classify a RemoteProtocolError and build the detail.
        Goal: Confirm the mid-stream drop maps to a 502 connectivity detail.
        """
        err = httpx.RemoteProtocolError(
            "peer closed connection without sending complete message body (incomplete chunked read)"
        )
        info = classify_network_error(err)
        detail = build_http_error_detail(info)

        assert info.suggested_http_code == 502
        assert info.is_retryable is True
        assert "Network request failed" in detail or "connection" in detail.lower()
