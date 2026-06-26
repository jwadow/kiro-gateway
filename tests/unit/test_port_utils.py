# -*- coding: utf-8 -*-

"""
Unit tests for kiro.port_utils.

Covers port-in-use detection, listening-PID discovery (lsof/netstat parsing,
cross-platform), self-exclusion, graceful termination/escalation, and free_port.
All subprocess and signal interactions are mocked - no real processes are killed.
"""

import os
import socket
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from kiro.port_utils import (
    is_port_in_use,
    find_listening_pids,
    free_port,
    _terminate_pid,
)


class TestIsPortInUse:
    """Tests for is_port_in_use (real local sockets, no network)."""

    def test_free_port_is_not_in_use(self):
        """A port nobody is bound to reports not-in-use."""
        # Find a definitely-free port by binding then releasing it.
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
        s.close()
        print(f"Testing freed port {free}")
        assert is_port_in_use("127.0.0.1", free) is False

    def test_bound_port_is_in_use(self):
        """A port held by a live listener reports in-use."""
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen()
        port = s.getsockname()[1]
        try:
            print(f"Testing bound port {port}")
            assert is_port_in_use("127.0.0.1", port) is True
        finally:
            s.close()

    def test_wildcard_host_is_normalized(self):
        """An empty/wildcard host is treated as 0.0.0.0 without error."""
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
        s.close()
        # Should not raise and should report free.
        assert is_port_in_use("", free) is False


class TestFindListeningPids:
    """Tests for find_listening_pids parsing and self-exclusion."""

    def test_parses_lsof_output(self):
        """lsof -t output (one PID per line) is parsed to ints."""
        fake = MagicMock(stdout="4242\n4243\n")
        with patch("kiro.port_utils.os.name", "posix"):
            with patch("kiro.port_utils.subprocess.run", return_value=fake) as run:
                with patch("kiro.port_utils.os.getpid", return_value=1):
                    pids = find_listening_pids(9000)
        print(f"PIDs: {pids}, cmd: {run.call_args.args[0]}")
        assert pids == [4242, 4243]
        assert run.call_args.args[0][0] == "lsof"

    def test_excludes_current_process(self):
        """The current PID is never returned (no self-kill)."""
        fake = MagicMock(stdout="111\n222\n")
        with patch("kiro.port_utils.os.name", "posix"):
            with patch("kiro.port_utils.subprocess.run", return_value=fake):
                with patch("kiro.port_utils.os.getpid", return_value=111):
                    pids = find_listening_pids(9000)
        print(f"PIDs: {pids}")
        assert pids == [222]

    def test_parses_windows_netstat_output(self):
        """Windows netstat LISTENING lines are parsed for the PID (last column)."""
        netstat = (
            "  Proto  Local Address          Foreign Address        State           PID\n"
            "  TCP    0.0.0.0:9000           0.0.0.0:0              LISTENING       7777\n"
            "  TCP    0.0.0.0:8000           0.0.0.0:0              LISTENING       8888\n"
        )
        fake = MagicMock(stdout=netstat)
        with patch("kiro.port_utils.os.name", "nt"):
            with patch("kiro.port_utils.subprocess.run", return_value=fake) as run:
                with patch("kiro.port_utils.os.getpid", return_value=1):
                    pids = find_listening_pids(9000)
        print(f"PIDs: {pids}, cmd: {run.call_args.args[0]}")
        assert pids == [7777]  # only the :9000 listener
        assert run.call_args.args[0][0] == "netstat"

    def test_missing_tool_returns_empty(self):
        """If lsof/netstat isn't installed, return [] instead of crashing."""
        with patch("kiro.port_utils.subprocess.run", side_effect=FileNotFoundError()):
            pids = find_listening_pids(9000)
        assert pids == []

    def test_timeout_returns_empty(self):
        """A hung inspection command degrades to []."""
        with patch(
            "kiro.port_utils.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="lsof", timeout=10),
        ):
            pids = find_listening_pids(9000)
        assert pids == []

    def test_ignores_non_integer_tokens(self):
        """Garbage tokens in tool output are skipped."""
        fake = MagicMock(stdout="123\nnot_a_pid\n456\n")
        with patch("kiro.port_utils.os.name", "posix"):
            with patch("kiro.port_utils.subprocess.run", return_value=fake):
                with patch("kiro.port_utils.os.getpid", return_value=1):
                    pids = find_listening_pids(9000)
        assert pids == [123, 456]


class TestTerminatePid:
    """Tests for _terminate_pid graceful/forceful behavior (POSIX)."""

    def test_graceful_termination(self):
        """SIGTERM that takes effect (process gone) returns True without SIGKILL."""
        calls = []

        def fake_kill(pid, sig):
            calls.append(sig)
            # SIGTERM (15) then probe (0): probe raises -> process gone.
            if sig == 0:
                raise ProcessLookupError()

        with patch("kiro.port_utils.os.name", "posix"):
            with patch("kiro.port_utils.os.kill", side_effect=fake_kill):
                result = _terminate_pid(999, timeout=1.0)
        print(f"signals: {calls}")
        assert result is True
        assert 15 in calls   # SIGTERM sent
        assert 9 not in calls  # never escalated

    def test_force_kill_when_still_alive(self):
        """A process that ignores SIGTERM gets SIGKILL."""
        sent = []

        def fake_kill(pid, sig):
            sent.append(sig)
            # Probe (0) always succeeds -> still alive until SIGKILL.

        with patch("kiro.port_utils.os.name", "posix"):
            with patch("kiro.port_utils.os.kill", side_effect=fake_kill):
                with patch("kiro.port_utils.time.monotonic", side_effect=[0.0, 0.05, 1.0, 2.0]):
                    with patch("kiro.port_utils.time.sleep"):
                        result = _terminate_pid(999, timeout=0.1)
        print(f"signals: {sent}")
        assert result is True
        assert 9 in sent  # SIGKILL escalation happened

    def test_already_gone(self):
        """If the process is already gone, SIGTERM raising is treated as success."""
        with patch("kiro.port_utils.os.name", "posix"):
            with patch("kiro.port_utils.os.kill", side_effect=ProcessLookupError()):
                result = _terminate_pid(999, timeout=1.0)
        assert result is True

    def test_permission_error_returns_false(self):
        """Lack of permission to signal the process is reported as failure."""
        with patch("kiro.port_utils.os.name", "posix"):
            with patch("kiro.port_utils.os.kill", side_effect=PermissionError()):
                result = _terminate_pid(999, timeout=1.0)
        assert result is False

    def test_windows_uses_taskkill(self):
        """On Windows, termination shells out to taskkill /F."""
        with patch("kiro.port_utils.os.name", "nt"):
            with patch("kiro.port_utils.subprocess.run") as run:
                result = _terminate_pid(999, timeout=1.0)
        assert result is True
        assert run.call_args.args[0][:1] == ["taskkill"]


class TestFreePort:
    """Tests for free_port orchestration."""

    def test_no_listeners_returns_empty(self):
        """Freeing an already-free port stops nothing."""
        with patch("kiro.port_utils.find_listening_pids", return_value=[]):
            assert free_port(9000) == []

    def test_stops_all_listeners(self):
        """Every listening PID is terminated and reported."""
        with patch("kiro.port_utils.find_listening_pids", return_value=[10, 20]):
            with patch("kiro.port_utils._terminate_pid", return_value=True) as term:
                stopped = free_port(9000)
        print(f"stopped: {stopped}")
        assert stopped == [10, 20]
        assert term.call_count == 2

    def test_excludes_failed_terminations(self):
        """PIDs that could not be stopped are not reported as stopped."""
        with patch("kiro.port_utils.find_listening_pids", return_value=[10, 20]):
            with patch("kiro.port_utils._terminate_pid", side_effect=[True, False]):
                stopped = free_port(9000)
        print(f"stopped: {stopped}")
        assert stopped == [10]
