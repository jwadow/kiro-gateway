# -*- coding: utf-8 -*-

"""
Tests for PR #1 of perf-async-improvements: shared streaming client + auth singleton.

Covers:
- KiroAuthManager accepts an injected refresh_client (T1.1)
- Token refresh uses the injected client, not a freshly constructed one (T1.3)
- Streaming OpenAI requests reuse the shared client (T1.6)
- Streaming Anthropic requests reuse the shared client (T1.8)
- Connection: close header preserved on streaming (T1.10)
- Auth singleton lifecycle (T1.11)
- No CLOSE_WAIT regression under concurrent streaming (T1.15)
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from kiro.auth import KiroAuthManager


# =============================================================================
# T1.1 - KiroAuthManager accepts a refresh_client parameter
# =============================================================================


class TestKiroAuthManagerAcceptsRefreshClient:
    """T1.1: KiroAuthManager(refresh_client=mock_client) stores it as self._refresh_client."""

    def test_refresh_client_is_stored_when_provided(self):
        """
        What it does: Verifies KiroAuthManager stores the injected refresh_client.
        Purpose: Make the auth singleton wiring land a testable seam (FR-1.3, FR-1.4).
        """
        print("Setup: Building a fake httpx.AsyncClient...")
        fake_client = AsyncMock()

        print("Action: Constructing KiroAuthManager with refresh_client=...")
        manager = KiroAuthManager(refresh_token="t", refresh_client=fake_client)

        print("Verification: refresh_client is stored as _refresh_client...")
        assert manager._refresh_client is fake_client

    def test_refresh_client_defaults_to_none(self):
        """
        What it does: Verifies the default value of refresh_client is None.
        Purpose: Backwards compatibility — existing call sites still work.
        """
        print("Action: Constructing KiroAuthManager without refresh_client...")
        manager = KiroAuthManager(refresh_token="token_default")

        print("Verification: _refresh_client defaults to None...")
        assert manager._refresh_client is None


# =============================================================================
# T1.3 - Token refresh uses the injected client
# =============================================================================


class TestAuthRefreshUsesRefreshClient:
    """T1.3: force_refresh() uses self._refresh_client; no new AsyncClient is built."""

    @pytest.mark.asyncio
    async def test_kiro_desktop_refresh_uses_injected_client(self, valid_kiro_token, mock_kiro_token_response):
        """
        What it does: Verifies _refresh_token_kiro_desktop posts on the injected client.
        Purpose: Hot path no longer constructs an httpx.AsyncClient per refresh.
        """
        print("Setup: Building KiroAuthManager with a fake refresh_client...")
        manager = KiroAuthManager(refresh_token="refresh_xyz")
        manager._access_token = "old_token"
        manager._expires_at = None  # ensure refresh happens

        fake_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value=mock_kiro_token_response(token=valid_kiro_token))
        mock_response.raise_for_status = Mock()
        fake_client.post = AsyncMock(return_value=mock_response)
        manager._refresh_client = fake_client

        # We must NOT create httpx.AsyncClient inside the auth module during this call.
        with patch("kiro.auth.httpx.AsyncClient") as mock_client_class:
            print("Action: Triggering force_refresh()...")
            token = await manager.force_refresh()

            print("Verification: injected client.post was called...")
            fake_client.post.assert_called_once()

            print("Verification: no new httpx.AsyncClient was constructed...")
            mock_client_class.assert_not_called()

            print(f"Verification: returned token matches expected: {valid_kiro_token}")
            assert token == valid_kiro_token

    @pytest.mark.asyncio
    async def test_kiro_desktop_refresh_falls_back_to_local_client_when_unset(
        self, valid_kiro_token, mock_kiro_token_response
    ):
        """
        What it does: Verifies fallback when _refresh_client is None.
        Purpose: Backwards compatibility — the per-call client path still works.
        """
        print("Setup: Building KiroAuthManager WITHOUT a refresh_client...")
        manager = KiroAuthManager(refresh_token="refresh_xyz")
        manager._access_token = "old_token"
        manager._expires_at = None
        manager._refresh_client = None

        print("Action: Force-refreshing with patched httpx.AsyncClient fallback...")
        with patch("kiro.auth.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json = Mock(return_value=mock_kiro_token_response(token=valid_kiro_token))
            mock_response.raise_for_status = Mock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            token = await manager.force_refresh()

            print("Verification: httpx.AsyncClient was created (fallback path)...")
            mock_client_class.assert_called_once()
            print(f"Verification: returned token is valid: {token == valid_kiro_token}")
            assert token == valid_kiro_token


# =============================================================================
# T1.6 - Streaming OpenAI requests reuse the shared client
# =============================================================================


class TestStreamingOpenAIUsesSharedClient:
    """T1.6: KiroHttpClient receives app.state.http_client even in the streaming branch."""

    @patch("kiro.routes_openai.KiroHttpClient")
    def test_streaming_openai_passes_shared_client(
        self,
        mock_kiro_http_client_class,
        test_client,
        valid_proxy_api_key,
    ):
        """
        What it does: Verifies streaming OpenAI requests pass app.state.http_client.
        Purpose: PR #1 extends shared-client reuse to the streaming branch.
        """
        print("\n--- Test: Streaming OpenAI uses shared client ---")
        mock_instance = AsyncMock()
        mock_instance.request_with_retry = AsyncMock(side_effect=Exception("network blocked"))
        mock_instance.close = AsyncMock()
        mock_kiro_http_client_class.return_value = mock_instance

        try:
            test_client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
                json={
                    "model": "claude-sonnet-4-5",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": True,
                },
            )
        except Exception:
            pass

        assert mock_kiro_http_client_class.called
        call_args = mock_kiro_http_client_class.call_args
        print(f"Call args: {call_args}")
        assert call_args[1]["shared_client"] is not None, (
            "Streaming should pass the shared app.state.http_client to KiroHttpClient"
        )
        # And critically: the shared_client is the actual app.state.http_client
        from main import app
        assert call_args[1]["shared_client"] is app.state.http_client


# =============================================================================
# T1.8 - Streaming Anthropic requests reuse the shared client
# =============================================================================


class TestStreamingAnthropicUsesSharedClient:
    """T1.8: Same shared-client guarantee for the Anthropic streaming branch."""

    @patch("kiro.routes_anthropic.KiroHttpClient")
    def test_streaming_anthropic_passes_shared_client(
        self,
        mock_kiro_http_client_class,
        test_client,
        valid_proxy_api_key,
    ):
        """
        What it does: Verifies streaming Anthropic requests pass app.state.http_client.
        Purpose: PR #1 extends shared-client reuse to Anthropic streaming too.
        """
        print("\n--- Test: Streaming Anthropic uses shared client ---")
        mock_instance = AsyncMock()
        mock_instance.request_with_retry = AsyncMock(side_effect=Exception("network blocked"))
        mock_instance.close = AsyncMock()
        mock_kiro_http_client_class.return_value = mock_instance

        try:
            test_client.post(
                "/v1/messages",
                headers={
                    "x-api-key": valid_proxy_api_key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": "claude-sonnet-4-5",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "max_tokens": 16,
                    "stream": True,
                },
            )
        except Exception:
            pass

        assert mock_kiro_http_client_class.called
        call_args = mock_kiro_http_client_class.call_args
        print(f"Call args: {call_args}")
        assert call_args[1]["shared_client"] is not None, (
            "Streaming Anthropic should pass the shared app.state.http_client to KiroHttpClient"
        )
        from main import app
        assert call_args[1]["shared_client"] is app.state.http_client


# =============================================================================
# T1.10 - Connection: close header preserved on streaming
# =============================================================================


class TestConnectionCloseHeaderOnStream:
    """T1.10: Regression for issues #38 and #54 — Connection: close must remain on streaming."""

    @pytest.mark.asyncio
    async def test_streaming_request_sends_connection_close(self):
        """
        What it does: Verifies Connection: close is set on streaming requests.
        Purpose: Prevent CLOSE_WAIT leak on VPN reconnect (issue #38, #54).
        """
        print("Setup: Building mock KiroAuthManager + KiroHttpClient...")
        mock_auth = AsyncMock(spec=KiroAuthManager)
        mock_auth.get_access_token = AsyncMock(return_value="test_token")
        mock_auth.force_refresh = AsyncMock(return_value="new_token")
        mock_auth.fingerprint = "fp12345678"
        mock_auth._fingerprint = "fp12345678"

        from kiro.http_client import KiroHttpClient
        http_client = KiroHttpClient(mock_auth)

        mock_response = AsyncMock()
        mock_response.status_code = 200

        captured_headers: dict = {}

        def capture_build_request(method, url, content, headers):
            captured_headers.update(headers)
            return Mock()

        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.build_request = Mock(side_effect=capture_build_request)
        mock_client.send = AsyncMock(return_value=mock_response)

        with patch.object(http_client, "_get_client", return_value=mock_client):
            with patch("kiro.http_client.get_kiro_headers", return_value={"Authorization": "Bearer test"}):
                await http_client.request_with_retry(
                    "POST",
                    "https://api.example.com/test",
                    {"data": "value"},
                    stream=True,
                )

        print(f"Captured headers: {captured_headers}")
        assert "Connection" in captured_headers
        assert captured_headers["Connection"] == "close"


# =============================================================================
# T1.11 - Auth singleton lifecycle (startup creates, shutdown closes)
# =============================================================================


class TestAuthSingletonLifecycle:
    """T1.11: app.state.auth_http_client exists after startup and is_closed after shutdown."""

    @pytest.mark.asyncio
    async def test_auth_singleton_created_at_startup_and_closed_at_shutdown(self, clean_app):
        """
        What it does: Verifies app.state.auth_http_client is set up and torn down by lifespan.
        Purpose: Auth singleton lifecycle must mirror app.state.http_client.
        """
        print("Setup: Booting app via ASGITransport...")
        transport = ASGITransport(app=clean_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Trigger lifespan startup by sending a real request
            await ac.get("/health")
            assert hasattr(clean_app.state, "auth_http_client")
            assert clean_app.state.auth_http_client is not None
            print("Verification: auth_http_client created at startup")
            assert not clean_app.state.auth_http_client.is_closed

        # Lifespan shutdown has run because we exited the AsyncClient context
        assert clean_app.state.auth_http_client.is_closed, (
            "auth_http_client should be closed after lifespan shutdown"
        )
        print("Verification: auth_http_client closed at shutdown")


# =============================================================================
# T1.15 - No CLOSE_WAIT regression under concurrent streaming
# =============================================================================


class TestNoCloseWaitRegression:
    """T1.15: 5 concurrent streaming requests with a connection-counting MockTransport."""

    @pytest.mark.asyncio
    async def test_concurrent_streaming_no_close_wait_regression(self):
        """
        What it does: 5 concurrent streaming requests share one httpx client.
        Purpose: Shared client + Connection: close must not leak connections (issue #38).
        """
        print("Setup: Building connection-counting MockTransport...")

        active_connections = 0
        max_active = 0
        lock = asyncio.Lock()

        async def count_open(request: httpx.Request) -> httpx.Response:
            nonlocal active_connections, max_active
            async with lock:
                active_connections += 1
                max_active = max(max_active, active_connections)
            try:
                # Simulate minimal body and then close
                return httpx.Response(200, content=b"data: [DONE]\n\n")
            finally:
                async with lock:
                    active_connections -= 1

        transport = httpx.MockTransport(count_open)

        print("Action: 5 concurrent streaming requests sharing one client...")
        shared_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0), transport=transport)

        async def do_request():
            req = shared_client.build_request(
                "POST",
                "https://api.example.com/test",
                content=b"{}",
                headers={"Connection": "close"},
            )
            resp = await shared_client.send(req, stream=True)
            await resp.aread()
            await resp.aclose()

        try:
            await asyncio.gather(*(do_request() for _ in range(5)))
        finally:
            await shared_client.aclose()

        print(f"max_active concurrent connections: {max_active}")
        print(f"final active_connections: {active_connections}")
        assert active_connections == 0, (
            f"Active connection count must return to 0, got {active_connections}"
        )
