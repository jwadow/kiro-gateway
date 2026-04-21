# -*- coding: utf-8 -*-

"""
Unit tests for payload size guard logic.
Tests check_payload_size() and trim_payload_to_limit() functions.
"""

import json

import pytest

from kiro.payload_guards import (
    PayloadTrimStats,
    check_payload_size,
    trim_payload_to_limit,
)


def _make_payload(num_pairs=5, content_size=100):
    """Helper: build a minimal Kiro-shaped payload with N user/assistant pairs."""
    history = []
    for i in range(num_pairs):
        history.append({
            "userInputMessage": {"content": f"user message {i} " + "x" * content_size}
        })
        history.append({
            "assistantResponseMessage": {"content": f"assistant message {i} " + "y" * content_size}
        })
    return {
        "conversationState": {
            "chatTriggerType": "MANUAL",
            "conversationId": "test-conv",
            "currentMessage": {
                "userInputMessage": {"content": "current message", "modelId": "test"}
            },
            "history": history,
        },
        "profileArn": "arn:aws:test",
    }


class TestCheckPayloadSize:

    def test_check_payload_size_returns_bytes(self):
        """Correct byte count for a simple payload."""
        payload = {"key": "value"}
        expected = len(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        assert check_payload_size(payload) == expected

    def test_check_payload_size_utf8(self):
        """Non-ASCII characters counted correctly."""
        payload = {"emoji": "\U0001f600", "chinese": "\u4f60\u597d"}
        size = check_payload_size(payload)
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        assert size == len(raw)
        # json.dumps escapes non-ASCII by default, so byte count matches
        # The important thing is consistency with what gets sent over the wire
        assert size > 0


class TestTrimPayloadToLimit:

    def test_trim_does_nothing_when_under_limit(self):
        """No-op when payload is small."""
        payload = _make_payload(num_pairs=2, content_size=10)
        original_size = check_payload_size(payload)
        stats = trim_payload_to_limit(payload, max_bytes=original_size + 1000)
        assert not stats.trimmed
        assert stats.original_entries == stats.final_entries
        assert stats.original_bytes == stats.final_bytes

    def test_trim_removes_oldest_history_pairs(self):
        """Removes pairs from the beginning of history."""
        payload = _make_payload(num_pairs=10, content_size=500)
        original_size = check_payload_size(payload)
        # Set limit to ~half the original size
        limit = original_size // 2
        stats = trim_payload_to_limit(payload, max_bytes=limit)

        assert stats.trimmed
        assert stats.final_entries < stats.original_entries
        assert stats.final_bytes <= limit
        # History should still exist and be shorter
        history = payload["conversationState"]["history"]
        assert len(history) == stats.final_entries
        assert len(history) < 20  # original was 20 entries (10 pairs)

    def test_trim_aligns_to_user_message(self):
        """Start index always lands on userInputMessage entry."""
        payload = _make_payload(num_pairs=10, content_size=500)
        limit = check_payload_size(payload) // 3
        trim_payload_to_limit(payload, max_bytes=limit)

        history = payload["conversationState"]["history"]
        assert len(history) > 0
        assert "userInputMessage" in history[0]

    def test_trim_preserves_minimum_history(self):
        """Never trims below 2 entries."""
        payload = _make_payload(num_pairs=5, content_size=1000)
        # Set an impossibly low limit
        stats = trim_payload_to_limit(payload, max_bytes=100)

        history = payload["conversationState"]["history"]
        assert len(history) >= 2
        assert stats.final_entries >= 2

    def test_trim_repairs_orphaned_tool_results(self):
        """Orphaned toolResults removed, text preserved inline."""
        history = [
            {"userInputMessage": {"content": "msg0"}},
            {
                "assistantResponseMessage": {
                    "content": "resp0",
                    "toolUses": [{"toolUseId": "tool-A", "name": "read", "input": "{}"}],
                }
            },
            {
                "userInputMessage": {
                    "content": "msg1",
                    "userInputMessageContext": {
                        "toolResults": [
                            {
                                "toolUseId": "tool-A",
                                "content": [{"text": "result from tool-A"}],
                            },
                            {
                                "toolUseId": "tool-ORPHAN",
                                "content": [{"text": "orphaned data"}],
                            },
                        ]
                    },
                }
            },
            {"assistantResponseMessage": {"content": "resp1"}},
        ]
        payload = {
            "conversationState": {
                "conversationId": "test",
                "chatTriggerType": "MANUAL",
                "currentMessage": {"userInputMessage": {"content": "now", "modelId": "m"}},
                "history": history,
            }
        }
        # Trim with a generous limit so only repair logic runs (no pair removal)
        big_limit = check_payload_size(payload) + 10000
        trim_payload_to_limit(payload, max_bytes=big_limit)

        # tool-A should remain, tool-ORPHAN should be removed with text preserved
        ctx = history[2]["userInputMessage"]["userInputMessageContext"]
        assert len(ctx["toolResults"]) == 1
        assert ctx["toolResults"][0]["toolUseId"] == "tool-A"
        # Orphaned text preserved in content
        assert "orphaned data" in history[2]["userInputMessage"]["content"]
        assert "[trimmed tool result]" in history[2]["userInputMessage"]["content"]

    def test_trim_strips_empty_tool_uses(self):
        """Empty toolUses: [] arrays cleaned before size measurement."""
        history = [
            {"userInputMessage": {"content": "msg"}},
            {"assistantResponseMessage": {"content": "resp", "toolUses": []}},
        ]
        payload = {
            "conversationState": {
                "conversationId": "test",
                "chatTriggerType": "MANUAL",
                "currentMessage": {"userInputMessage": {"content": "now", "modelId": "m"}},
                "history": history,
            }
        }
        big_limit = check_payload_size(payload) + 10000
        trim_payload_to_limit(payload, max_bytes=big_limit)

        # Empty toolUses should be stripped
        assert "toolUses" not in history[1]["assistantResponseMessage"]

    def test_trim_stats_accurate(self):
        """Stats reflect actual changes."""
        payload = _make_payload(num_pairs=8, content_size=500)
        original_size = check_payload_size(payload)
        limit = original_size // 2

        stats = trim_payload_to_limit(payload, max_bytes=limit)

        assert stats.original_bytes == original_size
        assert stats.original_entries == 16  # 8 pairs * 2
        assert stats.final_bytes == check_payload_size(payload)
        assert stats.final_entries == len(payload["conversationState"]["history"])
        assert stats.trimmed is True

    def test_trim_no_history(self):
        """Payload with no history returns no-op stats."""
        payload = {
            "conversationState": {
                "conversationId": "test",
                "chatTriggerType": "MANUAL",
                "currentMessage": {"userInputMessage": {"content": "hi", "modelId": "m"}},
            }
        }
        stats = trim_payload_to_limit(payload, max_bytes=100)
        assert not stats.trimmed
        assert stats.original_entries == 0
        assert stats.final_entries == 0
