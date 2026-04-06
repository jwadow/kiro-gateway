# -*- coding: utf-8 -*-

"""Unit tests for kiro.app.validate_configuration().

Covers: returns True/False (no SystemExit), credential source checks,
missing file warnings, and error message content.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from kiro.app import validate_configuration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _env(**kwargs: str):
    """Return a patch.dict context that sets only the given env vars.

    Clears the three credential env vars first so tests are isolated.
    """
    base = {
        "REFRESH_TOKEN": "",
        "KIRO_CREDS_FILE": "",
        "KIRO_CLI_DB_FILE": "",
    }
    base.update(kwargs)
    return patch.dict(os.environ, base, clear=False)


# ---------------------------------------------------------------------------
# Returns True when credentials are present
# ---------------------------------------------------------------------------


class TestValidateConfigurationReturnsTrue:
    def test_refresh_token_set(self) -> None:
        with _env(REFRESH_TOKEN="eyJhbGci.token"):
            assert validate_configuration() is True

    def test_kiro_creds_file_exists(self, tmp_path: Path) -> None:
        creds = tmp_path / "creds.json"
        creds.write_text("{}", encoding="utf-8")
        with _env(KIRO_CREDS_FILE=str(creds)):
            assert validate_configuration() is True

    def test_kiro_cli_db_exists(self, tmp_path: Path) -> None:
        db = tmp_path / "data.sqlite3"
        db.write_text("", encoding="utf-8")
        with _env(KIRO_CLI_DB_FILE=str(db)):
            assert validate_configuration() is True


# ---------------------------------------------------------------------------
# Returns False when credentials are missing
# ---------------------------------------------------------------------------


class TestValidateConfigurationReturnsFalse:
    def test_no_credentials_returns_false(self) -> None:
        with _env():
            assert validate_configuration() is False

    def test_does_not_raise_system_exit(self) -> None:
        """validate_configuration() must NOT call sys.exit() anymore."""
        with _env():
            try:
                result = validate_configuration()
            except SystemExit:
                pytest.fail("validate_configuration() raised SystemExit — it should return False instead")
            assert result is False

    def test_creds_file_path_set_but_missing(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "missing.json"
        with _env(KIRO_CREDS_FILE=str(nonexistent)):
            assert validate_configuration() is False

    def test_cli_db_path_set_but_missing(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "missing.sqlite3"
        with _env(KIRO_CLI_DB_FILE=str(nonexistent)):
            assert validate_configuration() is False

    def test_creds_file_missing_logs_warning(self, tmp_path: Path, caplog) -> None:
        nonexistent = tmp_path / "missing.json"
        import logging
        with _env(KIRO_CREDS_FILE=str(nonexistent)):
            with patch("kiro.app.logger") as mock_logger:
                validate_configuration()
                # Should have logged a warning about the missing file
                warning_calls = [
                    str(call) for call in mock_logger.warning.call_args_list
                ]
                assert any("KIRO_CREDS_FILE" in c for c in warning_calls)


# ---------------------------------------------------------------------------
# Error message content
# ---------------------------------------------------------------------------


class TestValidateConfigurationErrorMessage:
    def test_error_message_contains_config_edit_hint(self) -> None:
        """Error output should guide user to 'kiro-gateway config --edit'."""
        with _env():
            with patch("kiro.app._print_config_errors") as mock_print:
                validate_configuration()
                assert mock_print.called
                errors = mock_print.call_args[0][0]
                combined = "\n".join(errors)
                assert "kiro-gateway config --edit" in combined

    def test_error_message_contains_config_file_path(self) -> None:
        """Error output should show the user config file path."""
        with _env():
            with patch("kiro.app._print_config_errors") as mock_print:
                validate_configuration()
                errors = mock_print.call_args[0][0]
                combined = "\n".join(errors)
                assert "kiro-gateway" in combined  # path contains kiro-gateway dir


# ---------------------------------------------------------------------------
# _print_config_errors
# ---------------------------------------------------------------------------


class TestPrintConfigErrors:
    def test_does_not_raise(self) -> None:
        from kiro.app import _print_config_errors
        with patch("kiro.app.logger"):
            _print_config_errors(["Error line 1", "Error line 2"])

    def test_called_with_error_list(self) -> None:
        from kiro.app import _print_config_errors
        with patch("kiro.app.logger") as mock_logger:
            _print_config_errors(["Test error"])
            assert mock_logger.error.called
