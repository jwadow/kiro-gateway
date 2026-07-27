
# -*- coding: utf-8 -*-

"""
Unit tests for the subscription usage endpoint (routes_usage.py).

Tests the following:
- build_usage_summary() - flattening getUsageLimits payloads
- fetch_usage_limits() - host fallback and error handling
- GET /v1/usage - authentication and account requirements
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch

import httpx
from fastapi import HTTPException

from kiro.routes_usage import (
    USAGE_HOST_TEMPLATES,
    USAGE_PARAMS,
    build_usage_summary,
    fetch_usage_limits,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def usage_payload():
    """A getUsageLimits response for a paid plan with one credit bucket."""
    return {
        "daysUntilReset": 4,
        "nextDateReset": 1785542400.0,
        "subscriptionInfo": {
            "subscriptionTitle": "KIRO PRO MAX",
            "type": "Q_DEVELOPER_STANDALONE_PRO_MAX",
        },
        "usageBreakdownList": [
            {
                "currentUsage": 4541,
                "currentUsageWithPrecision": 4541.47,
                "displayNamePlural": "Credits",
                "overageCap": 10000,
                "overageCapWithPrecision": 10000.0,
                "overageRate": 0.04,
                "resourceType": "CREDIT",
                "usageLimit": 5000,
                "usageLimitWithPrecision": 5000.0,
            }
        ],
        "userInfo": {"userId": "d-906670d0a6.4478e4f8"},
    }


def _client_returning(*responses):
    """
    Builds a mock httpx.AsyncClient whose get() yields the given results.

    Each entry is either an httpx.Response to return or an exception to raise.
    """
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    client.get = AsyncMock(side_effect=list(responses))
    return client


def _response(status_code, json_data=None, text=""):
    """Builds a minimal mock httpx.Response."""
    response = Mock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data or {}
    response.text = text
    return response


# =============================================================================
# Tests for build_usage_summary
# =============================================================================

class TestBuildUsageSummary:
    """Tests for flattening getUsageLimits payloads."""

    def test_extracts_primary_quota_bucket(self, usage_payload):
        """
        What it does: Verifies the first breakdown entry becomes the summary.
        Purpose: Ensure dashboards read the subscription's main allowance.
        """
        print("Action: Summarizing a paid-plan payload...")
        summary = build_usage_summary(usage_payload)

        print(f"Comparing plan name: Expected KIRO PRO MAX, Got {summary['planName']}")
        assert summary["planName"] == "KIRO PRO MAX"
        assert summary["subscriptionType"] == "Q_DEVELOPER_STANDALONE_PRO_MAX"

        print(f"Comparing usage: Expected 4541.5/5000.0, Got {summary['used']}/{summary['total']}")
        assert summary["used"] == 4541.5
        assert summary["total"] == 5000.0
        assert summary["remaining"] == 458.5
        assert summary["unit"] == "Credits"

        print("Checking: overage and reset fields are carried through...")
        assert summary["overageCap"] == 10000.0
        assert summary["overageRate"] == 0.04
        assert summary["daysUntilReset"] == 4
        assert summary["nextDateReset"] == 1785542400.0
        assert summary["userId"] == "d-906670d0a6.4478e4f8"
        assert summary["isValid"] is True

    def test_preserves_raw_payload(self, usage_payload):
        """
        What it does: Verifies the untouched payload is returned under "raw".
        Purpose: Let callers read fields the summary does not surface.
        """
        print("Action: Summarizing and inspecting raw...")
        summary = build_usage_summary(usage_payload)

        print("Checking: raw matches the input payload...")
        assert summary["raw"] == usage_payload

    def test_handles_missing_breakdown_list(self):
        """
        What it does: Verifies a payload without quota buckets is summarized.
        Purpose: Free-tier accounts return an empty list; must not raise.
        """
        print("Setup: Payload with no usageBreakdownList...")
        payload = {"subscriptionInfo": {"subscriptionTitle": "KIRO FREE"}}

        print("Action: Summarizing...")
        summary = build_usage_summary(payload)

        print(f"Comparing totals: Expected zeros, Got {summary['used']}/{summary['total']}")
        assert summary["planName"] == "KIRO FREE"
        assert summary["used"] == 0.0
        assert summary["total"] == 0
        assert summary["remaining"] == 0.0
        assert summary["unit"] == "credits"

    def test_falls_back_to_default_plan_name(self):
        """
        What it does: Verifies a missing subscription title defaults to "Kiro".
        Purpose: Avoid rendering an empty plan label.
        """
        print("Action: Summarizing an empty payload...")
        summary = build_usage_summary({})

        print(f"Comparing plan name: Expected Kiro, Got {summary['planName']}")
        assert summary["planName"] == "Kiro"
        assert summary["subscriptionType"] is None

    def test_clamps_remaining_at_zero_when_over_limit(self):
        """
        What it does: Verifies overage usage never yields negative remaining.
        Purpose: Accounts past their limit should read 0, not a negative number.
        """
        print("Setup: Usage above the plan limit...")
        payload = {
            "usageBreakdownList": [
                {"currentUsageWithPrecision": 6200.0, "usageLimitWithPrecision": 5000.0}
            ]
        }

        print("Action: Summarizing...")
        summary = build_usage_summary(payload)

        print(f"Comparing remaining: Expected 0.0, Got {summary['remaining']}")
        assert summary["remaining"] == 0.0
        assert summary["used"] == 6200.0

    def test_prefers_precise_values_over_rounded(self):
        """
        What it does: Verifies *WithPrecision fields win over integer fields.
        Purpose: Credit usage is fractional; the rounded value loses detail.
        """
        print("Setup: Payload with both precise and rounded usage...")
        payload = {
            "usageBreakdownList": [
                {
                    "currentUsage": 100,
                    "currentUsageWithPrecision": 100.94,
                    "usageLimit": 500,
                    "usageLimitWithPrecision": 500.0,
                }
            ]
        }

        print("Action: Summarizing...")
        summary = build_usage_summary(payload)

        print(f"Comparing used: Expected 100.9, Got {summary['used']}")
        assert summary["used"] == 100.9


# =============================================================================
# Tests for fetch_usage_limits
# =============================================================================

class TestFetchUsageLimits:
    """Tests for the getUsageLimits request and host fallback."""

    @pytest.mark.asyncio
    async def test_returns_payload_from_first_host(self, usage_payload):
        """
        What it does: Verifies a 200 from the first host short-circuits.
        Purpose: Avoid a needless request to the fallback host.
        """
        print("Setup: First host returns 200...")
        client = _client_returning(_response(200, usage_payload))

        with patch("kiro.routes_usage.httpx.AsyncClient", return_value=client):
            print("Action: Fetching usage limits...")
            result = await fetch_usage_limits("test_token", "us-east-1")

        print("Checking: payload returned and only one request made...")
        assert result == usage_payload
        assert client.get.await_count == 1

    @pytest.mark.asyncio
    async def test_sends_bearer_token_and_expected_params(self, usage_payload):
        """
        What it does: Verifies the access token and query params are sent.
        Purpose: getUsageLimits requires bearer auth; profileArn must be absent
                 because Enterprise IdC accounts reject it.
        """
        print("Setup: First host returns 200...")
        client = _client_returning(_response(200, usage_payload))

        with patch("kiro.routes_usage.httpx.AsyncClient", return_value=client):
            print("Action: Fetching usage limits...")
            await fetch_usage_limits("secret_token", "us-east-1")

        call = client.get.await_args
        print(f"Checking request: {call.args[0]}")
        assert call.args[0] == "https://q.us-east-1.amazonaws.com/getUsageLimits"
        assert call.kwargs["headers"] == {"Authorization": "Bearer secret_token"}
        assert call.kwargs["params"] == USAGE_PARAMS
        assert "profileArn" not in call.kwargs["params"]

    @pytest.mark.asyncio
    async def test_uses_account_region_in_url(self, usage_payload):
        """
        What it does: Verifies the account's region is used in the host.
        Purpose: Non us-east-1 accounts must not be queried in the wrong region.
        """
        print("Setup: eu-central-1 account...")
        client = _client_returning(_response(200, usage_payload))

        with patch("kiro.routes_usage.httpx.AsyncClient", return_value=client):
            print("Action: Fetching usage limits...")
            await fetch_usage_limits("test_token", "eu-central-1")

        url = client.get.await_args.args[0]
        print(f"Comparing host region: Got {url}")
        assert url == "https://q.eu-central-1.amazonaws.com/getUsageLimits"

    @pytest.mark.asyncio
    async def test_falls_back_to_second_host_on_error_status(self, usage_payload):
        """
        What it does: Verifies a non-200 first host falls through to the next.
        Purpose: Some accounts are only reachable via the CodeWhisperer alias.
        """
        print("Setup: First host 403, second host 200...")
        client = _client_returning(
            _response(403, text="Forbidden"),
            _response(200, usage_payload),
        )

        with patch("kiro.routes_usage.httpx.AsyncClient", return_value=client):
            print("Action: Fetching usage limits...")
            result = await fetch_usage_limits("test_token", "us-east-1")

        print("Checking: payload came from the fallback host...")
        assert result == usage_payload
        assert client.get.await_count == len(USAGE_HOST_TEMPLATES)

    @pytest.mark.asyncio
    async def test_falls_back_to_second_host_on_transport_error(self, usage_payload):
        """
        What it does: Verifies a network failure falls through to the next host.
        Purpose: A DNS failure on one alias must not fail the whole request.
        """
        print("Setup: First host raises, second host 200...")
        client = _client_returning(
            httpx.ConnectError("dns failure"),
            _response(200, usage_payload),
        )

        with patch("kiro.routes_usage.httpx.AsyncClient", return_value=client):
            print("Action: Fetching usage limits...")
            result = await fetch_usage_limits("test_token", "us-east-1")

        print("Checking: payload came from the fallback host...")
        assert result == usage_payload

    @pytest.mark.asyncio
    async def test_raises_502_when_all_hosts_fail(self):
        """
        What it does: Verifies exhausting every host raises HTTP 502.
        Purpose: Surface upstream failure instead of returning empty usage.
        """
        print("Setup: Every host returns 500...")
        client = _client_returning(
            *[_response(500, text="boom") for _ in USAGE_HOST_TEMPLATES]
        )

        with patch("kiro.routes_usage.httpx.AsyncClient", return_value=client):
            print("Action: Fetching usage limits...")
            with pytest.raises(HTTPException) as exc_info:
                await fetch_usage_limits("test_token", "us-east-1")

        print(f"Checking: status 502, Got {exc_info.value.status_code}")
        assert exc_info.value.status_code == 502
        assert "getUsageLimits failed" in exc_info.value.detail


# =============================================================================
# Tests for GET /v1/usage
# =============================================================================

class TestUsageEndpoint:
    """Tests for the /v1/usage route."""

    def test_requires_api_key(self, test_client):
        """
        What it does: Verifies an unauthenticated request is rejected.
        Purpose: Usage data must not be readable without the proxy key.
        """
        print("Action: Requesting /v1/usage with no Authorization header...")
        response = test_client.get("/v1/usage")

        print(f"Comparing status: Expected 401, Got {response.status_code}")
        assert response.status_code == 401

    def test_returns_503_when_no_account_initialized(self, test_client, auth_headers):
        """
        What it does: Verifies a missing account yields HTTP 503.
        Purpose: Distinguish "gateway not ready" from an upstream failure.
        """
        print("Setup: account_manager with no initialized account...")
        manager = Mock()
        manager.get_first_account.return_value = None

        with patch.object(test_client.app.state, "account_manager", manager):
            print("Action: Requesting /v1/usage...")
            response = test_client.get("/v1/usage", headers=auth_headers())

        print(f"Comparing status: Expected 503, Got {response.status_code}")
        assert response.status_code == 503
        assert "No initialized account" in response.json()["detail"]

    def test_returns_summary_for_initialized_account(
        self, test_client, auth_headers, usage_payload
    ):
        """
        What it does: Verifies a summary is returned for a ready account.
        Purpose: End-to-end check of auth, token retrieval, and summarizing.
        """
        print("Setup: account with a valid token in us-east-1...")
        auth_manager = Mock()
        auth_manager.region = "us-east-1"
        auth_manager.get_access_token = AsyncMock(return_value="test_token")

        account = Mock()
        account.auth_manager = auth_manager

        manager = Mock()
        manager.get_first_account.return_value = account

        with patch.object(test_client.app.state, "account_manager", manager), patch(
            "kiro.routes_usage.fetch_usage_limits",
            AsyncMock(return_value=usage_payload),
        ):
            print("Action: Requesting /v1/usage...")
            response = test_client.get("/v1/usage", headers=auth_headers())

        print(f"Comparing status: Expected 200, Got {response.status_code}")
        assert response.status_code == 200

        body = response.json()
        print(f"Checking body: plan {body['planName']}, remaining {body['remaining']}")
        assert body["planName"] == "KIRO PRO MAX"
        assert body["remaining"] == 458.5
        assert body["isValid"] is True
