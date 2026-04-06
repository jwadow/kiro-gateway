# -*- coding: utf-8 -*-

"""Unit tests for cli.py subcommand structure and wizard integration.

Tests the 'config' subcommand parsing, handle_config_command() branches,
and main() wizard trigger logic.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from kiro.cli import (
    parse_cli_args,
    handle_config_command,
    _mask_value,
    _SENSITIVE_KEYS,
)


# ---------------------------------------------------------------------------
# parse_cli_args — config subcommand
# ---------------------------------------------------------------------------


class TestParseCliArgsConfigSubcommand:
    def _parse(self, *argv: str):
        with patch("sys.argv", ["kiro-gateway", *argv]):
            return parse_cli_args()

    def test_no_subcommand_command_is_none(self) -> None:
        args = self._parse()
        assert args.command is None

    def test_config_subcommand_sets_command(self) -> None:
        args = self._parse("config")
        assert args.command == "config"

    def test_config_reset_flag(self) -> None:
        args = self._parse("config", "--reset")
        assert args.reset is True

    def test_config_show_path_flag(self) -> None:
        args = self._parse("config", "--show-path")
        assert args.show_path is True

    def test_config_no_flags_all_false(self) -> None:
        args = self._parse("config")
        assert args.reset is False
        assert args.show_path is False

    def test_host_and_port_still_work(self) -> None:
        args = self._parse("--host", "127.0.0.1", "--port", "9000")
        assert args.host == "127.0.0.1"
        assert args.port == 9000
        assert args.command is None


# ---------------------------------------------------------------------------
# handle_config_command
# ---------------------------------------------------------------------------


class TestHandleConfigCommandShowPath:
    def test_show_path_prints_config_file_path(self, capsys) -> None:
        from kiro.config import USER_CONFIG_FILE
        args = MagicMock(show_path=True, reset=False)
        handle_config_command(args)
        captured = capsys.readouterr()
        assert str(USER_CONFIG_FILE) in captured.out

    def test_show_path_takes_priority_over_reset(self, capsys) -> None:
        args = MagicMock(show_path=True, reset=True)
        with patch("kiro.cli._reset_config") as mock_reset:
            handle_config_command(args)
            mock_reset.assert_not_called()


class TestHandleConfigCommandReset:
    def test_reset_calls_reset_config(self) -> None:
        args = MagicMock(show_path=False, reset=True)
        with patch("kiro.cli._reset_config") as mock_reset:
            handle_config_command(args)
            mock_reset.assert_called_once()

    def test_reset_deletes_file_on_confirm(self, tmp_path: Path) -> None:
        from kiro.cli import _reset_config
        config_file = tmp_path / ".env"
        config_file.write_text("KEY=val\n", encoding="utf-8")

        with patch("kiro.config.USER_CONFIG_FILE", config_file), \
             patch("kiro.cli.USER_CONFIG_FILE", config_file), \
             patch("builtins.input", return_value="y"):
            _reset_config()

        assert not config_file.exists()

    def test_reset_does_not_delete_on_cancel(self, tmp_path: Path) -> None:
        from kiro.cli import _reset_config
        config_file = tmp_path / ".env"
        config_file.write_text("KEY=val\n", encoding="utf-8")

        with patch("kiro.config.USER_CONFIG_FILE", config_file), \
             patch("kiro.cli.USER_CONFIG_FILE", config_file), \
             patch("builtins.input", return_value="n"):
            _reset_config()

        assert config_file.exists()

    def test_reset_no_file_prints_message(self, tmp_path: Path, capsys) -> None:
        from kiro.cli import _reset_config
        nonexistent = tmp_path / "missing.env"

        with patch("kiro.cli.USER_CONFIG_FILE", nonexistent):
            _reset_config()

        captured = capsys.readouterr()
        assert "No config file" in captured.out


class TestHandleConfigCommandEditor:
    def test_no_flags_launches_config_editor(self) -> None:
        args = MagicMock(show_path=False, reset=False)
        with patch("kiro.cli.ConfigEditor") as mock_editor_cls:
            mock_editor = MagicMock()
            mock_editor_cls.return_value = mock_editor
            handle_config_command(args)
            mock_editor.run.assert_called_once()


# ---------------------------------------------------------------------------
# _mask_value
# ---------------------------------------------------------------------------


class TestMaskValue:
    def test_sensitive_key_long_value_is_masked(self) -> None:
        result = _mask_value("REFRESH_TOKEN", "eyJhbGciOiJSUzI1NiJ9.payload")
        assert result.endswith("****")
        assert result.startswith("eyJhbGci")

    def test_sensitive_key_short_value_not_masked(self) -> None:
        result = _mask_value("REFRESH_TOKEN", "short")
        assert result == "short"

    def test_non_sensitive_key_not_masked(self) -> None:
        result = _mask_value("SERVER_PORT", "8001")
        assert result == "8001"

    def test_proxy_api_key_is_sensitive(self) -> None:
        result = _mask_value("PROXY_API_KEY", "my-super-secret-password-123")
        assert "****" in result


# ---------------------------------------------------------------------------
# main() — wizard trigger
# ---------------------------------------------------------------------------


class TestMainWizardTrigger:
    def _run_main_with_mocks(self, validate_returns, wizard_returns=True):
        """Helper: run main() with mocked validate and wizard."""
        with patch("sys.argv", ["kiro-gateway"]), \
             patch("kiro.cli.validate_configuration", side_effect=validate_returns), \
             patch("kiro.cli._run_wizard_and_save", return_value=wizard_returns), \
             patch("kiro.cli._warn_timeout_configuration"), \
             patch("kiro.cli.resolve_server_config", return_value=("0.0.0.0", 8001)), \
             patch("kiro.cli.print_startup_banner"), \
             patch("uvicorn.run"):
            from kiro.cli import main
            main()

    def test_valid_config_skips_wizard(self) -> None:
        with patch("sys.argv", ["kiro-gateway"]), \
             patch("kiro.cli.validate_configuration", return_value=True), \
             patch("kiro.cli._run_wizard_and_save") as mock_wizard, \
             patch("kiro.cli._warn_timeout_configuration"), \
             patch("kiro.cli.resolve_server_config", return_value=("0.0.0.0", 8001)), \
             patch("kiro.cli.print_startup_banner"), \
             patch("uvicorn.run"):
            from kiro.cli import main
            main()
            mock_wizard.assert_not_called()

    def test_invalid_config_triggers_wizard(self) -> None:
        with patch("sys.argv", ["kiro-gateway"]), \
             patch("kiro.cli.validate_configuration", return_value=False), \
             patch("kiro.cli._run_wizard_and_save", return_value=True) as mock_wizard, \
             patch("os.execv") as mock_execv:
            from kiro.cli import main
            main()
            mock_wizard.assert_called_once()
            mock_execv.assert_called_once()

    def test_wizard_abort_exits_with_error(self) -> None:
        with patch("sys.argv", ["kiro-gateway"]), \
             patch("kiro.cli.validate_configuration", return_value=False), \
             patch("kiro.cli._run_wizard_and_save", return_value=False), \
             pytest.raises(SystemExit) as exc_info:
            from kiro.cli import main
            main()
        assert exc_info.value.code == 1

    def test_config_subcommand_skips_server_start(self) -> None:
        with patch("sys.argv", ["kiro-gateway", "config"]), \
             patch("kiro.cli.handle_config_command") as mock_handle, \
             patch("kiro.cli.validate_configuration") as mock_validate, \
             patch("uvicorn.run") as mock_uvicorn:
            from kiro.cli import main
            main()
            mock_handle.assert_called_once()
            mock_validate.assert_not_called()
            mock_uvicorn.assert_not_called()
