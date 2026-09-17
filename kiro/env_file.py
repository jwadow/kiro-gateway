# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Read and update .env files while preserving comments, blank lines and ordering."""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def default_env_path() -> Path:
    """Return the .env path: bundled resource dir first, then project dir."""
    bundled = Path(getattr(__import__("sys"), "_MEIPASS", "")) / ".env" if False else None
    # py2app puts Resources on sys.path; a .env resource lives next to the executable
    executable_dir = Path(__import__("sys").executable).resolve().parent
    for candidate in (executable_dir.parent / "Resources" / ".env", Path.cwd() / ".env"):
        if candidate.is_file():
            return candidate
    return Path.cwd() / ".env"


def read_env(path: Path) -> Dict[str, str]:
    """Parse a .env file into a dict. Later duplicates override earlier ones."""
    values: Dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _split_env_line(raw_line: str) -> Optional[Tuple[str, str]]:
    stripped = raw_line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key, _, _ = stripped.partition("=")
    key = key.strip()
    if not key:
        return None
    return key, stripped


def update_env_value(path: Path, key: str, value: str) -> bool:
    """
    Set `key` to `value` in the .env file, preserving comments and ordering.

    Existing quoting style is preserved. Missing keys are appended.
    Empty value removes the key.

    Returns:
        True if the file changed, False if no change was needed
    """
    key = key.strip()
    if not key:
        raise ValueError("env key must not be empty")

    lines: List[str] = []
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()

    existing_style = _existing_quote_style(lines, key)
    formatted_value = _format_value(value, existing_style)

    replaced = False
    changed = False
    new_lines: List[str] = []
    for raw_line in lines:
        parsed = _split_env_line(raw_line)
        if parsed is not None and parsed[0] == key and not replaced:
            if parsed[1] != f"{key}={formatted_value}":
                changed = True
                if value == "":
                    continue
                new_lines.append(f"{key}={formatted_value}")
            else:
                new_lines.append(raw_line)
            replaced = True
        else:
            new_lines.append(raw_line)

    if not replaced and value != "":
        if new_lines and new_lines[-1].strip() != "":
            new_lines.append("")
        new_lines.append(f"{key}={formatted_value}")
        changed = True

    if changed:
        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return changed


def _existing_quote_style(lines: List[str], key: str) -> str:
    for raw_line in lines:
        parsed = _split_env_line(raw_line)
        if parsed is not None and parsed[0] == key:
            _, _, value = parsed[1].partition("=")
            value = value.strip()
            if value.startswith('"'):
                return '"'
            if value.startswith("'"):
                return "'"
            return ""
    return '"'


def _format_value(value: str, quote: str) -> str:
    if value == "":
        return ""
    if quote:
        return f"{quote}{value}{quote}"
    return value


def os_env_with_file(path: Path) -> Dict[str, str]:
    """Merge process environment with .env values (.env wins, mirroring python-dotenv default)."""
    merged = dict(os.environ)
    merged.update(read_env(path))
    return merged
