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
Profile ARN resolution for Kiro API requests.

The Kiro runtime (``runtime.kiro.dev``) requires a ``profileArn`` on every
``generateAssistantResponse`` request. When it is missing, the upstream API
rejects the request with an opaque HTTP 400 ("profileArn is required for this
request.") that is not actionable for the user.

This module centralizes the single rule used by BOTH API surfaces (OpenAI and
Anthropic) and BOTH request modes (streaming and non-streaming) for resolving
the effective profile ARN, so behaviour is identical everywhere. Routes call
:func:`resolve_profile_arn` and, when it yields an empty result, return the
``Missing_Profile_Error`` instead of contacting the Kiro API.
"""

from typing import Any
import re

from loguru import logger

from kiro.config import PROFILE_ARN


# Strict-enough shape for a CodeWhisperer profile ARN:
#   arn:aws:codewhisperer:<region>:<aws-account-id>:profile/<profile-id>
# - region: lowercase letters, digits, hyphens (e.g. us-east-1)
# - account id: one or more digits (real AWS account IDs are 12 digits, but we
#   only require "all digits, non-empty" to avoid rejecting legitimate-but-
#   unusual setups while still catching the "..." placeholder, whose account-id
#   segment is non-numeric)
# - profile id: non-empty token of allowed identifier characters
#
# This intentionally rejects the documentation placeholder
# "arn:aws:codewhisperer:us-east-1:..." whose account-id segment is "..".
_PROFILE_ARN_PATTERN = re.compile(
    r"^arn:aws:codewhisperer:[a-z0-9-]+:\d+:profile/[A-Za-z0-9._-]+$"
)


def is_valid_profile_arn(profile_arn: str) -> bool:
    """
    Check whether a string is a structurally valid CodeWhisperer profile ARN.

    This does NOT verify the ARN exists or is authorized — it only catches
    obviously malformed values (most importantly the ``...`` placeholder) so
    the Gateway can surface an actionable error instead of the opaque upstream
    ``REQUEST_BODY_INVALID``.

    Args:
        profile_arn: The candidate ARN string.

    Returns:
        True if the value matches the expected ARN shape, False otherwise.

    Examples:
        >>> is_valid_profile_arn("arn:aws:codewhisperer:us-east-1:123456789012:profile/ABCDEF123456")
        True
        >>> is_valid_profile_arn("arn:aws:codewhisperer:us-east-1:...")
        False
        >>> is_valid_profile_arn("")
        False
    """
    if not profile_arn or not isinstance(profile_arn, str):
        return False
    return bool(_PROFILE_ARN_PATTERN.match(profile_arn.strip()))


def resolve_profile_arn(auth_manager: Any) -> str:
    """
    Resolve the effective profileArn from the auth manager and configuration.

    Resolution rule (single source of truth for both APIs and both modes):

    1. If the auth manager provides a non-empty ``profile_arn``, use it.
    2. Otherwise, if the ``PROFILE_ARN`` configuration value is non-empty,
       use it.
    3. Otherwise, return an empty string, signalling that no profileArn could
       be resolved.

    The returned value is stripped of surrounding whitespace so that a value
    consisting only of spaces is treated as missing.

    Args:
        auth_manager: The account's auth manager. Expected to expose a
            ``profile_arn`` attribute (may be ``None`` or empty).

    Returns:
        The resolved profile ARN, or an empty string when none is available.

    Examples:
        >>> class _Auth:
        ...     profile_arn = "arn:aws:codewhisperer:us-east-1:123:profile/abc"
        >>> resolve_profile_arn(_Auth())
        'arn:aws:codewhisperer:us-east-1:123:profile/abc'
    """
    auth_profile_arn = getattr(auth_manager, "profile_arn", None) or ""
    if isinstance(auth_profile_arn, str):
        auth_profile_arn = auth_profile_arn.strip()

    if auth_profile_arn:
        return auth_profile_arn

    config_profile_arn = (PROFILE_ARN or "").strip()
    if config_profile_arn:
        return config_profile_arn

    logger.debug(
        "Profile resolver found no profileArn (auth manager empty and "
        "PROFILE_ARN unset)"
    )
    return ""
