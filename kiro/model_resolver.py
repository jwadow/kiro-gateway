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
Dynamic Model Resolution System for Kiro Gateway.

Implements a 4-layer resolution pipeline:
1. Normalize Name - Convert client formats to Kiro format (dashes→dots, strip dates)
2. Check Dynamic Cache - Models from /ListAvailableModels API
3. Check Hidden Models - Manual config for undocumented models
4. Pass-through - Unknown models sent to Kiro (let Kiro decide)

Key Principle: We are a gateway, not a gatekeeper. Kiro API is the final arbiter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional

from loguru import logger

if TYPE_CHECKING:
    from kiro.cache import ModelInfoCache


# Valid model IDs accepted by runtime.{region}.kiro.dev
# Generated from FALLBACK_MODELS to maintain single source of truth
from kiro.config import FALLBACK_MODELS

VALID_RUNTIME_MODEL_IDS: set = {model["modelId"] for model in FALLBACK_MODELS}


def to_runtime_model_id(normalized: str) -> str:
    """
    Pass-through function for runtime.kiro.dev model ID.
    
    Previously performed fallback to "auto" for unknown models, but this violated
    the "gateway, not gatekeeper" principle. Now returns model as-is and lets
    Kiro API decide if the model exists.
    
    Args:
        normalized: Normalized model name
    
    Returns:
        Model name as-is (no fallback)
    """
    return normalized


@dataclass(frozen=True)
class ModelResolution:
    """
    Result of model resolution.
    
    Attributes:
        internal_id: ID to send to Kiro API
        source: Resolution source - "cache", "hidden", or "passthrough"
        original_request: What client originally sent
        normalized: Model name after normalization
        is_verified: True if found in cache/hidden, False if passthrough
    """
    internal_id: str
    source: str
    original_request: str
    normalized: str
    is_verified: bool


def normalize_model_name(name: str) -> str:
    """
    Normalize client model name to Kiro format.
    
    Transformations applied:
    1. claude-haiku-4-5 → claude-haiku-4.5 (dash to dot for minor version)
    2. claude-haiku-4-5-20251001 → claude-haiku-4.5 (strip date suffix)
    3. claude-haiku-4-5-latest → claude-haiku-4.5 (strip 'latest' suffix)
    4. claude-sonnet-4-20250514 → claude-sonnet-4 (strip date, no minor)
    5. claude-3-7-sonnet → claude-3.7-sonnet (legacy format normalization)
    6. claude-3-7-sonnet-20250219 → claude-3.7-sonnet (legacy + strip date)
    7. claude-4.5-opus-high → claude-opus-4.5 (inverted format with suffix)
    
    Args:
        name: External model name from client
    
    Returns:
        Normalized model name in Kiro format
    
    Examples:
        >>> normalize_model_name("claude-haiku-4-5-20251001")
        'claude-haiku-4.5'
        >>> normalize_model_name("claude-sonnet-4-5")
        'claude-sonnet-4.5'
        >>> normalize_model_name("claude-opus-4-5")
        'claude-opus-4.5'
        >>> normalize_model_name("claude-sonnet-4")
        'claude-sonnet-4'
        >>> normalize_model_name("claude-sonnet-4-20250514")
        'claude-sonnet-4'
        >>> normalize_model_name("claude-3-7-sonnet")
        'claude-3.7-sonnet'
        >>> normalize_model_name("claude-3-7-sonnet-20250219")
        'claude-3.7-sonnet'
        >>> normalize_model_name("claude-4.5-opus-high")
        'claude-opus-4.5'
        >>> normalize_model_name("claude-4.5-sonnet-low")
        'claude-sonnet-4.5'
        >>> normalize_model_name("auto")
        'auto'
    """
    if not name:
        return name

    # Strip context window suffix (e.g., [1m], [200k]) — client-side indicator, not a model ID
    name = re.sub(r'\[\d+[mk]\]$', '', name, flags=re.IGNORECASE)

    # Lowercase for consistent matching
    name_lower = name.lower()
    
    # Pattern 1: Standard format - claude-{family}-{major}-{minor}(-{suffix})?
    # Matches: claude-haiku-4-5, claude-haiku-4-5-20251001, claude-haiku-4-5-latest
    # Groups: (claude-haiku-4), (5), optional suffix
    # IMPORTANT: Minor version is 1-2 digits only! 8-digit dates should NOT match here.
    standard_pattern = r'^(claude-(?:haiku|sonnet|opus)-\d+)-(\d{1,2})(?:-(?:\d{8}|latest|\d+))?$'
    match = re.match(standard_pattern, name_lower)
    if match:
        base = match.group(1)  # claude-haiku-4
        minor = match.group(2)  # 5
        return f"{base}.{minor}"  # claude-haiku-4.5
    
    # Pattern 2: Standard format without minor - claude-{family}-{major}(-{date})?
    # Matches: claude-sonnet-4, claude-sonnet-4-20250514
    # Groups: (claude-sonnet-4), optional date
    no_minor_pattern = r'^(claude-(?:haiku|sonnet|opus)-\d+)(?:-\d{8})?$'
    match = re.match(no_minor_pattern, name_lower)
    if match:
        return match.group(1)  # claude-sonnet-4
    
    # Pattern 3: Legacy format - claude-{major}-{minor}-{family}(-{suffix})?
    # Matches: claude-3-7-sonnet, claude-3-7-sonnet-20250219
    # Groups: (claude), (3), (7), (sonnet), optional suffix
    legacy_pattern = r'^(claude)-(\d+)-(\d+)-(haiku|sonnet|opus)(?:-(?:\d{8}|latest|\d+))?$'
    match = re.match(legacy_pattern, name_lower)
    if match:
        prefix = match.group(1)  # claude
        major = match.group(2)   # 3
        minor = match.group(3)   # 7
        family = match.group(4)  # sonnet
        return f"{prefix}-{major}.{minor}-{family}"  # claude-3.7-sonnet
    
    # Pattern 4: Already normalized with dot but has date suffix
    # Matches: claude-haiku-4.5-20251001, claude-3.7-sonnet-20250219
    dot_with_date_pattern = r'^(claude-(?:\d+\.\d+-)?(?:haiku|sonnet|opus)(?:-\d+\.\d+)?)-\d{8}$'
    match = re.match(dot_with_date_pattern, name_lower)
    if match:
        return match.group(1)
    
    # Pattern 5: Inverted format with suffix - claude-{major}.{minor}-{family}-{suffix}
    # Matches: claude-4.5-opus-high, claude-4.5-sonnet-low, claude-4.5-opus-high-thinking
    # Convert to: claude-{family}-{major}.{minor}
    # Groups: (4), (5), (opus), any suffix
    # NOTE: This pattern REQUIRES a suffix to avoid matching already-normalized formats like claude-3.7-sonnet
    inverted_with_suffix_pattern = r'^claude-(\d+)\.(\d+)-(haiku|sonnet|opus)-(.+)$'
    match = re.match(inverted_with_suffix_pattern, name_lower)
    if match:
        major = match.group(1)   # 4
        minor = match.group(2)   # 5
        family = match.group(3)  # opus
        return f"claude-{family}-{major}.{minor}"  # claude-opus-4.5
    
    # No transformation needed - return as-is (preserving original case for passthrough)
    return name


def get_model_id_for_kiro(model_name: str, hidden_models: Dict[str, str]) -> str:
    """
    Get the model ID to send to Kiro API.
    
    This is a simple helper for converters that don't have access to the full
    ModelResolver. It normalizes the name and checks hidden models.
    
    For hidden models (like claude-3.7-sonnet), returns the internal Kiro ID.
    For regular models, returns the normalized name.
    
    Args:
        model_name: External model name from client
        hidden_models: Dict mapping display names to internal Kiro IDs
    
    Returns:
        Model ID to send to Kiro API
    
    Examples:
        >>> get_model_id_for_kiro("claude-haiku-4-5-20251001", {})
        'claude-haiku-4.5'
        >>> get_model_id_for_kiro("claude-3.7-sonnet", {"claude-3.7-sonnet": "CLAUDE_3_7_SONNET_20250219_V1_0"})
        'CLAUDE_3_7_SONNET_20250219_V1_0'
        >>> get_model_id_for_kiro("claude-3-7-sonnet", {"claude-3.7-sonnet": "CLAUDE_3_7_SONNET_20250219_V1_0"})
        'CLAUDE_3_7_SONNET_20250219_V1_0'
    """
    normalized = normalize_model_name(model_name)
    internal = hidden_models.get(normalized, normalized)
    return to_runtime_model_id(internal)


def extract_model_family(model_name: str) -> Optional[str]:
    """
    Extract model family from model name.
    
    Args:
        model_name: Model name (normalized or not)
    
    Returns:
        Family name ('haiku', 'sonnet', 'opus') or None if not a Claude model
    
    Examples:
        >>> extract_model_family("claude-haiku-4.5")
        'haiku'
        >>> extract_model_family("claude-sonnet-4-5")
        'sonnet'
        >>> extract_model_family("claude-3.7-sonnet")
        'sonnet'
        >>> extract_model_family("gpt-4")
        None
    """
    family_match = re.search(r'(haiku|sonnet|opus)', model_name, re.IGNORECASE)
    if family_match:
        return family_match.group(1).lower()
    return None


class ModelResolver:
    """
    Dynamic model resolver with normalization and optimistic pass-through.
    
    Key principle: We are a gateway, not a gatekeeper.
    Kiro API is the final arbiter of what models exist.
    
    Resolution layers:
    0. Resolve aliases (custom name mappings)
    1. Normalize name (dashes→dots, strip dates)
    2. Check dynamic cache (from /ListAvailableModels)
    3. Check hidden models (manual config)
    4. Pass-through (let Kiro decide)
    
    Attributes:
        cache: ModelInfoCache instance for dynamic model lookup
        hidden_models: Dict mapping display names to internal Kiro IDs
        aliases: Dict mapping alias names to real model IDs
        hidden_from_list: Set of model IDs to hide from /v1/models endpoint
    
    Example:
        >>> resolver = ModelResolver(cache, hidden_models, aliases={"auto-kiro": "auto"})
        >>> resolution = resolver.resolve("auto-kiro")
        >>> resolution.internal_id
        'auto'
        >>> resolution.source
        'cache'
    """
    
    def __init__(
        self,
        cache: ModelInfoCache,
        hidden_models: Optional[Dict[str, str]] = None,
        aliases: Optional[Dict[str, str]] = None,
        hidden_from_list: Optional[List[str]] = None
    ):
        """
        Initialize the model resolver.
        
        Args:
            cache: ModelInfoCache instance for dynamic model lookup
            hidden_models: Dict mapping display names to internal Kiro IDs.
                          Display names should use dot format (e.g., "claude-3.7-sonnet")
            aliases: Dict mapping alias names to real model IDs.
                    Example: {"auto-kiro": "auto", "my-opus": "claude-opus-4.5"}
            hidden_from_list: List of model IDs to hide from /v1/models endpoint.
                             These models still work but are not shown in the list.
        """
        self.cache = cache
        self.hidden_models = hidden_models or {}
        self.aliases = aliases or {}
        self.hidden_from_list = set(hidden_from_list or [])
    
    def resolve(self, external_model: str) -> ModelResolution:
        """
        Resolve external model name to internal Kiro ID.
        
        NEVER raises - always returns a resolution.
        If model is not in cache/hidden, we pass it through to Kiro.
        Kiro will be the final judge.
        
        Args:
            external_model: Model name from client request
        
        Returns:
            ModelResolution with internal ID and metadata
        """
        # Layer 0: Resolve alias (if exists)
        resolved_model = self.aliases.get(external_model, external_model)
        if resolved_model != external_model:
            logger.debug(
                f"Alias resolved: '{external_model}' → '{resolved_model}'"
            )
        
        # Layer 1: Normalize name (dashes→dots, strip date)
        normalized = normalize_model_name(resolved_model)
        
        logger.debug(
            f"Model resolution: '{external_model}' → normalized: '{normalized}'"
        )
        
        # Layer 2: Check dynamic cache (from /ListAvailableModels)
        if self.cache.is_valid_model(normalized):
            logger.debug(f"Model '{normalized}' found in dynamic cache")
            runtime_id = to_runtime_model_id(normalized)
            return ModelResolution(
                internal_id=runtime_id,
                source="cache",
                original_request=external_model,
                normalized=normalized,
                is_verified=True
            )

        # Layer 3: Check hidden models
        if normalized in self.hidden_models:
            internal_id = self.hidden_models[normalized]
            runtime_id = to_runtime_model_id(internal_id)
            logger.debug(
                f"Model '{normalized}' found in hidden models → '{runtime_id}'"
            )
            return ModelResolution(
                internal_id=runtime_id,
                source="hidden",
                original_request=external_model,
                normalized=normalized,
                is_verified=True
            )

        # Layer 4: Pass-through - validate for runtime endpoint
        runtime_id = to_runtime_model_id(normalized)
        logger.info(
            f"Model '{external_model}' (normalized: '{normalized}') not in cache, "
            f"mapped to runtime ID: '{runtime_id}'"
        )
        return ModelResolution(
            internal_id=runtime_id,
            source="passthrough",
            original_request=external_model,
            normalized=normalized,
            is_verified=False
        )
    
    def get_available_models(self) -> List[str]:
        """
        Get list of all available model IDs for /v1/models endpoint.
        
        Combines:
        - Models from dynamic cache (Kiro API)
        - Hidden models (manual config)
        - Alias names (custom mappings)
        
        Excludes:
        - Models in hidden_from_list (e.g., "auto" when showing "auto-kiro")
        
        Returns:
            List of model IDs in consistent format (with dots)
        """
        # Start with cache models
        models = set(self.cache.get_all_model_ids())
        
        # Add hidden model display names (they use dot format)
        models.update(self.hidden_models.keys())
        
        # Remove models that should be hidden from list
        models -= self.hidden_from_list
        
        # Add alias keys (these are the names users will see and use)
        models.update(self.aliases.keys())
        
        return sorted(models)
    
    def get_models_by_family(self, family: str) -> List[str]:
        """
        Get available models filtered by family.
        
        Used for error messages to suggest alternatives from the same family.
        
        Args:
            family: Model family ('haiku', 'sonnet', 'opus')
        
        Returns:
            List of model IDs from the specified family
        """
        all_models = self.get_available_models()
        return [m for m in all_models if family.lower() in m.lower()]
    
    def get_suggestions_for_model(self, model_name: str) -> List[str]:
        """
        Get available models from the SAME family for error message.
        
        IMPORTANT: Never suggests models from different family!
        Opus request → only Opus suggestions
        Sonnet request → only Sonnet suggestions
        
        Args:
            model_name: The model that was requested but not found
        
        Returns:
            List of available models from the same family, or all models
            if family cannot be determined
        """
        family = extract_model_family(model_name)
        if family:
            return self.get_models_by_family(family)
        
        # If we can't determine family, return all models
        return self.get_available_models()
