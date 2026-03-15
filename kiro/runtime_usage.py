"""
Usage limit helpers for CodeWhisperer Runtime endpoints.

This module keeps usage/plan retrieval separate from route handlers so
additional runtime billing endpoints can reuse the same request flow.
"""

import json
from typing import Any, Optional

import httpx
from fastapi import HTTPException
from loguru import logger

from kiro.auth import AuthType, KiroAuthManager
from kiro.http_client import KiroHttpClient

DEFAULT_USAGE_ORIGIN = "AI_EDITOR"
DEFAULT_USAGE_RESOURCE_TYPE = "AGENTIC_REQUEST"


def build_usage_limits_params(
    auth_manager: KiroAuthManager,
    origin: str = DEFAULT_USAGE_ORIGIN,
    resource_type: str = DEFAULT_USAGE_RESOURCE_TYPE,
    is_email_required: bool = True,
) -> dict[str, str]:
    """
    Build query parameters for CodeWhisperer Runtime GetUsageLimits.

    Args:
        auth_manager: Authentication manager with auth type and optional profile ARN
        origin: Request origin expected by CodeWhisperer Runtime
        resource_type: Resource type to query usage for
        is_email_required: Whether upstream should include user email in the response

    Returns:
        Query parameters for the `/getUsageLimits` runtime endpoint

    Raises:
        ValueError: If origin or resource_type is empty
    """
    if not origin:
        raise ValueError("origin must not be empty")
    if not resource_type:
        raise ValueError("resource_type must not be empty")

    params = {
        "origin": origin,
        "resourceType": resource_type,
        "isEmailRequired": str(is_email_required).lower(),
    }

    if auth_manager.auth_type == AuthType.KIRO_DESKTOP and auth_manager.profile_arn:
        params["profileArn"] = auth_manager.profile_arn

    return params


def _extract_usage_error_message(response: httpx.Response) -> str:
    """
    Extract a readable error message from an upstream usage response.

    Args:
        response: HTTP response returned by the runtime API

    Returns:
        Best-effort human-readable error message
    """
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return response.text or "Unknown upstream error"

    if isinstance(payload, dict):
        if isinstance(payload.get("Output"), dict):
            nested_message = payload["Output"].get("message")
            if isinstance(nested_message, str) and nested_message:
                return nested_message

        for key in ("message", "Message", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value

    return response.text or "Unknown upstream error"


async def fetch_usage_limits(
    auth_manager: KiroAuthManager,
    shared_client: Optional[httpx.AsyncClient],
    origin: str = DEFAULT_USAGE_ORIGIN,
    resource_type: str = DEFAULT_USAGE_RESOURCE_TYPE,
    is_email_required: bool = True,
) -> dict[str, Any]:
    """
    Fetch current usage limits from CodeWhisperer Runtime.

    Args:
        auth_manager: Authentication manager for token refresh and profile selection
        shared_client: Shared HTTP client from app state
        origin: Request origin expected by upstream
        resource_type: Usage bucket to query
        is_email_required: Whether upstream should include user email

    Returns:
        Parsed upstream JSON response

    Raises:
        HTTPException: If upstream returns an error or invalid JSON
        ValueError: If the request parameters are invalid
    """
    params = build_usage_limits_params(
        auth_manager=auth_manager,
        origin=origin,
        resource_type=resource_type,
        is_email_required=is_email_required,
    )
    url = f"{auth_manager.q_host}/getUsageLimits"

    logger.info(
        "Fetching usage limits from CodeWhisperer Runtime "
        f"(origin={origin}, resource_type={resource_type}, include_email={is_email_required})"
    )

    async with KiroHttpClient(auth_manager, shared_client=shared_client) as http_client:
        response = await http_client.request_with_retry(
            "GET",
            url,
            params=params,
        )

    if response.status_code != 200:
        error_message = _extract_usage_error_message(response)
        logger.error(
            f"GetUsageLimits failed: status={response.status_code}, message={error_message}"
        )
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Failed to fetch usage limits: {error_message}",
        )

    try:
        return response.json()
    except json.JSONDecodeError as exc:
        logger.error(f"GetUsageLimits returned invalid JSON: {exc}")
        raise HTTPException(
            status_code=502,
            detail="Kiro usage endpoint returned invalid JSON.",
        ) from exc
