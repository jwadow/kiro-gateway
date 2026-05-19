import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from loguru import logger

from kiro.config import PROXY_API_KEY
from kiro.usage_limits import AccountUsageService

router = APIRouter()
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)

_usage_service = AccountUsageService()

CIRCUIT_TRIP_THRESHOLD = 3


def _verify_api_key(authorization: str = Security(api_key_header)) -> bool:
    # timing-safe comparison prevents key-length oracle attacks
    if not hmac.compare_digest(authorization or "", f"Bearer {PROXY_API_KEY}"):
        raise HTTPException(status_code=403, detail="Invalid API key")
    return True


def _circuit_state(failures: int) -> str:
    return "tripped" if failures >= CIRCUIT_TRIP_THRESHOLD else "healthy"


def _safe_account_id(raw_id: str) -> str:
    """Return a display-safe account identifier that does not leak filesystem paths."""
    if raw_id.startswith("refresh_token_"):
        return raw_id
    return "acct_" + hashlib.sha256(raw_id.encode()).hexdigest()[:12]


def _build_usage_summary(usage_raw: Dict[str, Any]) -> Dict[str, Any]:
    sub = usage_raw.get("subscriptionInfo") or {}
    breakdown_list = usage_raw.get("usageBreakdownList") or []
    bd = breakdown_list[0] if breakdown_list else {}
    current = bd.get("currentUsageWithPrecision") or 0.0
    limit = bd.get("usageLimitWithPrecision") or 0.0
    percent = round(current / limit * 100, 2) if limit > 0 else 0.0
    next_reset_ts = bd.get("nextDateReset") or usage_raw.get("nextDateReset")
    next_reset_iso = (
        datetime.fromtimestamp(next_reset_ts, tz=timezone.utc).isoformat()
        if next_reset_ts else None
    )
    overage_cfg = usage_raw.get("overageConfiguration") or {}
    return {
        "subscription_title": sub.get("subscriptionTitle"),
        "subscription_type": sub.get("type"),
        "current_usage": current,
        "usage_limit": limit,
        "percent_used": percent,
        "unit": bd.get("displayName", "Credits"),
        "currency": bd.get("currency"),
        "next_reset_at": next_reset_iso,
        "days_until_reset": usage_raw.get("daysUntilReset"),
        "overage": {
            "charges": bd.get("overageCharges", 0.0),
            "rate": bd.get("overageRate"),
            "cap": bd.get("overageCapWithPrecision"),
            "status": overage_cfg.get("overageStatus"),
        },
    }


def _build_profile_summary(profile_raw: Dict[str, Any]) -> Dict[str, Any]:
    p = profile_raw.get("profile") or {}
    return {
        "arn": p.get("arn"),
        "profile_name": p.get("profileName"),
        "status": p.get("status"),
    }


@router.get("/admin/accounts/usage", dependencies=[Depends(_verify_api_key)])
async def get_accounts_usage(
    request: Request,
    account_id: Optional[str] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Returns usage limits and profile info for all configured Kiro accounts.
    Responses are cached (5 min for usage, 24 h for profile).
    Use ?force_refresh=true to bypass cache (min 30s between forced refreshes).
    Use ?account_id=<safe_id> to filter to a single account.
    """
    manager = getattr(request.app.state, "account_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    all_accounts = manager.get_all_accounts()

    if account_id is not None:
        all_accounts = [a for a in all_accounts if _safe_account_id(a.id) == account_id]
        if not all_accounts:
            raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")

    results: List[Dict[str, Any]] = []
    for account in all_accounts:
        if account.auth_manager is None:
            results.append({
                "account_id": _safe_account_id(account.id),
                "enabled": False,
                "circuit_state": _circuit_state(account.failures),
                "profile": None,
                "usage": None,
                "stale": False,
                "error": "Account not initialized",
            })
            continue

        usage_summary = None
        profile_summary = None
        usage_stale = False
        profile_stale = False
        error: Optional[str] = None

        try:
            usage_result = await _usage_service.get_usage(
                account.id, account.auth_manager, force_refresh=force_refresh
            )
            usage_summary = _build_usage_summary(usage_result.raw)
            usage_stale = usage_result.stale
        except Exception as exc:
            logger.warning(f"Failed to get usage for {account.id}: {exc}")
            error = str(exc)

        try:
            profile_result = await _usage_service.get_profile(account.id, account.auth_manager)
            profile_summary = _build_profile_summary(profile_result.raw)
            profile_stale = profile_result.stale
        except Exception as exc:
            logger.warning(f"Failed to get profile for {account.id}: {exc}")
            if error is None:
                error = str(exc)

        results.append({
            "account_id": _safe_account_id(account.id),
            "enabled": True,
            "circuit_state": _circuit_state(account.failures),
            "stats": {
                "total_requests": account.stats.total_requests,
                "successful_requests": account.stats.successful_requests,
                "failed_requests": account.stats.failed_requests,
            },
            "profile": profile_summary,
            "usage": usage_summary,
            "stale": usage_stale or profile_stale,
            "error": error,
        })

    return {
        "object": "list",
        "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
        "accounts": results,
    }
