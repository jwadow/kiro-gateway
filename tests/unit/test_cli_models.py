# -*- coding: utf-8 -*-

"""
Unit tests for kiro/cli_models.py.

Tests the Kiro CLI model list provider that parses
`kiro-cli chat --list-models --format json` output.
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from kiro.cli_models import (
    KiroCliModelListError,
    fetch_kiro_cli_models,
    parse_kiro_cli_models_json,
)


def _cli_payload() -> dict:
    """
    Build a representative kiro-cli model list payload.

    Returns:
        JSON-compatible payload matching kiro-cli output.
    """
    return {
        "models": [
            {
                "model_name": "auto",
                "description": "Models chosen by task",
                "model_id": "auto",
                "context_window_tokens": 1000000,
                "rate_multiplier": 1.0,
                "rate_unit": "Credit",
            },
            {
                "model_name": "claude-opus-4.8",
                "description": "Experimental preview",
                "model_id": "claude-opus-4.8",
                "context_window_tokens": 1000000,
                "rate_multiplier": 2.2,
                "rate_unit": "Credit",
            },
        ],
        "default_model": "claude-opus-4.8",
    }


class FakeProcess:
    """
    Fake asyncio subprocess process.

    Args:
        stdout: Bytes returned from stdout.
        stderr: Bytes returned from stderr.
        returncode: Process return code.
    """

    def __init__(self, stdout: bytes, stderr: bytes = b"", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.killed = False
        self.wait = AsyncMock(return_value=None)

    async def communicate(self):
        """
        Return fake subprocess output.

        Returns:
            Tuple of stdout and stderr bytes.
        """
        return self.stdout, self.stderr

    def kill(self) -> None:
        """Mark the fake process as killed."""
        self.killed = True


class HangingProcess(FakeProcess):
    """Fake process whose communicate call never completes quickly."""

    async def communicate(self):
        """
        Sleep long enough for asyncio.wait_for to time out.

        Returns:
            Tuple of stdout and stderr bytes.
        """
        await asyncio.sleep(60)
        return self.stdout, self.stderr


class TestParseKiroCliModelsJson:
    """Tests for parse_kiro_cli_models_json()."""

    def test_parses_valid_json_payload(self):
        """
        What it does: Parses valid kiro-cli JSON output.
        Purpose: Convert CLI schema to ModelInfoCache schema.
        """
        result = parse_kiro_cli_models_json(json.dumps(_cli_payload()))

        assert result.default_model == "claude-opus-4.8"
        assert result.raw_payload == _cli_payload()
        assert [model["modelId"] for model in result.models] == [
            "auto",
            "claude-opus-4.8",
        ]
        assert result.models[1]["modelName"] == "claude-opus-4.8"
        assert result.models[1]["description"] == "Experimental preview"
        assert result.models[1]["tokenLimits"]["maxInputTokens"] == 1000000
        assert result.models[1]["rateMultiplier"] == 2.2
        assert result.models[1]["rateUnit"] == "Credit"
        assert result.models[1]["_is_default"] is True
        assert result.models[1]["_source"] == "kiro_cli"

    def test_skips_malformed_model_entries(self):
        """
        What it does: Skips non-dict and missing-id model entries.
        Purpose: Handle partial CLI schema changes without failing all models.
        """
        payload = {
            "models": [
                "not-a-dict",
                {"model_name": "missing-id"},
                {"model_id": ""},
                {"model_id": "claude-sonnet-4.6"},
            ]
        }

        result = parse_kiro_cli_models_json(json.dumps(payload))

        assert len(result.models) == 1
        assert result.models[0]["modelId"] == "claude-sonnet-4.6"
        assert result.models[0]["modelName"] == "claude-sonnet-4.6"

    def test_uses_default_token_limit_for_invalid_context_window(self):
        """
        What it does: Falls back when context_window_tokens is invalid.
        Purpose: Prevent malformed CLI metadata from breaking token accounting.
        """
        payload = {"models": [{"model_id": "claude-opus-4.8", "context_window_tokens": -1}]}

        result = parse_kiro_cli_models_json(json.dumps(payload))

        assert result.models[0]["tokenLimits"]["maxInputTokens"] == 200000

    def test_invalid_json_raises_error(self):
        """
        What it does: Parses invalid JSON output.
        Purpose: Surface CLI output format problems clearly.
        """
        with pytest.raises(KiroCliModelListError, match="invalid JSON"):
            parse_kiro_cli_models_json("not json")

    def test_non_object_json_raises_error(self):
        """
        What it does: Parses a JSON array instead of object.
        Purpose: Reject unexpected top-level schema.
        """
        with pytest.raises(KiroCliModelListError, match="JSON object"):
            parse_kiro_cli_models_json("[]")

    def test_missing_models_array_raises_error(self):
        """
        What it does: Parses a payload without models array.
        Purpose: Reject incomplete CLI output.
        """
        with pytest.raises(KiroCliModelListError, match="models array"):
            parse_kiro_cli_models_json("{}")

    def test_no_usable_models_raises_error(self):
        """
        What it does: Parses a payload where every model entry is invalid.
        Purpose: Avoid replacing cache with an empty CLI result.
        """
        with pytest.raises(KiroCliModelListError, match="no usable models"):
            parse_kiro_cli_models_json(json.dumps({"models": [{"model_id": ""}]}))


class TestFetchKiroCliModels:
    """Tests for fetch_kiro_cli_models()."""

    @pytest.mark.asyncio
    async def test_fetches_models_from_cli_json_output(self):
        """
        What it does: Runs the kiro-cli command and parses stdout.
        Purpose: Verify subprocess invocation uses JSON format.
        """
        process = FakeProcess(json.dumps(_cli_payload()).encode("utf-8"))

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=process)) as create_process:
            result = await fetch_kiro_cli_models(command="kiro-cli", timeout_seconds=5)

        create_process.assert_awaited_once_with(
            "kiro-cli",
            "chat",
            "--list-models",
            "--format",
            "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert [model["modelId"] for model in result.models] == ["auto", "claude-opus-4.8"]

    @pytest.mark.asyncio
    async def test_empty_command_raises_error(self):
        """
        What it does: Calls fetch with an empty command.
        Purpose: Reject invalid configuration before subprocess execution.
        """
        with pytest.raises(KiroCliModelListError, match="command is empty"):
            await fetch_kiro_cli_models(command="")

    @pytest.mark.asyncio
    async def test_command_not_found_raises_error(self):
        """
        What it does: Simulates missing kiro-cli executable.
        Purpose: Fall back cleanly when CLI is unavailable.
        """
        with patch(
            "asyncio.create_subprocess_exec",
            AsyncMock(side_effect=FileNotFoundError("missing")),
        ):
            with pytest.raises(KiroCliModelListError, match="command not found"):
                await fetch_kiro_cli_models(command="missing-cli")

    @pytest.mark.asyncio
    async def test_nonzero_exit_raises_error_with_stderr(self):
        """
        What it does: Simulates kiro-cli returning a non-zero exit code.
        Purpose: Preserve actionable CLI failure details.
        """
        process = FakeProcess(b"", b"not logged in", returncode=2)

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=process)):
            with pytest.raises(KiroCliModelListError, match="not logged in"):
                await fetch_kiro_cli_models(command="kiro-cli")

    @pytest.mark.asyncio
    async def test_timeout_kills_process_and_raises_error(self):
        """
        What it does: Simulates kiro-cli hanging.
        Purpose: Ensure account initialization cannot block indefinitely.
        """
        process = HangingProcess(b"")

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=process)):
            with pytest.raises(KiroCliModelListError, match="timed out"):
                await fetch_kiro_cli_models(command="kiro-cli", timeout_seconds=0.01)

        assert process.killed is True
        process.wait.assert_awaited_once()
