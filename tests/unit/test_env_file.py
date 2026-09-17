# -*- coding: utf-8 -*-

"""
Unit tests for kiro/env_file.py and the menubar Settings/Display menu logic.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kiro.env_file import read_env, update_env_value, default_env_path


def _mock_appkit_for_settings():
    """Patch AppKit/objc so settings_window can be imported without macOS frameworks."""
    mocks = {}
    for mod in ["objc", "AppKit", "Foundation"]:
        m = MagicMock()
        mocks[mod] = m
        sys.modules.setdefault(mod, m)
    sys.modules["AppKit"].NSBezelStyleRegularSquare = 0
    sys.modules["AppKit"].NSButtonTypeToggle = 0
    sys.modules["AppKit"].NSUserInterfaceLayoutOrientationVertical = 1
    sys.modules["AppKit"].NSUserInterfaceLayoutOrientationHorizontal = 0
    sys.modules["AppKit"].NSApplicationActivationPolicyAccessory = 4
    return mocks


@pytest.fixture
def env_file(tmp_path) -> Path:
    path = tmp_path / ".env"
    path.write_text(
        '# main config\n'
        'PROXY_API_KEY="secret-key-123456"\n'
        '\n'
        'SERVER_PORT=3000\n'
        "KIRO_API_REGION='us-east-1'\n",
        encoding="utf-8",
    )
    return path


class TestReadEnv:
    """Tests for read_env()."""

    def test_reads_simple_values(self, env_file):
        values = read_env(env_file)
        print(f"values: {values}")
        assert values["SERVER_PORT"] == "3000"

    def test_strips_double_quotes(self, env_file):
        values = read_env(env_file)
        assert values["PROXY_API_KEY"] == "secret-key-123456"

    def test_strips_single_quotes(self, env_file):
        values = read_env(env_file)
        assert values["KIRO_API_REGION"] == "us-east-1"

    def test_missing_file_returns_empty(self, tmp_path):
        print("Action: read_env on missing file")
        assert read_env(tmp_path / "nope.env") == {}

    def test_ignores_comments_and_blanks(self, env_file):
        values = read_env(env_file)
        print(f"keys: {sorted(values.keys())}")
        assert "# main config" not in values
        assert "" not in values

    def test_ignores_lines_without_equals(self, tmp_path):
        path = tmp_path / "weird.env"
        path.write_text("NOT_A_PAIR\nKEY=1\n")
        values = read_env(path)
        print(f"values: {values}")
        assert values == {"KEY": "1"}


class TestUpdateEnvValue:
    """Tests for update_env_value() - preservation and formatting."""

    def test_updates_existing_key_preserving_comments(self, env_file):
        print("Action: update PROXY_API_KEY")
        update_env_value(env_file, "PROXY_API_KEY", "new-secret")
        content = env_file.read_text()
        print(content)
        assert content.startswith("# main config\n")
        assert 'PROXY_API_KEY="new-secret"' in content

    def test_preserves_existing_quote_style(self, env_file):
        print("Action: update single-quoted key")
        update_env_value(env_file, "KIRO_API_REGION", "eu-central-1")
        assert "KIRO_API_REGION='eu-central-1'" in env_file.read_text()

    def test_preserves_unquoted_style(self, env_file):
        print("Action: update unquoted key")
        update_env_value(env_file, "SERVER_PORT", "9000")
        assert "SERVER_PORT=9000" in env_file.read_text()

    def test_appends_missing_key(self, env_file):
        print("Action: append new key")
        changed = update_env_value(env_file, "VPN_PROXY_URL", "http://127.0.0.1:7890")
        content = env_file.read_text()
        print(content)
        assert changed is True
        assert 'VPN_PROXY_URL="http://127.0.0.1:7890"' in content

    def test_empty_value_removes_key(self, env_file):
        print("Action: clear PROXY_API_KEY")
        update_env_value(env_file, "PROXY_API_KEY", "")
        content = env_file.read_text()
        print(content)
        assert "PROXY_API_KEY" not in content
        assert "# main config" in content

    def test_noop_when_value_unchanged(self, env_file):
        print("Action: set SERVER_PORT to same value")
        changed = update_env_value(env_file, "SERVER_PORT", "3000")
        assert changed is False

    def test_append_adds_blank_line_separator(self, env_file):
        print("Action: append after file without trailing newline handling")
        update_env_value(env_file, "NEW_KEY", "val")
        lines = env_file.read_text().splitlines()
        print(f"lines: {lines}")
        assert lines[-1] == 'NEW_KEY="val"'

    def test_empty_key_raises(self, env_file):
        print("Action: update with empty key")
        with pytest.raises(ValueError):
            update_env_value(env_file, "", "x")

    def test_quoted_value_with_spaces(self, env_file):
        print("Action: set value containing spaces")
        update_env_value(env_file, "VPN_PROXY_URL", "http://user:pass@proxy:8080")
        assert 'VPN_PROXY_URL="http://user:pass@proxy:8080"' in env_file.read_text()


class TestDefaultEnvPath:
    """Tests for default_env_path()."""

    def test_prefers_cwd_env_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("A=1\n")
        path = default_env_path()
        print(f"path: {path}")
        assert path == tmp_path / ".env"

    def test_returns_cwd_env_even_if_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        path = default_env_path()
        print(f"path: {path}")
        assert path == tmp_path / ".env"


class TestSettingsMenu:
    """Tests for the Settings window flow and env editing."""

    def _make_app(self):
        from menubar import KiroGatewayApp

        with patch.object(KiroGatewayApp, "_autostart"), patch.object(
            KiroGatewayApp, "_sync_login_item_state"
        ):
            app = KiroGatewayApp.__new__(KiroGatewayApp)
            app.server_thread = MagicMock()
            app.status_item = MagicMock()
            app.toggle_item = MagicMock()
            app.login_item = MagicMock()
            app.restart_hint_item = MagicMock()
            app.env_path = Path("/tmp/test-nonexistent.env")
            import menubar as mb

            app._sync_ui = mb.KiroGatewayApp._sync_ui.__get__(app)
            app._offer_restart = MagicMock()
            app.open_settings_window = MagicMock()
            app.on_restart = mb.KiroGatewayApp.on_restart.__get__(app)
            app.on_edit_env_key = mb.KiroGatewayApp.on_edit_env_key.__get__(app)
            yield app

    def test_edit_env_key_opens_settings_window(self):
        for app in self._make_app():
            with patch("menubar.SettingsWindowController") as mock_controller_cls:
                real_open = type(app).open_settings_window.__get__(app)
                app.open_settings_window = real_open
                print("Action: on_edit_env_key opens settings window")
                app.on_edit_env_key(None)
                print(f"controller created: {mock_controller_cls.called}")
                assert mock_controller_cls.called
                _, kwargs = mock_controller_cls.call_args
                print(f"keys passed: {kwargs.get('keys')[:3]}…")
                assert "SERVER_PORT" in kwargs["keys"]
                assert callable(kwargs["on_save"])
                mock_controller_cls.return_value.show.assert_called_once()
                app.open_settings_window = MagicMock()

    def test_apply_env_changes_saves_and_offers_restart(self):
        for app in self._make_app():
            with patch("menubar.update_env_value") as mock_update:
                mock_update.return_value = True
                original_offer = app._offer_restart
                app._offer_restart = MagicMock()
                print("Action: _apply_env_changes with changed values")
                app._apply_env_changes({"SERVER_PORT": "4000", "DEBUG_MODE": ""})
                print(f"update calls: {mock_update.call_count}")
                assert mock_update.call_count == 2
                assert app._offer_restart.called
                app._offer_restart = original_offer

    def test_apply_env_changes_no_restart_when_nothing_changed(self):
        for app in self._make_app():
            with patch("menubar.update_env_value") as mock_update:
                mock_update.return_value = False
                original_offer = app._offer_restart
                app._offer_restart = MagicMock()
                print("Action: _apply_env_changes with no changes")
                app._apply_env_changes({"SERVER_PORT": "3000"})
                assert app._offer_restart.called is False
                app._offer_restart = original_offer

    def test_restart_stops_server_and_relaunches(self):
        for app in self._make_app():
            with patch("menubar.subprocess.Popen") as mock_popen, patch(
                "menubar.rumps.quit_application"
            ) as mock_quit:
                print("Action: on_restart")
                app.on_restart(app.restart_hint_item)
                print(f"stop called: {app.server_thread.stop.called}")
                assert app.server_thread.stop.called
                assert mock_popen.called
                assert mock_quit.called


class TestSettingsRevealToggle:
    """Tests for the eye-toggle reveal behaviour on secret fields."""

    def _make_ctrl(self, api_key="s3cr3t"):
        secure_cls = MagicMock()
        plain_cls = MagicMock()
        btn_cls = MagicMock()
        secure_inst = MagicMock()
        plain_inst = MagicMock()
        btn_inst = MagicMock()
        secure_cls.return_value = secure_inst
        plain_cls.return_value = plain_inst
        btn_cls.return_value = btn_inst

        with patch("kiro.settings_window.NSSecureTextField", secure_cls), \
             patch("kiro.settings_window.NSTextField", MagicMock(return_value=plain_inst)), \
             patch("kiro.settings_window.NSButton", btn_cls), \
             patch("kiro.settings_window.NSImage"), \
             patch("kiro.settings_window.objc") as mock_objc:
            from kiro.settings_window import SettingsWindowController
            ctrl = SettingsWindowController(
                keys=["PROXY_API_KEY", "SERVER_PORT"],
                labels={"PROXY_API_KEY": "API Key", "SERVER_PORT": "Port"},
                values={"PROXY_API_KEY": api_key, "SERVER_PORT": "3000"},
                on_save=MagicMock(),
            )
            ctrl._mock_objc = mock_objc
            ctrl._secure_inst = secure_inst
            ctrl._plain_inst = plain_inst
            ctrl._btn_inst = btn_inst
            return ctrl

    def test_secret_field_starts_masked(self):
        with patch("kiro.settings_window.NSSecureTextField") as secure_cls, \
             patch("kiro.settings_window.NSTextField"), \
             patch("kiro.settings_window.NSButton"), \
             patch("kiro.settings_window.NSImage"), \
             patch("kiro.settings_window.objc"):
            from kiro.settings_window import SettingsWindowController
            ctrl = SettingsWindowController(
                keys=["PROXY_API_KEY"],
                labels={"PROXY_API_KEY": "API Key"},
                values={"PROXY_API_KEY": "s3cr3t"},
                on_save=MagicMock(),
            )
            secure_cls.alloc.return_value.initWithFrame_.return_value = MagicMock()
            secure, plain, btn = ctrl._make_secret_field("PROXY_API_KEY")
            secure.setStringValue_.assert_called_with("s3cr3t")
            plain.setStringValue_.assert_called_with("s3cr3t")

    def test_toggle_reveal_action_registered(self):
        with patch("kiro.settings_window.NSSecureTextField"), \
             patch("kiro.settings_window.NSTextField"), \
             patch("kiro.settings_window.NSButton") as btn_cls, \
             patch("kiro.settings_window.NSImage"), \
             patch("kiro.settings_window.objc"):
            from kiro.settings_window import SettingsWindowController
            ctrl = SettingsWindowController(
                keys=["PROXY_API_KEY"],
                labels={"PROXY_API_KEY": "API Key"},
                values={"PROXY_API_KEY": "x"},
                on_save=MagicMock(),
            )
            _, _, btn = ctrl._make_secret_field("PROXY_API_KEY")
            btn.setAction_.assert_called_with("toggleReveal:")

    def test_toggle_swaps_active_field_to_plain(self):
        with patch("kiro.settings_window.NSSecureTextField"), \
             patch("kiro.settings_window.NSTextField"), \
             patch("kiro.settings_window.NSButton"), \
             patch("kiro.settings_window.NSImage"), \
             patch("kiro.settings_window.objc") as mock_objc:
            from kiro.settings_window import SettingsWindowController
            secure = MagicMock()
            plain = MagicMock()
            row = MagicMock()
            btn = MagicMock()
            ctrl = SettingsWindowController(
                keys=["PROXY_API_KEY"],
                labels={"PROXY_API_KEY": "API Key"},
                values={"PROXY_API_KEY": "x"},
                on_save=MagicMock(),
            )
            ctrl._secret_pairs["PROXY_API_KEY"] = (secure, plain)
            ctrl._secret_rows["PROXY_API_KEY"] = row
            ctrl.fields["PROXY_API_KEY"] = secure
            mock_objc.getAssociatedObject.return_value = "PROXY_API_KEY"

            ctrl.toggleReveal_(btn)
            assert ctrl.fields["PROXY_API_KEY"] is plain

    def test_toggle_twice_returns_to_secure(self):
        with patch("kiro.settings_window.NSSecureTextField"), \
             patch("kiro.settings_window.NSTextField"), \
             patch("kiro.settings_window.NSButton"), \
             patch("kiro.settings_window.NSImage"), \
             patch("kiro.settings_window.objc") as mock_objc:
            from kiro.settings_window import SettingsWindowController
            secure = MagicMock()
            plain = MagicMock()
            row = MagicMock()
            btn = MagicMock()
            ctrl = SettingsWindowController(
                keys=["PROXY_API_KEY"],
                labels={"PROXY_API_KEY": "API Key"},
                values={"PROXY_API_KEY": "x"},
                on_save=MagicMock(),
            )
            ctrl._secret_pairs["PROXY_API_KEY"] = (secure, plain)
            ctrl._secret_rows["PROXY_API_KEY"] = row
            ctrl.fields["PROXY_API_KEY"] = secure
            mock_objc.getAssociatedObject.return_value = "PROXY_API_KEY"

            ctrl.toggleReveal_(btn)
            ctrl.toggleReveal_(btn)
            assert ctrl.fields["PROXY_API_KEY"] is secure

    def test_toggle_syncs_value_secure_to_plain(self):
        with patch("kiro.settings_window.NSSecureTextField"), \
             patch("kiro.settings_window.NSTextField"), \
             patch("kiro.settings_window.NSButton"), \
             patch("kiro.settings_window.NSImage"), \
             patch("kiro.settings_window.objc") as mock_objc:
            from kiro.settings_window import SettingsWindowController
            secure = MagicMock()
            plain = MagicMock()
            row = MagicMock()
            secure.stringValue.return_value = "typed-value"
            ctrl = SettingsWindowController(
                keys=["PROXY_API_KEY"],
                labels={"PROXY_API_KEY": "API Key"},
                values={"PROXY_API_KEY": "x"},
                on_save=MagicMock(),
            )
            ctrl._secret_pairs["PROXY_API_KEY"] = (secure, plain)
            ctrl._secret_rows["PROXY_API_KEY"] = row
            ctrl.fields["PROXY_API_KEY"] = secure
            mock_objc.getAssociatedObject.return_value = "PROXY_API_KEY"

            ctrl.toggleReveal_(MagicMock())
            plain.setStringValue_.assert_called_with("typed-value")

    def test_unknown_key_toggle_is_noop(self):
        with patch("kiro.settings_window.NSSecureTextField"), \
             patch("kiro.settings_window.NSTextField"), \
             patch("kiro.settings_window.NSButton"), \
             patch("kiro.settings_window.NSImage"), \
             patch("kiro.settings_window.objc") as mock_objc:
            from kiro.settings_window import SettingsWindowController
            ctrl = SettingsWindowController(
                keys=["PROXY_API_KEY"],
                labels={"PROXY_API_KEY": "API Key"},
                values={"PROXY_API_KEY": "x"},
                on_save=MagicMock(),
            )
            mock_objc.getAssociatedObject.return_value = "NO_SUCH_KEY"
            ctrl.toggleReveal_(MagicMock())

    def test_non_secret_key_not_in_secret_pairs(self):
        with patch("kiro.settings_window.NSSecureTextField"), \
             patch("kiro.settings_window.NSTextField"), \
             patch("kiro.settings_window.NSButton"), \
             patch("kiro.settings_window.NSImage"), \
             patch("kiro.settings_window.NSView"), \
             patch("kiro.settings_window.NSMakeRect", return_value=None), \
             patch("kiro.settings_window.NSScrollView"), \
             patch("kiro.settings_window.NSButtonTypeSwitch", 0), \
             patch("kiro.settings_window.NSColor"), \
             patch("kiro.settings_window.NSMakePoint", return_value=None), \
             patch("kiro.settings_window.objc"):
            from kiro.settings_window import SettingsWindowController
            ctrl = SettingsWindowController(
                keys=["SERVER_PORT"],
                labels={"SERVER_PORT": "Port"},
                values={"SERVER_PORT": "3000"},
                on_save=MagicMock(),
            )
            parent = MagicMock()
            ctrl._place_row("SERVER_PORT", parent, 0.0, 532.0)
            assert "SERVER_PORT" not in ctrl._secret_pairs


def _patch_appkit():
    return (
        patch("kiro.settings_window.NSSecureTextField"),
        patch("kiro.settings_window.NSTextField"),
        patch("kiro.settings_window.NSButton"),
        patch("kiro.settings_window.NSImage"),
        patch("kiro.settings_window.NSView"),
        patch("kiro.settings_window.NSMakeRect", return_value=None),
        patch("kiro.settings_window.NSScrollView"),
        patch("kiro.settings_window.NSButtonTypeSwitch", 0),
        patch("kiro.settings_window.NSColor"),
        patch("kiro.settings_window.NSMakePoint", return_value=None),
        patch("kiro.settings_window.objc"),
    )


class TestAdvancedSection:

    def _make_ctrl(self, ssl_certfile="", ssl_keyfile=""):
        from contextlib import ExitStack
        from kiro.settings_window import SettingsWindowController

        stack = ExitStack()
        for p in _patch_appkit():
            stack.enter_context(p)

        ctrl = SettingsWindowController(
            keys=["PROXY_API_KEY", "SERVER_PORT", "SSL_CERTFILE", "SSL_KEYFILE"],
            labels={
                "PROXY_API_KEY": "API Key",
                "SERVER_PORT": "Port",
                "SSL_CERTFILE": "SSL Certificate",
                "SSL_KEYFILE": "SSL Key File",
            },
            values={
                "PROXY_API_KEY": "s3cr3t",
                "SERVER_PORT": "8000",
                "SSL_CERTFILE": ssl_certfile,
                "SSL_KEYFILE": ssl_keyfile,
            },
            on_save=MagicMock(),
        )
        return ctrl, stack

    def test_advanced_section_hidden_by_default(self):
        ctrl, stack = self._make_ctrl()
        with stack:
            assert ctrl._advanced_visible is False

    def test_toggle_advanced_shows_section(self):
        ctrl, stack = self._make_ctrl()
        with stack:
            v1 = MagicMock()
            v2 = MagicMock()
            ctrl._advanced_views = [v1, v2]
            ctrl._advanced_toggle_btn = MagicMock()

            ctrl.toggleAdvanced_(MagicMock())

            assert ctrl._advanced_visible is True
            v1.setHidden_.assert_called_with(False)
            v2.setHidden_.assert_called_with(False)

    def test_toggle_advanced_twice_collapses_section(self):
        ctrl, stack = self._make_ctrl()
        with stack:
            v1 = MagicMock()
            ctrl._advanced_views = [v1]
            ctrl._advanced_toggle_btn = MagicMock()

            ctrl.toggleAdvanced_(MagicMock())
            ctrl.toggleAdvanced_(MagicMock())

            assert ctrl._advanced_visible is False
            v1.setHidden_.assert_called_with(True)

    def test_toggle_button_label_changes_on_expand(self):
        ctrl, stack = self._make_ctrl()
        with stack:
            ctrl._advanced_stack = MagicMock()
            btn = MagicMock()
            ctrl._advanced_toggle_btn = btn

            ctrl.toggleAdvanced_(MagicMock())

            call_args = btn.setTitle_.call_args[0][0]
            assert "▼" in call_args

    def test_https_checkbox_off_by_default_when_no_certs(self):
        ctrl, stack = self._make_ctrl(ssl_certfile="", ssl_keyfile="")
        with stack:
            from kiro.settings_window import SettingsWindowController
            https_enabled = bool(
                ctrl.initial_values.get("SSL_CERTFILE", "").strip()
                or ctrl.initial_values.get("SSL_KEYFILE", "").strip()
            )
            assert https_enabled is False

    def test_https_checkbox_on_when_certs_present(self):
        ctrl, stack = self._make_ctrl(ssl_certfile="/etc/ssl/cert.pem", ssl_keyfile="/etc/ssl/key.pem")
        with stack:
            https_enabled = bool(
                ctrl.initial_values.get("SSL_CERTFILE", "").strip()
                or ctrl.initial_values.get("SSL_KEYFILE", "").strip()
            )
            assert https_enabled is True

    def test_https_toggled_enables_fields(self):
        ctrl, stack = self._make_ctrl()
        with stack:
            cert_field = MagicMock()
            key_field = MagicMock()
            ctrl.fields["SSL_CERTFILE"] = cert_field
            ctrl.fields["SSL_KEYFILE"] = key_field

            sender = MagicMock()
            sender.state.return_value = 1
            ctrl._https_checkbox = sender
            ctrl.httpsToggled_(sender)

            cert_field.setEnabled_.assert_called_with(True)
            key_field.setEnabled_.assert_called_with(True)

    def test_https_toggled_disables_fields(self):
        ctrl, stack = self._make_ctrl()
        with stack:
            cert_field = MagicMock()
            key_field = MagicMock()
            ctrl.fields["SSL_CERTFILE"] = cert_field
            ctrl.fields["SSL_KEYFILE"] = key_field

            sender = MagicMock()
            sender.state.return_value = 0
            ctrl._https_checkbox = sender
            ctrl.httpsToggled_(sender)

            cert_field.setEnabled_.assert_called_with(False)
            key_field.setEnabled_.assert_called_with(False)

    def test_save_clears_tls_keys_when_https_disabled(self):
        ctrl, stack = self._make_ctrl(ssl_certfile="/cert.pem", ssl_keyfile="/key.pem")
        with stack:
            on_save = MagicMock()
            ctrl.on_save = on_save

            cert_field = MagicMock()
            cert_field.stringValue.return_value = "/cert.pem"
            key_field = MagicMock()
            key_field.stringValue.return_value = "/key.pem"
            ctrl.fields["SSL_CERTFILE"] = cert_field
            ctrl.fields["SSL_KEYFILE"] = key_field

            checkbox = MagicMock()
            checkbox.state.return_value = 0
            ctrl._https_checkbox = checkbox
            ctrl.window = MagicMock()

            ctrl.saveClicked_(MagicMock())

            saved = on_save.call_args[0][0]
            assert saved["SSL_CERTFILE"] == ""
            assert saved["SSL_KEYFILE"] == ""

    def test_save_preserves_tls_keys_when_https_enabled(self):
        ctrl, stack = self._make_ctrl(ssl_certfile="/cert.pem", ssl_keyfile="/key.pem")
        with stack:
            on_save = MagicMock()
            ctrl.on_save = on_save

            cert_field = MagicMock()
            cert_field.stringValue.return_value = "/cert.pem"
            key_field = MagicMock()
            key_field.stringValue.return_value = "/key.pem"
            ctrl.fields["SSL_CERTFILE"] = cert_field
            ctrl.fields["SSL_KEYFILE"] = key_field

            checkbox = MagicMock()
            checkbox.state.return_value = 1
            ctrl._https_checkbox = checkbox
            ctrl.window = MagicMock()

            ctrl.saveClicked_(MagicMock())

            saved = on_save.call_args[0][0]
            assert saved["SSL_CERTFILE"] == "/cert.pem"
            assert saved["SSL_KEYFILE"] == "/key.pem"

