import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from loguru import logger
from kiro.http_client import KiroHttpClient

USAGE_TTL_SECONDS: float = 300.0        # 5 minutes
PROFILE_TTL_SECONDS: float = 86400.0    # 24 hours
FORCE_REFRESH_MIN_INTERVAL: float = 30.0  # prevent abuse


@dataclass
class UsageLimitsResult:
    raw: Dict[str, Any]
    cached_at: float
    stale: bool = False


@dataclass
class ProfileResult:
    raw: Dict[str, Any]
    cached_at: float
    stale: bool = False


@dataclass
class _CacheEntry:
    value: Any
    cached_at: float


class UsageCache:
    """Per-account TTL cache for GetUsageLimits and GetProfile responses."""

    def __init__(
        self,
        usage_ttl: float = USAGE_TTL_SECONDS,
        profile_ttl: float = PROFILE_TTL_SECONDS,
    ) -> None:
        self._usage_ttl = usage_ttl
        self._profile_ttl = profile_ttl
        self._usage: Dict[str, _CacheEntry] = {}
        self._profile: Dict[str, _CacheEntry] = {}

    def get_usage(self, account_id: str) -> Optional[UsageLimitsResult]:
        entry = self._usage.get(account_id)
        if entry is None:
            return None
        if time.time() - entry.cached_at > self._usage_ttl:
            return None
        return entry.value

    def set_usage(self, account_id: str, result: UsageLimitsResult) -> None:
        self._usage[account_id] = _CacheEntry(value=result, cached_at=result.cached_at)

    def get_stale_usage(self, account_id: str) -> Optional[UsageLimitsResult]:
        """Return cached value even if expired (for fallback on error)."""
        entry = self._usage.get(account_id)
        return entry.value if entry else None

    def get_profile(self, account_id: str) -> Optional[ProfileResult]:
        entry = self._profile.get(account_id)
        if entry is None:
            return None
        if time.time() - entry.cached_at > self._profile_ttl:
            return None
        return entry.value

    def set_profile(self, account_id: str, result: ProfileResult) -> None:
        self._profile[account_id] = _CacheEntry(value=result, cached_at=result.cached_at)

    def get_stale_profile(self, account_id: str) -> Optional[ProfileResult]:
        entry = self._profile.get(account_id)
        return entry.value if entry else None

    def last_usage_fetch_at(self, account_id: str) -> float:
        entry = self._usage.get(account_id)
        return entry.cached_at if entry else 0.0


async def fetch_usage_limits(
    auth_manager: Any,
    stale_fallback: Optional[Dict[str, Any]] = None,
) -> UsageLimitsResult:
    """
    Call GET /getUsageLimits on the Kiro Q API.
    On any exception, returns a stale result if fallback provided, else re-raises.
    """
    url = f"{auth_manager.api_host}/getUsageLimits"
    params: Dict[str, str] = {}
    if auth_manager.profile_arn:
        params["profileArn"] = auth_manager.profile_arn

    try:
        async with KiroHttpClient(auth_manager, shared_client=None) as http_client:
            response = await http_client.request_with_retry(
                method="GET", url=url, params=params or None
            )
        raw = response.json()
        return UsageLimitsResult(raw=raw, cached_at=time.time())
    except Exception as exc:
        if stale_fallback is not None:
            logger.warning(f"GetUsageLimits failed, returning stale cache: {exc}")
            return UsageLimitsResult(raw=stale_fallback, cached_at=time.time(), stale=True)
        raise


async def fetch_profile(
    auth_manager: Any,
    stale_fallback: Optional[Dict[str, Any]] = None,
) -> ProfileResult:
    """
    Call POST /GetProfile on the Kiro Q API.
    On any exception, returns a stale result if fallback provided, else re-raises.
    """
    url = f"{auth_manager.api_host}/GetProfile"
    body: Dict[str, Any] = {}
    if auth_manager.profile_arn:
        body["profileArn"] = auth_manager.profile_arn

    try:
        async with KiroHttpClient(auth_manager, shared_client=None) as http_client:
            response = await http_client.request_with_retry(
                method="POST", url=url, json_data=body
            )
        raw = response.json()
        return ProfileResult(raw=raw, cached_at=time.time())
    except Exception as exc:
        if stale_fallback is not None:
            logger.warning(f"GetProfile failed, returning stale cache: {exc}")
            return ProfileResult(raw=stale_fallback, cached_at=time.time(), stale=True)
        raise


class AccountUsageService:
    """
    Coordinates cache + concurrency for per-account Kiro API calls.
    One asyncio.Lock per account prevents thundering-herd on cache miss.
    """

    def __init__(self) -> None:
        self._cache = UsageCache()
        self._usage_locks: Dict[str, asyncio.Lock] = {}
        self._profile_locks: Dict[str, asyncio.Lock] = {}

    def _usage_lock(self, account_id: str) -> asyncio.Lock:
        if account_id not in self._usage_locks:
            self._usage_locks[account_id] = asyncio.Lock()
        return self._usage_locks[account_id]

    def _profile_lock(self, account_id: str) -> asyncio.Lock:
        if account_id not in self._profile_locks:
            self._profile_locks[account_id] = asyncio.Lock()
        return self._profile_locks[account_id]

    async def get_usage(
        self,
        account_id: str,
        auth_manager: Any,
        force_refresh: bool = False,
    ) -> UsageLimitsResult:
        async with self._usage_lock(account_id):
            cached = self._cache.get_usage(account_id)
            if cached is not None and not force_refresh:
                return cached
            if force_refresh:
                last = self._cache.last_usage_fetch_at(account_id)
                if time.time() - last < FORCE_REFRESH_MIN_INTERVAL:
                    stale = self._cache.get_stale_usage(account_id)
                    if stale:
                        return stale
            stale_raw = None
            stale_entry = self._cache.get_stale_usage(account_id)
            if stale_entry:
                stale_raw = stale_entry.raw
            result = await fetch_usage_limits(auth_manager, stale_fallback=stale_raw)
            if not result.stale:
                self._cache.set_usage(account_id, result)
            return result

    async def get_profile(
        self,
        account_id: str,
        auth_manager: Any,
    ) -> ProfileResult:
        async with self._profile_lock(account_id):
            cached = self._cache.get_profile(account_id)
            if cached is not None:
                return cached
            stale_raw = None
            stale_entry = self._cache.get_stale_profile(account_id)
            if stale_entry:
                stale_raw = stale_entry.raw
            result = await fetch_profile(auth_manager, stale_fallback=stale_raw)
            self._cache.set_profile(account_id, result)
            return result
