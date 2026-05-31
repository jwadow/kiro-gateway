# -*- coding: utf-8 -*-

"""
Unit tests for the admin usage endpoint and usage limits service.

Covers (Issue #159, #144 via PR #160):
- UsageCache TTL + stale fallback behavior
- AccountUsageService caching, force-refresh throttle, and concurrency lock
- /admin/accounts/usage authentication, account-id hashing, and summary shaping
"""

import time
import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from kiro.usage_limits import (
    UsageCache,
    UsageLimitsResult,
    ProfileResult,
    AccountUsageService,
    USAGE_TTL_SECONDS,
)
from kiro.routes_admin import (
    _safe_account_id,
    _circuit_state,
    _build_usage_summary,
    _verify_api_key,
    CIRCUIT_TRIP_THRESHOLD,
)
from kiro.config import PROXY_API_KEY
from fastapi import HTTPException


# ==================================================================================================
# UsageCache
# ==================================================================================================

class TestUsageCache:
    """Tests for the per-account TTL cache."""

    def test_returns_none_on_miss(self):
        cache = UsageCache()
        assert cache.get_usage("acct") is None
        assert cache.get_profile("acct") is None

    def test_returns_fresh_value(self):
        cache = UsageCache()
        result = UsageLimitsResult(raw={"x": 1}, cached_at=time.time())
        cache.set_usage("acct", result)
        assert cache.get_usage("acct") is result

    def test_expired_value_not_returned_but_stale_is(self):
        """
        What it does: A value older than the TTL is not returned by get_usage,
        but remains accessible via get_stale_usage for error fallback.
        Purpose: Stale-on-error behavior must keep the last value around.
        """
        cache = UsageCache(usage_ttl=0.0)
        result = UsageLimitsResult(raw={"x": 1}, cached_at=time.time() - 10)
        cache.set_usage("acct", result)
        assert cache.get_usage("acct") is None
        assert cache.get_stale_usage("acct") is result

    def test_last_usage_fetch_at(self):
        cache = UsageCache()
        assert cache.last_usage_fetch_at("acct") == 0.0
        now = time.time()
        cache.set_usage("acct", UsageLimitsResult(raw={}, cached_at=now))
        assert cache.last_usage_fetch_at("acct") == now


# ==================================================================================================
# AccountUsageService
# ==================================================================================================

class TestAccountUsageService:
    """Tests for cache + concurrency coordination."""

    @pytest.mark.asyncio
    async def test_get_usage_caches_result(self):
        """
        What it does: A successful fetch is cached; a second call does not refetch.
        Purpose: Avoid hammering the Kiro API for every admin poll.
        """
        service = AccountUsageService()
        auth = Mock()

        fake = UsageLimitsResult(raw={"usageBreakdownList": []}, cached_at=time.time())
        with patch("kiro.usage_limits.fetch_usage_limits", AsyncMock(return_value=fake)) as mock_fetch:
            first = await service.get_usage("acct", auth)
            second = await service.get_usage("acct", auth)

        assert first is fake
        assert second is fake
        assert mock_fetch.await_count == 1, "Second call must hit the cache, not refetch"

    @pytest.mark.asyncio
    async def test_stale_result_not_cached(self):
        """
        What it does: A stale (error-fallback) result is returned but NOT cached.
        Purpose: Ensure the service retries on the next call after a failure.
        """
        service = AccountUsageService()
        auth = Mock()

        stale = UsageLimitsResult(raw={}, cached_at=time.time(), stale=True)
        with patch("kiro.usage_limits.fetch_usage_limits", AsyncMock(return_value=stale)) as mock_fetch:
            await service.get_usage("acct", auth)
            await service.get_usage("acct", auth)

        assert mock_fetch.await_count == 2, "Stale results must not be cached"

    @pytest.mark.asyncio
    async def test_force_refresh_throttled(self):
        """
        What it does: A forced refresh within the min interval returns the stale
        cached value instead of refetching.
        Purpose: Prevent abuse of ?force_refresh=true.
        """
        service = AccountUsageService()
        auth = Mock()

        first = UsageLimitsResult(raw={"n": 1}, cached_at=time.time())
        with patch("kiro.usage_limits.fetch_usage_limits", AsyncMock(return_value=first)) as mock_fetch:
            await service.get_usage("acct", auth)
            # Immediate forced refresh should be throttled (returns stale, no refetch).
            result = await service.get_usage("acct", auth, force_refresh=True)

        assert result is first
        assert mock_fetch.await_count == 1, "Forced refresh within interval must be throttled"

    @pytest.mark.asyncio
    async def test_get_profile_caches_result(self):
        service = AccountUsageService()
        auth = Mock()
        fake = ProfileResult(raw={"profile": {"arn": "a"}}, cached_at=time.time())
        with patch("kiro.usage_limits.fetch_profile", AsyncMock(return_value=fake)) as mock_fetch:
            first = await service.get_profile("acct", auth)
            second = await service.get_profile("acct", auth)
        assert first is fake and second is fake
        assert mock_fetch.await_count == 1


# ==================================================================================================
# Admin route helpers
# ==================================================================================================

class TestAdminHelpers:
    """Tests for admin route helper functions."""

    def test_safe_account_id_hashes_paths(self):
        """
        What it does: Non-refresh-token IDs (file paths) are hashed to acct_*.
        Purpose: Avoid leaking filesystem paths in the admin response.
        """
        raw = "/home/user/.aws/sso/cache/secret-token.json"
        safe = _safe_account_id(raw)
        assert safe.startswith("acct_")
        assert "/home/user" not in safe
        assert raw not in safe
        # Deterministic.
        assert _safe_account_id(raw) == safe

    def test_safe_account_id_preserves_refresh_token_ids(self):
        assert _safe_account_id("refresh_token_abc123") == "refresh_token_abc123"

    def test_circuit_state_threshold(self):
        assert _circuit_state(0) == "healthy"
        assert _circuit_state(CIRCUIT_TRIP_THRESHOLD - 1) == "healthy"
        assert _circuit_state(CIRCUIT_TRIP_THRESHOLD) == "tripped"
        assert _circuit_state(CIRCUIT_TRIP_THRESHOLD + 5) == "tripped"

    def test_build_usage_summary_computes_percent(self):
        """
        What it does: Builds a usage summary with a computed percent_used.
        Purpose: Verify percentage math and field mapping.
        """
        raw = {
            "subscriptionInfo": {"subscriptionTitle": "Pro", "type": "paid"},
            "usageBreakdownList": [{
                "currentUsageWithPrecision": 25.0,
                "usageLimitWithPrecision": 100.0,
                "displayName": "Credits",
                "currency": "USD",
            }],
            "daysUntilReset": 5,
        }
        summary = _build_usage_summary(raw)
        assert summary["current_usage"] == 25.0
        assert summary["usage_limit"] == 100.0
        assert summary["percent_used"] == 25.0
        assert summary["subscription_title"] == "Pro"
        assert summary["days_until_reset"] == 5

    def test_build_usage_summary_zero_limit_no_div_by_zero(self):
        """
        What it does: A zero usage limit yields 0.0 percent, not a ZeroDivisionError.
        Purpose: Guard the percentage math against unlimited/zero-limit plans.
        """
        raw = {"usageBreakdownList": [{"currentUsageWithPrecision": 5.0, "usageLimitWithPrecision": 0.0}]}
        summary = _build_usage_summary(raw)
        assert summary["percent_used"] == 0.0


# ==================================================================================================
# Admin auth dependency
# ==================================================================================================

class TestAdminAuth:
    """Tests for the timing-safe admin auth dependency."""

    def test_valid_bearer_passes(self):
        assert _verify_api_key(f"Bearer {PROXY_API_KEY}") is True

    def test_missing_header_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            _verify_api_key(None)
        assert exc_info.value.status_code == 403

    def test_wrong_key_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            _verify_api_key("Bearer wrong-key")
        assert exc_info.value.status_code == 403
