# -*- coding: utf-8 -*-

"""Unit tests for config.py multi-path loading logic.

Tests the priority order: current-dir .env > user config .env > system env vars,
and the _read_raw_from_file() / _get_raw_env_value() helper functions.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from kiro.config import _read_raw_from_file, USER_CONFIG_FILE


# ---------------------------------------------------------------------------
# _read_raw_from_file
# ---------------------------------------------------------------------------


class TestReadRawFromFile:
    """Tests for the _read_raw_from_file() helper."""

    def test_returns_unquoted_value(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("MY_VAR=hello\n", encoding="utf-8")
        assert _read_raw_from_file("MY_VAR", env) == "hello"

    def test_returns_double_quoted_value(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text('MY_VAR="hello world"\n', encoding="utf-8")
        assert _read_raw_from_file("MY_VAR", env) == "hello world"

    def test_returns_single_quoted_value(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("MY_VAR='hello world'\n", encoding="utf-8")
        assert _read_raw_from_file("MY_VAR", env) == "hello world"

    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        assert _read_raw_from_file("MY_VAR", tmp_path / "nonexistent.env") is None

    def test_returns_none_when_var_not_in_file(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("OTHER_VAR=value\n", encoding="utf-8")
        assert _read_raw_from_file("MY_VAR", env) is None

    def test_skips_comment_lines(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("# MY_VAR=commented\nMY_VAR=real\n", encoding="utf-8")
        assert _read_raw_from_file("MY_VAR", env) == "real"

    def test_skips_empty_lines(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("\n\nMY_VAR=value\n\n", encoding="utf-8")
        assert _read_raw_from_file("MY_VAR", env) == "value"

    def test_windows_path_not_mangled(self, tmp_path: Path) -> None:
        """Backslashes in Windows paths must not be interpreted as escape sequences."""
        env = tmp_path / ".env"
        env.write_text("KIRO_CREDS_FILE=D:\\Projects\\file.json\n", encoding="utf-8")
        result = _read_raw_from_file("KIRO_CREDS_FILE", env)
        # The raw value should contain literal backslashes, not escape chars
        assert result == "D:\\Projects\\file.json"

    def test_first_match_wins(self, tmp_path: Path) -> None:
        """When a variable appears twice, the first occurrence is returned."""
        env = tmp_path / ".env"
        env.write_text("MY_VAR=first\nMY_VAR=second\n", encoding="utf-8")
        assert _read_raw_from_file("MY_VAR", env) == "first"


# ---------------------------------------------------------------------------
# _get_raw_env_value — fallback to user config dir
# ---------------------------------------------------------------------------


class TestGetRawEnvValueFallback:
    """Tests for _get_raw_env_value() fallback to USER_CONFIG_FILE."""

    def test_returns_value_from_current_dir(self, tmp_path: Path) -> None:
        """Value in current-dir .env is returned."""
        from kiro.config import _get_raw_env_value

        env = tmp_path / ".env"
        env.write_text("_TEST_RAW_VAR=from_cwd\n", encoding="utf-8")

        result = _get_raw_env_value("_TEST_RAW_VAR", str(env))
        assert result == "from_cwd"

    def test_falls_back_to_user_config(self, tmp_path: Path) -> None:
        """When current-dir .env has no value, user config dir is checked."""
        from kiro.config import _get_raw_env_value

        user_env = tmp_path / "kiro-gateway" / ".env"
        user_env.parent.mkdir(parents=True)
        user_env.write_text("_TEST_RAW_VAR=from_user_config\n", encoding="utf-8")

        # Patch USER_CONFIG_FILE to point to our temp file
        with patch("kiro.config.USER_CONFIG_FILE", user_env):
            result = _get_raw_env_value("_TEST_RAW_VAR", str(tmp_path / "missing.env"))

        assert result == "from_user_config"

    def test_current_dir_takes_priority_over_user_config(self, tmp_path: Path) -> None:
        """Current-dir .env value wins over user config dir value."""
        from kiro.config import _get_raw_env_value

        cwd_env = tmp_path / ".env"
        cwd_env.write_text("_TEST_RAW_VAR=from_cwd\n", encoding="utf-8")

        user_env = tmp_path / "user" / ".env"
        user_env.parent.mkdir(parents=True)
        user_env.write_text("_TEST_RAW_VAR=from_user\n", encoding="utf-8")

        with patch("kiro.config.USER_CONFIG_FILE", user_env):
            result = _get_raw_env_value("_TEST_RAW_VAR", str(cwd_env))

        assert result == "from_cwd"

    def test_returns_none_when_not_found_anywhere(self, tmp_path: Path) -> None:
        """Returns None when variable is absent from both locations."""
        from kiro.config import _get_raw_env_value

        with patch("kiro.config.USER_CONFIG_FILE", tmp_path / "missing.env"):
            result = _get_raw_env_value("_NONEXISTENT_VAR_XYZ", str(tmp_path / "also_missing.env"))

        assert result is None


# ---------------------------------------------------------------------------
# USER_CONFIG_FILE constant
# ---------------------------------------------------------------------------


class TestUserConfigFile:
    def test_is_path_instance(self) -> None:
        assert isinstance(USER_CONFIG_FILE, Path)

    def test_filename_is_dot_env(self) -> None:
        assert USER_CONFIG_FILE.name == ".env"

    def test_parent_dir_is_kiro_gateway(self) -> None:
        assert USER_CONFIG_FILE.parent.name == "kiro-gateway"

    def test_under_dot_config(self) -> None:
        assert USER_CONFIG_FILE.parent.parent.name == ".config"

    def test_is_absolute(self) -> None:
        assert USER_CONFIG_FILE.is_absolute()
