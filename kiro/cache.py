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
Model metadata cache for Kiro Gateway.

Thread-safe storage for available model information
with TTL and lazy loading support.
"""

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from kiro.config import MODEL_CACHE_TTL, DEFAULT_MAX_INPUT_TOKENS, PROMPT_CACHE_TTL_SECONDS, PROMPT_CACHE_ACCOUNTING_ENABLED


class ModelInfoCache:
    """
    Thread-safe cache for storing model metadata.
    
    Uses Lazy Loading for population - data is loaded
    only on first access or when cache is stale.
    
    Attributes:
        cache_ttl: Cache time-to-live in seconds
    
    Example:
        >>> cache = ModelInfoCache()
        >>> await cache.update([{"modelId": "claude-sonnet-4", "tokenLimits": {...}}])
        >>> info = cache.get("claude-sonnet-4")
        >>> max_tokens = cache.get_max_input_tokens("claude-sonnet-4")
    """
    
    def __init__(self, cache_ttl: int = MODEL_CACHE_TTL):
        """
        Initializes the model cache.
        
        Args:
            cache_ttl: Cache time-to-live in seconds (default from config)
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._last_update: Optional[float] = None
        self._cache_ttl = cache_ttl
    
    async def update(self, models_data: List[Dict[str, Any]]) -> None:
        """
        Updates the model cache.
        
        Thread-safely replaces cache contents with new data.
        
        Args:
            models_data: List of dictionaries with model information.
                        Each dictionary must contain the "modelId" key.
        """
        async with self._lock:
            logger.info(f"Updating model cache. Found {len(models_data)} models.")
            self._cache = {model["modelId"]: model for model in models_data}
            self._last_update = time.time()
    
    def get(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Returns model information.
        
        Args:
            model_id: Model ID
        
        Returns:
            Dictionary with model information or None if model not found
        """
        return self._cache.get(model_id)
    
    def is_valid_model(self, model_id: str) -> bool:
        """
        Check if model exists in dynamic cache.
        
        Used by ModelResolver to verify if a model is available.
        
        Args:
            model_id: Model ID to check
        
        Returns:
            True if model exists in cache, False otherwise
        """
        return model_id in self._cache
    
    def add_hidden_model(self, display_name: str, internal_id: str) -> None:
        """
        Add a hidden model to the cache.
        
        Hidden models are not returned by Kiro /ListAvailableModels API
        but are still functional. They are added to the cache so they
        appear in our /v1/models endpoint.
        
        Args:
            display_name: Model name to display (e.g., "claude-3.7-sonnet")
            internal_id: Internal Kiro ID (e.g., "CLAUDE_3_7_SONNET_20250219_V1_0")
        """
        if display_name not in self._cache:
            self._cache[display_name] = {
                "modelId": display_name,
                "modelName": display_name,
                "description": f"Hidden model (internal: {internal_id})",
                "tokenLimits": {"maxInputTokens": DEFAULT_MAX_INPUT_TOKENS},
                "_internal_id": internal_id,  # Store internal ID for reference
                "_is_hidden": True,  # Mark as hidden model
            }
            logger.debug(f"Added hidden model: {display_name} → {internal_id}")
    
    def get_max_input_tokens(self, model_id: str) -> int:
        """
        Returns maxInputTokens for the model.
        
        Args:
            model_id: Model ID
        
        Returns:
            Maximum number of input tokens or DEFAULT_MAX_INPUT_TOKENS
        """
        model = self._cache.get(model_id)
        if model and model.get("tokenLimits"):
            return model["tokenLimits"].get("maxInputTokens") or DEFAULT_MAX_INPUT_TOKENS
        return DEFAULT_MAX_INPUT_TOKENS
    
    def is_empty(self) -> bool:
        """
        Checks if the cache is empty.
        
        Returns:
            True if cache is empty
        """
        return not self._cache
    
    def is_stale(self) -> bool:
        """
        Checks if the cache is stale.
        
        Returns:
            True if cache is stale (more than cache_ttl seconds have passed)
            or if cache was never updated
        """
        if not self._last_update:
            return True
        return time.time() - self._last_update > self._cache_ttl
    
    def get_all_model_ids(self) -> List[str]:
        """
        Returns a list of all model IDs in the cache.
        
        Returns:
            List of model IDs
        """
        return list(self._cache.keys())
    
    @property
    def size(self) -> int:
        """Number of models in the cache."""
        return len(self._cache)
    
    @property
    def last_update_time(self) -> Optional[float]:
        """Last update time (timestamp) or None."""
        return self._last_update


@dataclass
class PromptCacheUsage:
    """Anthropic-compatible prompt cache usage fields."""

    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    def to_anthropic_usage_fields(self) -> Dict[str, int]:
        """Return non-zero Anthropic usage fields."""
        fields: Dict[str, int] = {}
        if self.cache_read_input_tokens > 0:
            fields["cache_read_input_tokens"] = self.cache_read_input_tokens
        if self.cache_creation_input_tokens > 0:
            fields["cache_creation_input_tokens"] = self.cache_creation_input_tokens
        return fields


@dataclass
class _PromptCacheEntry:
    tokens: int
    expires_at: float


@dataclass
class _PromptCacheBlock:
    prefix_fingerprint: str
    cumulative_tokens: int
    breakpoint: bool = False
    implicit_breakpoint: bool = False


class PromptCacheTracker:
    """
    In-memory prompt cache accounting using cacheable prompt prefixes.

    This only reports Anthropic cache usage fields. It does not cache model
    responses and does not alter upstream requests. When Anthropic
    ``cache_control`` markers are present, cache reads are matched on the
    stable prompt prefix up to the most recent cacheable breakpoint, so
    appended turns can reuse earlier cached context. Entry TTL is fixed when
    the entry is created and is not refreshed by cache hits.
    """

    def __init__(
        self,
        cache_ttl: int = PROMPT_CACHE_TTL_SECONDS,
        enabled: bool = PROMPT_CACHE_ACCOUNTING_ENABLED,
    ):
        self._cache_ttl = cache_ttl
        self._enabled = enabled
        self._entries: Dict[str, _PromptCacheEntry] = {}
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def size(self) -> int:
        self._prune_expired(time.time())
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()

    async def record(
        self,
        *,
        model: str,
        messages: Optional[List[Dict[str, Any]]],
        tools: Optional[List[Dict[str, Any]]],
        system: Optional[Any],
        input_tokens: int,
    ) -> PromptCacheUsage:
        """
        Record a successful request and return cache accounting usage.

        Args:
            model: Requested model name
            messages: Anthropic request messages as dictionaries
            tools: Anthropic request tools as dictionaries
            system: Anthropic system prompt
            input_tokens: Estimated input tokens for this request
        """
        if not self._enabled or input_tokens <= 0:
            return PromptCacheUsage()

        blocks = self._build_prefix_blocks(
            model=model,
            messages=messages or [],
            tools=tools,
            system=system,
            input_tokens=input_tokens,
        )
        breakpoints = [block for block in blocks if block.breakpoint]
        if not breakpoints:
            return PromptCacheUsage()

        last_breakpoint_tokens = min(breakpoints[-1].cumulative_tokens, input_tokens)
        now = time.time()

        async with self._lock:
            self._prune_expired(now)

            matched_tokens = 0
            for block in reversed(breakpoints[-10:]):
                entry = self._entries.get(block.prefix_fingerprint)
                if entry and entry.expires_at > now:
                    matched_tokens = min(entry.tokens, block.cumulative_tokens, input_tokens)
                    break

            for block in breakpoints:
                self._entries.setdefault(
                    block.prefix_fingerprint,
                    _PromptCacheEntry(
                        tokens=min(block.cumulative_tokens, input_tokens),
                        expires_at=now + self._cache_ttl,
                    ),
                )

            return PromptCacheUsage(
                cache_read_input_tokens=matched_tokens,
                cache_creation_input_tokens=max(last_breakpoint_tokens - matched_tokens, 0),
            )

    def _prune_expired(self, now: float) -> None:
        expired_keys = [
            key for key, entry in self._entries.items()
            if entry.expires_at <= now
        ]
        for key in expired_keys:
            self._entries.pop(key, None)

    def _build_prefix_blocks(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        system: Optional[Any],
        input_tokens: int,
    ) -> List[_PromptCacheBlock]:
        flattened = self._flatten_cache_blocks(
            messages=messages,
            tools=tools or [],
            system=system,
        )
        if not flattened:
            return []

        prelude = {
            "model": model,
        }
        prefix_hash = self._hash_payload(prelude)
        blocks: List[_PromptCacheBlock] = []
        cumulative_tokens = 0
        has_explicit_breakpoint = False
        active_cache = False

        for value, tokens, has_cache_control, is_message_end in flattened:
            cumulative_tokens += max(tokens, 0)
            prefix_hash = self._hash_payload({
                "previous": prefix_hash,
                "block": value,
            })

            if has_cache_control:
                has_explicit_breakpoint = True
                active_cache = True
                blocks.append(_PromptCacheBlock(
                    prefix_fingerprint=prefix_hash,
                    cumulative_tokens=cumulative_tokens,
                    breakpoint=True,
                ))
            elif active_cache and is_message_end:
                blocks.append(_PromptCacheBlock(
                    prefix_fingerprint=prefix_hash,
                    cumulative_tokens=cumulative_tokens,
                    breakpoint=True,
                ))
            else:
                blocks.append(_PromptCacheBlock(
                    prefix_fingerprint=prefix_hash,
                    cumulative_tokens=cumulative_tokens,
                    breakpoint=False,
                    implicit_breakpoint=is_message_end,
                ))

        if not has_explicit_breakpoint:
            min_cacheable_tokens = self._minimum_cacheable_tokens(model)
            implicit_blocks = [
                _PromptCacheBlock(
                    prefix_fingerprint=block.prefix_fingerprint,
                    cumulative_tokens=block.cumulative_tokens,
                    breakpoint=block.cumulative_tokens >= min_cacheable_tokens,
                    implicit_breakpoint=block.implicit_breakpoint,
                )
                for block in blocks
            ]
            if any(block.breakpoint for block in implicit_blocks):
                blocks = implicit_blocks
            else:
                # Preserve the old behavior for short callers without
                # Anthropic cache_control markers: exact repeated requests
                # still report cache reads, but appended short conversations do
                # not accidentally match.
                blocks[-1] = _PromptCacheBlock(
                    prefix_fingerprint=prefix_hash,
                    cumulative_tokens=input_tokens,
                    breakpoint=True,
                )

        return blocks

    def _flatten_cache_blocks(
        self,
        *,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system: Optional[Any],
    ) -> List[Tuple[Any, int, bool, bool]]:
        blocks: List[Tuple[Any, int, bool, bool]] = []

        for index, tool in enumerate(tools):
            normalized, has_cache_control = self._strip_cache_control(tool)
            blocks.append((
                {"kind": "tool", "tool_index": index, "tool": normalized},
                self._estimate_tokens(normalized),
                has_cache_control,
                False,
            ))

        system_blocks = system if isinstance(system, list) else ([system] if system else [])
        for index, block in enumerate(system_blocks):
            normalized, has_cache_control = self._strip_cache_control(block)
            blocks.append((
                {"kind": "system", "system_index": index, "block": normalized},
                self._estimate_tokens(normalized),
                has_cache_control,
                False,
            ))

        for message_index, message in enumerate(messages):
            role = message.get("role", "")
            content = message.get("content")
            if isinstance(content, list):
                last_block_index = len(content) - 1
                for block_index, content_block in enumerate(content):
                    normalized, has_cache_control = self._strip_cache_control(content_block)
                    blocks.append((
                        {
                            "kind": "message",
                            "message_index": message_index,
                            "role": role,
                            "block_index": block_index,
                            "block": normalized,
                        },
                        self._estimate_tokens(normalized),
                        has_cache_control,
                        block_index == last_block_index,
                    ))
            else:
                normalized, has_cache_control = self._strip_cache_control(content)
                blocks.append((
                    {
                        "kind": "message",
                        "message_index": message_index,
                        "role": role,
                        "block_index": 0,
                        "block": normalized,
                    },
                    self._estimate_tokens(normalized),
                    has_cache_control,
                    True,
                ))

        return blocks

    def _strip_cache_control(self, value: Any) -> Tuple[Any, bool]:
        normalized = self._normalize(value)
        found = False

        def strip(item: Any) -> Any:
            nonlocal found
            if isinstance(item, dict):
                output = {}
                for key, subvalue in item.items():
                    if key == "cache_control":
                        if isinstance(subvalue, dict) and subvalue.get("type") == "ephemeral":
                            found = True
                        continue
                    output[key] = strip(subvalue)
                return output
            if isinstance(item, list):
                return [strip(subvalue) for subvalue in item]
            return item

        return strip(normalized), found

    def _estimate_tokens(self, value: Any) -> int:
        if isinstance(value, str):
            text = value
        else:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        try:
            from kiro.tokenizer import count_tokens
            return count_tokens(text)
        except Exception:
            return len(text) // 4 + 1

    def _hash_payload(self, value: Any) -> str:
        serialized = json.dumps(
            self._normalize(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _minimum_cacheable_tokens(self, model: str) -> int:
        model_lower = model.lower()
        if "opus" in model_lower:
            return 4096
        if "haiku-3" in model_lower or "haiku_3" in model_lower:
            return 2048
        return 1024

    def _normalize(self, value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return self._normalize(value.model_dump(exclude_none=True))
        if isinstance(value, dict):
            return {
                str(key): self._normalize(item)
                for key, item in sorted(value.items(), key=lambda kv: str(kv[0]))
                if item is not None
            }
        if isinstance(value, list):
            return [self._normalize(item) for item in value]
        return value


prompt_cache_tracker = PromptCacheTracker()