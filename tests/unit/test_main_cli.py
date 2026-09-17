# -*- coding: utf-8 -*-

"""
Unit tests for main.py CLI functions.
Tests for parse_cli_args(), resolve_server_config(), and print_startup_banner().
"""

import pytest
import argparse
import sys
from unittest.mock import patch, MagicMock
from io import StringIO


class TestParseCliArgs:
    """Tests for parse_cli_args() function."""
    
    def test_default_values_are_none(self):
        """
        What it does: Verifies that default values for host and port are None.
        Purpose: Ensure that None indicates "use env or default" in priority resolution.
        """
        print("Setup: Importing parse_cli_args...")
        from main import parse_cli_args
        
        print("Action: Calling parse_cli_args with no arguments...")
        with patch.object(sys, 'argv', ['main.py']):
            args = parse_cli_args()
        
        print(f"args.host: {args.host}")
        print(f"args.port: {args.port}")
        print(f"Comparing: Expected host=None, port=None")
        assert args.host is None
        assert args.port is None
    
    def test_port_argument_long_form(self):
        """
        What it does: Verifies that --port argument is parsed correctly.
        Purpose: Ensure long form --port works.
        """
        print("Setup: Importing parse_cli_args...")
        from main import parse_cli_args
        
        print("Action: Calling parse_cli_args with --port 9000...")
        with patch.object(sys, 'argv', ['main.py', '--port', '9000']):
            args = parse_cli_args()
        
        print(f"args.port: {args.port}")
        print(f"Comparing: Expected 9000, Got {args.port}")
        assert args.port == 9000
    
    def test_port_argument_short_form(self):
        """
        What it does: Verifies that -p argument is parsed correctly.
        Purpose: Ensure short form -p works.
        """
        print("Setup: Importing parse_cli_args...")
        from main import parse_cli_args
        
        print("Action: Calling parse_cli_args with -p 8080...")
        with patch.object(sys, 'argv', ['main.py', '-p', '8080']):
            args = parse_cli_args()
        
        print(f"args.port: {args.port}")
        print(f"Comparing: Expected 8080, Got {args.port}")
        assert args.port == 8080
    
    def test_host_argument_long_form(self):
        """
        What it does: Verifies that --host argument is parsed correctly.
        Purpose: Ensure long form --host works.
        """
        print("Setup: Importing parse_cli_args...")
        from main import parse_cli_args
        
        print("Action: Calling parse_cli_args with --host 127.0.0.1...")
        with patch.object(sys, 'argv', ['main.py', '--host', '127.0.0.1']):
            args = parse_cli_args()
        
        print(f"args.host: {args.host}")
        print(f"Comparing: Expected '127.0.0.1', Got '{args.host}'")
        assert args.host == "127.0.0.1"
    
    def test_host_argument_short_form(self):
        """
        What it does: Verifies that -H argument is parsed correctly.
        Purpose: Ensure short form -H works.
        """
        print("Setup: Importing parse_cli_args...")
        from main import parse_cli_args
        
        print("Action: Calling parse_cli_args with -H 192.168.1.1...")
        with patch.object(sys, 'argv', ['main.py', '-H', '192.168.1.1']):
            args = parse_cli_args()
        
        print(f"args.host: {args.host}")
        print(f"Comparing: Expected '192.168.1.1', Got '{args.host}'")
        assert args.host == "192.168.1.1"
    
    def test_both_arguments_together(self):
        """
        What it does: Verifies that both --host and --port can be used together.
        Purpose: Ensure both arguments work simultaneously.
        """
        print("Setup: Importing parse_cli_args...")
        from main import parse_cli_args
        
        print("Action: Calling parse_cli_args with --host 0.0.0.0 --port 3000...")
        with patch.object(sys, 'argv', ['main.py', '--host', '0.0.0.0', '--port', '3000']):
            args = parse_cli_args()
        
        print(f"args.host: {args.host}")
        print(f"args.port: {args.port}")
        assert args.host == "0.0.0.0"
        assert args.port == 3000
    
    def test_short_forms_together(self):
        """
        What it does: Verifies that both -H and -p can be used together.
        Purpose: Ensure short forms work simultaneously.
        """
        print("Setup: Importing parse_cli_args...")
        from main import parse_cli_args
        
        print("Action: Calling parse_cli_args with -H 127.0.0.1 -p 5000...")
        with patch.object(sys, 'argv', ['main.py', '-H', '127.0.0.1', '-p', '5000']):
            args = parse_cli_args()
        
        print(f"args.host: {args.host}")
        print(f"args.port: {args.port}")
        assert args.host == "127.0.0.1"
        assert args.port == 5000


class TestResolveServerConfig:
    """Tests for resolve_server_config() function - priority hierarchy."""
    def test_cli_args_take_priority_over_env(self):
        """
        What it does: Verifies that CLI arguments have highest priority.
        Purpose: Ensure CLI args override environment variables.
        """
        print("Setup: Importing resolve_server_config...")
        from main import resolve_server_config
        
        print("Setup: Creating args with host=127.0.0.1, port=9000...")
        args = argparse.Namespace(host="127.0.0.1", port=9000)
        
        print("Action: Calling resolve_server_config with CLI args...")
        # Even if env vars are set, CLI should win
        with patch('main.SERVER_HOST', '0.0.0.0'), \
             patch('main.SERVER_PORT', 8000), \
             patch('main.DEFAULT_SERVER_HOST', '0.0.0.0'), \
             patch('main.DEFAULT_SERVER_PORT', 8000):
            host, port = resolve_server_config(args)
        
        print(f"Resolved host: {host}")
        print(f"Resolved port: {port}")
        print(f"Comparing: Expected ('127.0.0.1', 9000)")
        assert host == "127.0.0.1"
        assert port == 9000
    
    def test_env_vars_take_priority_over_defaults(self):
        """
        What it does: Verifies that env vars have priority over defaults.
        Purpose: Ensure env vars are used when CLI args are not provided.
        """
        print("Setup: Importing resolve_server_config...")
        from main import resolve_server_config
        
        print("Setup: Creating args with host=None, port=None (no CLI args)...")
        args = argparse.Namespace(host=None, port=None)
        
        print("Action: Calling resolve_server_config with env vars set...")
        # SERVER_HOST and SERVER_PORT are different from defaults
        with patch('main.SERVER_HOST', '192.168.1.100'), \
             patch('main.SERVER_PORT', 3000), \
             patch('main.DEFAULT_SERVER_HOST', '0.0.0.0'), \
             patch('main.DEFAULT_SERVER_PORT', 8000):
            host, port = resolve_server_config(args)
        
        print(f"Resolved host: {host}")
        print(f"Resolved port: {port}")
        print(f"Comparing: Expected ('192.168.1.100', 3000)")
        assert host == "192.168.1.100"
        assert port == 3000
    
    def test_defaults_used_when_nothing_set(self):
        """
        What it does: Verifies that defaults are used when nothing else is set.
        Purpose: Ensure default values work correctly.
        """
        print("Setup: Importing resolve_server_config...")
        from main import resolve_server_config
        
        print("Setup: Creating args with host=None, port=None...")
        args = argparse.Namespace(host=None, port=None)
        
        print("Action: Calling resolve_server_config with defaults...")
        # SERVER_HOST and SERVER_PORT equal to defaults (no env override)
        with patch('main.SERVER_HOST', '0.0.0.0'), \
             patch('main.SERVER_PORT', 8000), \
             patch('main.DEFAULT_SERVER_HOST', '0.0.0.0'), \
             patch('main.DEFAULT_SERVER_PORT', 8000):
            host, port = resolve_server_config(args)
        
        print(f"Resolved host: {host}")
        print(f"Resolved port: {port}")
        print(f"Comparing: Expected ('0.0.0.0', 8000)")
        assert host == "0.0.0.0"
        assert port == 8000
    
    def test_cli_host_only_env_port(self):
        """
        What it does: Verifies mixed priority - CLI host with env port.
        Purpose: Ensure each argument is resolved independently.
        """
        print("Setup: Importing resolve_server_config...")
        from main import resolve_server_config
        
        print("Setup: Creating args with host='127.0.0.1', port=None...")
        args = argparse.Namespace(host="127.0.0.1", port=None)
        
        print("Action: Calling resolve_server_config...")
        with patch('main.SERVER_HOST', '0.0.0.0'), \
             patch('main.SERVER_PORT', 9000), \
             patch('main.DEFAULT_SERVER_HOST', '0.0.0.0'), \
             patch('main.DEFAULT_SERVER_PORT', 8000):
            host, port = resolve_server_config(args)
        
        print(f"Resolved host: {host}")
        print(f"Resolved port: {port}")
        print(f"Comparing: Expected ('127.0.0.1', 9000)")
        assert host == "127.0.0.1"  # From CLI
        assert port == 9000  # From env (different from default)
    
    def test_cli_port_only_env_host(self):
        """
        What it does: Verifies mixed priority - CLI port with env host.
        Purpose: Ensure each argument is resolved independently.
        """
        print("Setup: Importing resolve_server_config...")
        from main import resolve_server_config
        
        print("Setup: Creating args with host=None, port=5000...")
        args = argparse.Namespace(host=None, port=5000)
        
        print("Action: Calling resolve_server_config...")
        with patch('main.SERVER_HOST', '192.168.1.1'), \
             patch('main.SERVER_PORT', 8000), \
             patch('main.DEFAULT_SERVER_HOST', '0.0.0.0'), \
             patch('main.DEFAULT_SERVER_PORT', 8000):
            host, port = resolve_server_config(args)
        
        print(f"Resolved host: {host}")
        print(f"Resolved port: {port}")
        print(f"Comparing: Expected ('192.168.1.1', 5000)")
        assert host == "192.168.1.1"  # From env (different from default)
        assert port == 5000  # From CLI


class TestResolveTlsConfig:
    """Tests for resolve_tls_config() function - TLS priority and validation."""

    def test_no_tls_by_default(self):
        """
        What it does: Verifies TLS is disabled when no CLI args or env vars.
        Purpose: Ensure empty strings (TLS off) are returned by default.
        """
        print("Setup: Importing resolve_tls_config...")
        from main import resolve_tls_config

        print("Setup: Creating args with ssl options None...")
        args = argparse.Namespace(ssl_certfile=None, ssl_keyfile=None)

        print("Action: Calling resolve_tls_config with no env vars...")
        with patch('main.SSL_CERTFILE', ''), patch('main.SSL_KEYFILE', ''):
            certfile, keyfile = resolve_tls_config(args)

        print(f"certfile: {certfile!r}, keyfile: {keyfile!r}")
        assert certfile == ""
        assert keyfile == ""

    def test_env_vars_used_when_no_cli_args(self):
        """
        What it does: Verifies env vars are used when CLI args are None.
        Purpose: Ensure SSL_CERTFILE/SSL_KEYFILE env vars enable TLS.
        """
        print("Setup: Importing resolve_tls_config...")
        from main import resolve_tls_config

        args = argparse.Namespace(ssl_certfile=None, ssl_keyfile=None)

        print("Action: Calling resolve_tls_config with env vars set...")
        with patch('main.SSL_CERTFILE', '/certs/fullchain.pem'), \
             patch('main.SSL_KEYFILE', '/certs/privkey.pem'):
            certfile, keyfile = resolve_tls_config(args)

        print(f"certfile: {certfile}, keyfile: {keyfile}")
        assert certfile == "/certs/fullchain.pem"
        assert keyfile == "/certs/privkey.pem"

    def test_cli_args_take_priority_over_env(self):
        """
        What it does: Verifies CLI args override env vars.
        Purpose: Ensure CLI has highest priority for TLS paths.
        """
        print("Setup: Importing resolve_tls_config...")
        from main import resolve_tls_config

        args = argparse.Namespace(
            ssl_certfile="/cli/cert.pem", ssl_keyfile="/cli/key.pem"
        )

        print("Action: Calling resolve_tls_config with both CLI and env set...")
        with patch('main.SSL_CERTFILE', '/env/cert.pem'), \
             patch('main.SSL_KEYFILE', '/env/key.pem'):
            certfile, keyfile = resolve_tls_config(args)

        print(f"certfile: {certfile}, keyfile: {keyfile}")
        assert certfile == "/cli/cert.pem"
        assert keyfile == "/cli/key.pem"

    def test_only_certfile_raises_error(self):
        """
        What it does: Verifies error when only certfile is provided.
        Purpose: Ensure partial TLS config is rejected, not silently ignored.
        """
        print("Setup: Importing resolve_tls_config...")
        from main import resolve_tls_config

        args = argparse.Namespace(ssl_certfile="/cert.pem", ssl_keyfile=None)

        print("Action: Calling resolve_tls_config with certfile only...")
        with patch('main.SSL_CERTFILE', ''), patch('main.SSL_KEYFILE', ''):
            with pytest.raises(ValueError) as exc_info:
                resolve_tls_config(args)

        print(f"Error message: {exc_info.value}")
        assert "both" in str(exc_info.value).lower()

    def test_only_keyfile_raises_error(self):
        """
        What it does: Verifies error when only keyfile is provided.
        Purpose: Ensure partial TLS config is rejected in both directions.
        """
        print("Setup: Importing resolve_tls_config...")
        from main import resolve_tls_config

        args = argparse.Namespace(ssl_certfile=None, ssl_keyfile="/key.pem")

        print("Action: Calling resolve_tls_config with keyfile only...")
        with patch('main.SSL_CERTFILE', ''), patch('main.SSL_KEYFILE', ''):
            with pytest.raises(ValueError):
                resolve_tls_config(args)

    def test_empty_strings_do_not_raise(self):
        """
        What it does: Verifies empty strings for both paths are treated as TLS off.
        Purpose: Ensure empty env vars do not trigger the mismatch error.
        """
        print("Setup: Importing resolve_tls_config...")
        from main import resolve_tls_config

        args = argparse.Namespace(ssl_certfile="", ssl_keyfile="")

        print("Action: Calling resolve_tls_config with empty strings...")
        with patch('main.SSL_CERTFILE', ''), patch('main.SSL_KEYFILE', ''):
            certfile, keyfile = resolve_tls_config(args)

        print(f"certfile: {certfile!r}, keyfile: {keyfile!r}")
        assert certfile == ""
        assert keyfile == ""


class TestParseCliTlsArgs:
    """Tests for --ssl-certfile/--ssl-keyfile CLI argument parsing."""

    def test_ssl_args_parsed(self):
        """
        What it does: Verifies --ssl-certfile/--ssl-keyfile are parsed.
        Purpose: Ensure TLS can be enabled via CLI.
        """
        print("Setup: Importing parse_cli_args...")
        from main import parse_cli_args

        print("Action: Calling parse_cli_args with ssl args...")
        with patch.object(sys, 'argv', [
            'main.py',
            '--ssl-certfile', '/certs/fullchain.pem',
            '--ssl-keyfile', '/certs/privkey.pem',
        ]):
            args = parse_cli_args()

        print(f"ssl_certfile: {args.ssl_certfile}, ssl_keyfile: {args.ssl_keyfile}")
        assert args.ssl_certfile == "/certs/fullchain.pem"
        assert args.ssl_keyfile == "/certs/privkey.pem"

    def test_ssl_args_default_none(self):
        """
        What it does: Verifies ssl args default to None.
        Purpose: Ensure None means "use env or default" like host/port.
        """
        print("Setup: Importing parse_cli_args...")
        from main import parse_cli_args

        print("Action: Calling parse_cli_args without ssl args...")
        with patch.object(sys, 'argv', ['main.py']):
            args = parse_cli_args()

        print(f"ssl_certfile: {args.ssl_certfile}, ssl_keyfile: {args.ssl_keyfile}")
        assert args.ssl_certfile is None
        assert args.ssl_keyfile is None


class TestPrintStartupBanner:
    """Tests for print_startup_banner() function."""
    
    def test_banner_contains_url(self, capsys):
        """
        What it does: Verifies that banner contains the server URL.
        Purpose: Ensure URL is displayed to user.
        """
        print("Setup: Importing print_startup_banner...")
        from main import print_startup_banner
        
        print("Action: Calling print_startup_banner('0.0.0.0', 8000)...")
        print_startup_banner("0.0.0.0", 8000)
        
        captured = capsys.readouterr()
        print(f"Captured output length: {len(captured.out)}")
        
        # When host is 0.0.0.0, display should show localhost
        assert "localhost:8000" in captured.out or "8000" in captured.out
    
    def test_banner_contains_custom_port(self, capsys):
        """
        What it does: Verifies that banner shows custom port.
        Purpose: Ensure custom port is displayed correctly.
        """
        print("Setup: Importing print_startup_banner...")
        from main import print_startup_banner
        
        print("Action: Calling print_startup_banner('127.0.0.1', 9000)...")
        print_startup_banner("127.0.0.1", 9000)
        
        captured = capsys.readouterr()
        print(f"Captured output contains '9000': {'9000' in captured.out}")
        
        assert "9000" in captured.out
    
    def test_banner_contains_docs_url(self, capsys):
        """
        What it does: Verifies that banner contains API docs URL.
        Purpose: Ensure /docs endpoint is mentioned.
        """
        print("Setup: Importing print_startup_banner...")
        from main import print_startup_banner
        
        print("Action: Calling print_startup_banner('0.0.0.0', 8000)...")
        print_startup_banner("0.0.0.0", 8000)
        
        captured = capsys.readouterr()
        print(f"Captured output contains '/docs': {'/docs' in captured.out}")
        
        assert "/docs" in captured.out
    
    def test_banner_contains_health_url(self, capsys):
        """
        What it does: Verifies that banner contains health check URL.
        Purpose: Ensure /health endpoint is mentioned.
        """
        print("Setup: Importing print_startup_banner...")
        from main import print_startup_banner
        
        print("Action: Calling print_startup_banner('0.0.0.0', 8000)...")
        print_startup_banner("0.0.0.0", 8000)
        
        captured = capsys.readouterr()
        print(f"Captured output contains '/health': {'/health' in captured.out}")
        
        assert "/health" in captured.out


class TestCliHelp:
    """Tests for CLI help output."""
    
    def test_help_shows_port_option(self):
        """
        What it does: Verifies that --help shows port option.
        Purpose: Ensure help is informative.
        """
        print("Setup: Importing parse_cli_args...")
        from main import parse_cli_args
        
        print("Action: Calling parse_cli_args with --help...")
        with patch.object(sys, 'argv', ['main.py', '--help']):
            with pytest.raises(SystemExit) as exc_info:
                parse_cli_args()
        
        print(f"Exit code: {exc_info.value.code}")
        # --help exits with code 0
        assert exc_info.value.code == 0
    
    def test_help_shows_host_option(self, capsys):
        """
        What it does: Verifies that --help output contains host option.
        Purpose: Ensure host option is documented.
        """
        print("Setup: Importing parse_cli_args...")
        from main import parse_cli_args
        
        print("Action: Calling parse_cli_args with --help...")
        with patch.object(sys, 'argv', ['main.py', '--help']):
            with pytest.raises(SystemExit):
                parse_cli_args()
        
        captured = capsys.readouterr()
        print(f"Help output contains '--host': {'--host' in captured.out}")
        print(f"Help output contains '-H': {'-H' in captured.out}")
        
        assert "--host" in captured.out
        assert "-H" in captured.out


class TestCliVersion:
    """Tests for CLI version output."""
    
    def test_version_flag_exits_with_zero(self):
        """
        What it does: Verifies that --version exits with code 0.
        Purpose: Ensure version flag works correctly.
        """
        print("Setup: Importing parse_cli_args...")
        from main import parse_cli_args
        
        print("Action: Calling parse_cli_args with --version...")
        with patch.object(sys, 'argv', ['main.py', '--version']):
            with pytest.raises(SystemExit) as exc_info:
                parse_cli_args()
        
        print(f"Exit code: {exc_info.value.code}")
        assert exc_info.value.code == 0
    
    def test_version_shows_app_version(self, capsys):
        """
        What it does: Verifies that --version shows application version.
        Purpose: Ensure version is displayed.
        """
        print("Setup: Importing parse_cli_args and APP_VERSION...")
        from main import parse_cli_args
        from kiro.config import APP_VERSION
        
        print("Action: Calling parse_cli_args with --version...")
        with patch.object(sys, 'argv', ['main.py', '--version']):
            with pytest.raises(SystemExit):
                parse_cli_args()
        
        captured = capsys.readouterr()
        print(f"Version output: {captured.out}")
        print(f"APP_VERSION: {APP_VERSION}")
        
        assert APP_VERSION in captured.out