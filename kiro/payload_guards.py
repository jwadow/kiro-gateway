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
Payload size guard for Kiro API requests.

The Kiro API rejects payloads exceeding ~615KB with a misleading
"Improperly formed request." (reason: null) error. This module provides:
- Pre-flight size checking
- Auto-trimming of oldest history entries to fit under the limit

Ported from sametakofficial's payload_guards.py, simplified.
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from loguru import logger


# Compact JSON separators used for every size measurement.
_COMPACT_SEPARATORS = (",", ":")

# Byte length of the serialized member  "toolUses":[]  (without braces).
_EMPTY_TOOL_USES_BYTES = len(json.dumps({"toolUses": []}, separators=_COMPACT_SEPARATORS)) - 2


@dataclass
class PayloadTrimStats:
    """Statistics from a payload trim operation."""
    original_bytes: int
    final_bytes: int
    original_entries: int
    final_entries: int
    trimmed: bool


def check_payload_size(payload: Dict[str, Any]) -> int:
    """Return the serialized byte size of the payload as UTF-8 JSON."""
    return len(json.dumps(payload, separators=_COMPACT_SEPARATORS).encode("utf-8"))


def _entry_size(entry: Any) -> int:
    """
    Return the compact UTF-8 JSON byte size of a single history entry.

    Args:
        entry: History entry (any JSON-serializable value)

    Returns:
        Serialized byte size of the entry
    """
    return len(json.dumps(entry, separators=_COMPACT_SEPARATORS).encode("utf-8"))


def _strip_empty_tool_uses(history: list) -> int:
    """
    Remove empty toolUses arrays in-place (Kiro quirk).

    Args:
        history: Kiro history list (modified in place)

    Returns:
        Number of serialized bytes removed from the payload. Each removal drops
        the "toolUses":[] member plus one separating comma when the assistant
        message has other keys.
    """
    removed_bytes = 0
    for entry in history:
        assistant = entry.get("assistantResponseMessage")
        if assistant and "toolUses" in assistant and assistant["toolUses"] == []:
            removed_bytes += _EMPTY_TOOL_USES_BYTES + (1 if len(assistant) > 1 else 0)
            del assistant["toolUses"]
    return removed_bytes


def _align_to_user_message(history: list) -> list:
    """Ensure history starts with a userInputMessage entry."""
    while history and "userInputMessage" not in history[0]:
        history.pop(0)
    return history


def _repair_orphaned_tool_results(history: list) -> Set[int]:
    """
    Remove orphaned toolResults that reference toolUseIds not present
    in the preceding assistant message. Preserve orphaned text content
    inline with a marker.

    Args:
        history: Kiro history list (modified in place)

    Returns:
        Indices of history entries that were modified.
    """
    modified: Set[int] = set()
    for i, entry in enumerate(history):
        user_msg = entry.get("userInputMessage")
        if not user_msg:
            continue

        ctx = user_msg.get("userInputMessageContext")
        if not ctx or "toolResults" not in ctx:
            continue

        # Collect toolUseIds from the preceding assistant message
        valid_ids = set()
        if i > 0:
            prev_assistant = history[i - 1].get("assistantResponseMessage")
            if prev_assistant:
                for tu in prev_assistant.get("toolUses", []):
                    tool_use_id = tu.get("toolUseId")
                    if tool_use_id:
                        valid_ids.add(tool_use_id)

        kept = []
        orphaned_text_parts = []
        for tr in ctx["toolResults"]:
            if tr.get("toolUseId") in valid_ids:
                kept.append(tr)
            else:
                # Preserve text content from orphaned results
                content = tr.get("content")
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("text"):
                            orphaned_text_parts.append(part["text"])
                elif isinstance(content, str) and content:
                    orphaned_text_parts.append(content)

        if len(kept) != len(ctx["toolResults"]):
            modified.add(i)
            if kept:
                ctx["toolResults"] = kept
            else:
                del ctx["toolResults"]
                if not ctx:
                    del user_msg["userInputMessageContext"]

            # Append orphaned text to user message content
            if orphaned_text_parts:
                marker = "\n[trimmed tool result] " + "; ".join(orphaned_text_parts)
                current_content = user_msg.get("content", "")
                user_msg["content"] = current_content + marker
    return modified


class _HistorySizeTracker:
    """
    Tracks the serialized payload size while history entries are removed.

    The compact JSON of a list is "[" + ",".join(items) + "]", so removing one
    of several entries shrinks the payload by exactly entry_size + 1 bytes, and
    removing the last remaining entry shrinks it by entry_size. Each entry is
    serialized once, instead of re-serializing the whole payload after every
    removal (which made trimming quadratic in history length).

    Attributes:
        sizes: Serialized byte size of each remaining history entry
        total_bytes: Current serialized size of the whole payload
    """

    def __init__(self, history: List[Any], total_bytes: int) -> None:
        """
        Args:
            history: History list being trimmed (each entry is measured once)
            total_bytes: Current serialized size of the whole payload
        """
        self.sizes: List[int] = [_entry_size(entry) for entry in history]
        self.total_bytes = total_bytes

    def pop_front(self, history: List[Any]) -> None:
        """
        Remove the first history entry and update the running total.

        Args:
            history: History list tracked by this instance (modified in place)
        """
        history.pop(0)
        size = self.sizes.pop(0)
        self.total_bytes -= size + (1 if self.sizes else 0)

    def remeasure(self, history: List[Any], index: int) -> None:
        """
        Re-measure an entry that was modified in place.

        Args:
            history: History list tracked by this instance
            index: Index of the modified entry
        """
        new_size = _entry_size(history[index])
        self.total_bytes += new_size - self.sizes[index]
        self.sizes[index] = new_size


def trim_payload_to_limit(
    payload: Dict[str, Any],
    max_bytes: int,
    current_size: Optional[int] = None,
) -> PayloadTrimStats:
    """
    Trim oldest history entries so the serialized payload fits under max_bytes.

    Trims in user/assistant pairs (2 entries at a time), aligns start to
    userInputMessage, and repairs orphaned toolResults after trimming.
    Each history entry is serialized once and the payload size is kept as a
    running total, so trimming is linear in history size.

    Args:
        payload: Kiro payload (modified in place)
        max_bytes: Maximum allowed serialized size in bytes
        current_size: Precomputed check_payload_size(payload), if the caller
            already has it. Saves one full serialization.

    Returns:
        PayloadTrimStats describing the trim operation
    """
    original_bytes = current_size if current_size is not None else check_payload_size(payload)
    history = payload.get("conversationState", {}).get("history")

    if not history:
        return PayloadTrimStats(
            original_bytes=original_bytes,
            final_bytes=original_bytes,
            original_entries=0,
            final_entries=0,
            trimmed=False,
        )

    original_entries = len(history)

    # Strip empty toolUses before measuring
    stripped_bytes = _strip_empty_tool_uses(history)
    tracker = _HistorySizeTracker(history, original_bytes - stripped_bytes)

    # Trim pairs from the beginning until under limit (keep at least 2 entries)
    while len(history) > 2 and tracker.total_bytes > max_bytes:
        # Remove 2 entries (a user/assistant pair)
        tracker.pop_front(history)
        tracker.pop_front(history)

    # Align to userInputMessage boundary
    while history and "userInputMessage" not in history[0]:
        tracker.pop_front(history)

    # Repair orphaned tool results after trimming
    for index in _repair_orphaned_tool_results(history):
        tracker.remeasure(history, index)

    final_bytes = tracker.total_bytes
    logger.debug(
        f"Payload trim: {original_entries} -> {len(history)} entries, "
        f"{original_bytes} -> {final_bytes} bytes (limit {max_bytes})"
    )
    return PayloadTrimStats(
        original_bytes=original_bytes,
        final_bytes=final_bytes,
        original_entries=original_entries,
        final_entries=len(history),
        trimmed=original_entries != len(history),
    )
