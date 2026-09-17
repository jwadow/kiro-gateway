# -*- coding: utf-8 -*-

"""
Unit tests for menubar.py.

Tests for build_base_url(), build_launch_agent_plist(), GatewayServerThread
lifecycle state machine, and KiroGatewayApp UI synchronization logic.

All tests run without a real GUI: rumps.App is instantiated only where safe
(headless PyObjC may still initialize NSApplication; tests that cannot run
headless are guarded), and server threads are always mocked.
"""

import plistlib
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def stop_real_threads():
    """Guard fixture: prevents accidentally started threads from leaking."""
    yield
    deadline = threading.Event()
    for _ in range(50):
        alive = [t for t in threading.enumerate() if t.name == "kiro-gateway-uvicorn" and t.is_alive()]
        if not alive:
            deadline.set()
            break
        time.sleep(0.1)
    if not deadline.is_set():
        raise AssertionError("GatewayServerThread left a real uvicorn thread alive after teardown")


class TestBuildBaseUrl:
    """Tests for build_base_url()."""

    def test_https_when_ssl_enabled(self):
        print("Action: build_base_url with ssl enabled")
        from menubar import build_base_url

        url = build_base_url("0.0.0.0", 3000, True)
        print(f"url: {url}")
        assert url == "https://localhost:3000"

    def test_http_when_ssl_disabled(self):
        print("Action: build_base_url with ssl disabled")
        from menubar import build_base_url

        url = build_base_url("0.0.0.0", 3000, False)
        print(f"url: {url}")
        assert url == "http://localhost:3000"

    def test_wildcard_host_displayed_as_localhost(self):
        print("Action: build_base_url with 0.0.0.0 host")
        from menubar import build_base_url

        url = build_base_url("0.0.0.0", 8000, False)
        print(f"url: {url}")
        assert "localhost" in url
        assert "0.0.0.0" not in url

    def test_explicit_host_preserved(self):
        print("Action: build_base_url with explicit host")
        from menubar import build_base_url

        url = build_base_url("192.168.1.5", 3000, True)
        print(f"url: {url}")
        assert url == "https://192.168.1.5:3000"

    def test_ipv6_wildcard_displayed_as_localhost(self):
        print("Action: build_base_url with :: host")
        from menubar import build_base_url

        url = build_base_url("::", 8000, False)
        print(f"url: {url}")
        assert url == "http://localhost:8000"


class TestBuildLaunchAgentPlist:
    """Tests for build_launch_agent_plist()."""

    def test_plist_contains_required_keys(self):
        print("Setup: building plist payload")
        from menubar import build_launch_agent_plist, LAUNCH_AGENT_LABEL

        payload = build_launch_agent_plist(LAUNCH_AGENT_LABEL, Path("/proj"), Path("/tmp/x.log"))
        print(f"payload keys: {sorted(payload.keys())}")
        for key in ("Label", "ProgramArguments", "RunAtLoad", "KeepAlive", "WorkingDirectory"):
            assert key in payload, f"missing key: {key}"

    def test_plist_label_matches(self):
        from menubar import build_launch_agent_plist, LAUNCH_AGENT_LABEL

        payload = build_launch_agent_plist(LAUNCH_AGENT_LABEL, Path("/proj"), Path("/tmp/x.log"))
        print(f"Label: {payload['Label']}")
        assert payload["Label"] == LAUNCH_AGENT_LABEL

    def test_plist_program_arguments_use_venv_python_and_menubar(self):
        from menubar import build_launch_agent_plist

        payload = build_launch_agent_plist("lbl", Path("/proj"), Path("/tmp/x.log"))
        args = payload["ProgramArguments"]
        print(f"args: {args}")
        assert args[0] == "/proj/.venv/bin/python"
        assert args[1] == "/proj/menubar.py"

    def test_plist_roundtrips_through_plistlib(self):
        from menubar import build_launch_agent_plist, LAUNCH_AGENT_LABEL

        payload = build_launch_agent_plist(LAUNCH_AGENT_LABEL, Path("/proj"), Path("/tmp/x.log"))
        encoded = plistlib.dumps(payload)
        decoded = plistlib.loads(encoded)
        print(f"decoded == payload: {decoded == payload}")
        assert decoded == payload

    def test_plist_log_paths_set(self):
        from menubar import build_launch_agent_plist

        payload = build_launch_agent_plist("lbl", Path("/proj"), Path("/tmp/gw.log"))
        print(f"stdout: {payload['StandardOutPath']}, stderr: {payload['StandardErrorPath']}")
        assert payload["StandardOutPath"] == "/tmp/gw.log"
        assert payload["StandardErrorPath"] == "/tmp/gw.log"


class TestGatewayServerThread:
    """Tests for GatewayServerThread lifecycle (server never really started)."""

    def _make_thread(self):
        from menubar import GatewayServerThread

        with patch("menubar.uvicorn.Server") as mock_server_cls, patch(
            "menubar.uvicorn.Config"
        ) as mock_config_cls:
            mock_server = MagicMock()
            mock_server.started = False
            mock_server_cls.return_value = mock_server

            def run_side_effect():
                # simulate server marking itself as started shortly after run()
                mock_server.started = True

            mock_server.run.side_effect = run_side_effect
            thread = GatewayServerThread("127.0.0.1", 3000, "", "")
            yield thread, mock_server, mock_config_cls

    def test_initial_state_not_running(self, stop_real_threads):
        for thread, _, _ in self._make_thread():
            print(f"is_running: {thread.is_running}")
            assert thread.is_running is False

    def test_start_creates_server_with_tls_disabled(self, stop_real_threads):
        for thread, mock_server, mock_config in self._make_thread():
            print("Action: start()")
            thread.start()
            assert thread._thread is not None
            thread._thread.join(timeout=5)
            print(f"config kwargs: {mock_config.call_args}")
            kwargs = mock_config.call_args.kwargs
            assert kwargs["ssl_certfile"] is None
            assert kwargs["ssl_keyfile"] is None

    def test_start_passes_tls_files_when_configured(self, stop_real_threads):
        from menubar import GatewayServerThread

        with patch("menubar.uvicorn.Server") as mock_server_cls, patch("menubar.uvicorn.Config") as mock_config:
            mock_server_cls.return_value = MagicMock(started=False)
            thread = GatewayServerThread("127.0.0.1", 3000, "/cert.pem", "/key.pem")
            thread.start()
            thread._thread.join(timeout=5)
            kwargs = mock_config.call_args.kwargs
            print(f"certfile: {kwargs['ssl_certfile']}, keyfile: {kwargs['ssl_keyfile']}")
            assert kwargs["ssl_certfile"] == "/cert.pem"
            assert kwargs["ssl_keyfile"] == "/key.pem"

    def test_start_is_idempotent(self, stop_real_threads):
        for thread, mock_server, _ in self._make_thread():
            # Keep the mocked run() alive so the thread survives to the second call,
            # matching real uvicorn behavior where run() blocks until shutdown.
            mock_server.run.side_effect = None
            mock_server.run.return_value = None
            started = threading.Event()

            def blocking_run():
                mock_server.started = True
                started.set()
                threading.Event().wait(timeout=5)

            mock_server.run.side_effect = blocking_run
            print("Action: start() twice")
            thread.start()
            assert started.wait(timeout=5), "mock server never started"
            first_thread = thread._thread
            thread.start()
            print(f"same thread preserved: {thread._thread is first_thread}")
            assert thread._thread is first_thread
            thread.stop()

    def test_stop_signals_should_exit(self, stop_real_threads):
        for thread, mock_server, _ in self._make_thread():
            print("Action: start() then stop()")
            thread.start()
            thread.stop()
            print(f"should_exit: {mock_server.should_exit}")
            assert mock_server.should_exit is True
            assert thread._server is None
            assert thread._thread is None

    def test_stop_without_start_is_safe(self, stop_real_threads):
        for thread, _, _ in self._make_thread():
            print("Action: stop() without start()")
            thread.stop()  # must not raise

    def test_is_running_true_after_started(self, stop_real_threads):
        for thread, _, _ in self._make_thread():
            thread.start()
            thread._thread.join(timeout=5)
            print(f"is_running after start: {thread.is_running}")
            assert thread.is_running is True
            thread.stop()

    def test_is_running_false_after_stop(self, stop_real_threads):
        for thread, mock_server, _ in self._make_thread():
            thread.start()
            thread.stop()
            print(f"is_running after stop: {thread.is_running}")
            assert thread.is_running is False


class TestKiroGatewayApp:
    """Tests for KiroGatewayApp menu wiring and state sync (no GUI event loop)."""

    def _make_app(self):
        from menubar import KiroGatewayApp

        with patch.object(KiroGatewayApp, "_autostart"), patch.object(
            KiroGatewayApp, "_sync_login_item_state"
        ):
            app = KiroGatewayApp.__new__(KiroGatewayApp)
            app.server_thread = MagicMock()
            app.server_thread.is_running = False
            app.server_thread.is_transitioning = False
            app.status_item = MagicMock()
            app.toggle_item = MagicMock()
            app.login_item = MagicMock()
            app.base_url = "https://localhost:3000"
            app.icon = None
            app._template = True
            app.title = None
            # bind real sync methods
            import menubar

            app._sync_ui = menubar.KiroGatewayApp._sync_ui.__get__(app)
            app._sync_login_item_state = MagicMock()
            yield app

    def test_sync_ui_stopped_state(self):
        for app in self._make_app():
            print("Action: _sync_ui with server stopped")
            app._sync_ui()
            print(f"toggle title: {app.toggle_item.title}")
            assert app.toggle_item.title == "Start"
            assert "Stopped" in app.status_item.title

    def test_sync_ui_running_state(self):
        for app in self._make_app():
            app.server_thread.is_running = True
            print("Action: _sync_ui with server running")
            app._sync_ui()
            print(f"toggle title: {app.toggle_item.title}")
            assert app.toggle_item.title == "Stop"
            assert "Running" in app.status_item.title

    def test_sync_ui_sets_running_icon(self):
        for app in self._make_app():
            app.server_thread.is_running = True
            print("Action: _sync_ui sets running icon")
            app._sync_ui()
            from menubar import ICON_RUNNING
            print(f"icon: {app.icon}")
            assert app.icon == ICON_RUNNING

    def test_sync_ui_sets_stopped_icon(self):
        for app in self._make_app():
            app.server_thread.is_running = False
            app.server_thread.is_transitioning = False
            print("Action: _sync_ui sets stopped icon")
            app._sync_ui()
            from menubar import ICON_STOPPED
            print(f"icon: {app.icon}")
            assert app.icon == ICON_STOPPED

    def test_sync_ui_clears_title_text(self):
        for app in self._make_app():
            app.server_thread.is_running = True
            app.title = "some old text"
            print("Action: _sync_ui must clear title (icon-only display)")
            app._sync_ui()
            print(f"title: {app.title}")
            assert app.title is None

    def test_sync_ui_transitioning_state(self):
        for app in self._make_app():
            app.server_thread.is_running = False
            app.server_thread.is_transitioning = True
            print("Action: _sync_ui while starting")
            app._sync_ui()
            print(f"status: {app.status_item.title}")
            assert "Starting" in app.status_item.title
            assert app.toggle_item.title == "Start"

    def test_on_toggle_starts_when_stopped(self):
        for app in self._make_app():
            app.server_thread.is_running = False
            app.server_thread._thread = None
            print("Action: on_toggle while stopped")
            app.on_toggle(app.toggle_item)
            print(f"start called: {app.server_thread.start.called}")
            assert app.server_thread.start.called

    def test_on_toggle_stops_when_running(self):
        for app in self._make_app():
            app.server_thread.is_running = True
            thread_mock = MagicMock()
            thread_mock.is_alive.return_value = True
            app.server_thread._thread = thread_mock
            print("Action: on_toggle while running")
            app.on_toggle(app.toggle_item)
            print(f"stop called: {app.server_thread.stop.called}")
            assert app.server_thread.stop.called

    def test_on_copy_url_uses_pbcopy(self):
        for app in self._make_app():
            with patch("menubar.subprocess.run") as mock_run:
                print("Action: on_copy_url")
                app.on_copy_url(None)
                args, kwargs = mock_run.call_args
                print(f"command: {args[0]}, input: {kwargs.get('input')}")
                assert args[0] == ["pbcopy"]
                assert kwargs["input"] == b"https://localhost:3000"

    def test_on_open_logs_touches_and_opens_log_file(self):
        for app in self._make_app():
            from menubar import LOG_FILE

            with patch("menubar.subprocess.run") as mock_run, patch.object(Path, "touch") as mock_touch:
                print("Action: on_open_logs")
                app.on_open_logs(None)
                args, _ = mock_run.call_args
                print(f"open target: {args[0]}")
                assert args[0] == ["open", str(LOG_FILE)]
                assert mock_touch.called

    def test_login_state_detection(self):
        for app in self._make_app():
            with patch.object(Path, "exists", return_value=False):
                print(f"login enabled (no plist): {app._is_login_enabled()}")
                assert app._is_login_enabled() is False

    def test_quit_stops_server(self):
        for app in self._make_app():
            import menubar

            app.on_quit = menubar.KiroGatewayApp.on_quit.__get__(app)
            with patch("menubar.rumps.quit_application"):
                print("Action: on_quit")
                app.on_quit(None)
                print(f"stop called: {app.server_thread.stop.called}")
                assert app.server_thread.stop.called
