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
Kiro CLI model list provider.

The runtime Kiro endpoint does not expose /ListAvailableModels, but kiro-cli can
query the user's actual model entitlement list via `kiro-cli chat --list-models`.
This module isolates that CLI dependency and converts its JSON output into the
ModelInfoCache format used by the gateway.
"""

from __future__ import annotations

import asyncio
import json
from asyncio.subprocess import PIPE
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from loguru import logger

from kiro.config import (
    DEFAULT_MAX_INPUT_TOKENS,
    KIRO_CLI_LIST_MODELS_COMMAND,
    KIRO_CLI_LIST_MODELS_TIMEOUT_SECONDS,
)


class KiroCliModelListError(RuntimeError):
    """Raised when the Kiro CLI model list cannot be retrieved or parsed."""


@dataclass(frozen=True)
class KiroCliModelList:
    """
    Parsed Kiro CLI model list.

    Attributes:
        models: Model metadata converted to ModelInfoCache format.
        default_model: Default model ID reported by kiro-cli, if present.
        raw_payload: Raw JSON payload decoded from kiro-cli output.
    """

    models: List[Dict[str, Any]]
    default_model: Optional[str]
    raw_payload: Dict[str, Any]


def _positive_int_or_default(value: Any, default: int) -> int:
    """
    Convert a value to a positive integer or return a default.

    Args:
        value: Candidate numeric value.
        default: Fallback value.

    Returns:
        Positive integer value or the default.
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, int) and value > 0:
        return value
    return default


def parse_kiro_cli_models_json(output: str) -> KiroCliModelList:
    """
    Parse `kiro-cli chat --list-models --format json` output.

    Args:
        output: Raw stdout from kiro-cli.

    Returns:
        Parsed model list with metadata converted to gateway cache format.

    Raises:
        KiroCliModelListError: If output is not valid JSON or contains no
            usable model entries.
    """
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise KiroCliModelListError(f"kiro-cli returned invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise KiroCliModelListError("kiro-cli model payload must be a JSON object")

    raw_models = payload.get("models")
    if not isinstance(raw_models, list):
        raise KiroCliModelListError("kiro-cli model payload missing models array")

    default_model = payload.get("default_model")
    if not isinstance(default_model, str):
        default_model = None

    models: List[Dict[str, Any]] = []
    for raw_model in raw_models:
        if not isinstance(raw_model, dict):
            continue

        model_id = raw_model.get("model_id")
        if not isinstance(model_id, str) or not model_id:
            continue

        model_name = raw_model.get("model_name")
        if not isinstance(model_name, str) or not model_name:
            model_name = model_id

        description = raw_model.get("description")
        if not isinstance(description, str):
            description = ""

        max_input_tokens = _positive_int_or_default(
            raw_model.get("context_window_tokens"),
            DEFAULT_MAX_INPUT_TOKENS,
        )

        converted_model: Dict[str, Any] = {
            "modelId": model_id,
            "modelName": model_name,
            "description": description,
            "tokenLimits": {"maxInputTokens": max_input_tokens},
            "_source": "kiro_cli",
        }

        if model_id == default_model:
            converted_model["_is_default"] = True

        rate_multiplier = raw_model.get("rate_multiplier")
        if isinstance(rate_multiplier, (int, float)) and not isinstance(rate_multiplier, bool):
            converted_model["rateMultiplier"] = float(rate_multiplier)

        rate_unit = raw_model.get("rate_unit")
        if isinstance(rate_unit, str) and rate_unit:
            converted_model["rateUnit"] = rate_unit

        models.append(converted_model)

    if not models:
        raise KiroCliModelListError("kiro-cli returned no usable models")

    return KiroCliModelList(
        models=models,
        default_model=default_model,
        raw_payload=payload,
    )


async def fetch_kiro_cli_models(
    command: str = KIRO_CLI_LIST_MODELS_COMMAND,
    timeout_seconds: float = KIRO_CLI_LIST_MODELS_TIMEOUT_SECONDS,
) -> KiroCliModelList:
    """
    Fetch available models from kiro-cli.

    Args:
        command: Executable name or path for kiro-cli.
        timeout_seconds: Maximum time to wait for the CLI command.

    Returns:
        Parsed Kiro CLI model list.

    Raises:
        KiroCliModelListError: If the command cannot be executed, times out,
            exits with an error, or returns malformed output.
    """
    if not command:
        raise KiroCliModelListError("kiro-cli command is empty")

    args = [command, "chat", "--list-models", "--format", "json"]
    logger.debug(f"Fetching model list via {' '.join(args)}")

    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=PIPE,
            stderr=PIPE,
        )
    except FileNotFoundError as exc:
        raise KiroCliModelListError(f"kiro-cli command not found: {command}") from exc
    except PermissionError as exc:
        raise KiroCliModelListError(f"kiro-cli command is not executable: {command}") from exc
    except OSError as exc:
        raise KiroCliModelListError(f"failed to start kiro-cli: {exc}") from exc

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        try:
            process.kill()
            await process.wait()
        except ProcessLookupError:
            pass
        raise KiroCliModelListError(
            f"kiro-cli model list timed out after {timeout_seconds}s"
        ) from exc

    stdout_text = stdout.decode("utf-8", errors="replace")
    stderr_text = stderr.decode("utf-8", errors="replace").strip()

    if process.returncode != 0:
        detail = stderr_text or stdout_text.strip() or f"exit code {process.returncode}"
        raise KiroCliModelListError(f"kiro-cli model list failed: {detail}")

    return parse_kiro_cli_models_json(stdout_text)
