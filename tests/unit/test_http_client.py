# -*- coding: utf-8 -*-

"""
Unit tests for KiroHttpClient.
Tests retry logic, error handling, and HTTP client management.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import HTTPException

from kiro.http_client import KiroHttpClient
from kiro.auth import KiroAuthManager
from kiro.config import MAX_RETRIES, BASE_RETRY_DELAY, FIRST_TOKEN_MAX_RETRIES, STREAMING_READ_TIMEOUT


@pytest.fixture
def mock_auth_manager_for_http():
    """Creates a mocked KiroAuthManager for HTTP client tests."""
    manager = Mock(spec=KiroAuthManager)
    manager.get_access_token = AsyncMock(return_value="test_access_token")
    manager.force_refresh = AsyncMock(return_value="new_access_token")
    manager.fingerprint = "test_fingerprint_12345678"
    manager._fingerprint = "test_fingerprint_12345678"
    return manager


class TestKiroHttpClientInitialization:
    """Tests for KiroHttpClient initialization."""
    
    def test_initialization_stores_auth_manager(self, mock_auth_manager_for_http):
        """
        What it does: Verifies auth_manager is stored during initialization.
        Purpose: Ensure auth_manager is available for obtaining tokens.
        """
        print("Setup: Creating KiroHttpClient...")
        client = KiroHttpClient(mock_auth_manager_for_http)
        
        print("Verification: auth_manager is stored...")
        assert client.auth_manager is mock_auth_manager_for_http
    
    def test_initialization_client_is_none(self, mock_auth_manager_for_http):
        """
        What it does: Verifies that HTTP client is initially None.
        Purpose: Ensure lazy initialization.
        """
        print("Setup: Creating KiroHttpClient...")
        client = KiroHttpClient(mock_auth_manager_for_http)
        
        print("Verification: client is initially None...")
        assert client.client is None


class TestKiroHttpClientGetClient:
    """Tests for _get_client method."""
    
    @pytest.mark.asyncio
    async def test_get_client_creates_new_client(self, mock_auth_manager_for_http):
        """
        What it does: Verifies creation of a new HTTP client.
        Purpose: Ensure client is created on first call.
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        print("Action: Getting client...")
        with patch('kiro.http_client.httpx.AsyncClient') as mock_async_client:
            mock_instance = AsyncMock()
            mock_instance.is_closed = False
            mock_async_client.return_value = mock_instance
            
            client = await http_client._get_client()
            
            print("Verification: Client created...")
            mock_async_client.assert_called_once()
            assert client is mock_instance
    
    @pytest.mark.asyncio
    async def test_get_client_reuses_existing_client(self, mock_auth_manager_for_http):
        """
        What it does: Verifies reuse of existing client.
        Purpose: Ensure client is not recreated unnecessarily.
        """
        print("Setup: Creating KiroHttpClient with existing client...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_existing = AsyncMock()
        mock_existing.is_closed = False
        http_client.client = mock_existing
        
        print("Action: Getting client...")
        client = await http_client._get_client()
        
        print("Verification: Existing client returned...")
        assert client is mock_existing
    
    @pytest.mark.asyncio
    async def test_get_client_recreates_closed_client(self, mock_auth_manager_for_http):
        """
        What it does: Verifies recreation of closed client.
        Purpose: Ensure closed client is replaced with a new one.
        """
        print("Setup: Creating KiroHttpClient with closed client...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_closed = AsyncMock()
        mock_closed.is_closed = True
        http_client.client = mock_closed
        
        print("Action: Getting client...")
        with patch('kiro.http_client.httpx.AsyncClient') as mock_async_client:
            mock_new = AsyncMock()
            mock_new.is_closed = False
            mock_async_client.return_value = mock_new
            
            client = await http_client._get_client()
            
            print("Verification: New client created...")
            mock_async_client.assert_called_once()
            assert client is mock_new


class TestKiroHttpClientClose:
    """Tests for close method."""
    
    @pytest.mark.asyncio
    async def test_close_closes_client(self, mock_auth_manager_for_http):
        """
        What it does: Verifies HTTP client closure.
        Purpose: Ensure aclose() is called.
        """
        print("Setup: Creating KiroHttpClient with client...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.aclose = AsyncMock()
        http_client.client = mock_client
        
        print("Action: Closing client...")
        await http_client.close()
        
        print("Verification: aclose() called...")
        mock_client.aclose.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_close_does_nothing_for_none_client(self, mock_auth_manager_for_http):
        """
        What it does: Verifies that close() doesn't fail for None client.
        Purpose: Ensure safe close() call without client.
        """
        print("Setup: Creating KiroHttpClient without client...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        print("Action: Closing client...")
        await http_client.close()  # Should not raise an error
        
        print("Verification: No errors...")
    
    @pytest.mark.asyncio
    async def test_close_does_nothing_for_closed_client(self, mock_auth_manager_for_http):
        """
        What it does: Verifies that close() doesn't fail for closed client.
        Purpose: Ensure safe repeated close() call.
        """
        print("Setup: Creating KiroHttpClient with closed client...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_client = AsyncMock()
        mock_client.is_closed = True
        http_client.client = mock_client
        
        print("Action: Closing client...")
        await http_client.close()
        
        print("Verification: aclose() NOT called...")
        mock_client.aclose.assert_not_called()


class TestKiroHttpClientRequestWithRetry:
    """Tests for request_with_retry method."""
    
    @pytest.mark.asyncio
    async def test_successful_request_returns_response(self, mock_auth_manager_for_http):
        """
        What it does: Verifies successful request.
        Purpose: Ensure 200 response is returned immediately.
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.request = AsyncMock(return_value=mock_response)
        
        print("Action: Executing request...")
        with patch.object(http_client, '_get_client', return_value=mock_client):
            with patch('kiro.http_client.get_kiro_headers', return_value={}):
                response = await http_client.request_with_retry(
                    "POST",
                    "https://api.example.com/test",
                    {"data": "value"}
                )
        
        print("Verification: Response received...")
        assert response.status_code == 200
        mock_client.request.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_403_triggers_token_refresh(self, mock_auth_manager_for_http):
        """
        What it does: Verifies token refresh on 403.
        Purpose: Ensure force_refresh() is called on 403.
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_response_403 = AsyncMock()
        mock_response_403.status_code = 403
        
        mock_response_200 = AsyncMock()
        mock_response_200.status_code = 200
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.request = AsyncMock(side_effect=[mock_response_403, mock_response_200])
        
        print("Action: Executing request...")
        with patch.object(http_client, '_get_client', return_value=mock_client):
            with patch('kiro.http_client.get_kiro_headers', return_value={}):
                response = await http_client.request_with_retry(
                    "POST",
                    "https://api.example.com/test",
                    {"data": "value"}
                )
        
        print("Verification: force_refresh() called...")
        mock_auth_manager_for_http.force_refresh.assert_called_once()
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_429_triggers_backoff(self, mock_auth_manager_for_http):
        """
        What it does: Verifies exponential backoff on 429.
        Purpose: Ensure request is retried after delay.
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_response_429 = AsyncMock()
        mock_response_429.status_code = 429
        
        mock_response_200 = AsyncMock()
        mock_response_200.status_code = 200
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.request = AsyncMock(side_effect=[mock_response_429, mock_response_200])
        
        print("Action: Executing request...")
        with patch.object(http_client, '_get_client', return_value=mock_client):
            with patch('kiro.http_client.get_kiro_headers', return_value={}):
                with patch('kiro.http_client.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                    response = await http_client.request_with_retry(
                        "POST",
                        "https://api.example.com/test",
                        {"data": "value"}
                    )
        
        print("Verification: sleep() called for backoff...")
        mock_sleep.assert_called_once()
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_5xx_triggers_backoff(self, mock_auth_manager_for_http):
        """
        What it does: Verifies exponential backoff on 5xx.
        Purpose: Ensure server errors are handled with retry.
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_response_500 = AsyncMock()
        mock_response_500.status_code = 500
        
        mock_response_200 = AsyncMock()
        mock_response_200.status_code = 200
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.request = AsyncMock(side_effect=[mock_response_500, mock_response_200])
        
        print("Action: Executing request...")
        with patch.object(http_client, '_get_client', return_value=mock_client):
            with patch('kiro.http_client.get_kiro_headers', return_value={}):
                with patch('kiro.http_client.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                    response = await http_client.request_with_retry(
                        "POST",
                        "https://api.example.com/test",
                        {"data": "value"}
                    )
        
        print("Verification: sleep() called for backoff...")
        mock_sleep.assert_called_once()
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_timeout_triggers_backoff(self, mock_auth_manager_for_http):
        """
        What it does: Verifies exponential backoff on timeout.
        Purpose: Ensure timeouts are handled with retry.
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_response_200 = AsyncMock()
        mock_response_200.status_code = 200
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.request = AsyncMock(side_effect=[
            httpx.TimeoutException("Timeout"),
            mock_response_200
        ])
        
        print("Action: Executing request...")
        with patch.object(http_client, '_get_client', return_value=mock_client):
            with patch('kiro.http_client.get_kiro_headers', return_value={}):
                with patch('kiro.http_client.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                    response = await http_client.request_with_retry(
                        "POST",
                        "https://api.example.com/test",
                        {"data": "value"}
                    )
        
        print("Verification: sleep() called for backoff...")
        mock_sleep.assert_called_once()
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_request_error_triggers_backoff(self, mock_auth_manager_for_http):
        """
        What it does: Verifies exponential backoff on request error.
        Purpose: Ensure network errors are handled with retry.
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_response_200 = AsyncMock()
        mock_response_200.status_code = 200
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.request = AsyncMock(side_effect=[
            httpx.RequestError("Connection error"),
            mock_response_200
        ])
        
        print("Action: Executing request...")
        with patch.object(http_client, '_get_client', return_value=mock_client):
            with patch('kiro.http_client.get_kiro_headers', return_value={}):
                with patch('kiro.http_client.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                    response = await http_client.request_with_retry(
                        "POST",
                        "https://api.example.com/test",
                        {"data": "value"}
                    )
        
        print("Verification: sleep() called for backoff...")
        mock_sleep.assert_called_once()
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_max_retries_exceeded_raises_502(self, mock_auth_manager_for_http):
        """
        What it does: Verifies HTTPException is raised after exhausting retries.
        Purpose: Ensure 504 is raised after MAX_RETRIES for timeout errors.
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.request = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        
        print("Action: Executing request...")
        with patch.object(http_client, '_get_client', return_value=mock_client):
            with patch('kiro.http_client.get_kiro_headers', return_value={}):
                with patch('kiro.http_client.asyncio.sleep', new_callable=AsyncMock):
                    with pytest.raises(HTTPException) as exc_info:
                        await http_client.request_with_retry(
                            "POST",
                            "https://api.example.com/test",
                            {"data": "value"}
                        )
        
        print(f"Verification: HTTPException with code 504 (timeout errors now return 504)...")
        assert exc_info.value.status_code == 504
        print(f"Verification: Error detail contains user-friendly message...")
        assert "timeout" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    async def test_other_status_codes_returned_as_is(self, mock_auth_manager_for_http):
        """
        What it does: Verifies other status codes are returned without retry.
        Purpose: Ensure 400, 404, etc. are returned immediately.
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_response = AsyncMock()
        mock_response.status_code = 400
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.request = AsyncMock(return_value=mock_response)
        
        print("Action: Executing request...")
        with patch.object(http_client, '_get_client', return_value=mock_client):
            with patch('kiro.http_client.get_kiro_headers', return_value={}):
                response = await http_client.request_with_retry(
                    "POST",
                    "https://api.example.com/test",
                    {"data": "value"}
                )
        
        print("Verification: 400 response returned without retry...")
        assert response.status_code == 400
        mock_client.request.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_streaming_request_uses_send(self, mock_auth_manager_for_http):
        """
        What it does: Verifies send() is used for streaming.
        Purpose: Ensure stream=True uses build_request + send.
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        
        mock_request = Mock()
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.build_request = Mock(return_value=mock_request)
        mock_client.send = AsyncMock(return_value=mock_response)
        
        print("Action: Executing streaming request...")
        with patch.object(http_client, '_get_client', return_value=mock_client):
            with patch('kiro.http_client.get_kiro_headers', return_value={}):
                response = await http_client.request_with_retry(
                    "POST",
                    "https://api.example.com/test",
                    {"data": "value"},
                    stream=True
                )
        
        print("Verification: build_request and send called...")
        mock_client.build_request.assert_called_once()
        mock_client.send.assert_called_once_with(mock_request, stream=True)
        assert response.status_code == 200


class TestKiroHttpClientContextManager:
    """Tests for async context manager."""
    
    @pytest.mark.asyncio
    async def test_context_manager_returns_self(self, mock_auth_manager_for_http):
        """
        What it does: Verifies that __aenter__ returns self.
        Purpose: Ensure correct async with behavior.
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        print("Action: Entering context...")
        result = await http_client.__aenter__()
        
        print("Verification: self returned...")
        assert result is http_client
    
    @pytest.mark.asyncio
    async def test_context_manager_closes_on_exit(self, mock_auth_manager_for_http):
        """
        What it does: Verifies client closure on context exit.
        Purpose: Ensure close() is called in __aexit__.
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.aclose = AsyncMock()
        http_client.client = mock_client
        
        print("Action: Exiting context...")
        await http_client.__aexit__(None, None, None)
        
        print("Verification: aclose() called...")
        mock_client.aclose.assert_called_once()


class TestKiroHttpClientExponentialBackoff:
    """Tests for exponential backoff logic."""
    
    @pytest.mark.asyncio
    async def test_backoff_delay_increases_exponentially(self, mock_auth_manager_for_http):
        """
        What it does: Verifies exponential delay increase.
        Purpose: Ensure delay = BASE_RETRY_DELAY * (2 ** attempt).
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_response_429 = AsyncMock()
        mock_response_429.status_code = 429
        
        mock_response_200 = AsyncMock()
        mock_response_200.status_code = 200
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        # 2 errors 429, then success (to verify 2 backoff delays)
        mock_client.request = AsyncMock(side_effect=[
            mock_response_429,
            mock_response_429,
            mock_response_200
        ])
        
        sleep_delays = []
        
        async def capture_sleep(delay):
            sleep_delays.append(delay)
        
        print("Action: Executing request with multiple retries...")
        with patch.object(http_client, '_get_client', return_value=mock_client):
            with patch('kiro.http_client.get_kiro_headers', return_value={}):
                with patch('kiro.http_client.asyncio.sleep', side_effect=capture_sleep):
                    response = await http_client.request_with_retry(
                        "POST",
                        "https://api.example.com/test",
                        {"data": "value"}
                    )
        
        print(f"Verification: Delays increase exponentially...")
        print(f"Delays: {sleep_delays}")
        assert len(sleep_delays) == 2
        assert sleep_delays[0] == BASE_RETRY_DELAY * (2 ** 0)  # 1.0
        assert sleep_delays[1] == BASE_RETRY_DELAY * (2 ** 1)  # 2.0


class TestKiroHttpClientStreamingTimeout:
    """Tests for streaming request timeout logic."""
    
    @pytest.mark.asyncio
    async def test_streaming_uses_streaming_read_timeout(self, mock_auth_manager_for_http):
        """
        What it does: Verifies that streaming requests use STREAMING_READ_TIMEOUT.
        Purpose: Ensure stream=True uses httpx.Timeout with correct values.
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        
        mock_request = Mock()
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.build_request = Mock(return_value=mock_request)
        mock_client.send = AsyncMock(return_value=mock_response)
        
        print("Action: Executing streaming request...")
        with patch('kiro.http_client.httpx.AsyncClient') as mock_async_client:
            mock_async_client.return_value = mock_client
            
            with patch('kiro.http_client.get_kiro_headers', return_value={}):
                response = await http_client.request_with_retry(
                    "POST",
                    "https://api.example.com/test",
                    {"data": "value"},
                    stream=True
                )
        
        print("Verification: AsyncClient created with httpx.Timeout for streaming...")
        call_args = mock_async_client.call_args
        timeout_arg = call_args.kwargs.get('timeout')
        assert timeout_arg is not None, f"timeout not found in call_args: {call_args}"
        print(f"Comparing connect: Expected 30.0, Got {timeout_arg.connect}")
        assert timeout_arg.connect == 30.0, f"Expected connect=30.0, got {timeout_arg.connect}"
        print(f"Comparing read: Expected {STREAMING_READ_TIMEOUT}, Got {timeout_arg.read}")
        assert timeout_arg.read == STREAMING_READ_TIMEOUT, f"Expected read={STREAMING_READ_TIMEOUT}, got {timeout_arg.read}"
        assert call_args.kwargs.get('follow_redirects') == True
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_streaming_uses_first_token_max_retries(self, mock_auth_manager_for_http):
        """
        What it does: Verifies that streaming requests use FIRST_TOKEN_MAX_RETRIES.
        Purpose: Ensure stream=True uses separate retry counter.
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_request = Mock()
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.build_request = Mock(return_value=mock_request)
        mock_client.send = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        
        print("Action: Executing streaming request with timeouts...")
        with patch('kiro.http_client.httpx.AsyncClient', return_value=mock_client):
            with patch('kiro.http_client.get_kiro_headers', return_value={}):
                with patch('kiro.http_client.asyncio.sleep', new_callable=AsyncMock):
                    with pytest.raises(HTTPException) as exc_info:
                        await http_client.request_with_retry(
                            "POST",
                            "https://api.example.com/test",
                            {"data": "value"},
                            stream=True
                        )
        
        print(f"Verification: HTTPException with code 504...")
        assert exc_info.value.status_code == 504
        assert str(FIRST_TOKEN_MAX_RETRIES) in exc_info.value.detail
        
        print(f"Verification: Attempt count = FIRST_TOKEN_MAX_RETRIES ({FIRST_TOKEN_MAX_RETRIES})...")
        assert mock_client.send.call_count == FIRST_TOKEN_MAX_RETRIES
    
    @pytest.mark.asyncio
    async def test_streaming_timeout_retry_without_delay(self, mock_auth_manager_for_http):
        """
        What it does: Verifies that streaming timeout retry happens with exponential backoff.
        Purpose: Ensure timeouts are retried with proper delay (new behavior with classifier).
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        
        mock_request = Mock()
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.build_request = Mock(return_value=mock_request)
        # First timeout, then success
        mock_client.send = AsyncMock(side_effect=[
            httpx.TimeoutException("Timeout"),
            mock_response
        ])
        
        sleep_called = False
        
        async def capture_sleep(delay):
            nonlocal sleep_called
            sleep_called = True
        
        print("Action: Executing streaming request with one timeout...")
        with patch('kiro.http_client.httpx.AsyncClient', return_value=mock_client):
            with patch('kiro.http_client.get_kiro_headers', return_value={}):
                with patch('kiro.http_client.asyncio.sleep', side_effect=capture_sleep):
                    response = await http_client.request_with_retry(
                        "POST",
                        "https://api.example.com/test",
                        {"data": "value"},
                        stream=True
                    )
        
        print("Verification: sleep() IS called for timeout retry (new behavior)...")
        assert sleep_called
        assert response.status_code == 200
        
    @pytest.mark.asyncio
    async def test_non_streaming_uses_default_timeout(self, mock_auth_manager_for_http):
        """
        What it does: Verifies that non-streaming requests use 300 seconds.
        Purpose: Ensure stream=False uses unified httpx.Timeout.
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.request = AsyncMock(return_value=mock_response)
        
        print("Action: Executing non-streaming request...")
        with patch('kiro.http_client.httpx.AsyncClient') as mock_async_client:
            mock_async_client.return_value = mock_client
            
            with patch('kiro.http_client.get_kiro_headers', return_value={}):
                response = await http_client.request_with_retry(
                    "POST",
                    "https://api.example.com/test",
                    {"data": "value"},
                    stream=False
                )
        
        print("Verification: AsyncClient created with httpx.Timeout(timeout=300)...")
        call_args = mock_async_client.call_args
        timeout_arg = call_args.kwargs.get('timeout')
        assert timeout_arg is not None, f"timeout not found in call_args: {call_args}"
        # httpx.Timeout(timeout=300) sets all timeouts to 300
        print(f"Comparing timeout: Expected 300.0 for all, Got connect={timeout_arg.connect}")
        assert timeout_arg.connect == 300.0
        assert timeout_arg.read == 300.0
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_connect_timeout_logged_correctly(self, mock_auth_manager_for_http):
        """
        What it does: Verifies ConnectTimeout logging.
        Purpose: Ensure ConnectTimeout is logged with user-friendly message.
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        
        mock_request = Mock()
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.build_request = Mock(return_value=mock_request)
        # First ConnectTimeout, then success
        mock_client.send = AsyncMock(side_effect=[
            httpx.ConnectTimeout("Connection timeout"),
            mock_response
        ])
        
        print("Action: Executing streaming request with ConnectTimeout...")
        with patch('kiro.http_client.httpx.AsyncClient', return_value=mock_client):
            with patch('kiro.http_client.get_kiro_headers', return_value={}):
                with patch('kiro.http_client.asyncio.sleep', new_callable=AsyncMock):
                    with patch('kiro.http_client.logger') as mock_logger:
                        response = await http_client.request_with_retry(
                            "POST",
                            "https://api.example.com/test",
                            {"data": "value"},
                            stream=True
                        )
        
        print("Verification: logger.warning called with user-friendly timeout message...")
        warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
        assert any("timeout" in call.lower() for call in warning_calls), f"Timeout message not found in: {warning_calls}"
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_read_timeout_logged_correctly(self, mock_auth_manager_for_http):
        """
        What it does: Verifies ReadTimeout logging.
        Purpose: Ensure ReadTimeout is logged with user-friendly message.
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        
        mock_request = Mock()
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.build_request = Mock(return_value=mock_request)
        # First ReadTimeout, then success
        mock_client.send = AsyncMock(side_effect=[
            httpx.ReadTimeout("Read timeout"),
            mock_response
        ])
        
        print("Action: Executing streaming request with ReadTimeout...")
        with patch('kiro.http_client.httpx.AsyncClient', return_value=mock_client):
            with patch('kiro.http_client.get_kiro_headers', return_value={}):
                with patch('kiro.http_client.asyncio.sleep', new_callable=AsyncMock):
                    with patch('kiro.http_client.logger') as mock_logger:
                        response = await http_client.request_with_retry(
                            "POST",
                            "https://api.example.com/test",
                            {"data": "value"},
                            stream=True
                        )
        
        print("Verification: logger.warning called with user-friendly timeout message...")
        warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
        assert any("timeout" in call.lower() for call in warning_calls), f"Timeout message not found in: {warning_calls}"
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_streaming_timeout_returns_504_with_error_type(self, mock_auth_manager_for_http):
        """
        What it does: Verifies that streaming timeout returns 504 with error type.
        Purpose: Ensure 504 is returned with error info after exhausting retries.
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_request = Mock()
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.build_request = Mock(return_value=mock_request)
        mock_client.send = AsyncMock(side_effect=httpx.ReadTimeout("Timeout"))
        
        print("Action: Executing streaming request with persistent timeouts...")
        with patch('kiro.http_client.httpx.AsyncClient', return_value=mock_client):
            with patch('kiro.http_client.get_kiro_headers', return_value={}):
                with patch('kiro.http_client.asyncio.sleep', new_callable=AsyncMock):
                    with pytest.raises(HTTPException) as exc_info:
                        await http_client.request_with_retry(
                            "POST",
                            "https://api.example.com/test",
                            {"data": "value"},
                            stream=True
                        )
        
        print("Verification: HTTPException with code 504 and user-friendly message...")
        print(f"Comparing status_code: Expected 504, Got {exc_info.value.status_code}")
        assert exc_info.value.status_code == 504
        print(f"Comparing detail: Expected timeout message with troubleshooting in '{exc_info.value.detail}'")
        assert "timeout" in exc_info.value.detail.lower()
        assert "Troubleshooting" in exc_info.value.detail or "Technical details" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_non_streaming_timeout_returns_502(self, mock_auth_manager_for_http):
        """
        What it does: Verifies that non-streaming timeout returns 504.
        Purpose: Ensure timeouts consistently return 504 (new behavior with classifier).
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.request = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        
        print("Action: Executing non-streaming request with persistent timeouts...")
        with patch('kiro.http_client.httpx.AsyncClient', return_value=mock_client):
            with patch('kiro.http_client.get_kiro_headers', return_value={}):
                with patch('kiro.http_client.asyncio.sleep', new_callable=AsyncMock):
                    with pytest.raises(HTTPException) as exc_info:
                        await http_client.request_with_retry(
                            "POST",
                            "https://api.example.com/test",
                            {"data": "value"},
                            stream=False
                        )
        
        print("Verification: HTTPException with code 504 (timeouts now consistently return 504)...")
        assert exc_info.value.status_code == 504


class TestKiroHttpClientSharedClient:
    """Tests for shared client functionality (connection pooling support)."""
    
    def test_initialization_with_shared_client(self, mock_auth_manager_for_http):
        """
        What it does: Verifies shared_client is stored during initialization.
        Purpose: Ensure shared client is available for connection pooling.
        """
        print("Setup: Creating mock shared client...")
        mock_shared = AsyncMock()
        mock_shared.is_closed = False
        
        print("Action: Creating KiroHttpClient with shared client...")
        http_client = KiroHttpClient(mock_auth_manager_for_http, shared_client=mock_shared)
        
        print("Verification: shared_client is stored...")
        print(f"Comparing _shared_client: Expected mock_shared, Got {http_client._shared_client}")
        assert http_client._shared_client is mock_shared
        print(f"Comparing client: Expected mock_shared, Got {http_client.client}")
        assert http_client.client is mock_shared
    
    def test_initialization_without_shared_client_owns_client(self, mock_auth_manager_for_http):
        """
        What it does: Verifies _owns_client is True when no shared client provided.
        Purpose: Ensure client ownership is tracked correctly for cleanup.
        """
        print("Setup: Creating KiroHttpClient without shared client...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        print("Verification: _owns_client is True...")
        print(f"Comparing _owns_client: Expected True, Got {http_client._owns_client}")
        assert http_client._owns_client is True
        print(f"Comparing _shared_client: Expected None, Got {http_client._shared_client}")
        assert http_client._shared_client is None
    
    def test_initialization_with_shared_client_does_not_own(self, mock_auth_manager_for_http):
        """
        What it does: Verifies _owns_client is False when shared client provided.
        Purpose: Ensure shared client is not closed by this instance.
        """
        print("Setup: Creating mock shared client...")
        mock_shared = AsyncMock()
        mock_shared.is_closed = False
        
        print("Action: Creating KiroHttpClient with shared client...")
        http_client = KiroHttpClient(mock_auth_manager_for_http, shared_client=mock_shared)
        
        print("Verification: _owns_client is False...")
        print(f"Comparing _owns_client: Expected False, Got {http_client._owns_client}")
        assert http_client._owns_client is False
    
    @pytest.mark.asyncio
    async def test_get_client_returns_shared_client(self, mock_auth_manager_for_http):
        """
        What it does: Verifies _get_client returns shared client directly.
        Purpose: Ensure shared client is used without creating new one.
        """
        print("Setup: Creating mock shared client...")
        mock_shared = AsyncMock()
        mock_shared.is_closed = False
        
        print("Action: Creating KiroHttpClient with shared client...")
        http_client = KiroHttpClient(mock_auth_manager_for_http, shared_client=mock_shared)
        
        print("Action: Getting client...")
        with patch('kiro.http_client.httpx.AsyncClient') as mock_async_client:
            client = await http_client._get_client(stream=True)
            
            print("Verification: Shared client returned, no new client created...")
            print(f"Comparing client: Expected mock_shared, Got {client}")
            assert client is mock_shared
            mock_async_client.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_close_does_not_close_shared_client(self, mock_auth_manager_for_http):
        """
        What it does: Verifies close() does NOT close shared client.
        Purpose: Ensure shared client lifecycle is managed by application.
        """
        print("Setup: Creating mock shared client...")
        mock_shared = AsyncMock()
        mock_shared.is_closed = False
        mock_shared.aclose = AsyncMock()
        
        print("Action: Creating KiroHttpClient with shared client...")
        http_client = KiroHttpClient(mock_auth_manager_for_http, shared_client=mock_shared)
        
        print("Action: Closing client...")
        await http_client.close()
        
        print("Verification: aclose() NOT called on shared client...")
        mock_shared.aclose.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_close_closes_owned_client(self, mock_auth_manager_for_http):
        """
        What it does: Verifies close() DOES close owned client.
        Purpose: Ensure owned client is properly cleaned up.
        """
        print("Setup: Creating KiroHttpClient without shared client...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_owned = AsyncMock()
        mock_owned.is_closed = False
        mock_owned.aclose = AsyncMock()
        http_client.client = mock_owned
        
        print("Action: Closing client...")
        await http_client.close()
        
        print("Verification: aclose() called on owned client...")
        mock_owned.aclose.assert_called_once()


class TestKiroHttpClientGracefulClose:
    """Tests for graceful exception handling in close() method."""
    
    @pytest.mark.asyncio
    async def test_close_handles_aclose_exception_gracefully(self, mock_auth_manager_for_http):
        """
        What it does: Verifies exception in aclose() is caught and doesn't propagate.
        Purpose: Ensure cleanup errors don't mask original exceptions.
        """
        print("Setup: Creating KiroHttpClient with client that raises on close...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.aclose = AsyncMock(side_effect=Exception("Connection reset"))
        http_client.client = mock_client
        
        print("Action: Closing client (should not raise)...")
        # Should not raise - exception should be caught
        await http_client.close()
        
        print("Verification: No exception propagated...")
        # If we get here, the test passed
        assert True
    
    @pytest.mark.asyncio
    async def test_close_logs_warning_on_exception(self, mock_auth_manager_for_http):
        """
        What it does: Verifies warning is logged when aclose() fails.
        Purpose: Ensure errors are visible in logs for debugging.
        """
        print("Setup: Creating KiroHttpClient with client that raises on close...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.aclose = AsyncMock(side_effect=Exception("Connection reset"))
        http_client.client = mock_client
        
        print("Action: Closing client with logger mock...")
        with patch('kiro.http_client.logger') as mock_logger:
            await http_client.close()
            
            print("Verification: logger.warning called...")
            mock_logger.warning.assert_called_once()
            warning_message = str(mock_logger.warning.call_args)
            print(f"Warning message: {warning_message}")
            assert "Connection reset" in warning_message or "Error closing" in warning_message


class TestKiroHttpClientConnectionCloseHeader:
    """Tests for Connection: close header on streaming requests (issue #38)."""
    
    @pytest.mark.asyncio
    async def test_streaming_request_includes_connection_close_header(self, mock_auth_manager_for_http):
        """
        What it does: Verifies that streaming requests include Connection: close header.
        Purpose: Prevent CLOSE_WAIT connection leak by disabling connection reuse for streaming.
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        
        mock_request = Mock()
        captured_headers = {}
        
        def capture_build_request(method, url, content, headers):
            captured_headers.update(headers)
            return mock_request
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.build_request = Mock(side_effect=capture_build_request)
        mock_client.send = AsyncMock(return_value=mock_response)
        
        print("Action: Executing streaming request...")
        with patch.object(http_client, '_get_client', return_value=mock_client):
            with patch('kiro.http_client.get_kiro_headers', return_value={"Authorization": "Bearer test"}):
                response = await http_client.request_with_retry(
                    "POST",
                    "https://api.example.com/test",
                    {"data": "value"},
                    stream=True
                )
        
        print("Verification: Connection: close header is present...")
        print(f"Captured headers: {captured_headers}")
        assert "Connection" in captured_headers, f"Connection header not found in: {captured_headers}"
        print(f"Comparing Connection: Expected 'close', Got '{captured_headers['Connection']}'")
        assert captured_headers["Connection"] == "close"
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_non_streaming_request_does_not_include_connection_close_header(self, mock_auth_manager_for_http):
        """
        What it does: Verifies that non-streaming requests do NOT include Connection: close header.
        Purpose: Ensure connection pooling is preserved for non-streaming requests.
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        
        captured_headers = {}
        
        async def capture_request(method, url, content, headers):
            captured_headers.update(headers)
            return mock_response
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.request = AsyncMock(side_effect=capture_request)
        
        print("Action: Executing non-streaming request...")
        with patch.object(http_client, '_get_client', return_value=mock_client):
            with patch('kiro.http_client.get_kiro_headers', return_value={"Authorization": "Bearer test"}):
                response = await http_client.request_with_retry(
                    "POST",
                    "https://api.example.com/test",
                    {"data": "value"},
                    stream=False
                )
        
        print("Verification: Connection: close header is NOT present...")
        print(f"Captured headers: {captured_headers}")
        assert "Connection" not in captured_headers, f"Connection header should not be present for non-streaming: {captured_headers}"
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_streaming_connection_close_preserves_other_headers(self, mock_auth_manager_for_http):
        """
        What it does: Verifies that adding Connection: close doesn't remove other headers.
        Purpose: Ensure Authorization and other headers are preserved.
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        
        mock_request = Mock()
        captured_headers = {}
        
        def capture_build_request(method, url, content, headers):
            captured_headers.update(headers)
            return mock_request
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.build_request = Mock(side_effect=capture_build_request)
        mock_client.send = AsyncMock(return_value=mock_response)
        
        original_headers = {
            "Authorization": "Bearer test_token",
            "Content-Type": "application/json",
            "X-Custom-Header": "custom_value"
        }
        
        print("Action: Executing streaming request with multiple headers...")
        with patch.object(http_client, '_get_client', return_value=mock_client):
            with patch('kiro.http_client.get_kiro_headers', return_value=original_headers.copy()):
                response = await http_client.request_with_retry(
                    "POST",
                    "https://api.example.com/test",
                    {"data": "value"},
                    stream=True
                )
        
        print("Verification: All original headers preserved plus Connection: close...")
        print(f"Captured headers: {captured_headers}")
        assert captured_headers["Authorization"] == "Bearer test_token"
        assert captured_headers["Content-Type"] == "application/json"
        assert captured_headers["X-Custom-Header"] == "custom_value"
        assert captured_headers["Connection"] == "close"
        assert response.status_code == 200


class TestKiroHttpClientRequestParameters:
    """Tests for request_with_retry method with params and optional json_data (Account System)."""
    
    @pytest.mark.asyncio
    async def test_request_with_retry_get_with_params(self, mock_auth_manager_for_http):
        """
        What it does: Verifies GET request with query parameters.
        Purpose: Ensure params are passed correctly for GET requests (used by AccountManager for /ListAvailableModels).
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={"models": []})
        
        captured_kwargs = {}
        
        async def capture_request(method, url, **kwargs):
            captured_kwargs.update(kwargs)
            return mock_response
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.request = AsyncMock(side_effect=capture_request)
        
        print("Action: Executing GET request with params...")
        with patch.object(http_client, '_get_client', return_value=mock_client):
            with patch('kiro.http_client.get_kiro_headers', return_value={"Authorization": "Bearer test"}):
                response = await http_client.request_with_retry(
                    "GET",
                    "https://api.example.com/ListAvailableModels",
                    json_data=None,
                    params={"origin": "AI_EDITOR", "profileArn": "arn:aws:..."}
                )
        
        print("Verification: params passed, json NOT passed...")
        print(f"Captured kwargs: {captured_kwargs}")
        assert "params" in captured_kwargs, f"params not found in kwargs: {captured_kwargs}"
        assert captured_kwargs["params"]["origin"] == "AI_EDITOR"
        assert captured_kwargs["params"]["profileArn"] == "arn:aws:..."
        assert "json" not in captured_kwargs, f"json should not be present for GET: {captured_kwargs}"
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_request_with_retry_post_without_json(self, mock_auth_manager_for_http):
        """
        What it does: Verifies POST request without json_data.
        Purpose: Ensure json_data is optional and not passed when None.
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        
        captured_kwargs = {}
        
        async def capture_request(method, url, **kwargs):
            captured_kwargs.update(kwargs)
            return mock_response
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.request = AsyncMock(side_effect=capture_request)
        
        print("Action: Executing POST request without json_data...")
        with patch.object(http_client, '_get_client', return_value=mock_client):
            with patch('kiro.http_client.get_kiro_headers', return_value={"Authorization": "Bearer test"}):
                response = await http_client.request_with_retry(
                    "POST",
                    "https://api.example.com/test",
                    json_data=None,
                    params=None
                )
        
        print("Verification: Only headers passed, no json or params...")
        print(f"Captured kwargs: {captured_kwargs}")
        assert "headers" in captured_kwargs
        assert "json" not in captured_kwargs, f"json should not be present when None: {captured_kwargs}"
        assert "params" not in captured_kwargs, f"params should not be present when None: {captured_kwargs}"
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_request_with_retry_params_and_json(self, mock_auth_manager_for_http):
        """
        What it does: Verifies simultaneous use of params and json_data.
        Purpose: Ensure both params and json can be passed together (edge case).
        """
        print("Setup: Creating KiroHttpClient...")
        http_client = KiroHttpClient(mock_auth_manager_for_http)
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        
        captured_kwargs = {}
        
        async def capture_request(method, url, **kwargs):
            captured_kwargs.update(kwargs)
            return mock_response
        
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.request = AsyncMock(side_effect=capture_request)
        
        print("Action: Executing request with both params and json...")
        with patch.object(http_client, '_get_client', return_value=mock_client):
            with patch('kiro.http_client.get_kiro_headers', return_value={"Authorization": "Bearer test"}):
                response = await http_client.request_with_retry(
                    "POST",
                    "https://api.example.com/test",
                    json_data={"data": "value"},
                    params={"filter": "active"}
                )
        
        print("Verification: Both params and content passed...")
        print(f"Captured kwargs: {captured_kwargs}")
        assert "params" in captured_kwargs, f"params not found: {captured_kwargs}"
        assert "content" in captured_kwargs, f"content not found: {captured_kwargs}"
        assert captured_kwargs["params"]["filter"] == "active"
        assert json.loads(captured_kwargs["content"])["data"] == "value"
        assert response.status_code == 200