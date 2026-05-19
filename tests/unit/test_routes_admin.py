# -*- coding: utf-8 -*-
"""Tests for kiro/routes_admin.py"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kiro.account_manager import Account, AccountStats
from kiro.usage_limits import UsageLimitsResult, ProfileResult

FAKE_KEY = "test-key"


def _make_account(account_id: str, failures: int = 0, initialized: bool = True) -> Account:
    a = Account(id=account_id)
    a.failures = failures
    a.stats = AccountStats(total_requests=10, successful_requests=9, failed_requests=1)
    if initialized:
        m = MagicMock()
        m.api_host = "https://q.us-east-1.amazonaws.com"
        m.profile_arn = None
        a.auth_manager = m
    return a


def _usage_result(current: float = 8181.27, limit: float = 10000.0) -> UsageLimitsResult:
    return UsageLimitsResult(
        raw={
            "daysUntilReset": 5,
            "nextDateReset": 1780272000.0,
            "subscriptionInfo": {
                "type": "Q_DEVELOPER_STANDALONE_POWER",
                "subscriptionTitle": "KIRO POWER",
            },
            "usageBreakdownList": [{
                "displayName": "Credit",
                "currentUsage": int(current),
                "currentUsageWithPrecision": current,
                "usageLimit": int(limit),
                "usageLimitWithPrecision": limit,
                "currency": "USD",
                "resourceType": "CREDIT",
                "unit": "INVOCATIONS",
                "nextDateReset": 1780272000.0,
                "currentOverages": 0,
                "currentOveragesWithPrecision": 0.0,
                "overageCap": 10000,
                "overageCapWithPrecision": 10000.0,
                "overageCharges": 0.0,
                "overageRate": 0.04,
                "freeTrialInfo": None,
                "bonuses": [],
            }],
            "userInfo": {"userId": "u1", "email": None},
            "overageConfiguration": {"overageStatus": "DISABLED", "overageLimit": None},
            "totalUsage": None,
            "usageBreakdown": None,
            "limits": [],
        },
        cached_at=1000.0,
    )


def _profile_result() -> ProfileResult:
    return ProfileResult(
        raw={"profile": {"arn": "arn:aws:...", "profileName": "test-profile", "status": "ACTIVE"}},
        cached_at=1000.0,
    )


@pytest.fixture
def app():
    from kiro.routes_admin import router
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture
def client(app):
    with patch("kiro.routes_admin.PROXY_API_KEY", FAKE_KEY):
        yield TestClient(app)


def test_usage_requires_auth(client):
    resp = client.get("/admin/accounts/usage")
    assert resp.status_code == 403


def test_usage_returns_all_accounts(client, app):
    acct = _make_account("acct1")
    mock_manager = MagicMock()
    mock_manager.get_all_accounts.return_value = [acct]
    app.state.account_manager = mock_manager

    mock_service = MagicMock()
    mock_service.get_usage = AsyncMock(return_value=_usage_result())
    mock_service.get_profile = AsyncMock(return_value=_profile_result())

    with patch("kiro.routes_admin._usage_service", mock_service):
        resp = client.get(
            "/admin/accounts/usage",
            headers={"Authorization": f"Bearer {FAKE_KEY}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    assert len(data["accounts"]) == 1
    a = data["accounts"][0]
    assert a["account_id"] == "acct_ed0fe2baf82b"
    assert a["circuit_state"] == "healthy"
    assert a["usage"]["current_usage"] == pytest.approx(8181.27)
    assert a["usage"]["usage_limit"] == pytest.approx(10000.0)
    assert a["usage"]["percent_used"] == pytest.approx(81.81, abs=0.1)
    assert a["usage"]["subscription_title"] == "KIRO POWER"
    assert a["profile"]["profile_name"] == "test-profile"
    assert a["stale"] is False
    assert a["error"] is None


def test_usage_filter_by_account_id(client, app):
    acct1 = _make_account("acct1")
    acct2 = _make_account("acct2")
    mock_manager = MagicMock()
    mock_manager.get_all_accounts.return_value = [acct1, acct2]
    app.state.account_manager = mock_manager

    mock_service = MagicMock()
    mock_service.get_usage = AsyncMock(return_value=_usage_result())
    mock_service.get_profile = AsyncMock(return_value=_profile_result())

    with patch("kiro.routes_admin._usage_service", mock_service):
        resp = client.get(
            "/admin/accounts/usage?account_id=acct_ed0fe2baf82b",
            headers={"Authorization": f"Bearer {FAKE_KEY}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["account_id"] == "acct_ed0fe2baf82b"


def test_usage_filter_unknown_account_returns_404(client, app):
    mock_manager = MagicMock()
    mock_manager.get_all_accounts.return_value = [_make_account("acct1")]
    app.state.account_manager = mock_manager

    mock_service = MagicMock()
    with patch("kiro.routes_admin._usage_service", mock_service):
        resp = client.get(
            "/admin/accounts/usage?account_id=unknown",
            headers={"Authorization": f"Bearer {FAKE_KEY}"},
        )

    assert resp.status_code == 404


def test_usage_uninitialized_account(client, app):
    acct = _make_account("acct1", initialized=False)
    mock_manager = MagicMock()
    mock_manager.get_all_accounts.return_value = [acct]
    app.state.account_manager = mock_manager

    mock_service = MagicMock()
    with patch("kiro.routes_admin._usage_service", mock_service):
        resp = client.get(
            "/admin/accounts/usage",
            headers={"Authorization": f"Bearer {FAKE_KEY}"},
        )

    assert resp.status_code == 200
    a = resp.json()["accounts"][0]
    assert a["enabled"] is False
    assert a["usage"] is None
    assert a["error"] == "Account not initialized"


def test_usage_tripped_circuit(client, app):
    acct = _make_account("acct1", failures=5)
    mock_manager = MagicMock()
    mock_manager.get_all_accounts.return_value = [acct]
    app.state.account_manager = mock_manager

    mock_service = MagicMock()
    mock_service.get_usage = AsyncMock(return_value=_usage_result())
    mock_service.get_profile = AsyncMock(return_value=_profile_result())

    with patch("kiro.routes_admin._usage_service", mock_service):
        resp = client.get(
            "/admin/accounts/usage",
            headers={"Authorization": f"Bearer {FAKE_KEY}"},
        )

    assert resp.status_code == 200
    assert resp.json()["accounts"][0]["circuit_state"] == "tripped"


def test_usage_stale_on_fetch_error(client, app):
    acct = _make_account("acct1")
    mock_manager = MagicMock()
    mock_manager.get_all_accounts.return_value = [acct]
    app.state.account_manager = mock_manager

    stale = _usage_result()
    stale.stale = True
    mock_service = MagicMock()
    mock_service.get_usage = AsyncMock(return_value=stale)
    mock_service.get_profile = AsyncMock(return_value=_profile_result())

    with patch("kiro.routes_admin._usage_service", mock_service):
        resp = client.get(
            "/admin/accounts/usage",
            headers={"Authorization": f"Bearer {FAKE_KEY}"},
        )

    assert resp.status_code == 200
    assert resp.json()["accounts"][0]["stale"] is True
