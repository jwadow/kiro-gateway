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
    # As installed tool
    kiro-gateway
    kiro-gateway --port 9000
    kiro-gateway --host 127.0.0.1 --port 9000

    # Via python -m
    python -m kiro
"""

import argparse

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
    _warn_timeout_configuration,
)


def parse_cli_args() -> argparse.Namespace:
    """Parse command-line arguments for server configuration.

    CLI arguments have the highest priority, overriding both
    environment variables and default values.

    Returns:
        Parsed arguments namespace with host and port values.
    """
    parser = argparse.ArgumentParser(
        description=f"{APP_TITLE} - {APP_DESCRIPTION}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Configuration Priority (highest to lowest):
  1. CLI arguments (--host, --port)
  2. Environment variables (SERVER_HOST, SERVER_PORT)
  3. Default values (0.0.0.0:8000)

Examples:
  kiro-gateway                            # Use defaults or env vars
  kiro-gateway --port 9000                # Override port only
  kiro-gateway --host 127.0.0.1           # Local connections only
  kiro-gateway -H 0.0.0.0 -p 8080        # Short form

  SERVER_PORT=9000 kiro-gateway           # Via environment
        """
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

    return parser.parse_args()


def resolve_server_config(args: argparse.Namespace) -> tuple[str, int]:
    """Resolve final server configuration using priority hierarchy.

    Priority (highest to lowest):
    1. CLI arguments (--host, --port)
    2. Environment variables (SERVER_HOST, SERVER_PORT)
    3. Default values (0.0.0.0:8000)

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
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    display_host = "localhost" if host == "0.0.0.0" else host
    url = f"http://{display_host}:{port}"

    print()
    print(f"  {WHITE}{BOLD}👻 {APP_TITLE} v{APP_VERSION}{RESET}")
    print()
    print(f"  {WHITE}Server running at:{RESET}")
    print(f"  {GREEN}{BOLD}➜  {url}{RESET}")
    print()
    print(f"  {DIM}API Docs:      {url}/docs{RESET}")
    print(f"  {DIM}Health Check:  {url}/health{RESET}")
    print()
    print(f"  {DIM}{'─' * 48}{RESET}")
    print(f"  {WHITE}💬 Found a bug? Need help? Have questions?{RESET}")
    print(f"  {YELLOW}➜  https://github.com/jwadow/kiro-gateway/issues{RESET}")
    print(f"  {DIM}{'─' * 48}{RESET}")
    print()


def main() -> None:
    """Entry point for the kiro-gateway CLI.

    Validates configuration, parses CLI arguments, resolves server
    settings, and starts the uvicorn server.
    """
    validate_configuration()
    _warn_timeout_configuration()

    args = parse_cli_args()
    final_host, final_port = resolve_server_config(args)

    print_startup_banner(final_host, final_port)

    logger.info(f"Starting Uvicorn server on {final_host}:{final_port}...")

    uvicorn.run(
        app,
        host=final_host,
        port=final_port,
    )
