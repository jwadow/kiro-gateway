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
Truncation recovery system for handling upstream Kiro API limitations.

Generates synthetic messages to inform the model about truncation.
ONLY activates when truncation is actually detected.

This module addresses Issue #56 - Kiro API truncates large tool call payloads
and content mid-stream. Since this is an upstream limitation that cannot be
prevented, we inform the model about the truncation so it can adapt its approach.
"""

from typing import Dict, Any

from loguru import logger


def should_inject_recovery() -> bool:
    """
    Check if truncation recovery is enabled.
    
    Returns:
        True if recovery should be injected, False otherwise
    """
    from kiro.config import TRUNCATION_RECOVERY
    return TRUNCATION_RECOVERY


def generate_truncation_tool_result(
    tool_name: str,
    tool_use_id: str,
    truncation_info: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate synthetic tool_result for truncated tool call.
    
    Message is carefully worded to:
    - Acknowledge API limitation (not model's fault)
    - Warn against repeating same operation
    - NOT give specific instructions (avoid micro-steps)
    
    Args:
        tool_name: Name of the truncated tool
        tool_use_id: ID of the truncated tool call
        truncation_info: Diagnostic information about truncation
    
    Returns:
        Synthetic tool_result in unified format
    
    Example:
        >>> generate_truncation_tool_result("Write", "call_123", {"size_bytes": 5000, "reason": "missing 2 closing braces"})
        {'type': 'tool_result', 'tool_use_id': 'call_123', 'content': '[API Limitation] ...', 'is_error': True}
    """
    size_bytes = truncation_info.get("size_bytes", 0)
    reason = truncation_info.get("reason", "incomplete tool call")
    tool_lower = (tool_name or "").lower()

    # Distinguish two very different failure modes that the old one-size message
    # conflated:
    #
    #  - SMALL truncations (the common case for subagents — tens to a few hundred
    #    bytes) are a TRANSIENT upstream stream cutoff, NOT an output-size limit.
    #    The old message told the model "output too large", which is misleading and
    #    makes it needlessly shrink or abandon a tiny, correct call. For these, a
    #    straight retry usually succeeds.
    #  - LARGE truncations are genuine size pressure, where repeating the same call
    #    will truncate again and the work must be split into smaller pieces.
    SMALL_TRUNCATION_BYTES = 1024

    is_write_like = any(k in tool_lower for k in ("write", "edit", "replace", "create", "notebook", "multiedit"))
    is_agent_like = any(k in tool_lower for k in ("agent", "task"))

    if size_bytes <= SMALL_TRUNCATION_BYTES:
        lead = (
            "[Upstream Glitch] Your tool call was cut off mid-transmission by the upstream API "
            f"before it finished (only {size_bytes} bytes arrived; {reason}). This is a known, "
            "intermittent upstream issue \u2014 NOT a problem with your input and NOT an output-size "
            "limit. The error in the tool result below is a CONSEQUENCE of that cutoff.\n\n"
        )
        if is_agent_like:
            action = (
                "Recommended: just retry launching the same subagent again. These cutoffs are "
                "transient and the retry typically succeeds \u2014 do not abandon or redesign the task."
            )
        elif is_write_like:
            action = (
                "Recommended: retry the same edit once. If it is cut off again, write the file in "
                "smaller pieces (create it with the first portion, then append the rest) so each "
                "individual call is smaller."
            )
        else:
            action = (
                "Recommended: retry the same tool call \u2014 these transient cutoffs usually "
                "succeed on the next attempt."
            )
    else:
        lead = (
            "[API Limitation] Your tool call was truncated by the upstream API due to its size "
            f"({size_bytes} bytes; {reason}). It was cut off before it could be fully transmitted, "
            "so the tool result below reflects that incomplete call, not a problem with your logic.\n\n"
        )
        if is_write_like:
            action = (
                "Repeating the same large operation will be truncated again. Split it: write an "
                "initial smaller version of the file, then append/extend it in follow-up calls so "
                "no single call is too big."
            )
        else:
            action = (
                "Repeating the exact same operation will be truncated again. Reduce the size of this "
                "call's input, or break the work into smaller steps."
            )

    content = lead + action

    logger.debug(
        f"Generated synthetic tool_result for truncated tool '{tool_name}' "
        f"(id={tool_use_id}, {size_bytes} bytes, {reason}, "
        f"mode={'small/transient' if size_bytes <= SMALL_TRUNCATION_BYTES else 'large/size'})"
    )
    
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content,
        "is_error": True
    }


def generate_tool_protocol_failure_message(tool_call: Dict[str, Any]) -> str:
    """Generate redacted corrective context for a non-executable tool call."""
    failure = tool_call.get("_protocol_failure") or {}
    classification = failure.get("classification", "malformed")
    reason = failure.get("reason", "invalid JSON arguments")
    size_bytes = failure.get("size_bytes", 0)
    function = tool_call.get("function") or {}
    tool_name = function.get("name") or tool_call.get("name") or "unknown"
    tool_use_id = tool_call.get("id") or "unknown"

    if classification == "truncated":
        return generate_truncation_tool_result(
            tool_name=tool_name,
            tool_use_id=tool_use_id,
            truncation_info={"size_bytes": size_bytes, "reason": reason},
        )["content"] + "\n\nNo tool was executed."

    return (
        f"[Tool Protocol Error] The upstream model produced malformed JSON arguments "
        f"for tool '{tool_name}' ({reason}). No tool was executed. Retry the intended "
        "action using one native structured tool call with valid JSON arguments."
    )


def generate_truncation_user_message() -> str:
    """
    Generate synthetic user message for content truncation.
    
    Message is carefully worded to:
    - Acknowledge it's not model's fault
    - Suggest adaptation without specific instructions
    - NOT tell model to "break into steps" (causes micro-steps)
    
    Returns:
        Synthetic user message text
    
    Example:
        >>> generate_truncation_user_message()
        '[System Notice] Your previous response was truncated...'
    """
    return (
        "[System Notice] Your previous response was truncated by the API due to "
        "output size limitations. This is not an error on your part. "
        "If you need to continue, please adapt your approach rather than repeating the same output."
    )
