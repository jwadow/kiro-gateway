# -*- coding: utf-8 -*-
"""Tests for kiro/usage_limits.py"""

import time
import pytest
from kiro.usage_limits import UsageCache, UsageLimitsResult, ProfileResult


def test_usage_cache_miss_returns_none():
    cache = UsageCache()
    assert cache.get_usage("acct1") is None


def test_usage_cache_hit_returns_value():
    cache = UsageCache()
    result = UsageLimitsResult(raw={}, cached_at=time.time())
    cache.set_usage("acct1", result)
    assert cache.get_usage("acct1") is result


def test_usage_cache_expired_returns_none():
    cache = UsageCache(usage_ttl=0.001)
    result = UsageLimitsResult(raw={}, cached_at=time.time() - 1)
    cache.set_usage("acct1", result)
    assert cache.get_usage("acct1") is None


def test_profile_cache_hit():
    cache = UsageCache()
    p = ProfileResult(raw={}, cached_at=time.time())
    cache.set_profile("acct1", p)
    assert cache.get_profile("acct1") is p


def test_profile_cache_expired_returns_none():
    cache = UsageCache(profile_ttl=0.001)
    p = ProfileResult(raw={}, cached_at=time.time() - 1)
    cache.set_profile("acct1", p)
    assert cache.get_profile("acct1") is None


def test_get_stale_usage_returns_even_if_expired():
    cache = UsageCache(usage_ttl=0.001)
    result = UsageLimitsResult(raw={"x": 1}, cached_at=time.time() - 1)
    cache.set_usage("acct1", result)
    assert cache.get_stale_usage("acct1") is result


def test_get_stale_usage_returns_none_if_never_set():
    cache = UsageCache()
    assert cache.get_stale_usage("acct1") is None


def test_last_usage_fetch_at_zero_if_never_set():
    cache = UsageCache()
    assert cache.last_usage_fetch_at("acct1") == 0.0


def test_last_usage_fetch_at_returns_cached_at():
    cache = UsageCache()
    t = time.time()
    result = UsageLimitsResult(raw={}, cached_at=t)
    cache.set_usage("acct1", result)
    assert cache.last_usage_fetch_at("acct1") == t


# ── Task 3: fetch functions ──────────────────────────────────────────────────

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from kiro.usage_limits import fetch_usage_limits, fetch_profile, AccountUsageService


@pytest.fixture
def mock_auth():
    m = MagicMock()
    m.get_access_token = AsyncMock(return_value="fake-token")
    m.api_host = "https://q.us-east-1.amazonaws.com"
    m.profile_arn = None
    return m


def _mock_response(payload: dict) -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = 200
    r.json.return_value = payload
    return r


@pytest.mark.asyncio
async def test_fetch_usage_limits_success(mock_auth):
    payload = {"usageBreakdownList": [], "subscriptionInfo": {"type": "FREE"}}
    with patch("kiro.usage_limits.KiroHttpClient") as MockClient:
        inst = MockClient.return_value.__aenter__.return_value
        inst.request_with_retry = AsyncMock(return_value=_mock_response(payload))
        result = await fetch_usage_limits(mock_auth)
    assert result.raw == payload
    assert result.stale is False


@pytest.mark.asyncio
async def test_fetch_usage_limits_error_returns_stale(mock_auth):
    with patch("kiro.usage_limits.KiroHttpClient") as MockClient:
        inst = MockClient.return_value.__aenter__.return_value
        inst.request_with_retry = AsyncMock(side_effect=Exception("network error"))
        result = await fetch_usage_limits(mock_auth, stale_fallback={"cached": True})
    assert result.stale is True
    assert result.raw == {"cached": True}


@pytest.mark.asyncio
async def test_fetch_usage_limits_error_reraises_without_fallback(mock_auth):
    with patch("kiro.usage_limits.KiroHttpClient") as MockClient:
        inst = MockClient.return_value.__aenter__.return_value
        inst.request_with_retry = AsyncMock(side_effect=Exception("boom"))
        with pytest.raises(Exception, match="boom"):
            await fetch_usage_limits(mock_auth)


@pytest.mark.asyncio
async def test_fetch_profile_success(mock_auth):
    payload = {"profile": {"arn": "arn:aws:...", "profileName": "test", "status": "ACTIVE"}}
    with patch("kiro.usage_limits.KiroHttpClient") as MockClient:
        inst = MockClient.return_value.__aenter__.return_value
        inst.request_with_retry = AsyncMock(return_value=_mock_response(payload))
        result = await fetch_profile(mock_auth)
    assert result.raw == payload
    assert result.stale is False


# ── Task 4: AccountUsageService ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_service_returns_cached_on_second_call(mock_auth):
    payload = {"usageBreakdownList": [], "subscriptionInfo": {"type": "FREE"}}
    service = AccountUsageService()
    with patch("kiro.usage_limits.KiroHttpClient") as MockClient:
        inst = MockClient.return_value.__aenter__.return_value
        inst.request_with_retry = AsyncMock(return_value=_mock_response(payload))
        r1 = await service.get_usage("acct1", mock_auth)
        r2 = await service.get_usage("acct1", mock_auth)
    assert r1.raw == payload
    assert r2.raw == payload
    assert MockClient.call_count == 1  # only one real call


@pytest.mark.asyncio
async def test_service_force_refresh_respects_min_interval(mock_auth):
    payload = {"usageBreakdownList": []}
    service = AccountUsageService()
    with patch("kiro.usage_limits.KiroHttpClient") as MockClient:
        inst = MockClient.return_value.__aenter__.return_value
        inst.request_with_retry = AsyncMock(return_value=_mock_response(payload))
        await service.get_usage("acct1", mock_auth)
        # Immediately force_refresh — should be blocked by min interval
        await service.get_usage("acct1", mock_auth, force_refresh=True)
    assert MockClient.call_count == 1


@pytest.mark.asyncio
async def test_service_profile_cached(mock_auth):
    payload = {"profile": {"profileName": "p1"}}
    service = AccountUsageService()
    with patch("kiro.usage_limits.KiroHttpClient") as MockClient:
        inst = MockClient.return_value.__aenter__.return_value
        inst.request_with_retry = AsyncMock(return_value=_mock_response(payload))
        p1 = await service.get_profile("acct1", mock_auth)
        p2 = await service.get_profile("acct1", mock_auth)
    assert p1.raw == payload
    assert p2.raw == payload
    assert MockClient.call_count == 1
