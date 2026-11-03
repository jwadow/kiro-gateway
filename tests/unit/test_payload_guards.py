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


# ==================================================================================================
# Linear-time trimming: parity with the original quadratic algorithm
# ==================================================================================================

import copy
import random
from unittest.mock import patch

import kiro.payload_guards as payload_guards_module
from kiro.payload_guards import (
    _align_to_user_message,
    _repair_orphaned_tool_results,
    _strip_empty_tool_uses,
)


def _reference_trim(payload, max_bytes):
    """
    Copy of the original (quadratic) trim algorithm.

    Used as the oracle: the optimized implementation must trim exactly the
    same entries and report the same sizes.
    """
    original_bytes = check_payload_size(payload)
    history = payload.get("conversationState", {}).get("history")
    if not history:
        return PayloadTrimStats(original_bytes, original_bytes, 0, 0, False)
    original_entries = len(history)
    _strip_empty_tool_uses(history)
    while len(history) > 2 and check_payload_size(payload) > max_bytes:
        history.pop(0)
        history.pop(0)
    _align_to_user_message(history)
    _repair_orphaned_tool_results(history)
    final_bytes = check_payload_size(payload)
    return PayloadTrimStats(
        original_bytes, final_bytes, original_entries, len(history),
        original_entries != len(history),
    )


_UNICODE_SAMPLES = [
    "plain",
    "café",
    "你好",
    "\U0001f600 emoji",
    "quote \" and \\ slash",
    "tab\tnew\nline",
]


def _random_entry(rng, role, index, tool_ids):
    """Build a random Kiro history entry of the given role."""
    text = rng.choice(_UNICODE_SAMPLES) * rng.randint(0, 40)
    if role == "user":
        msg = {"content": f"u{index} {text}", "modelId": "m", "origin": "AI_EDITOR"}
        if tool_ids and rng.random() < 0.5:
            results = [
                {"toolUseId": tid, "status": "success", "content": [{"text": text or "r"}]}
                for tid in tool_ids
            ]
            if rng.random() < 0.3:
                results.append({"toolUseId": f"orphan-{index}", "content": [{"text": "orphan " + text}]})
            if rng.random() < 0.2:
                results.append({"toolUseId": f"orphan-str-{index}", "content": "string orphan"})
            msg["userInputMessageContext"] = {"toolResults": results}
        elif rng.random() < 0.1:
            # Orphan with no preceding assistant tool use at all
            msg["userInputMessageContext"] = {"toolResults": [{"toolUseId": "ghost", "content": []}]}
        return {"userInputMessage": msg}, []
    msg = {"content": f"a{index} {text}"}
    new_ids = []
    roll = rng.random()
    if roll < 0.3:
        msg["toolUses"] = []
    elif roll < 0.6:
        new_ids = [f"t{index}-{k}" for k in range(rng.randint(1, 3))]
        msg["toolUses"] = [{"toolUseId": t, "name": "tool", "input": {"x": text}} for t in new_ids]
    return {"assistantResponseMessage": msg}, new_ids


def _random_payload(rng):
    """Build a random Kiro payload with irregular history (roles not always alternating)."""
    history = []
    tool_ids = []
    for index in range(rng.randint(0, 30)):
        if rng.random() < 0.85:
            role = "user" if index % 2 == 0 else "assistant"
        else:
            role = rng.choice(["user", "assistant"])
        entry, new_ids = _random_entry(rng, role, index, tool_ids if role == "user" else [])
        tool_ids = new_ids
        history.append(entry)
    payload = {
        "conversationState": {
            "chatTriggerType": "MANUAL",
            "conversationId": "conv",
            "currentMessage": {
                "userInputMessage": {"content": rng.choice(_UNICODE_SAMPLES), "modelId": "m"}
            },
        },
    }
    if history or rng.random() < 0.5:
        payload["conversationState"]["history"] = history
    if rng.random() < 0.5:
        payload["profileArn"] = "arn:aws:test"
    return payload


class TestTrimParityWithReference:
    """The optimized trim must make the same decisions as the original algorithm."""

    @pytest.mark.parametrize("seed", range(300))
    def test_random_payloads_match_reference(self, seed):
        """
        What it does: Trims random payloads with both implementations at several limits.
        Purpose: Prove the running-total bookkeeping reproduces the original selection exactly.
        """
        rng = random.Random(seed)
        base = _random_payload(rng)
        full_size = check_payload_size(base)
        limits = [
            0, 1, full_size // 4, full_size // 2, full_size - 1, full_size, full_size + 100,
            rng.randint(0, full_size + 1),
        ]
        for limit in limits:
            expected_payload = copy.deepcopy(base)
            actual_payload = copy.deepcopy(base)

            expected = _reference_trim(expected_payload, limit)
            actual = trim_payload_to_limit(actual_payload, limit)

            assert actual_payload == expected_payload, f"seed={seed} limit={limit}"
            assert actual == expected, f"seed={seed} limit={limit}"
            # final_bytes is a running total; it must equal a real measurement
            assert actual.final_bytes == check_payload_size(actual_payload)

    @pytest.mark.parametrize("seed", range(50))
    def test_precomputed_size_gives_same_result(self, seed):
        """
        What it does: Passes the caller-computed size via current_size.
        Purpose: Ensure the precomputed-size path is equivalent.
        """
        rng = random.Random(1000 + seed)
        base = _random_payload(rng)
        limit = check_payload_size(base) // 2

        with_size = copy.deepcopy(base)
        without_size = copy.deepcopy(base)
        stats_with = trim_payload_to_limit(with_size, limit, current_size=check_payload_size(with_size))
        stats_without = trim_payload_to_limit(without_size, limit)

        assert with_size == without_size
        assert stats_with == stats_without

    def test_precomputed_size_skips_initial_serialization(self):
        """
        What it does: Spies on check_payload_size while passing current_size.
        Purpose: The caller's size must be reused, not recomputed.
        """
        payload = _make_payload(num_pairs=10, content_size=100)
        size = check_payload_size(payload)
        with patch.object(
            payload_guards_module, "check_payload_size", wraps=payload_guards_module.check_payload_size
        ) as spy:
            stats = trim_payload_to_limit(payload, max_bytes=size // 2, current_size=size)
        assert spy.call_count == 0
        assert stats.original_bytes == size
        assert stats.final_bytes == check_payload_size(payload)


class TestTrimEdgeCases:
    """Edge cases of the running-total trimming."""

    @staticmethod
    def _payload(history):
        return {
            "conversationState": {
                "conversationId": "c",
                "chatTriggerType": "MANUAL",
                "currentMessage": {"userInputMessage": {"content": "now", "modelId": "m"}},
                "history": history,
            }
        }

    def test_history_of_only_assistant_entries_aligns_to_empty(self):
        """
        What it does: History without any userInputMessage.
        Purpose: Alignment removes everything; the size of "[]" must be tracked correctly.
        """
        payload = self._payload([{"assistantResponseMessage": {"content": "a"}} for _ in range(3)])
        stats = trim_payload_to_limit(payload, max_bytes=10**9)
        assert payload["conversationState"]["history"] == []
        assert stats.final_entries == 0
        assert stats.trimmed is True
        assert stats.final_bytes == check_payload_size(payload)

    def test_single_entry_history_is_kept(self):
        """
        What it does: One-entry history with an impossible limit.
        Purpose: The pair loop keeps at least 2 entries, so the single entry stays.
        """
        payload = self._payload([{"userInputMessage": {"content": "x" * 1000}}])
        stats = trim_payload_to_limit(payload, max_bytes=1)
        assert stats.final_entries == 1
        assert stats.trimmed is False
        assert stats.final_bytes == check_payload_size(payload)

    def test_empty_tool_uses_as_only_key(self):
        """
        What it does: Assistant message whose only key is an empty toolUses.
        Purpose: Stripping {"toolUses":[]} -> {} has no comma; the byte count must match.
        """
        payload = self._payload([
            {"userInputMessage": {"content": "u"}},
            {"assistantResponseMessage": {"toolUses": []}},
        ])
        stats = trim_payload_to_limit(payload, max_bytes=10**9)
        assert payload["conversationState"]["history"][1] == {"assistantResponseMessage": {}}
        assert stats.final_bytes == check_payload_size(payload)
        assert stats.original_bytes > stats.final_bytes

    def test_repair_size_change_is_tracked(self):
        """
        What it does: Trimming orphans a tool result, which rewrites a kept entry.
        Purpose: final_bytes must reflect the rewritten entry, not its pre-repair size.
        """
        history = [
            {"userInputMessage": {"content": "old" * 200}},
            {"assistantResponseMessage": {
                "content": "a", "toolUses": [{"toolUseId": "T", "name": "n", "input": {}}]}},
            {"userInputMessage": {"content": "u", "userInputMessageContext": {
                "toolResults": [{"toolUseId": "T", "content": [{"text": "res " * 50}]}]}}},
            {"assistantResponseMessage": {"content": "b"}},
            {"userInputMessage": {"content": "u2"}},
            {"assistantResponseMessage": {"content": "c"}},
        ]
        payload = self._payload(history)
        # Limit forces removal of the first pair, which orphans tool result T
        limit = check_payload_size(payload) - 100
        stats = trim_payload_to_limit(payload, max_bytes=limit)
        first = payload["conversationState"]["history"][0]["userInputMessage"]
        assert "userInputMessageContext" not in first
        assert "[trimmed tool result]" in first["content"]
        assert stats.final_bytes == check_payload_size(payload)

    def test_trimming_large_history_serializes_payload_at_most_once(self):
        """
        What it does: Trims a 2000-entry history down to a few entries.
        Purpose: Guard against regressing to one full serialization per popped pair.
        """
        payload = _make_payload(num_pairs=1000, content_size=200)
        limit = check_payload_size(payload) // 100
        with patch.object(
            payload_guards_module, "check_payload_size", wraps=payload_guards_module.check_payload_size
        ) as spy:
            stats = trim_payload_to_limit(payload, max_bytes=limit)
        assert stats.trimmed
        assert spy.call_count <= 1
        assert stats.final_bytes == check_payload_size(payload)
        assert stats.final_bytes <= limit
