# -*- coding: utf-8 -*-

"""
Profile ARN selection for Kiro runtime payloads.

Since the migration to runtime.kiro.dev (upstream commits 07d24fc, 90d0509),
profileArn is required for ALL auth types — Kiro Desktop, kiro-cli AWS SSO
OIDC, and Enterprise Kiro IDE. The previous gating that stripped profileArn
for plain SSO OIDC requests applied only to the legacy q.amazonaws.com
endpoint and now causes 400 "profileArn is required" errors against runtime.

Falls back to the PROFILE_ARN environment variable if the auth manager has no
profile ARN of its own.
"""

from typing import Optional, Protocol

from kiro.auth import AuthType
from kiro.config import PROFILE_ARN


class ProfileArnCarrier(Protocol):
    """Auth object fields needed to resolve the profileArn for a payload."""

    @property
    def auth_type(self) -> AuthType:
        """Authentication type used by the account."""
        ...

    @property
    def profile_arn(self) -> Optional[str]:
        """AWS CodeWhisperer profile ARN if available."""
        ...


def profile_arn_for_payload(auth_manager: ProfileArnCarrier) -> str:
    """
    Return the profileArn that should be sent to runtime.kiro.dev.

    Args:
        auth_manager: Auth manager for the selected account.

    Returns:
        The auth manager's profile ARN, falling back to the PROFILE_ARN env
        variable, or an empty string if neither is available.
    """
    return auth_manager.profile_arn or PROFILE_ARN or ""
