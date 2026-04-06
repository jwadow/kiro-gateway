# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Kiro Gateway — CLI entry point.

Provides the ``main()`` function used by the ``kiro-gateway`` console script
and by ``python -m kiro``. Handles argument parsing, configuration resolution,
and uvicorn server startup.

Usage:
    # Start the server (runs setup wizard on first launch if unconfigured)
    kiro-gateway
    kiro-gateway --port 9000
    kiro-gateway --host 127.0.0.1 --port 9000

    # Manage configuration
    kiro-gateway config               # show current config
    kiro-gateway config --edit        # re-run setup wizard
    kiro-gateway config --reset       # delete saved config
    kiro-gateway config --show-path   # print config file path

    # Via python -m
    python -m kiro
"""

import argparse
import sys

import uvicorn
from loguru import logger

from kiro.app import app, validate_configuration
from kiro.config import (
    APP_TITLE,
    APP_DESCRIPTION,
    APP_VERSION,
    SERVER_HOST,
    SERVER_PORT,
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    USER_CONFIG_FILE,
    _warn_timeout_configuration,
)
from kiro.config_editor import ConfigEditor
from kiro.setup_wizard import ConsoleWizardIO, SetupWizard, save_config

# ---------------------------------------------------------------------------
# ANSI color constants (shared across banner and config display)
# ---------------------------------------------------------------------------

_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_WHITE = "\033[97m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"

# Sensitive env var names — values are masked in 'config' display
_SENSITIVE_KEYS = {"REFRESH_TOKEN", "PROXY_API_KEY"}


def parse_cli_args() -> argparse.Namespace:
    """Parse command-line arguments including the optional 'config' subcommand.

    Subcommands:
        (none)  — start the gateway server
        config  — manage saved configuration

    Returns:
        Parsed arguments namespace. ``args.command`` is ``"config"`` when the
        config subcommand is used, otherwise ``None``.
    """
    parser = argparse.ArgumentParser(
        description=f"{APP_TITLE} - {APP_DESCRIPTION}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Configuration Priority (highest to lowest):
  1. CLI arguments (--host, --port)
  2. Environment variables (SERVER_HOST, SERVER_PORT)
  3. Default values (0.0.0.0:{default_port})

Examples:
  kiro-gateway                            # Use defaults or env vars
  kiro-gateway --port 9000                # Override port only
  kiro-gateway --host 127.0.0.1           # Local connections only
  kiro-gateway -H 0.0.0.0 -p 8080        # Short form
  kiro-gateway config                     # Interactive config editor
  kiro-gateway config --reset             # Delete saved config

  SERVER_PORT=9000 kiro-gateway           # Via environment
        """.format(default_port=DEFAULT_SERVER_PORT)
    )

    parser.add_argument(
        "-H", "--host",
        type=str,
        default=None,
        metavar="HOST",
        help=f"Server host address (default: {DEFAULT_SERVER_HOST}, env: SERVER_HOST)"
    )

    parser.add_argument(
        "-p", "--port",
        type=int,
        default=None,
        metavar="PORT",
        help=f"Server port (default: {DEFAULT_SERVER_PORT}, env: SERVER_PORT)"
    )

    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"%(prog)s {APP_VERSION}"
    )

    subparsers = parser.add_subparsers(dest="command")

    config_parser = subparsers.add_parser(
        "config",
        help="Manage gateway configuration",
        description="Interactively view and edit the saved kiro-gateway configuration.",
    )
    config_parser.add_argument(
        "--reset",
        action="store_true",
        help=f"Delete the saved config file ({USER_CONFIG_FILE})",
    )
    config_parser.add_argument(
        "--show-path",
        action="store_true",
        help="Print the path to the saved config file and exit",
    )

    return parser.parse_args()


def resolve_server_config(args: argparse.Namespace) -> tuple[str, int]:
    """Resolve final server configuration using priority hierarchy.

    Priority (highest to lowest):
    1. CLI arguments (--host, --port)
    2. Environment variables (SERVER_HOST, SERVER_PORT)
    3. Default values

    Args:
        args: Parsed CLI arguments.

    Returns:
        Tuple of (host, port) with resolved values.
    """
    if args.host is not None:
        final_host = args.host
        host_source = "CLI argument"
    elif SERVER_HOST != DEFAULT_SERVER_HOST:
        final_host = SERVER_HOST
        host_source = "environment variable"
    else:
        final_host = DEFAULT_SERVER_HOST
        host_source = "default"

    if args.port is not None:
        final_port = args.port
        port_source = "CLI argument"
    elif SERVER_PORT != DEFAULT_SERVER_PORT:
        final_port = SERVER_PORT
        port_source = "environment variable"
    else:
        final_port = DEFAULT_SERVER_PORT
        port_source = "default"

    logger.debug(f"Host: {final_host} (from {host_source})")
    logger.debug(f"Port: {final_port} (from {port_source})")

    return final_host, final_port


def print_startup_banner(host: str, port: int) -> None:
    """Print a startup banner with server information.

    Args:
        host: Server host address.
        port: Server port.
    """
    display_host = "localhost" if host == "0.0.0.0" else host
    url = f"http://{display_host}:{port}"

    print()
    print(f"  {_WHITE}{_BOLD}👻 {APP_TITLE} v{APP_VERSION}{_RESET}")
    print()
    print(f"  {_WHITE}Server running at:{_RESET}")
    print(f"  {_GREEN}{_BOLD}➜  {url}{_RESET}")
    print()
    print(f"  {_DIM}API Docs:      {url}/docs{_RESET}")
    print(f"  {_DIM}Health Check:  {url}/health{_RESET}")
    print()
    print(f"  {_DIM}{'─' * 48}{_RESET}")
    print(f"  {_WHITE}💬 Found a bug? Need help? Have questions?{_RESET}")
    print(f"  {_YELLOW}➜  https://github.com/jwadow/kiro-gateway/issues{_RESET}")
    print(f"  {_DIM}{'─' * 48}{_RESET}")
    print()


def _mask_value(key: str, value: str) -> str:
    """Mask sensitive values for display, showing only the first 8 characters.

    Args:
        key: Environment variable name.
        value: The value to potentially mask.

    Returns:
        Masked string if the key is sensitive, otherwise the original value.
    """
    if key in _SENSITIVE_KEYS and len(value) > 8:
        return value[:8] + "****"
    return value


def _show_current_config() -> None:
    """Print the currently active configuration to stdout.

    Reads from the saved config file if it exists, and indicates which
    values are active. Sensitive values are partially masked.
    """
    import os

    print()
    print(f"  {_WHITE}{_BOLD}Kiro Gateway — Current Configuration{_RESET}")
    print(f"  {_DIM}{'─' * 44}{_RESET}")
    print(f"  {_DIM}Config file: {USER_CONFIG_FILE}{_RESET}")
    print()

    keys_to_show = [
        "REFRESH_TOKEN",
        "KIRO_CREDS_FILE",
        "KIRO_CLI_DB_FILE",
        "PROXY_API_KEY",
        "SERVER_HOST",
        "SERVER_PORT",
    ]

    if USER_CONFIG_FILE.exists():
        print(f"  {_GREEN}File exists{_RESET}")
    else:
        print(f"  {_YELLOW}File not found — using environment variables or defaults{_RESET}")

    print()
    for key in keys_to_show:
        value = os.environ.get(key, "")
        if value:
            display = _mask_value(key, value)
            print(f"  {_CYAN}{key}{_RESET} = {display}")
        else:
            print(f"  {_DIM}{key} = (not set){_RESET}")
    print()


def _run_wizard_and_save() -> bool:
    """Run the interactive setup wizard and save the result.

    Returns:
        True if the wizard completed and config was saved, False if aborted.
    """
    wizard = SetupWizard(ConsoleWizardIO())
    config = wizard.run()
    if config:
        save_config(config, USER_CONFIG_FILE)
        return True
    return False


def _reset_config() -> None:
    """Delete the saved user config file after confirmation."""
    if not USER_CONFIG_FILE.exists():
        print(f"  {_YELLOW}No config file found at {USER_CONFIG_FILE}{_RESET}")
        return

    print(f"  {_YELLOW}This will delete: {USER_CONFIG_FILE}{_RESET}")
    answer = input("  Are you sure? [y/N]: ").strip().lower()
    if answer in ("y", "yes"):
        USER_CONFIG_FILE.unlink()
        print(f"  {_GREEN}Config file deleted.{_RESET}")
    else:
        print(f"  {_DIM}Cancelled.{_RESET}")


def handle_config_command(args: argparse.Namespace) -> None:
    """Handle the 'config' subcommand and its flags.

    With no flags, launches the interactive configuration editor.

    Args:
        args: Parsed CLI arguments with config subcommand flags.
    """
    if args.show_path:
        print(str(USER_CONFIG_FILE))
    elif args.reset:
        _reset_config()
    else:
        ConfigEditor(USER_CONFIG_FILE).run()


def main() -> None:
    """Entry point for the kiro-gateway CLI.

    Parses CLI arguments first so the 'config' subcommand works even when
    no credentials are configured. For the default server-start flow,
    validates configuration and launches the setup wizard if needed.
    """
    args = parse_cli_args()

    # config subcommand: manage saved configuration, no server startup needed
    if args.command == "config":
        handle_config_command(args)
        return

    # Server startup flow: validate credentials, run wizard if missing
    if not validate_configuration(silent=True):
        print()
        print(f"  {_YELLOW}No credentials found. Starting setup wizard...{_RESET}")
        print()
        if not _run_wizard_and_save():
            logger.error("Setup wizard aborted. Cannot start server without credentials.")
            sys.exit(1)
        # Config was saved to disk. Re-exec the process so config.py module-level
        # variables (REFRESH_TOKEN, KIRO_CREDS_FILE, etc.) are re-initialized from
        # the newly written .env file. os.environ updates alone are not enough
        # because those variables were already bound at import time.
        import os as _os
        _os.execv(sys.argv[0], sys.argv)
        return  # unreachable in production; guards against mock fall-through in tests

    _warn_timeout_configuration()

    final_host, final_port = resolve_server_config(args)
    print_startup_banner(final_host, final_port)

    logger.info(f"Starting Uvicorn server on {final_host}:{final_port}...")

    uvicorn.run(
        app,
        host=final_host,
        port=final_port,
    )
