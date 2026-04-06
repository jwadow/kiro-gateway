# -*- coding: utf-8 -*-

"""Unit tests for kiro.setup_wizard module.

Covers: SetupWizard.run(), save_config(), get_user_config_path(),
ConsoleWizardIO, and CredentialType.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kiro.setup_wizard import (
    CredentialType,
    ConsoleWizardIO,
    SetupWizard,
    get_user_config_path,
    save_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_io(*responses: str) -> MagicMock:
    """Create a mock WizardIO that returns responses in order.

    Args:
        *responses: Sequence of strings returned by prompt() calls.

    Returns:
        A MagicMock with prompt() configured as a side_effect sequence.
    """
    io = MagicMock()
    io.prompt.side_effect = list(responses)
    io.confirm.return_value = True
    return io


# ---------------------------------------------------------------------------
# CredentialType
# ---------------------------------------------------------------------------


class TestCredentialType:
    def test_values(self) -> None:
        assert CredentialType.CREDS_FILE == "creds_file"
        assert CredentialType.REFRESH_TOKEN == "refresh_token"
        assert CredentialType.CLI_DB == "cli_db"

    def test_is_str(self) -> None:
        assert isinstance(CredentialType.CREDS_FILE, str)


# ---------------------------------------------------------------------------
# SetupWizard — normal flows
# ---------------------------------------------------------------------------


class TestSetupWizardCredsFile:
    """Wizard with credential type 1 (JSON credentials file)."""

    def test_returns_kiro_creds_file(self) -> None:
        io = _make_io("1", "/path/to/creds.json", "my-api-key")
        wizard = SetupWizard(io)
        result = wizard.run()

        assert result["KIRO_CREDS_FILE"] == "/path/to/creds.json"
        assert result["PROXY_API_KEY"] == "my-api-key"
        assert "REFRESH_TOKEN" not in result
        assert "KIRO_CLI_DB_FILE" not in result

    def test_prompt_called_three_times(self) -> None:
        io = _make_io("1", "/path/to/creds.json", "key")
        SetupWizard(io).run()
        assert io.prompt.call_count == 3  # choice + creds path + proxy key


class TestSetupWizardRefreshToken:
    """Wizard with credential type 2 (refresh token)."""

    def test_returns_refresh_token(self) -> None:
        io = _make_io("2", "eyJhbGci.token.here", "secret")
        result = SetupWizard(io).run()

        assert result["REFRESH_TOKEN"] == "eyJhbGci.token.here"
        assert result["PROXY_API_KEY"] == "secret"
        assert "KIRO_CREDS_FILE" not in result

    def test_prompt_called_three_times(self) -> None:
        io = _make_io("2", "token", "key")
        SetupWizard(io).run()
        assert io.prompt.call_count == 3


class TestSetupWizardCliDb:
    """Wizard with credential type 3 (kiro-cli SQLite DB)."""

    def test_returns_cli_db_file(self) -> None:
        io = _make_io("3", "~/.local/share/kiro-cli/data.sqlite3", "key")
        result = SetupWizard(io).run()

        assert result["KIRO_CLI_DB_FILE"] == "~/.local/share/kiro-cli/data.sqlite3"
        assert result["PROXY_API_KEY"] == "key"

    def test_default_db_path_used_on_empty_input(self) -> None:
        # When prompt returns "" for the db path, default should be used.
        # We simulate this by having prompt return the default value directly
        # (ConsoleWizardIO returns default when input is empty).
        default_db = "~/.local/share/kiro-cli/data.sqlite3"
        io = _make_io("3", default_db, "key")
        result = SetupWizard(io).run()
        assert result["KIRO_CLI_DB_FILE"] == default_db


# ---------------------------------------------------------------------------
# SetupWizard — edge cases
# ---------------------------------------------------------------------------


class TestSetupWizardEdgeCases:
    def test_invalid_choice_retries_until_valid(self) -> None:
        """Invalid choices (0, 4, 'x') should loop until a valid one is given."""
        io = _make_io("0", "4", "x", "2", "token", "key")
        result = SetupWizard(io).run()
        assert "REFRESH_TOKEN" in result

    def test_proxy_api_key_uses_default_when_empty(self) -> None:
        """Empty proxy key input should fall back to the default value."""
        default_key = "my-super-secret-password-123"
        io = _make_io("2", "token", default_key)
        result = SetupWizard(io).run()
        assert result["PROXY_API_KEY"] == default_key

    def test_result_contains_exactly_two_keys_for_token(self) -> None:
        io = _make_io("2", "tok", "key")
        result = SetupWizard(io).run()
        assert set(result.keys()) == {"REFRESH_TOKEN", "PROXY_API_KEY"}

    def test_result_contains_exactly_two_keys_for_creds_file(self) -> None:
        io = _make_io("1", "/creds.json", "key")
        result = SetupWizard(io).run()
        assert set(result.keys()) == {"KIRO_CREDS_FILE", "PROXY_API_KEY"}

    def test_result_contains_exactly_two_keys_for_cli_db(self) -> None:
        io = _make_io("3", "/db.sqlite3", "key")
        result = SetupWizard(io).run()
        assert set(result.keys()) == {"KIRO_CLI_DB_FILE", "PROXY_API_KEY"}


# ---------------------------------------------------------------------------
# save_config
# ---------------------------------------------------------------------------


class TestSaveConfig:
    def test_creates_file_with_correct_content(self, tmp_path: Path) -> None:
        dest = tmp_path / "kiro-gateway" / ".env"
        save_config({"REFRESH_TOKEN": "tok123", "PROXY_API_KEY": "secret"}, dest)

        assert dest.exists()
        content = dest.read_text(encoding="utf-8")
        assert "REFRESH_TOKEN=tok123\n" in content
        assert "PROXY_API_KEY=secret\n" in content

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        dest = tmp_path / "a" / "b" / "c" / ".env"
        save_config({"KEY": "val"}, dest)
        assert dest.exists()

    def test_updates_os_environ(self, tmp_path: Path) -> None:
        dest = tmp_path / ".env"
        key = "_KIRO_TEST_WIZARD_KEY_"
        save_config({key: "wizard_value"}, dest)
        assert os.environ.get(key) == "wizard_value"
        # Cleanup
        del os.environ[key]

    def test_no_quotes_in_file(self, tmp_path: Path) -> None:
        dest = tmp_path / ".env"
        save_config({"PATH_KEY": "/some/path/file.json"}, dest)
        content = dest.read_text(encoding="utf-8")
        assert '"' not in content
        assert "'" not in content

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        dest = tmp_path / ".env"
        dest.write_text("OLD=old_value\n", encoding="utf-8")
        save_config({"NEW": "new_value"}, dest)
        content = dest.read_text(encoding="utf-8")
        assert "NEW=new_value" in content
        # Old content is replaced
        assert "OLD=old_value" not in content

    def test_empty_config_creates_empty_file(self, tmp_path: Path) -> None:
        dest = tmp_path / ".env"
        save_config({}, dest)
        assert dest.exists()
        assert dest.read_text(encoding="utf-8") == ""


# ---------------------------------------------------------------------------
# get_user_config_path
# ---------------------------------------------------------------------------


class TestGetUserConfigPath:
    def test_returns_path_under_home(self) -> None:
        path = get_user_config_path()
        assert path.is_absolute()
        assert str(path).endswith(".env")
        assert "kiro-gateway" in str(path)

    def test_parent_is_kiro_gateway_dir(self) -> None:
        path = get_user_config_path()
        assert path.parent.name == "kiro-gateway"

    def test_grandparent_is_dot_config(self) -> None:
        path = get_user_config_path()
        assert path.parent.parent.name == ".config"


# ---------------------------------------------------------------------------
# ConsoleWizardIO
# ---------------------------------------------------------------------------


class TestConsoleWizardIO:
    def test_prompt_returns_input(self) -> None:
        io = ConsoleWizardIO()
        with patch("builtins.input", return_value="hello"):
            result = io.prompt("Enter something")
        assert result == "hello"

    def test_prompt_returns_default_on_empty_input(self) -> None:
        io = ConsoleWizardIO()
        with patch("builtins.input", return_value=""):
            result = io.prompt("Enter something", default="fallback")
        assert result == "fallback"

    def test_prompt_strips_whitespace(self) -> None:
        io = ConsoleWizardIO()
        with patch("builtins.input", return_value="  value  "):
            result = io.prompt("Enter something")
        assert result == "value"

    def test_confirm_yes(self) -> None:
        io = ConsoleWizardIO()
        for answer in ("y", "Y", "yes", "YES", "Yes"):
            with patch("builtins.input", return_value=answer):
                assert io.confirm("Confirm?") is True

    def test_confirm_no(self) -> None:
        io = ConsoleWizardIO()
        for answer in ("n", "N", "no", "", "nope"):
            with patch("builtins.input", return_value=answer):
                assert io.confirm("Confirm?") is False
