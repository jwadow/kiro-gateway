# -*- coding: utf-8 -*-

"""Unit tests for kiro.config_editor module.

Covers: read_config_file(), write_config_file(), update_config_value(),
ConfigEditor interaction loop, and display helpers.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from kiro.config_editor import (
    CONFIG_GROUPS,
    ConfigEditor,
    ConfigVar,
    read_config_file,
    update_config_value,
    write_config_file,
    _effective_value,
    _mask,
)


# ---------------------------------------------------------------------------
# read_config_file
# ---------------------------------------------------------------------------


class TestReadConfigFile:
    def test_returns_empty_dict_when_file_missing(self, tmp_path: Path) -> None:
        assert read_config_file(tmp_path / "missing.env") == {}

    def test_reads_unquoted_values(self, tmp_path: Path) -> None:
        f = tmp_path / ".env"
        f.write_text("KEY=value\n", encoding="utf-8")
        assert read_config_file(f) == {"KEY": "value"}

    def test_reads_double_quoted_values(self, tmp_path: Path) -> None:
        f = tmp_path / ".env"
        f.write_text('KEY="hello world"\n', encoding="utf-8")
        assert read_config_file(f) == {"KEY": "hello world"}

    def test_reads_single_quoted_values(self, tmp_path: Path) -> None:
        f = tmp_path / ".env"
        f.write_text("KEY='hello world'\n", encoding="utf-8")
        assert read_config_file(f) == {"KEY": "hello world"}

    def test_skips_comments(self, tmp_path: Path) -> None:
        f = tmp_path / ".env"
        f.write_text("# comment\nKEY=val\n", encoding="utf-8")
        assert read_config_file(f) == {"KEY": "val"}

    def test_skips_blank_lines(self, tmp_path: Path) -> None:
        f = tmp_path / ".env"
        f.write_text("\n\nKEY=val\n\n", encoding="utf-8")
        assert read_config_file(f) == {"KEY": "val"}

    def test_reads_multiple_keys(self, tmp_path: Path) -> None:
        f = tmp_path / ".env"
        f.write_text("A=1\nB=2\nC=3\n", encoding="utf-8")
        assert read_config_file(f) == {"A": "1", "B": "2", "C": "3"}


# ---------------------------------------------------------------------------
# write_config_file
# ---------------------------------------------------------------------------


class TestWriteConfigFile:
    def test_creates_file_with_correct_content(self, tmp_path: Path) -> None:
        f = tmp_path / ".env"
        write_config_file(f, {"KEY": "val", "OTHER": "x"})
        content = f.read_text(encoding="utf-8")
        assert "KEY=val\n" in content
        assert "OTHER=x\n" in content

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        f = tmp_path / "a" / "b" / ".env"
        write_config_file(f, {"K": "v"})
        assert f.exists()

    def test_skips_empty_values(self, tmp_path: Path) -> None:
        f = tmp_path / ".env"
        write_config_file(f, {"SET": "yes", "EMPTY": ""})
        content = f.read_text(encoding="utf-8")
        assert "SET=yes" in content
        assert "EMPTY" not in content

    def test_no_quotes_in_output(self, tmp_path: Path) -> None:
        f = tmp_path / ".env"
        write_config_file(f, {"PATH_KEY": "/some/path"})
        content = f.read_text(encoding="utf-8")
        assert '"' not in content
        assert "'" not in content

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        f = tmp_path / ".env"
        f.write_text("OLD=old\n", encoding="utf-8")
        write_config_file(f, {"NEW": "new"})
        content = f.read_text(encoding="utf-8")
        assert "NEW=new" in content
        assert "OLD" not in content


# ---------------------------------------------------------------------------
# update_config_value
# ---------------------------------------------------------------------------


class TestUpdateConfigValue:
    def test_adds_new_key(self, tmp_path: Path) -> None:
        f = tmp_path / ".env"
        update_config_value(f, "MY_KEY", "my_val")
        assert read_config_file(f)["MY_KEY"] == "my_val"

    def test_updates_existing_key(self, tmp_path: Path) -> None:
        f = tmp_path / ".env"
        f.write_text("MY_KEY=old\n", encoding="utf-8")
        update_config_value(f, "MY_KEY", "new")
        assert read_config_file(f)["MY_KEY"] == "new"

    def test_removes_key_when_value_empty(self, tmp_path: Path) -> None:
        f = tmp_path / ".env"
        f.write_text("MY_KEY=val\n", encoding="utf-8")
        update_config_value(f, "MY_KEY", "")
        assert "MY_KEY" not in read_config_file(f)

    def test_updates_os_environ(self, tmp_path: Path) -> None:
        f = tmp_path / ".env"
        key = "_KIRO_TEST_EDITOR_KEY_"
        update_config_value(f, key, "editor_value")
        assert os.environ.get(key) == "editor_value"
        del os.environ[key]

    def test_removes_from_os_environ_when_cleared(self, tmp_path: Path) -> None:
        f = tmp_path / ".env"
        key = "_KIRO_TEST_EDITOR_CLEAR_"
        os.environ[key] = "to_be_cleared"
        update_config_value(f, key, "")
        assert key not in os.environ


# ---------------------------------------------------------------------------
# _mask
# ---------------------------------------------------------------------------


class TestMask:
    def test_sensitive_long_value_masked(self) -> None:
        assert _mask("eyJhbGciOiJSUzI1NiJ9", sensitive=True) == "eyJhbGci****"

    def test_sensitive_short_value_not_masked(self) -> None:
        assert _mask("short", sensitive=True) == "short"

    def test_non_sensitive_not_masked(self) -> None:
        assert _mask("any_value_here", sensitive=False) == "any_value_here"


# ---------------------------------------------------------------------------
# _effective_value
# ---------------------------------------------------------------------------


class TestEffectiveValue:
    def test_os_environ_takes_priority(self) -> None:
        with patch.dict(os.environ, {"MY_VAR": "from_env"}):
            result = _effective_value("MY_VAR", {"MY_VAR": "from_file"}, "default")
        assert result == "from_env"

    def test_file_data_used_when_no_env(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MY_VAR_X", None)
            result = _effective_value("MY_VAR_X", {"MY_VAR_X": "from_file"}, "default")
        assert result == "from_file"

    def test_default_used_when_nothing_set(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MY_VAR_Y", None)
            result = _effective_value("MY_VAR_Y", {}, "my_default")
        assert result == "my_default"

    def test_empty_string_falls_through_to_default(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MY_VAR_Z", None)
            result = _effective_value("MY_VAR_Z", {"MY_VAR_Z": ""}, "fallback")
        assert result == "fallback"


# ---------------------------------------------------------------------------
# CONFIG_GROUPS
# ---------------------------------------------------------------------------


class TestConfigGroups:
    def test_all_groups_have_names(self) -> None:
        for group in CONFIG_GROUPS:
            assert group.name

    def test_all_vars_have_keys_and_descriptions(self) -> None:
        for group in CONFIG_GROUPS:
            for var in group.vars:
                assert var.key
                assert var.description

    def test_no_duplicate_keys(self) -> None:
        keys = [v.key for g in CONFIG_GROUPS for v in g.vars]
        assert len(keys) == len(set(keys))

    def test_credentials_group_exists(self) -> None:
        names = [g.name for g in CONFIG_GROUPS]
        assert "Credentials" in names

    def test_server_group_exists(self) -> None:
        names = [g.name for g in CONFIG_GROUPS]
        assert "Server" in names


# ---------------------------------------------------------------------------
# ConfigEditor — interaction loop
# ---------------------------------------------------------------------------


class TestConfigEditorQuit:
    def test_q_exits_loop(self, tmp_path: Path) -> None:
        editor = ConfigEditor(tmp_path / ".env")
        with patch("builtins.input", return_value="q"):
            editor.run()  # should not hang

    def test_empty_input_exits_loop(self, tmp_path: Path) -> None:
        editor = ConfigEditor(tmp_path / ".env")
        with patch("builtins.input", return_value=""):
            editor.run()

    def test_invalid_number_does_not_crash(self, tmp_path: Path) -> None:
        editor = ConfigEditor(tmp_path / ".env")
        with patch("builtins.input", side_effect=["999", "q"]):
            editor.run()

    def test_non_numeric_input_does_not_crash(self, tmp_path: Path) -> None:
        editor = ConfigEditor(tmp_path / ".env")
        with patch("builtins.input", side_effect=["abc", "q"]):
            editor.run()


class TestConfigEditorEdit:
    def _all_vars(self) -> list[ConfigVar]:
        return [v for g in CONFIG_GROUPS for v in g.vars]

    def test_edit_first_var_saves_value(self, tmp_path: Path) -> None:
        f = tmp_path / ".env"
        editor = ConfigEditor(f)
        first_var = self._all_vars()[0]

        # Input: select var 1, enter new value, then quit
        with patch("builtins.input", side_effect=["1", "new_value", "q"]):
            editor.run()

        data = read_config_file(f)
        assert data[first_var.key] == "new_value"

    def test_enter_keeps_current_value(self, tmp_path: Path) -> None:
        f = tmp_path / ".env"
        f.write_text("PROXY_API_KEY=existing\n", encoding="utf-8")
        editor = ConfigEditor(f)

        # Find PROXY_API_KEY number
        n = next(
            i for i, v in editor._index.items() if v.key == "PROXY_API_KEY"
        )
        with patch("builtins.input", side_effect=[str(n), "", "q"]):
            editor.run()

        assert read_config_file(f)["PROXY_API_KEY"] == "existing"

    def test_dash_clears_value(self, tmp_path: Path) -> None:
        f = tmp_path / ".env"
        f.write_text("SERVER_PORT=9000\n", encoding="utf-8")
        editor = ConfigEditor(f)

        n = next(i for i, v in editor._index.items() if v.key == "SERVER_PORT")
        with patch("builtins.input", side_effect=[str(n), "-", "q"]):
            editor.run()

        assert "SERVER_PORT" not in read_config_file(f)

    def test_invalid_allowed_value_not_saved(self, tmp_path: Path) -> None:
        f = tmp_path / ".env"
        editor = ConfigEditor(f)

        # LOG_LEVEL has allowed_values
        n = next(i for i, v in editor._index.items() if v.key == "LOG_LEVEL")
        with patch("builtins.input", side_effect=[str(n), "INVALID_LEVEL", "q"]):
            editor.run()

        assert "LOG_LEVEL" not in read_config_file(f)

    def test_valid_allowed_value_saved(self, tmp_path: Path) -> None:
        f = tmp_path / ".env"
        editor = ConfigEditor(f)

        n = next(i for i, v in editor._index.items() if v.key == "LOG_LEVEL")
        with patch("builtins.input", side_effect=[str(n), "DEBUG", "q"]):
            editor.run()

        assert read_config_file(f)["LOG_LEVEL"] == "DEBUG"
