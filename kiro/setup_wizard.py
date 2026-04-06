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
Kiro Gateway — Interactive setup wizard.

Guides first-time users through credential configuration when no config
is found. Saves the result to ~/.config/kiro-gateway/.env.

Usage:
    from kiro.setup_wizard import SetupWizard, ConsoleWizardIO, save_config
    from kiro.setup_wizard import get_user_config_path

    wizard = SetupWizard(ConsoleWizardIO())
    config = wizard.run()
    save_config(config, get_user_config_path())
"""

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Optional, Protocol

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_PROXY_API_KEY = "my-super-secret-password-123"

# ANSI color codes (consistent with cli.py style)
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_WHITE = "\033[97m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


class CredentialType(StrEnum):
    """Supported credential source types for Kiro authentication."""

    CREDS_FILE = "creds_file"
    REFRESH_TOKEN = "refresh_token"
    CLI_DB = "cli_db"


@dataclass
class DetectedCredential:
    """A credential source found automatically on the local system.

    Attributes:
        type: The credential type (always CLI_DB for auto-detected sources).
        path: Absolute path to the detected file.
        label: Human-readable description shown to the user.
    """

    type: CredentialType
    path: Path
    label: str


# Known SQLite database paths to probe during auto-detection.
# Ordered by likelihood: kiro-cli first, then amazon-q, then macOS variant.
_CLI_DB_CANDIDATES: list[tuple[Path, str]] = [
    (
        Path.home() / ".local" / "share" / "kiro-cli" / "data.sqlite3",
        "kiro-cli (Linux/macOS)",
    ),
    (
        Path.home() / ".local" / "share" / "amazon-q" / "data.sqlite3",
        "amazon-q-developer-cli (Linux/macOS)",
    ),
    (
        Path.home() / "Library" / "Application Support" / "kiro-cli" / "data.sqlite3",
        "kiro-cli (macOS)",
    ),
]


def detect_credentials() -> list[DetectedCredential]:
    """Scan well-known paths for installed Kiro credential sources.

    Checks each candidate path in ``_CLI_DB_CANDIDATES`` and returns
    a list of those that actually exist on disk.

    Returns:
        List of DetectedCredential instances for each found source.
        Empty list if nothing is found.
    """
    found: list[DetectedCredential] = []
    for path, label in _CLI_DB_CANDIDATES:
        if path.exists():
            found.append(DetectedCredential(
                type=CredentialType.CLI_DB,
                path=path,
                label=label,
            ))
    return found


# ---------------------------------------------------------------------------
# IO abstraction (enables unit testing without real stdin)
# ---------------------------------------------------------------------------


class WizardIO(Protocol):
    """Abstract I/O interface for the setup wizard.

    Implementations provide user prompting and confirmation.
    The production implementation uses stdin; tests inject a mock.
    """

    def prompt(self, message: str, default: str = "") -> str:
        """Display a prompt and return the user's input.

        Args:
            message: The prompt text shown to the user.
            default: Value returned when the user presses Enter without input.

        Returns:
            The user's input string, or ``default`` if input is empty.
        """
        ...

    def confirm(self, message: str) -> bool:
        """Ask a yes/no question and return the boolean answer.

        Args:
            message: The question text shown to the user.

        Returns:
            True if the user confirms, False otherwise.
        """
        ...


class ConsoleWizardIO:
    """Production WizardIO implementation that reads from stdin.

    Uses Python's built-in ``input()`` — no third-party dependencies.
    """

    def prompt(self, message: str, default: str = "") -> str:
        """Display a prompt and return the user's input.

        Args:
            message: The prompt text shown to the user.
            default: Value returned when the user presses Enter without input.

        Returns:
            The user's input string, or ``default`` if input is empty.
        """
        hint = f" [{default}]" if default else ""
        raw = input(f"{message}{hint}: ").strip()
        return raw if raw else default

    def confirm(self, message: str) -> bool:
        """Ask a yes/no question and return the boolean answer.

        Args:
            message: The question text shown to the user.

        Returns:
            True if the user answers 'y' or 'yes' (case-insensitive).
        """
        raw = input(f"{message} [y/N]: ").strip().lower()
        return raw in ("y", "yes")


# ---------------------------------------------------------------------------
# Wizard
# ---------------------------------------------------------------------------


class SetupWizard:
    """Interactive setup wizard for first-time Kiro Gateway configuration.

    Guides the user through selecting a credential type, entering the
    credential value, and setting a proxy API key. Returns a dict of
    environment variable names to values, ready to be saved as a .env file.

    Design: depends on WizardIO abstraction (Dependency Inversion Principle),
    so tests can inject a mock without touching stdin.

    Example:
        wizard = SetupWizard(ConsoleWizardIO())
        config = wizard.run()
        # config == {"REFRESH_TOKEN": "...", "PROXY_API_KEY": "..."}
    """

    def __init__(self, io: WizardIO) -> None:
        """Initialize the wizard with an I/O handler.

        Args:
            io: WizardIO implementation for user interaction.
        """
        self._io = io

    def run(self) -> dict[str, str]:
        """Run the interactive setup wizard.

        First attempts auto-detection of installed credential sources.
        If found, prompts the user to confirm before using them.
        Falls back to manual selection if nothing is detected or user declines.

        Returns:
            A dict mapping environment variable names to their values.
        """
        self._print_welcome()

        config: dict[str, str] = {}
        detected = detect_credentials()

        if detected:
            chosen = self._ask_use_detected(detected)
            if chosen is not None:
                config["KIRO_CLI_DB_FILE"] = str(chosen.path)
                proxy_key = self._io.prompt(
                    f"{_CYAN}  Proxy API key (clients use this to authenticate){_RESET}",
                    default=_DEFAULT_PROXY_API_KEY,
                )
                config["PROXY_API_KEY"] = proxy_key
                print()
                print(f"{_GREEN}  Configuration ready.{_RESET}")
                return config
            # User declined — fall through to manual flow

        cred_type = self._ask_credential_type()

        if cred_type == CredentialType.CREDS_FILE:
            value = self._io.prompt(
                f"{_CYAN}  Path to your Kiro credentials JSON file{_RESET}"
            )
            config["KIRO_CREDS_FILE"] = value

        elif cred_type == CredentialType.REFRESH_TOKEN:
            value = self._io.prompt(
                f"{_CYAN}  Refresh token (from Kiro IDE network traffic){_RESET}"
            )
            config["REFRESH_TOKEN"] = value

        elif cred_type == CredentialType.CLI_DB:
            default_db = "~/.local/share/kiro-cli/data.sqlite3"
            value = self._io.prompt(
                f"{_CYAN}  Path to kiro-cli SQLite database{_RESET}",
                default=default_db,
            )
            config["KIRO_CLI_DB_FILE"] = value

        proxy_key = self._io.prompt(
            f"{_CYAN}  Proxy API key (clients use this to authenticate){_RESET}",
            default=_DEFAULT_PROXY_API_KEY,
        )
        config["PROXY_API_KEY"] = proxy_key

        print()
        print(f"{_GREEN}  Configuration ready.{_RESET}")
        return config

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _print_welcome(self) -> None:
        """Print the wizard welcome banner."""
        print()
        print(f"  {_BOLD}{_WHITE}👻 Kiro Gateway — First-time Setup{_RESET}")
        print(f"  {_DIM}{'─' * 44}{_RESET}")
        print(f"  {_YELLOW}No credentials found. Let's set them up.{_RESET}")
        print()

    def _ask_use_detected(
        self, detected: list[DetectedCredential]
    ) -> Optional[DetectedCredential]:
        """Prompt the user to use an auto-detected credential source.

        If exactly one source is found, asks a simple yes/no question.
        If multiple are found, shows a numbered list and lets the user pick
        one or skip to manual setup.

        Args:
            detected: Non-empty list of auto-detected credential sources.

        Returns:
            The chosen DetectedCredential, or None if the user declined.
        """
        if len(detected) == 1:
            cred = detected[0]
            print(f"  {_GREEN}Found:{_RESET} {cred.label}")
            print(f"  {_DIM}{cred.path}{_RESET}")
            print()
            if self._io.confirm(f"  {_CYAN}Use this credential source?{_RESET}"):
                return cred
            return None

        # Multiple detected — show numbered list
        print(f"  {_GREEN}Found {len(detected)} credential sources:{_RESET}")
        for i, cred in enumerate(detected, start=1):
            print(f"  {_DIM}{i}){_RESET} {cred.label}")
            print(f"     {_DIM}{cred.path}{_RESET}")
        print(f"  {_DIM}0){_RESET} Enter manually")
        print()

        choices = {str(i): cred for i, cred in enumerate(detected, start=1)}
        choices["0"] = None  # type: ignore[assignment]

        while True:
            raw = self._io.prompt(
                f"  {_CYAN}Select (0-{len(detected)}){_RESET}"
            ).strip()
            if raw in choices:
                return choices[raw]
            print(f"  {_YELLOW}Invalid choice. Enter 0–{len(detected)}.{_RESET}")

    def _ask_credential_type(self) -> CredentialType:
        """Prompt the user to choose a credential type.

        Loops until a valid choice (1–3) is entered.

        Returns:
            The selected CredentialType.
        """
        print(f"  {_WHITE}Choose your credential source:{_RESET}")
        print(f"  {_DIM}1){_RESET} JSON credentials file  {_DIM}(recommended){_RESET}")
        print(f"  {_DIM}2){_RESET} Refresh token")
        print(f"  {_DIM}3){_RESET} kiro-cli SQLite database  {_DIM}(AWS SSO){_RESET}")
        print()

        _choices = {
            "1": CredentialType.CREDS_FILE,
            "2": CredentialType.REFRESH_TOKEN,
            "3": CredentialType.CLI_DB,
        }

        while True:
            choice = self._io.prompt(f"  {_CYAN}Enter choice (1-3){_RESET}").strip()
            if choice in _choices:
                return _choices[choice]
            print(f"  {_YELLOW}Invalid choice '{choice}'. Please enter 1, 2, or 3.{_RESET}")


# ---------------------------------------------------------------------------
# Config file helpers
# ---------------------------------------------------------------------------


def get_user_config_path() -> Path:
    """Return the path to the user-level config file.

    Follows XDG Base Directory convention: ~/.config/kiro-gateway/.env

    Returns:
        Path to ~/.config/kiro-gateway/.env
    """
    return Path.home() / ".config" / "kiro-gateway" / ".env"


def save_config(config: dict[str, str], path: Path) -> None:
    """Write a config dict to a .env file and update os.environ.

    Creates parent directories if they do not exist.
    Writes KEY=value lines without quoting (avoids escape-sequence issues
    on Windows paths). After writing, updates os.environ so the current
    process can use the new values immediately without a restart.

    Args:
        config: Mapping of environment variable names to values.
        path: Destination .env file path.

    Raises:
        OSError: If the file cannot be written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [f"{key}={value}\n" for key, value in config.items()]
    path.write_text("".join(lines), encoding="utf-8")

    # Update the current process environment so validate_configuration()
    # can re-check without requiring a full process restart.
    for key, value in config.items():
        os.environ[key] = value

    print(f"  {_GREEN}Config saved to: {path}{_RESET}")
