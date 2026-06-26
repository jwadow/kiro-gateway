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
Cross-platform helpers for inspecting and freeing the server port.

These power the ``--stop`` and ``--force`` CLI options so a stuck/orphaned
gateway process can be stopped without manually running ``lsof``/``kill``.

Only processes *listening* on the exact target port are considered, so we never
touch unrelated processes.
"""

import os
import socket
import subprocess
import time
from typing import List

from loguru import logger


def is_port_in_use(host: str, port: int) -> bool:
    """
    Check whether a TCP port is already bound on the given host.

    Uses a bind test (the same operation the server performs at startup), so a
    True result reliably predicts an "address already in use" failure.

    Args:
        host: Host address the server would bind to (e.g. "0.0.0.0").
        port: TCP port number.

    Returns:
        True if the port cannot be bound (already in use), False otherwise.
    """
    # "0.0.0.0" binds all interfaces; test against that to mirror the server.
    bind_host = host if host not in ("", "*") else "0.0.0.0"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((bind_host, port))
            return False
        except OSError:
            return True


def find_listening_pids(port: int) -> List[int]:
    """
    Find process IDs listening on the given TCP port.

    Cross-platform: uses ``lsof`` on macOS/Linux and ``netstat`` on Windows.
    The current process is excluded so callers never target themselves.

    Args:
        port: TCP port number.

    Returns:
        Sorted list of PIDs listening on the port (empty if none, or if the
        platform tool is unavailable).
    """
    pids: set[int] = set()

    try:
        if os.name == "nt":
            result = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"],
                capture_output=True, text=True, timeout=10,
            )
            needle = f":{port}"
            for line in result.stdout.splitlines():
                if needle in line and "LISTENING" in line.upper():
                    parts = line.split()
                    if parts:
                        try:
                            pids.add(int(parts[-1]))
                        except ValueError:
                            continue
        else:
            result = subprocess.run(
                ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
                capture_output=True, text=True, timeout=10,
            )
            for token in result.stdout.split():
                try:
                    pids.add(int(token))
                except ValueError:
                    continue
    except FileNotFoundError:
        logger.warning(
            "Could not inspect port {}: required tool ({}) not found.",
            port, "netstat" if os.name == "nt" else "lsof",
        )
    except subprocess.TimeoutExpired:
        logger.warning("Timed out inspecting processes on port {}.", port)

    pids.discard(os.getpid())
    return sorted(pids)


def _terminate_pid(pid: int, timeout: float) -> bool:
    """
    Terminate a single PID gracefully, escalating to a forceful kill.

    Args:
        pid: Process ID to terminate.
        timeout: Seconds to wait for graceful exit before forcing.

    Returns:
        True if the process is gone after the attempt, False otherwise.
    """
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True, text=True,
        )
        return True

    # POSIX: SIGTERM, wait, then SIGKILL.
    try:
        os.kill(pid, 15)  # SIGTERM
    except ProcessLookupError:
        return True
    except PermissionError:
        logger.error("No permission to stop PID {} (try running with sufficient privileges).", pid)
        return False

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)  # Probe: raises if process is gone.
        except ProcessLookupError:
            return True
        time.sleep(0.1)

    # Still alive - force kill.
    try:
        os.kill(pid, 9)  # SIGKILL
    except ProcessLookupError:
        return True
    return True


def free_port(port: int, timeout: float = 5.0) -> List[int]:
    """
    Stop every process listening on the given port.

    Args:
        port: TCP port to free.
        timeout: Seconds to wait for each process to exit gracefully.

    Returns:
        List of PIDs that were stopped (empty if the port was already free).
    """
    pids = find_listening_pids(port)
    if not pids:
        return []

    stopped: List[int] = []
    for pid in pids:
        logger.info("Stopping process {} listening on port {}...", pid, port)
        if _terminate_pid(pid, timeout):
            stopped.append(pid)
    return stopped
