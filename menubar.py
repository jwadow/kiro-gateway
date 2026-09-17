# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
macOS menu bar application for Kiro Gateway.

Runs the uvicorn server in a background thread and exposes controls via a
menu bar icon: start/stop, copy URL, open logs, launch at login, quit.

Usage:
    .venv/bin/python menubar.py
"""

import logging
import subprocess
import sys
import threading
from pathlib import Path

import rumps
import uvicorn

from kiro.config import SERVER_HOST, SERVER_PORT, SSL_CERTFILE, SSL_KEYFILE
from kiro.env_file import default_env_path, read_env, update_env_value
from kiro.settings_window import SettingsWindowController
from main import app as gateway_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("kiro.menubar")

PROJECT_DIR = Path(__file__).resolve().parent
LOG_FILE = Path("/tmp/kiro-gw.log")
LAUNCH_AGENT_LABEL = "dev.kiro.gateway.menubar"


def _find_icon_dir() -> Path:
    """Locate the icon directory in both source-tree and py2app bundle layouts."""
    candidates = [
        PROJECT_DIR / "kiro" / "resources",  # source tree: menubar.py at project root
        PROJECT_DIR / "resources",  # py2app: copied flat into Contents/Resources
        PROJECT_DIR / "lib" / "python3.11" / "kiro" / "resources",  # py2app: kiro package copy
    ]
    for candidate in candidates:
        if (candidate / "menubar-ghost.png").is_file():
            return candidate
    return candidates[0]


ICON_DIR = _find_icon_dir()
ICON_RUNNING = str(ICON_DIR / "menubar-ghost.png")
ICON_STOPPED = str(ICON_DIR / "menubar-ghost-dim.png")
ICON_STARTING = ICON_STOPPED

EDITABLE_ENV_KEYS = (
    "PROXY_API_KEY",
    "SERVER_PORT",
    "SERVER_HOST",
    "SSL_CERTFILE",
    "SSL_KEYFILE",
    "KIRO_CREDS_FILE",
    "KIRO_CLI_DB_FILE",
    "KIRO_API_REGION",
    "VPN_PROXY_URL",
    "DEBUG_MODE",
)

EDITABLE_ENV_LABELS = {
    "PROXY_API_KEY":   "API Key",
    "SERVER_PORT":     "Port",
    "SERVER_HOST":     "Bind Host",
    "SSL_CERTFILE":    "TLS Cert File",
    "SSL_KEYFILE":     "TLS Key File",
    "KIRO_CREDS_FILE": "Kiro Creds File",
    "KIRO_CLI_DB_FILE": "Kiro CLI DB",
    "KIRO_API_REGION": "API Region",
    "VPN_PROXY_URL":   "VPN Proxy URL",
    "DEBUG_MODE":      "Debug Mode",
}


def build_base_url(host: str, port: int, ssl_enabled: bool) -> str:
    """Build the externally visible base URL for display and copying."""
    scheme = "https" if ssl_enabled else "http"
    display_host = "localhost" if host in ("0.0.0.0", "::") else host
    return f"{scheme}://{display_host}:{port}"


def build_launch_agent_plist(label: str, project_dir: Path, log_file: Path) -> dict:
    """Build the LaunchAgent plist payload for launch-at-login."""
    return {
        "Label": label,
        "ProgramArguments": [
            str(project_dir / ".venv" / "bin" / "python"),
            str(project_dir / "menubar.py"),
        ],
        "WorkingDirectory": str(project_dir),
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(log_file),
        "StandardErrorPath": str(log_file),
    }


class GatewayServerThread:
    """Runs a uvicorn server in a daemon thread with async start/stop lifecycle.

    stop() signals shutdown and returns immediately (the join happens on a
    helper thread) so menu callbacks never block the NSApplication main loop.
    """

    def __init__(self, host: str, port: int, ssl_certfile: str, ssl_keyfile: str):
        self._host = host
        self._port = port
        self._ssl_certfile = ssl_certfile
        self._ssl_keyfile = ssl_keyfile
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._server is not None and self._server.started

    @property
    def is_transitioning(self) -> bool:
        return self._server is not None and not self._server.started

    def start(self) -> None:
        """Start the server thread. No-op if already running or starting."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            config = uvicorn.Config(
                gateway_app,
                host=self._host,
                port=self._port,
                ssl_certfile=self._ssl_certfile or None,
                ssl_keyfile=self._ssl_keyfile or None,
                log_config=None,
                workers=1,
            )
            self._server = uvicorn.Server(config)
            self._thread = threading.Thread(
                target=self._server.run, name="kiro-gateway-uvicorn", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        """Signal shutdown without blocking the caller."""
        with self._lock:
            if self._server is None:
                return
            server = self._server
            thread = self._thread
            self._server = None
            self._thread = None
        server.should_exit = True

        def reap() -> None:
            if thread is not None:
                thread.join(timeout=15)

        threading.Thread(target=reap, name="kiro-gateway-shutdown", daemon=True).start()


class KiroGatewayApp(rumps.App):
    """Menu bar app controlling the Kiro Gateway server."""

    def __init__(self) -> None:
        super().__init__("👻", icon=ICON_STOPPED, template=True, quit_button=None)
        self.base_url = build_base_url(SERVER_HOST, SERVER_PORT, bool(SSL_CERTFILE))
        self.server_thread = GatewayServerThread(SERVER_HOST, SERVER_PORT, SSL_CERTFILE, SSL_KEYFILE)
        self.env_path = default_env_path()
        self.status_item = rumps.MenuItem("Status: Starting…", callback=None)
        self.toggle_item = rumps.MenuItem("Stop", callback=self.on_toggle)
        self.url_item = rumps.MenuItem("Copy URL", callback=self.on_copy_url)
        self.logs_item = rumps.MenuItem("Open Logs", callback=self.on_open_logs)
        self.settings_item = rumps.MenuItem("Settings…", callback=self.on_edit_env_key)
        self.restart_hint_item = rumps.MenuItem("Restart to Apply", callback=self.on_restart)
        self.login_item = rumps.MenuItem("Launch at Login", callback=self.on_toggle_login)
        self.quit_item = rumps.MenuItem("Quit", callback=self.on_quit)
        self.menu = [
            self.status_item,
            None,
            self.toggle_item,
            self.url_item,
            self.logs_item,
            None,
            self.settings_item,
            None,
            self.login_item,
            None,
            self.quit_item,
        ]
        self._sync_login_item_state()
        self._state_timer = rumps.Timer(self._poll_server_state, 0.5)
        self._state_timer.start()
        self._autostart()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _sync_ui(self) -> None:
        running = self.server_thread.is_running
        transitioning = self.server_thread.is_transitioning
        if running:
            status_label = "Running"
            icon = ICON_RUNNING
        elif transitioning:
            status_label = "Starting…"
            icon = ICON_STARTING
        else:
            status_label = "Stopped"
            icon = ICON_STOPPED
        self.icon = icon
        self.title = None
        self.status_item.title = f"Status: {status_label}"
        self.toggle_item.title = "Stop" if running else "Start"

    def _poll_server_state(self, sender) -> None:
        """Periodically reconcile the menu UI with the actual server state."""
        self._sync_ui()

    def _autostart(self) -> None:
        self.server_thread.start()
        self._sync_ui()

    def _launch_agent_path(self) -> Path:
        return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"

    def _is_login_enabled(self) -> bool:
        return self._launch_agent_path().exists()

    def _sync_login_item_state(self) -> None:
        self.login_item.title = (
            "✓ Launch at Login" if self._is_login_enabled() else "Launch at Login"
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def on_toggle(self, sender: rumps.MenuItem) -> None:
        try:
            log.info("on_toggle clicked: is_running=%s", self.server_thread.is_running)
            if self.server_thread.is_running or self.server_thread.is_transitioning:
                log.info("on_toggle: stopping server")
                self.server_thread.stop()
            else:
                log.info("on_toggle: starting server")
                self.server_thread.start()
        except Exception:
            log.exception("on_toggle failed")
            raise
        self._sync_ui()

    def on_copy_url(self, sender: rumps.MenuItem) -> None:
        subprocess.run(["pbcopy"], input=self.base_url.encode(), check=False)
        try:
            rumps.notification(
                title="Kiro Gateway",
                subtitle=None,
                message=f"Copied: {self.base_url}",
            )
        except RuntimeError:
            # rumps notifications require a bundled app with CFBundleIdentifier;
            # clipboard copy already succeeded, so running from a plain script
            # must not surface this as an error to the user.
            pass

    def on_edit_env_key(self, sender: rumps.MenuItem) -> None:
        """Open the settings window (single panel for all editable keys)."""
        self.open_settings_window()

    def open_settings_window(self) -> None:
        """Show one panel with a field per editable .env key; save on OK."""
        try:
            env_values = read_env(self.env_path)
            controller = SettingsWindowController(
                keys=list(EDITABLE_ENV_KEYS),
                labels=EDITABLE_ENV_LABELS,
                values={k: env_values.get(k, "") for k in EDITABLE_ENV_KEYS},
                on_save=self._apply_env_changes,
            )
            controller.show()
        except Exception:
            log.exception("settings window failed")
            self._offer_restart()

    def _apply_env_changes(self, new_values: dict) -> None:
        """Persist changed values from the settings window and offer restart."""
        changed = False
        for key, value in new_values.items():
            if update_env_value(self.env_path, key, value):
                changed = True
        if changed:
            self._offer_restart()

    def on_restart(self, sender: rumps.MenuItem) -> None:
        """Restart the whole app process so new .env values are picked up."""
        self.server_thread.stop()
        subprocess.Popen([sys.executable, str(PROJECT_DIR / "menubar.py")])
        rumps.quit_application()

    def _offer_restart(self) -> None:
        window = rumps.Window(
            message="Settings saved.\nRestart the gateway now to apply?",
            title="Kiro Gateway",
            ok="Restart Now",
            cancel="Later",
        )
        try:
            response = window.run()
        except Exception:
            return
        if response.clicked:
            self.on_restart(self.restart_hint_item)

    def on_open_logs(self, sender: rumps.MenuItem) -> None:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOG_FILE.touch(exist_ok=True)
        subprocess.run(["open", str(LOG_FILE)], check=False)

    def on_toggle_login(self, sender: rumps.MenuItem) -> None:
        plist_path = self._launch_agent_path()
        if self._is_login_enabled():
            subprocess.run(
                ["launchctl", "bootout", f"gui/{rumps.os.getuid()}/{LAUNCH_AGENT_LABEL}"],
                capture_output=True,
                check=False,
            )
            plist_path.unlink(missing_ok=True)
        else:
            import plistlib

            plist_path.parent.mkdir(parents=True, exist_ok=True)
            payload = build_launch_agent_plist(LAUNCH_AGENT_LABEL, PROJECT_DIR, LOG_FILE)
            with open(plist_path, "wb") as f:
                plistlib.dump(payload, f)
            subprocess.run(
                ["launchctl", "bootstrap", f"gui/{rumps.os.getuid()}", str(plist_path)],
                capture_output=True,
                check=False,
            )
        self._sync_login_item_state()

    def on_quit(self, sender: rumps.MenuItem) -> None:
        self.server_thread.stop()
        rumps.quit_application()


def main() -> None:
    KiroGatewayApp().run()


if __name__ == "__main__":
    main()
