# -*- coding: utf-8 -*-

"""
Unit tests for runtime usage helpers.
"""

import json
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from fastapi import HTTPException

from kiro.auth import AuthType
from kiro.runtime_usage import build_usage_limits_params, fetch_usage_limits


@pytest.fixture
def mock_usage_auth_manager():
    """Create a mocked auth manager for usage helper tests."""
    manager = Mock()
    manager.auth_type = AuthType.KIRO_DESKTOP
    manager.profile_arn = "arn:aws:codewhisperer:us-east-1:123456789012:profile/test"
    manager.q_host = "https://q.us-east-1.amazonaws.com"
    return manager


class TestBuildUsageLimitsParams:
    """Tests for usage query parameter construction."""

    def test_includes_profile_arn_for_kiro_desktop(self, mock_usage_auth_manager):
        """
        What it does: Verifies desktop auth includes profileArn in query params.
        Purpose: Ensure GetUsageLimits matches Kiro desktop client behavior.
        """
        print("Action: Building params for desktop auth...")
        params = build_usage_limits_params(mock_usage_auth_manager)

        print(f"Result: {params}")
        assert params["origin"] == "AI_EDITOR"
        assert params["resourceType"] == "AGENTIC_REQUEST"
        assert params["isEmailRequired"] == "true"
        assert params["profileArn"] == mock_usage_auth_manager.profile_arn

    def test_omits_profile_arn_for_aws_sso(self, mock_usage_auth_manager):
        """
        What it does: Verifies AWS SSO auth omits profileArn.
        Purpose: Avoid sending unsupported profileArn for non-desktop auth.
        """
        print("Setup: Switching auth type to AWS SSO OIDC...")
        mock_usage_auth_manager.auth_type = AuthType.AWS_SSO_OIDC

        print("Action: Building params for AWS SSO auth...")
        params = build_usage_limits_params(mock_usage_auth_manager)

        print(f"Result: {params}")
        assert "profileArn" not in params

    def test_empty_origin_raises_value_error(self, mock_usage_auth_manager):
        """
        What it does: Verifies empty origin is rejected.
        Purpose: Ensure invalid query construction fails early.
        """
        print("Action: Building params with empty origin...")
        with pytest.raises(ValueError) as exc_info:
            build_usage_limits_params(mock_usage_auth_manager, origin="")

        print(f"Error: {exc_info.value}")
        assert "origin must not be empty" in str(exc_info.value)


class TestFetchUsageLimits:
    """Tests for GetUsageLimits fetching."""

    @pytest.mark.asyncio
    @patch("kiro.runtime_usage.KiroHttpClient")
    async def test_returns_usage_payload(self, mock_http_client_class, mock_usage_auth_manager):
        """
        What it does: Verifies successful upstream payload is returned unchanged.
        Purpose: Preserve transparency for usage responses.
        """
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "subscriptionInfo": {"subscriptionTitle": "KIRO PRO"},
            "usageBreakdownList": [],
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.request_with_retry = AsyncMock(return_value=mock_response)
        mock_http_client_class.return_value = mock_client

        print("Action: Fetching usage limits...")
        payload = await fetch_usage_limits(
            auth_manager=mock_usage_auth_manager,
            shared_client=None,
        )

        print(f"Result: {payload}")
        assert payload["subscriptionInfo"]["subscriptionTitle"] == "KIRO PRO"
        mock_client.request_with_retry.assert_awaited_once_with(
            "GET",
            "https://q.us-east-1.amazonaws.com/getUsageLimits",
            params={
                "origin": "AI_EDITOR",
                "resourceType": "AGENTIC_REQUEST",
                "isEmailRequired": "true",
                "profileArn": mock_usage_auth_manager.profile_arn,
            },
        )

    @pytest.mark.asyncio
    @patch("kiro.runtime_usage.KiroHttpClient")
    async def test_upstream_error_raises_http_exception(self, mock_http_client_class, mock_usage_auth_manager):
        """
        What it does: Verifies non-200 upstream responses become HTTPException.
        Purpose: Return actionable route errors to gateway clients.
        """
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 403
        mock_response.text = '{"message":"Access denied"}'
        mock_response.json.return_value = {"message": "Access denied"}

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.request_with_retry = AsyncMock(return_value=mock_response)
        mock_http_client_class.return_value = mock_client

        print("Action: Fetching usage limits with upstream 403...")
        with pytest.raises(HTTPException) as exc_info:
            await fetch_usage_limits(
                auth_manager=mock_usage_auth_manager,
                shared_client=None,
            )

        print(f"Error response: {exc_info.value.detail}")
        assert exc_info.value.status_code == 403
        assert "Failed to fetch usage limits" in exc_info.value.detail
        assert "Access denied" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("kiro.runtime_usage.KiroHttpClient")
    async def test_invalid_json_raises_502(self, mock_http_client_class, mock_usage_auth_manager):
        """
        What it does: Verifies invalid upstream JSON raises 502.
        Purpose: Prevent malformed upstream responses from leaking through silently.
        """
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("bad json", "x", 0)

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.request_with_retry = AsyncMock(return_value=mock_response)
        mock_http_client_class.return_value = mock_client

        print("Action: Fetching usage limits with invalid JSON response...")
        with pytest.raises(HTTPException) as exc_info:
            await fetch_usage_limits(
                auth_manager=mock_usage_auth_manager,
                shared_client=None,
            )

        print(f"Error response: {exc_info.value.detail}")
        assert exc_info.value.status_code == 502
        assert "invalid JSON" in exc_info.value.detail
