# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Subscription usage endpoint.

Exposes the Kiro account's quota (credits used / remaining, plan name, reset
date) so provider dashboards such as cc-switch can display it.

Kiro's getUsageLimits operation is only served by the legacy Q hosts; the
runtime.kiro.dev host used for inference answers it with
UnknownOperationException, so this module targets the Q hosts directly.
"""

from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger

from kiro.routes_openai import verify_api_key

router = APIRouter()

# Tried in order; the second host is a fallback for accounts whose quota is
# only reachable through the CodeWhisperer alias.
USAGE_HOST_TEMPLATES = (
    "https://q.{region}.amazonaws.com",
    "https://codewhisperer.{region}.amazonaws.com",
)

USAGE_TIMEOUT = 10.0

# Enterprise IdC accounts reject getUsageLimits when profileArn is present,
# while it is optional for every other account type, so it is never sent.
USAGE_PARAMS = {"origin": "AI_EDITOR", "resourceType": "AGENTIC_REQUEST"}


async def fetch_usage_limits(token: str, region: str) -> Dict[str, Any]:
    """
    Fetch raw getUsageLimits payload for an access token.

    Args:
        token: Valid Kiro access token
        region: AWS region of the account

    Returns:
        Parsed getUsageLimits response

    Raises:
        HTTPException: If every host fails
    """
    last_error: Optional[str] = None
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=USAGE_TIMEOUT) as client:
        for template in USAGE_HOST_TEMPLATES:
            url = f"{template.format(region=region)}/getUsageLimits"
            try:
                response = await client.get(url, params=USAGE_PARAMS, headers=headers)
            except httpx.HTTPError as e:
                last_error = f"{url}: {e}"
                logger.debug(f"getUsageLimits request failed: {last_error}")
                continue

            if response.status_code == 200:
                return response.json()

            last_error = f"{url}: HTTP {response.status_code} {response.text[:200]}"
            logger.debug(f"getUsageLimits rejected: {last_error}")

    raise HTTPException(status_code=502, detail=f"getUsageLimits failed: {last_error}")


def build_usage_summary(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten a getUsageLimits payload into a summary of the primary quota.

    Kiro returns a list of quota buckets; the first one is the subscription's
    main credit allowance, which is what dashboards display.

    Args:
        data: Raw getUsageLimits response

    Returns:
        Summary dict, with the untouched payload under "raw"
    """
    subscription = data.get("subscriptionInfo") or {}
    breakdowns = data.get("usageBreakdownList") or []
    primary = breakdowns[0] if breakdowns else {}

    used = primary.get("currentUsageWithPrecision") or primary.get("currentUsage") or 0
    total = primary.get("usageLimitWithPrecision") or primary.get("usageLimit") or 0
    remaining = max(0.0, float(total) - float(used))

    return {
        "isValid": True,
        "planName": subscription.get("subscriptionTitle") or "Kiro",
        "subscriptionType": subscription.get("type"),
        "used": round(float(used), 1),
        "total": total,
        "remaining": round(remaining, 1),
        "unit": primary.get("displayNamePlural") or "credits",
        "overageCap": primary.get("overageCapWithPrecision") or primary.get("overageCap"),
        "overageRate": primary.get("overageRate"),
        "daysUntilReset": data.get("daysUntilReset"),
        "nextDateReset": data.get("nextDateReset"),
        "userId": (data.get("userInfo") or {}).get("userId"),
        "raw": data,
    }


@router.get("/v1/usage", dependencies=[Depends(verify_api_key)])
async def get_usage(request: Request) -> Dict[str, Any]:
    """
    Return subscription quota for the first initialized account.

    Args:
        request: FastAPI Request for accessing app.state

    Returns:
        Usage summary for the account
    """
    logger.info("Request to /v1/usage")

    account = request.app.state.account_manager.get_first_account()
    if not account or not account.auth_manager:
        raise HTTPException(status_code=503, detail="No initialized account available")

    token = await account.auth_manager.get_access_token()
    data = await fetch_usage_limits(token, account.auth_manager.region)

    return build_usage_summary(data)
