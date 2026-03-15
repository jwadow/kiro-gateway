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
from kiro.runtime_usage import (
    build_usage_limits_params,
    build_usage_summary,
    fetch_usage_limits,
)


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
        What it does: Verifies successful upstream payload is returned with a derived summary.
        Purpose: Preserve transparency while exposing stable usage fields.
        """
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "subscriptionInfo": {"subscriptionTitle": "KIRO PRO"},
            "usageBreakdownList": [
                {
                    "resourceType": "CREDIT",
                    "usageLimit": 1000,
                    "currentUsageWithPrecision": 0.0,
                    "unit": "INVOCATIONS",
                    "nextDateReset": 1775001600.0,
                    "freeTrialInfo": {
                        "usageLimit": 500,
                        "currentUsageWithPrecision": 330.11,
                        "freeTrialExpiry": 1775916932.34,
                    },
                }
            ],
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
        assert payload["usageSummary"] == {
            "resetAt": "2026-04-01T00:00:00Z",
            "primaryLimit": 1000,
            "primaryUsed": 0.0,
            "primaryUnit": "INVOCATIONS",
            "freeTrialLimit": 500,
            "freeTrialUsed": 330.11,
            "freeTrialExpiresAt": "2026-04-11T14:15:32.340Z",
        }
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


class TestBuildUsageSummary:
    """Tests for derived usage summary generation."""

    def test_builds_summary_from_usage_breakdown_list(self):
        """
        What it does: Verifies the gateway derives stable summary fields.
        Purpose: Expose the key usage values clients need without losing raw payload data.
        """
        payload = {
            "nextDateReset": 1775001600.0,
            "usageBreakdownList": [
                {
                    "resourceType": "CREDIT",
                    "usageLimit": 1000,
                    "currentUsageWithPrecision": 0.0,
                    "unit": "INVOCATIONS",
                    "nextDateReset": 1775001600.0,
                    "freeTrialInfo": {
                        "usageLimit": 500,
                        "currentUsageWithPrecision": 330.11,
                        "freeTrialExpiry": 1775916932.34,
                    },
                }
            ],
        }

        print("Action: Building usage summary from upstream payload...")
        summary = build_usage_summary(payload)

        print(f"Summary: {summary}")
        assert summary == {
            "resetAt": "2026-04-01T00:00:00Z",
            "primaryLimit": 1000,
            "primaryUsed": 0.0,
            "primaryUnit": "INVOCATIONS",
            "freeTrialLimit": 500,
            "freeTrialUsed": 330.11,
            "freeTrialExpiresAt": "2026-04-11T14:15:32.340Z",
        }

    def test_handles_missing_breakdown_data(self):
        """
        What it does: Verifies missing upstream fields degrade gracefully.
        Purpose: Keep response shape stable even when upstream omits usage data.
        """
        print("Action: Building usage summary from incomplete payload...")
        summary = build_usage_summary({})

        print(f"Summary: {summary}")
        assert summary == {
            "resetAt": None,
            "primaryLimit": None,
            "primaryUsed": None,
            "primaryUnit": None,
            "freeTrialLimit": None,
            "freeTrialUsed": None,
            "freeTrialExpiresAt": None,
        }
