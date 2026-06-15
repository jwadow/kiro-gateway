# -*- coding: utf-8 -*-

"""
Unit tests for profile_resolver module.

Tests the shared Profile_Resolver rule used by both API surfaces (OpenAI and
Anthropic) and both request modes (streaming and non-streaming) to determine
the effective profileArn:

- Auth manager profileArn takes precedence when non-empty
- PROFILE_ARN config is used as a fallback
- Empty result is returned (and signals missing profileArn) when neither is set
- Whitespace-only values are treated as missing
"""

import pytest
from unittest.mock import patch, MagicMock

from kiro.profile_resolver import resolve_profile_arn, is_valid_profile_arn


class _Auth:
    """Minimal stand-in for an auth manager exposing profile_arn."""

    def __init__(self, profile_arn):
        self.profile_arn = profile_arn


class TestResolveProfileArnSuccess:
    """Tests for successful profileArn resolution."""

    def test_returns_auth_manager_arn_when_present(self):
        """
        What it does: Returns the auth manager profileArn when it is non-empty.
        Purpose: Requirement 3.1 - auth manager value takes precedence.
        """
        print("Setup: auth manager with a profile ARN...")
        auth = _Auth("arn:aws:codewhisperer:us-east-1:111:profile/auth")

        print("Action: resolving profile ARN...")
        with patch("kiro.profile_resolver.PROFILE_ARN", "arn:config:fallback"):
            result = resolve_profile_arn(auth)

        print(f"Result: {result}")
        assert result == "arn:aws:codewhisperer:us-east-1:111:profile/auth"

    def test_falls_back_to_config_when_auth_empty(self):
        """
        What it does: Uses PROFILE_ARN when auth manager profileArn is empty.
        Purpose: Requirement 3.2 - config fallback.
        """
        print("Setup: empty auth manager ARN, config ARN set...")
        auth = _Auth("")

        print("Action: resolving profile ARN...")
        with patch("kiro.profile_resolver.PROFILE_ARN", "arn:config:fallback"):
            result = resolve_profile_arn(auth)

        print(f"Result: {result}")
        assert result == "arn:config:fallback"

    def test_falls_back_to_config_when_auth_none(self):
        """
        What it does: Uses PROFILE_ARN when auth manager profileArn is None.
        Purpose: Ensure None auth value is handled like empty.
        """
        print("Setup: None auth manager ARN, config ARN set...")
        auth = _Auth(None)

        print("Action: resolving profile ARN...")
        with patch("kiro.profile_resolver.PROFILE_ARN", "arn:config:fallback"):
            result = resolve_profile_arn(auth)

        print(f"Result: {result}")
        assert result == "arn:config:fallback"


class TestResolveProfileArnMissing:
    """Tests for the empty/missing result path."""

    def test_returns_empty_when_both_missing(self):
        """
        What it does: Returns empty string when neither source provides a value.
        Purpose: Requirement 3.3 - empty result signals missing profileArn.
        """
        print("Setup: empty auth ARN, empty config...")
        auth = _Auth("")

        print("Action: resolving profile ARN...")
        with patch("kiro.profile_resolver.PROFILE_ARN", ""):
            result = resolve_profile_arn(auth)

        print(f"Result: {result!r}")
        assert result == ""

    def test_returns_empty_when_auth_missing_attr(self):
        """
        What it does: Handles an auth manager without a profile_arn attribute.
        Purpose: Defensive - getattr default must not raise.
        """
        print("Setup: auth manager missing profile_arn attribute...")
        auth = MagicMock(spec=[])  # no attributes

        print("Action: resolving profile ARN...")
        with patch("kiro.profile_resolver.PROFILE_ARN", ""):
            result = resolve_profile_arn(auth)

        print(f"Result: {result!r}")
        assert result == ""


class TestResolveProfileArnEdgeCases:
    """Paranoid edge-case checks."""

    def test_whitespace_only_auth_arn_treated_as_missing(self):
        """
        What it does: A whitespace-only auth ARN falls back to config.
        Purpose: Ensure whitespace is not mistaken for a real ARN.
        """
        print("Setup: whitespace auth ARN, config ARN set...")
        auth = _Auth("   ")

        print("Action: resolving profile ARN...")
        with patch("kiro.profile_resolver.PROFILE_ARN", "arn:config:fallback"):
            result = resolve_profile_arn(auth)

        print(f"Result: {result!r}")
        assert result == "arn:config:fallback"

    def test_whitespace_only_everywhere_returns_empty(self):
        """
        What it does: Whitespace in both sources yields an empty result.
        Purpose: Requirement 3.3 - whitespace-only must signal missing.
        """
        print("Setup: whitespace auth ARN and whitespace config...")
        auth = _Auth("  ")

        print("Action: resolving profile ARN...")
        with patch("kiro.profile_resolver.PROFILE_ARN", "   "):
            result = resolve_profile_arn(auth)

        print(f"Result: {result!r}")
        assert result == ""

    def test_auth_arn_is_stripped(self):
        """
        What it does: Surrounding whitespace on the auth ARN is stripped.
        Purpose: Ensure a clean value is passed downstream.
        """
        print("Setup: auth ARN with surrounding whitespace...")
        auth = _Auth("  arn:aws:profile/x  ")

        print("Action: resolving profile ARN...")
        with patch("kiro.profile_resolver.PROFILE_ARN", ""):
            result = resolve_profile_arn(auth)

        print(f"Result: {result!r}")
        assert result == "arn:aws:profile/x"


class TestIsValidProfileArn:
    """
    Tests for is_valid_profile_arn.

    The validator must reject the documentation placeholder
    (arn:aws:codewhisperer:us-east-1:...) and other malformed values while
    accepting real CodeWhisperer profile ARNs.
    """

    def test_accepts_valid_arn(self):
        """
        What it does: Accepts a well-formed CodeWhisperer profile ARN.
        Purpose: Ensure real ARNs pass validation.
        """
        print("Setup: valid ARN...")
        arn = "arn:aws:codewhisperer:us-east-1:123456789012:profile/EHGA3GRVQMUK"

        print("Action: validating...")
        assert is_valid_profile_arn(arn) is True

    def test_accepts_other_regions(self):
        """
        What it does: Accepts ARNs from non us-east-1 regions.
        Purpose: Region segment must be flexible.
        """
        print("Setup: eu-central-1 ARN...")
        arn = "arn:aws:codewhisperer:eu-central-1:123456789012:profile/ABC123"

        print("Action: validating...")
        assert is_valid_profile_arn(arn) is True

    def test_rejects_dots_placeholder(self):
        """
        What it does: Rejects the literal '...' placeholder.
        Purpose: Root-cause guard for the REQUEST_BODY_INVALID confusion.
        """
        print("Setup: placeholder ARN...")
        arn = "arn:aws:codewhisperer:us-east-1:..."

        print("Action: validating...")
        assert is_valid_profile_arn(arn) is False

    def test_rejects_empty(self):
        """
        What it does: Rejects empty string.
        Purpose: Empty is missing, not malformed - but still not valid.
        """
        print("Action: validating empty...")
        assert is_valid_profile_arn("") is False

    def test_rejects_non_arn(self):
        """
        What it does: Rejects an unrelated string.
        Purpose: Guard against garbage values.
        """
        print("Action: validating 'auto'...")
        assert is_valid_profile_arn("auto") is False

    def test_rejects_short_account_id(self):
        """
        What it does: Rejects an account id that is non-numeric (placeholder-like).
        Purpose: The account-id segment must be digits, catching '...'.
        """
        print("Action: validating non-numeric account id...")
        assert is_valid_profile_arn("arn:aws:codewhisperer:us-east-1:ab12:profile/x") is False

    def test_rejects_missing_profile_segment(self):
        """
        What it does: Rejects an ARN without the profile/<id> segment.
        Purpose: The profile path is required.
        """
        print("Action: validating ARN missing profile segment...")
        assert is_valid_profile_arn("arn:aws:codewhisperer:us-east-1:123456789012:") is False

    def test_strips_surrounding_whitespace(self):
        """
        What it does: Accepts a valid ARN with surrounding whitespace.
        Purpose: Be lenient about stray whitespace from config files.
        """
        print("Action: validating padded ARN...")
        arn = "  arn:aws:codewhisperer:us-east-1:123456789012:profile/ABC  "
        assert is_valid_profile_arn(arn) is True
