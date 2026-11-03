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
In-memory cache for truncation recovery state.

Tracks truncated tool calls and content by stable identifiers:
- Tool calls: tracked by tool_call_id (stable across requests)
- Content: tracked by hash of truncated assistant message (stable)

Thread-safe for concurrent requests.
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Dict, Optional
from threading import Lock

from loguru import logger


@dataclass
class ToolTruncationInfo:
    """
    Information about a truncated tool call.
    
    Attributes:
        tool_call_id: Stable ID of the truncated tool call
        tool_name: Name of the tool that was called
        truncation_info: Diagnostic information from parser
        timestamp: Unix timestamp when truncation was detected
    """
    tool_call_id: str
    tool_name: str
    truncation_info: Dict
    timestamp: float


@dataclass
class ContentTruncationInfo:
    """
    Information about truncated content (non-tool output).
    
    Attributes:
        message_hash: Hash of the truncated assistant message
        content_preview: First 200 chars of truncated content (for debugging)
        timestamp: Unix timestamp when truncation was detected
    """
    message_hash: str
    content_preview: str
    timestamp: float


# In-memory caches
# Entries persist until:
# 1. Retrieved via get_* functions (one-time retrieval deletes entry)
# 2. Gateway restart (in-memory cache is cleared)
# No TTL - if user takes a break for hours, truncation info should still be available
_tool_truncation_cache: Dict[str, ToolTruncationInfo] = {}
_content_truncation_cache: Dict[str, ContentTruncationInfo] = {}
_cache_lock = Lock()


def save_tool_truncation(tool_call_id: str, tool_name: str, truncation_info: Dict) -> None:
    """
    Save truncation info for a specific tool call.
    
    Thread-safe operation.
    
    Args:
        tool_call_id: Stable ID of the truncated tool call
        tool_name: Name of the tool
        truncation_info: Diagnostic information from parser
    
    Example:
        >>> save_tool_truncation("call_abc123", "Write", {"size_bytes": 5000, "reason": "..."})
    """
    with _cache_lock:
        info = ToolTruncationInfo(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            truncation_info=truncation_info,
            timestamp=time.time()
        )
        _tool_truncation_cache[tool_call_id] = info
        logger.debug(f"Saved tool truncation for {tool_call_id} ({tool_name})")


def get_tool_truncation(tool_call_id: str) -> Optional[ToolTruncationInfo]:
    """
    Get and remove truncation info for a specific tool call.
    
    This is a one-time operation - info is removed after retrieval.
    Thread-safe operation.
    
    Args:
        tool_call_id: Stable ID of the tool call
    
    Returns:
        ToolTruncationInfo if found, None otherwise
    
    Example:
        >>> info = get_tool_truncation("call_abc123")
        >>> if info:
        ...     print(f"Tool {info.tool_name} was truncated")
    """
    with _cache_lock:
        info = _tool_truncation_cache.pop(tool_call_id, None)
        if info:
            logger.debug(f"Retrieved tool truncation for {tool_call_id}")
        return info


def save_content_truncation(content: str) -> str:
    """
    Save truncation info for content (non-tool output).
    
    Generates a hash of the content to use as stable identifier.
    Thread-safe operation.
    
    Args:
        content: The truncated content
    
    Returns:
        Hash of the content (for tracking)
    
    Example:
        >>> content_hash = save_content_truncation("This is truncated conte...")
    """
    # Use first 500 chars for hash (enough to be unique, not too much)
    content_for_hash = content[:500]
    message_hash = hashlib.sha256(content_for_hash.encode()).hexdigest()[:16]
    
    with _cache_lock:
        info = ContentTruncationInfo(
            message_hash=message_hash,
            content_preview=content[:200],  # For debugging
            timestamp=time.time()
        )
        _content_truncation_cache[message_hash] = info
        logger.debug(f"Saved content truncation with hash {message_hash}")
    
    return message_hash


def get_content_truncation(content: str) -> Optional[ContentTruncationInfo]:
    """
    Get and remove truncation info for specific content.
    
    Generates hash from content and looks it up in cache.
    This is a one-time operation - info is removed after retrieval.
    Thread-safe operation.
    
    Args:
        content: The content to check (should match truncated content)
    
    Returns:
        ContentTruncationInfo if found, None otherwise
    
    Example:
        >>> # In next request, check if this assistant message was truncated
        >>> info = get_content_truncation(assistant_message.content)
        >>> if info:
        ...     print("This message was truncated in previous response")
    """
    content_for_hash = content[:500]
    message_hash = hashlib.sha256(content_for_hash.encode()).hexdigest()[:16]
    
    with _cache_lock:
        info = _content_truncation_cache.pop(message_hash, None)
        if info:
            logger.debug(f"Retrieved content truncation for hash {message_hash}")
        return info




def has_pending() -> bool:
    """
    Check whether any truncation info is waiting to be recovered.

    Lets routes skip the per-message recovery scan entirely in the common case
    where nothing was truncated. Reads dict sizes without taking the lock:
    len() on a dict is atomic in CPython, and a stale answer only means one
    request scans (or skips) an entry saved concurrently, which is then
    handled on the next request.

    Returns:
        True if either the tool or the content truncation cache is non-empty
    """
    return bool(_tool_truncation_cache) or bool(_content_truncation_cache)


def get_cache_stats() -> Dict[str, int]:
    """
    Get current cache statistics.
    
    Useful for monitoring and debugging.
    
    Returns:
        Dictionary with cache sizes
    
    Example:
        >>> stats = get_cache_stats()
        >>> print(f"Tool truncations: {stats['tool_truncations']}")
        >>> print(f"Content truncations: {stats['content_truncations']}")
    """
    with _cache_lock:
        return {
            "tool_truncations": len(_tool_truncation_cache),
            "content_truncations": len(_content_truncation_cache),
            "total": len(_tool_truncation_cache) + len(_content_truncation_cache)
        }
