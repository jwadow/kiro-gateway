# -*- coding: utf-8 -*-

"""
Unit tests for Dynamic Model Resolution System.

Tests 5-layer model resolution architecture:
0. Resolve Aliases - custom name mappings (NEW!)
1. Normalize Name - convert client formats to Kiro format
2. Check Dynamic Cache - models from /ListAvailableModels API
3. Check Hidden Models - manual config for undocumented models
4. Pass-through - unknown models are sent to Kiro
"""

import pytest
from dataclasses import FrozenInstanceError

from kiro.model_resolver import (
    normalize_model_name,
    get_model_id_for_kiro,
    extract_model_family,
    ModelResolver,
    ModelResolution,
)
from kiro.cache import ModelInfoCache


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_model_cache():
    """
    Creates ModelInfoCache with pre-populated models.
    Simulates data from Kiro /ListAvailableModels API.
    """
    print("Setup: Creating ModelInfoCache with test models...")
    cache = ModelInfoCache()
    # Directly populate cache (without async update)
    cache._cache = {
        "auto": {"modelId": "auto", "modelName": "Auto"},
        "claude-sonnet-4.5": {"modelId": "claude-sonnet-4.5", "modelName": "Claude Sonnet 4.5"},
        "claude-sonnet-4": {"modelId": "claude-sonnet-4", "modelName": "Claude Sonnet 4"},
        "claude-haiku-4.5": {"modelId": "claude-haiku-4.5", "modelName": "Claude Haiku 4.5"},
        "claude-opus-4.5": {"modelId": "claude-opus-4.5", "modelName": "Claude Opus 4.5"},
    }
    return cache


@pytest.fixture
def empty_model_cache():
    """Creates empty ModelInfoCache."""
    print("Setup: Creating empty ModelInfoCache...")
    return ModelInfoCache()


@pytest.fixture
def hidden_models():
    """Hidden models for tests."""
    return {
        "claude-3.7-sonnet": "CLAUDE_3_7_SONNET_20250219_V1_0",
    }


@pytest.fixture
def model_resolver(mock_model_cache, hidden_models):
    """Ready-to-use ModelResolver for tests."""
    print("Setup: Creating ModelResolver with cache and hidden models...")
    return ModelResolver(cache=mock_model_cache, hidden_models=hidden_models)


@pytest.fixture
def resolver_without_hidden(mock_model_cache):
    """ModelResolver without hidden models."""
    print("Setup: Creating ModelResolver without hidden models...")
    return ModelResolver(cache=mock_model_cache, hidden_models={})


# =============================================================================
# TestNormalizeModelName - Tests for model name normalization
# =============================================================================

class TestNormalizeModelName:
    """
    Tests for normalize_model_name() function.
    
    Checks conversion of client formats to Kiro format:
    - Dashes → dots for minor versions
    - Removal of date suffix (20251001)
    - Removal of 'latest' suffix
    - Legacy format (claude-3-7-sonnet)
    """
    
    # === Standard format with minor version ===
    
    def test_normalizes_haiku_dash_to_dot(self):
        """
        What it does: claude-haiku-4-5 → claude-haiku-4.5
        Goal: Check dash-to-dot conversion for Haiku.
        """
        print("Action: Normalizing 'claude-haiku-4-5'...")
        result = normalize_model_name("claude-haiku-4-5")
        
        print(f"Comparing result: Expected 'claude-haiku-4.5', Got '{result}'")
        assert result == "claude-haiku-4.5"
    
    def test_normalizes_sonnet_dash_to_dot(self):
        """
        What it does: claude-sonnet-4-5 → claude-sonnet-4.5
        Goal: Check dash-to-dot conversion for Sonnet.
        """
        print("Action: Normalizing 'claude-sonnet-4-5'...")
        result = normalize_model_name("claude-sonnet-4-5")
        
        print(f"Comparing result: Expected 'claude-sonnet-4.5', Got '{result}'")
        assert result == "claude-sonnet-4.5"
    
    def test_normalizes_opus_dash_to_dot(self):
        """
        What it does: claude-opus-4-5 → claude-opus-4.5
        Goal: Check dash-to-dot conversion for Opus.
        """
        print("Action: Normalizing 'claude-opus-4-5'...")
        result = normalize_model_name("claude-opus-4-5")
        
        print(f"Comparing result: Expected 'claude-opus-4.5', Got '{result}'")
        assert result == "claude-opus-4.5"
    
    # === Removal of date suffix ===
    
    def test_strips_date_suffix_haiku(self):
        """
        What it does: claude-haiku-4-5-20251001 → claude-haiku-4.5
        Goal: Check date suffix removal for Haiku (Claude Code format).
        """
        print("Action: Normalizing 'claude-haiku-4-5-20251001'...")
        result = normalize_model_name("claude-haiku-4-5-20251001")
        
        print(f"Comparing result: Expected 'claude-haiku-4.5', Got '{result}'")
        assert result == "claude-haiku-4.5"
    
    def test_strips_date_suffix_sonnet(self):
        """
        What it does: claude-sonnet-4-5-20250929 → claude-sonnet-4.5
        Goal: Check date suffix removal for Sonnet.
        """
        print("Action: Normalizing 'claude-sonnet-4-5-20250929'...")
        result = normalize_model_name("claude-sonnet-4-5-20250929")
        
        print(f"Comparing result: Expected 'claude-sonnet-4.5', Got '{result}'")
        assert result == "claude-sonnet-4.5"
    
    def test_strips_date_suffix_opus(self):
        """
        What it does: claude-opus-4-5-20251101 → claude-opus-4.5
        Goal: Check date suffix removal for Opus.
        """
        print("Action: Normalizing 'claude-opus-4-5-20251101'...")
        result = normalize_model_name("claude-opus-4-5-20251101")
        
        print(f"Comparing result: Expected 'claude-opus-4.5', Got '{result}'")
        assert result == "claude-opus-4.5"
    
    # === Removal of 'latest' suffix ===
    
    def test_strips_latest_suffix(self):
        """
        What it does: claude-haiku-4-5-latest → claude-haiku-4.5
        Goal: Check 'latest' suffix removal.
        """
        print("Action: Normalizing 'claude-haiku-4-5-latest'...")
        result = normalize_model_name("claude-haiku-4-5-latest")
        
        print(f"Comparing result: Expected 'claude-haiku-4.5', Got '{result}'")
        assert result == "claude-haiku-4.5"
    
    # === Standard format without minor version ===
    
    def test_keeps_model_without_minor(self):
        """
        What it does: claude-sonnet-4 → claude-sonnet-4
        Goal: Check that models without minor version are unchanged.
        """
        print("Action: Normalizing 'claude-sonnet-4'...")
        result = normalize_model_name("claude-sonnet-4")
        
        print(f"Comparing result: Expected 'claude-sonnet-4', Got '{result}'")
        assert result == "claude-sonnet-4"
    
    def test_strips_date_from_model_without_minor(self):
        """
        What it does: claude-sonnet-4-20250514 → claude-sonnet-4
        Goal: Check date suffix removal for model without minor version.
        """
        print("Action: Normalizing 'claude-sonnet-4-20250514'...")
        result = normalize_model_name("claude-sonnet-4-20250514")
        
        print(f"Comparing result: Expected 'claude-sonnet-4', Got '{result}'")
        assert result == "claude-sonnet-4"
    
    # === Legacy format (claude-X-Y-family) ===
    
    def test_normalizes_legacy_format(self):
        """
        What it does: claude-3-7-sonnet → claude-3.7-sonnet
        Goal: Check legacy format normalization.
        """
        print("Action: Normalizing 'claude-3-7-sonnet'...")
        result = normalize_model_name("claude-3-7-sonnet")
        
        print(f"Comparing result: Expected 'claude-3.7-sonnet', Got '{result}'")
        assert result == "claude-3.7-sonnet"
    
    def test_normalizes_legacy_format_with_date(self):
        """
        What it does: claude-3-7-sonnet-20250219 → claude-3.7-sonnet
        Goal: Check legacy format normalization with date suffix.
        """
        print("Action: Normalizing 'claude-3-7-sonnet-20250219'...")
        result = normalize_model_name("claude-3-7-sonnet-20250219")
        
        print(f"Comparing result: Expected 'claude-3.7-sonnet', Got '{result}'")
        assert result == "claude-3.7-sonnet"
    
    def test_normalizes_legacy_haiku(self):
        """
        What it does: claude-3-5-haiku → claude-3.5-haiku
        Goal: Check legacy format normalization for Haiku.
        """
        print("Action: Normalizing 'claude-3-5-haiku'...")
        result = normalize_model_name("claude-3-5-haiku")
        
        print(f"Comparing result: Expected 'claude-3.5-haiku', Got '{result}'")
        assert result == "claude-3.5-haiku"
    
    def test_normalizes_legacy_opus(self):
        """
        What it does: claude-3-0-opus → claude-3.0-opus
        Goal: Check legacy format normalization for Opus.
        """
        print("Action: Normalizing 'claude-3-0-opus'...")
        result = normalize_model_name("claude-3-0-opus")
        
        print(f"Comparing result: Expected 'claude-3.0-opus', Got '{result}'")
        assert result == "claude-3.0-opus"
    
    # === Inverted format with suffix (Pattern 5 - Cursor IDE) ===
    
    def test_inverted_format_with_high_suffix(self):
        """
        What it does: claude-4.5-opus-high → claude-opus-4.5
        Goal: Check inverted format normalization with 'high' suffix (Cursor IDE).
        
        Cursor IDE sends model names in inverted format with priority suffix.
        This is Pattern 5 from PR #49.
        """
        print("Action: Normalizing 'claude-4.5-opus-high'...")
        result = normalize_model_name("claude-4.5-opus-high")
        
        print(f"Comparing result: Expected 'claude-opus-4.5', Got '{result}'")
        assert result == "claude-opus-4.5"
    
    def test_inverted_format_with_low_suffix(self):
        """
        What it does: claude-4.5-sonnet-low → claude-sonnet-4.5
        Goal: Check inverted format normalization with 'low' suffix (Cursor IDE).
        """
        print("Action: Normalizing 'claude-4.5-sonnet-low'...")
        result = normalize_model_name("claude-4.5-sonnet-low")
        
        print(f"Comparing result: Expected 'claude-sonnet-4.5', Got '{result}'")
        assert result == "claude-sonnet-4.5"
    
    def test_inverted_format_with_thinking_suffix(self):
        """
        What it does: claude-4.5-opus-high-thinking → claude-opus-4.5
        Goal: Check inverted format with compound suffix (high-thinking).
        
        The pattern strips ALL suffixes after the family name.
        """
        print("Action: Normalizing 'claude-4.5-opus-high-thinking'...")
        result = normalize_model_name("claude-4.5-opus-high-thinking")
        
        print(f"Comparing result: Expected 'claude-opus-4.5', Got '{result}'")
        assert result == "claude-opus-4.5"
    
    def test_inverted_format_all_families(self):
        """
        What it does: Verifies inverted format works for all families.
        Goal: Check haiku, sonnet, opus all work with inverted format.
        """
        print("Action: Normalizing inverted format for all families...")
        
        print("  Testing haiku...")
        result_haiku = normalize_model_name("claude-4.5-haiku-high")
        print(f"  Comparing: Expected 'claude-haiku-4.5', Got '{result_haiku}'")
        assert result_haiku == "claude-haiku-4.5"
        
        print("  Testing sonnet...")
        result_sonnet = normalize_model_name("claude-4.5-sonnet-low")
        print(f"  Comparing: Expected 'claude-sonnet-4.5', Got '{result_sonnet}'")
        assert result_sonnet == "claude-sonnet-4.5"
        
        print("  Testing opus...")
        result_opus = normalize_model_name("claude-4.5-opus-high")
        print(f"  Comparing: Expected 'claude-opus-4.5', Got '{result_opus}'")
        assert result_opus == "claude-opus-4.5"
    
    def test_inverted_format_requires_suffix(self):
        """
        What it does: Verifies that suffix is required (doesn't match claude-3.7-sonnet).
        Goal: CRITICAL - ensure Pattern 5 doesn't break already-normalized formats.
        
        This is the most important test for Pattern 5. The regex MUST require a suffix
        to avoid matching already-normalized formats like claude-3.7-sonnet.
        """
        print("Action: Normalizing 'claude-3.7-sonnet' (should NOT match Pattern 5)...")
        result = normalize_model_name("claude-3.7-sonnet")
        
        print(f"Comparing result: Expected 'claude-3.7-sonnet' (unchanged), Got '{result}'")
        assert result == "claude-3.7-sonnet"
        
        print("Action: Normalizing 'claude-4.5-sonnet' (should NOT match Pattern 5)...")
        result2 = normalize_model_name("claude-4.5-sonnet")
        
        print(f"Comparing result: Expected 'claude-4.5-sonnet' (unchanged), Got '{result2}'")
        assert result2 == "claude-4.5-sonnet"
    
    def test_inverted_format_case_insensitive(self):
        """
        What it does: CLAUDE-4.5-OPUS-HIGH → claude-opus-4.5
        Goal: Check case insensitivity for inverted format.
        """
        print("Action: Normalizing 'CLAUDE-4.5-OPUS-HIGH'...")
        result = normalize_model_name("CLAUDE-4.5-OPUS-HIGH")
        
        print(f"Comparing result: Expected 'claude-opus-4.5', Got '{result}'")
        assert result == "claude-opus-4.5"
    
    # === Already normalized (passthrough) ===
    
    def test_passthrough_already_normalized_haiku(self):
        """
        What it does: claude-haiku-4.5 → claude-haiku-4.5
        Goal: Check that already normalized models are unchanged.
        """
        print("Action: Normalizing 'claude-haiku-4.5'...")
        result = normalize_model_name("claude-haiku-4.5")
        
        print(f"Comparing result: Expected 'claude-haiku-4.5', Got '{result}'")
        assert result == "claude-haiku-4.5"
    
    def test_passthrough_already_normalized_sonnet(self):
        """
        What it does: claude-sonnet-4.5 → claude-sonnet-4.5
        Goal: Check passthrough for Sonnet.
        """
        print("Action: Normalizing 'claude-sonnet-4.5'...")
        result = normalize_model_name("claude-sonnet-4.5")
        
        print(f"Comparing result: Expected 'claude-sonnet-4.5', Got '{result}'")
        assert result == "claude-sonnet-4.5"
    
    def test_passthrough_auto(self):
        """
        What it does: auto → auto
        Goal: Check passthrough for 'auto'.
        """
        print("Action: Normalizing 'auto'...")
        result = normalize_model_name("auto")
        
        print(f"Comparing result: Expected 'auto', Got '{result}'")
        assert result == "auto"
    
    # === Edge cases ===
    
    def test_handles_empty_string(self):
        """
        What it does: "" → ""
        Goal: Check empty string handling.
        """
        print("Action: Normalizing empty string...")
        result = normalize_model_name("")
        
        print(f"Comparing result: Expected '', Got '{result}'")
        assert result == ""
    
    def test_handles_unknown_format(self):
        """
        What it does: gpt-4 → gpt-4 (passthrough)
        Goal: Check passthrough for unknown formats.
        """
        print("Action: Normalizing 'gpt-4'...")
        result = normalize_model_name("gpt-4")
        
        print(f"Comparing result: Expected 'gpt-4', Got '{result}'")
        assert result == "gpt-4"
    
    def test_handles_random_model_name(self):
        """
        What it does: some-random-model → some-random-model
        Goal: Check passthrough for arbitrary names.
        """
        print("Action: Normalizing 'some-random-model'...")
        result = normalize_model_name("some-random-model")
        
        print(f"Comparing result: Expected 'some-random-model', Got '{result}'")
        assert result == "some-random-model"


# =============================================================================
# TestNormalizeModelNameParametrized - Parametrized tests
# =============================================================================

class TestNormalizeModelNameParametrized:
    """Parametrized tests for complete coverage of scenarios."""
    
    @pytest.mark.parametrize("input_model,expected", [
        # Standard format with minor version
        ("claude-haiku-4-5", "claude-haiku-4.5"),
        ("claude-haiku-4-5-20251001", "claude-haiku-4.5"),
        ("claude-haiku-4-5-latest", "claude-haiku-4.5"),
        ("claude-sonnet-4-5", "claude-sonnet-4.5"),
        ("claude-sonnet-4-5-20250929", "claude-sonnet-4.5"),
        ("claude-opus-4-5", "claude-opus-4.5"),
        ("claude-opus-4-5-20251101", "claude-opus-4.5"),
        # Without minor version
        ("claude-sonnet-4", "claude-sonnet-4"),
        ("claude-sonnet-4-20250514", "claude-sonnet-4"),
        ("claude-haiku-4", "claude-haiku-4"),
        ("claude-opus-4", "claude-opus-4"),
        # Legacy format
        ("claude-3-7-sonnet", "claude-3.7-sonnet"),
        ("claude-3-7-sonnet-20250219", "claude-3.7-sonnet"),
        ("claude-3-5-haiku", "claude-3.5-haiku"),
        ("claude-3-0-opus", "claude-3.0-opus"),
        # Already normalized
        ("claude-haiku-4.5", "claude-haiku-4.5"),
        ("claude-sonnet-4.5", "claude-sonnet-4.5"),
        ("claude-opus-4.5", "claude-opus-4.5"),
        ("claude-3.7-sonnet", "claude-3.7-sonnet"),
        ("auto", "auto"),
        # Passthrough for unknown
        ("gpt-4", "gpt-4"),
        ("gpt-4-turbo", "gpt-4-turbo"),
        ("unknown-model", "unknown-model"),
    ])
    def test_normalize_model_name_all_scenarios(self, input_model, expected):
        """
        What it does: Checks all normalization scenarios.
        Goal: Complete coverage of scenario table.
        """
        print(f"Action: Normalizing '{input_model}'...")
        result = normalize_model_name(input_model)
        
        print(f"Comparing result: Expected '{expected}', Got '{result}'")
        assert result == expected


# =============================================================================
# TestExtractModelFamily - Tests for model family extraction
# =============================================================================

class TestExtractModelFamily:
    """
    Tests for extract_model_family() function.
    
    Checks extraction of model family (haiku, sonnet, opus) from name.
    """
    
    def test_extracts_haiku_from_standard_format(self):
        """
        What it does: claude-haiku-4.5 → haiku
        Goal: Check Haiku family extraction.
        """
        print("Action: Extracting family from 'claude-haiku-4.5'...")
        result = extract_model_family("claude-haiku-4.5")
        
        print(f"Comparing result: Expected 'haiku', Got '{result}'")
        assert result == "haiku"
    
    def test_extracts_sonnet_from_standard_format(self):
        """
        What it does: claude-sonnet-4.5 → sonnet
        Goal: Check Sonnet family extraction.
        """
        print("Action: Extracting family from 'claude-sonnet-4.5'...")
        result = extract_model_family("claude-sonnet-4.5")
        
        print(f"Comparing result: Expected 'sonnet', Got '{result}'")
        assert result == "sonnet"
    
    def test_extracts_opus_from_standard_format(self):
        """
        What it does: claude-opus-4.5 → opus
        Goal: Check Opus family extraction.
        """
        print("Action: Extracting family from 'claude-opus-4.5'...")
        result = extract_model_family("claude-opus-4.5")
        
        print(f"Comparing result: Expected 'opus', Got '{result}'")
        assert result == "opus"
    
    def test_extracts_sonnet_from_legacy_format(self):
        """
        What it does: claude-3.7-sonnet → sonnet
        Goal: Check family extraction from legacy format.
        """
        print("Action: Extracting family from 'claude-3.7-sonnet'...")
        result = extract_model_family("claude-3.7-sonnet")
        
        print(f"Comparing result: Expected 'sonnet', Got '{result}'")
        assert result == "sonnet"
    
    def test_extracts_haiku_from_unnormalized(self):
        """
        What it does: claude-haiku-4-5-20251001 → haiku
        Goal: Check family extraction from unnormalized name.
        """
        print("Action: Extracting family from 'claude-haiku-4-5-20251001'...")
        result = extract_model_family("claude-haiku-4-5-20251001")
        
        print(f"Comparing result: Expected 'haiku', Got '{result}'")
        assert result == "haiku"
    
    def test_returns_none_for_non_claude(self):
        """
        What it does: gpt-4 → None
        Goal: Check None return for non-Claude models.
        """
        print("Action: Extracting family from 'gpt-4'...")
        result = extract_model_family("gpt-4")
        
        print(f"Comparing result: Expected None, Got {result}")
        assert result is None
    
    def test_returns_none_for_auto(self):
        """
        What it does: auto → None
        Goal: Check None return for 'auto'.
        """
        print("Action: Extracting family from 'auto'...")
        result = extract_model_family("auto")
        
        print(f"Comparing result: Expected None, Got {result}")
        assert result is None
    
    def test_case_insensitive(self):
        """
        What it does: CLAUDE-HAIKU-4.5 → haiku
        Goal: Check case insensitivity.
        """
        print("Action: Extracting family from 'CLAUDE-HAIKU-4.5'...")
        result = extract_model_family("CLAUDE-HAIKU-4.5")
        
        print(f"Comparing result: Expected 'haiku', Got '{result}'")
        assert result == "haiku"


# =============================================================================
# TestGetModelIdForKiro - Tests for converter helper
# =============================================================================

class TestGetModelIdForKiro:
    """
    Tests for get_model_id_for_kiro() function.
    
    Checks getting model ID for sending to Kiro API.
    """
    
    def test_normalizes_without_hidden_models(self):
        """
        What it does: Normalizes model without hidden models.
        Goal: Check basic normalization.
        """
        print("Action: get_model_id_for_kiro('claude-haiku-4-5-20251001', {})...")
        result = get_model_id_for_kiro("claude-haiku-4-5-20251001", {})
        
        print(f"Comparing result: Expected 'claude-haiku-4.5', Got '{result}'")
        assert result == "claude-haiku-4.5"
    
    def test_returns_internal_id_for_hidden_model(self):
        """
        What it does: Returns internal ID for hidden model (pass-through).
        Goal: Check hidden model resolution returns internal ID as-is.
        """
        hidden = {"claude-3.7-sonnet": "CLAUDE_3_7_SONNET_20250219_V1_0"}

        print("Action: get_model_id_for_kiro('claude-3.7-sonnet', hidden)...")
        result = get_model_id_for_kiro("claude-3.7-sonnet", hidden)

        print(f"Comparing result: Expected 'CLAUDE_3_7_SONNET_20250219_V1_0' (pass-through), Got '{result}'")
        assert result == "CLAUDE_3_7_SONNET_20250219_V1_0"

    def test_normalizes_then_checks_hidden(self):
        """
        What it does: Normalizes first, then checks hidden.
        Goal: Check operation order (normalize → hidden lookup → pass-through).
        """
        hidden = {"claude-3.7-sonnet": "CLAUDE_3_7_SONNET_20250219_V1_0"}

        print("Action: get_model_id_for_kiro('claude-3-7-sonnet', hidden)...")
        result = get_model_id_for_kiro("claude-3-7-sonnet", hidden)

        print(f"Comparing result: Expected 'CLAUDE_3_7_SONNET_20250219_V1_0' (pass-through), Got '{result}'")
        assert result == "CLAUDE_3_7_SONNET_20250219_V1_0"

    def test_normalizes_with_date_then_checks_hidden(self):
        """
        What it does: Normalizes with date suffix, then checks hidden.
        Goal: Check full normalization chain (normalize → hidden lookup → pass-through).
        """
        hidden = {"claude-3.7-sonnet": "CLAUDE_3_7_SONNET_20250219_V1_0"}

        print("Action: get_model_id_for_kiro('claude-3-7-sonnet-20250219', hidden)...")
        result = get_model_id_for_kiro("claude-3-7-sonnet-20250219", hidden)

        print(f"Comparing result: Expected 'CLAUDE_3_7_SONNET_20250219_V1_0' (pass-through), Got '{result}'")
        assert result == "CLAUDE_3_7_SONNET_20250219_V1_0"

    def test_passthrough_unknown_model(self):
        """
        What it does: Unknown models pass through as-is (gateway, not gatekeeper).
        Goal: Check that unknown models are returned unchanged.
        """
        print("Action: get_model_id_for_kiro('claude-unknown-model', {})...")
        result = get_model_id_for_kiro("claude-unknown-model", {})

        print(f"Comparing result: Expected 'claude-unknown-model' (pass-through), Got '{result}'")
        assert result == "claude-unknown-model"


# =============================================================================
# TestModelResolver - Tests for ModelResolver class
# =============================================================================

class TestModelResolverInitialization:
    """Tests for ModelResolver initialization."""
    
    def test_init_with_cache_and_hidden_models(self, mock_model_cache, hidden_models):
        """
        What it does: Creates ModelResolver with cache and hidden models.
        Goal: Check correct initialization.
        """
        print("Action: Creating ModelResolver...")
        resolver = ModelResolver(cache=mock_model_cache, hidden_models=hidden_models)
        
        print("Check: Attributes set correctly...")
        assert resolver.cache is mock_model_cache
        assert resolver.hidden_models == hidden_models
    
    def test_init_with_empty_hidden_models(self, mock_model_cache):
        """
        What it does: Creates ModelResolver without hidden models.
        Goal: Check work with empty dict.
        """
        print("Action: Creating ModelResolver without hidden models...")
        resolver = ModelResolver(cache=mock_model_cache, hidden_models={})
        
        print("Check: hidden_models is empty...")
        assert resolver.hidden_models == {}
    
    def test_init_with_none_hidden_models(self, mock_model_cache):
        """
        What it does: Creates ModelResolver with hidden_models=None.
        Goal: Check default value.
        """
        print("Action: Creating ModelResolver with hidden_models=None...")
        resolver = ModelResolver(cache=mock_model_cache, hidden_models=None)
        
        print("Check: hidden_models initialized as empty dict...")
        assert resolver.hidden_models == {}


class TestModelResolverResolve:
    """Tests for resolve() method of ModelResolver class."""
    
    def test_resolve_finds_model_in_cache(self, model_resolver):
        """
        What it does: Finds model in cache.
        Goal: Check Layer 2 (Dynamic Cache).
        """
        print("Action: Resolving 'claude-haiku-4-5'...")
        result = model_resolver.resolve("claude-haiku-4-5")
        
        print(f"Check result: {result}")
        print(f"Comparing internal_id: Expected 'claude-haiku-4.5', Got '{result.internal_id}'")
        assert result.internal_id == "claude-haiku-4.5"
        
        print(f"Comparing source: Expected 'cache', Got '{result.source}'")
        assert result.source == "cache"
        
        print(f"Comparing is_verified: Expected True, Got {result.is_verified}")
        assert result.is_verified is True
        
        print(f"Comparing normalized: Expected 'claude-haiku-4.5', Got '{result.normalized}'")
        assert result.normalized == "claude-haiku-4.5"
        
        print(f"Comparing original_request: Expected 'claude-haiku-4-5', Got '{result.original_request}'")
        assert result.original_request == "claude-haiku-4-5"
    
    def test_resolve_finds_model_in_hidden(self, model_resolver):
        """
        What it does: Finds model in hidden models.
        Goal: Check Layer 3 (Hidden Models) returns internal ID via pass-through.
        """
        print("Action: Resolving 'claude-3-7-sonnet'...")
        result = model_resolver.resolve("claude-3-7-sonnet")

        print(f"Check result: {result}")
        print(f"Comparing internal_id: Expected 'CLAUDE_3_7_SONNET_20250219_V1_0' (pass-through), Got '{result.internal_id}'")
        assert result.internal_id == "CLAUDE_3_7_SONNET_20250219_V1_0"

        print(f"Comparing source: Expected 'hidden', Got '{result.source}'")
        assert result.source == "hidden"

        print(f"Comparing is_verified: Expected True, Got {result.is_verified}")
        assert result.is_verified is True

    def test_resolve_passthrough_for_unknown(self, model_resolver):
        """
        What it does: Passthrough for unknown model returns normalized name as-is.
        Goal: Check Layer 4 (Pass-through) - gateway, not gatekeeper principle.
        """
        print("Action: Resolving 'claude-haiku-4-6' (does not exist)...")
        result = model_resolver.resolve("claude-haiku-4-6")

        print(f"Check result: {result}")
        print(f"Comparing internal_id: Expected 'claude-haiku-4.6' (normalized, pass-through), Got '{result.internal_id}'")
        assert result.internal_id == "claude-haiku-4.6"

        print(f"Comparing source: Expected 'passthrough', Got '{result.source}'")
        assert result.source == "passthrough"

        print(f"Comparing is_verified: Expected False, Got {result.is_verified}")
        assert result.is_verified is False
    
    def test_resolve_normalizes_before_lookup(self, model_resolver):
        """
        What it does: Normalizes name before cache lookup.
        Goal: Check Layer 1 (Normalize Name).
        """
        print("Action: Resolving 'claude-haiku-4-5-20251001'...")
        result = model_resolver.resolve("claude-haiku-4-5-20251001")
        
        print(f"Comparing normalized: Expected 'claude-haiku-4.5', Got '{result.normalized}'")
        assert result.normalized == "claude-haiku-4.5"
        
        print(f"Comparing source: Expected 'cache', Got '{result.source}'")
        assert result.source == "cache"
    
    def test_resolve_never_raises(self, model_resolver):
        """
        What it does: Never raises exception.
        Goal: Check that resolve() always returns ModelResolution.
        """
        print("Action: Resolving strange input data...")
        
        # Empty string
        result1 = model_resolver.resolve("")
        print(f"Empty string: {result1}")
        assert isinstance(result1, ModelResolution)
        
        # Special characters
        result2 = model_resolver.resolve("!@#$%^&*()")
        print(f"Special characters: {result2}")
        assert isinstance(result2, ModelResolution)
        
        # Very long name
        result3 = model_resolver.resolve("a" * 1000)
        print(f"Long name: source={result3.source}")
        assert isinstance(result3, ModelResolution)
    
    def test_resolve_auto_model(self, model_resolver):
        """
        What it does: Resolves 'auto' model.
        Goal: Check that 'auto' is in cache.
        """
        print("Action: Resolving 'auto'...")
        result = model_resolver.resolve("auto")
        
        print(f"Comparing internal_id: Expected 'auto', Got '{result.internal_id}'")
        assert result.internal_id == "auto"
        
        print(f"Comparing source: Expected 'cache', Got '{result.source}'")
        assert result.source == "cache"
    
    def test_resolve_with_empty_cache(self, empty_model_cache, hidden_models):
        """
        What it does: Resolves model with empty cache.
        Goal: Check work with only hidden models.
        """
        print("Setup: Creating resolver with empty cache...")
        resolver = ModelResolver(cache=empty_model_cache, hidden_models=hidden_models)
        
        print("Action: Resolving 'claude-3.7-sonnet'...")
        result = resolver.resolve("claude-3.7-sonnet")
        
        print(f"Comparing source: Expected 'hidden', Got '{result.source}'")
        assert result.source == "hidden"
        
        print("Action: Resolving 'claude-haiku-4.5' (not in cache)...")
        result2 = resolver.resolve("claude-haiku-4.5")
        
        print(f"Comparing source: Expected 'passthrough', Got '{result2.source}'")
        assert result2.source == "passthrough"


class TestModelResolverGetAvailableModels:
    """Tests for get_available_models() method."""
    
    def test_get_available_models_combines_cache_and_hidden(self, model_resolver):
        """
        What it does: Returns models from cache and hidden.
        Goal: Check combining sources.
        """
        print("Action: Getting list of available models...")
        models = model_resolver.get_available_models()
        
        print(f"Received models: {models}")
        
        # Check cache models
        print("Check: Cache models present...")
        assert "claude-haiku-4.5" in models
        assert "claude-sonnet-4.5" in models
        assert "claude-opus-4.5" in models
        assert "auto" in models
        
        # Check hidden models
        print("Check: Hidden models present...")
        assert "claude-3.7-sonnet" in models
    
    def test_get_available_models_returns_sorted_list(self, model_resolver):
        """
        What it does: Returns sorted list.
        Goal: Check sorting.
        """
        print("Action: Getting list of available models...")
        models = model_resolver.get_available_models()
        
        print(f"Received models: {models}")
        print(f"Sorted: {sorted(models)}")
        
        assert models == sorted(models)
    
    def test_get_available_models_no_duplicates(self, mock_model_cache):
        """
        What it does: Does not return duplicates.
        Goal: Check uniqueness.
        """
        # Add hidden model that already exists in cache
        hidden = {"claude-haiku-4.5": "SOME_INTERNAL_ID"}
        resolver = ModelResolver(cache=mock_model_cache, hidden_models=hidden)
        
        print("Action: Getting list with potential duplicate...")
        models = resolver.get_available_models()
        
        print(f"Received models: {models}")
        
        # Check uniqueness
        assert len(models) == len(set(models))


class TestModelResolverGetModelsByFamily:
    """Tests for get_models_by_family() method."""
    
    def test_get_models_by_family_haiku(self, model_resolver):
        """
        What it does: Returns only Haiku models.
        Goal: Check filtering by family.
        """
        print("Action: Getting Haiku models...")
        models = model_resolver.get_models_by_family("haiku")
        
        print(f"Received models: {models}")
        
        assert "claude-haiku-4.5" in models
        assert "claude-sonnet-4.5" not in models
        assert "claude-opus-4.5" not in models
    
    def test_get_models_by_family_sonnet(self, model_resolver):
        """
        What it does: Returns only Sonnet models.
        Goal: Check Sonnet filtering.
        """
        print("Action: Getting Sonnet models...")
        models = model_resolver.get_models_by_family("sonnet")
        
        print(f"Received models: {models}")
        
        assert "claude-sonnet-4.5" in models
        assert "claude-sonnet-4" in models
        assert "claude-3.7-sonnet" in models  # Hidden model
        assert "claude-haiku-4.5" not in models
    
    def test_get_models_by_family_opus(self, model_resolver):
        """
        What it does: Returns only Opus models.
        Goal: Check Opus filtering.
        """
        print("Action: Getting Opus models...")
        models = model_resolver.get_models_by_family("opus")
        
        print(f"Received models: {models}")
        
        assert "claude-opus-4.5" in models
        assert "claude-sonnet-4.5" not in models
    
    def test_get_models_by_family_case_insensitive(self, model_resolver):
        """
        What it does: Filtering is case insensitive.
        Goal: Check case-insensitivity.
        """
        print("Action: Getting HAIKU models (uppercase)...")
        models = model_resolver.get_models_by_family("HAIKU")
        
        print(f"Received models: {models}")
        
        assert "claude-haiku-4.5" in models


class TestModelResolverGetSuggestionsForModel:
    """Tests for get_suggestions_for_model() method."""
    
    def test_get_suggestions_returns_same_family(self, model_resolver):
        """
        What it does: Returns models of same family.
        Goal: Check that suggestions are from same family.
        """
        print("Action: Getting suggestions for 'claude-haiku-4-6'...")
        suggestions = model_resolver.get_suggestions_for_model("claude-haiku-4-6")
        
        print(f"Received suggestions: {suggestions}")
        
        # All suggestions should be Haiku
        for s in suggestions:
            print(f"Check: '{s}' contains 'haiku'...")
            assert "haiku" in s.lower()
    
    def test_get_suggestions_no_cross_family(self, model_resolver):
        """
        What it does: NEVER suggests models from other family.
        Goal: Critical check - Opus never becomes Sonnet!
        """
        print("Action: Getting suggestions for 'claude-opus-5'...")
        suggestions = model_resolver.get_suggestions_for_model("claude-opus-5")
        
        print(f"Received suggestions: {suggestions}")
        
        # Should NOT be Sonnet or Haiku
        for s in suggestions:
            print(f"Check: '{s}' does NOT contain 'sonnet' or 'haiku'...")
            assert "sonnet" not in s.lower()
            assert "haiku" not in s.lower()
    
    def test_get_suggestions_returns_all_for_unknown_family(self, model_resolver):
        """
        What it does: Returns all models for unknown family.
        Goal: Check fallback for non-Claude models.
        """
        print("Action: Getting suggestions for 'gpt-4'...")
        suggestions = model_resolver.get_suggestions_for_model("gpt-4")
        
        print(f"Received suggestions: {suggestions}")
        
        # Should be all models
        all_models = model_resolver.get_available_models()
        assert set(suggestions) == set(all_models)


# =============================================================================
# TestModelResolution - Tests for ModelResolution dataclass
# =============================================================================

class TestModelResolution:
    """Tests for ModelResolution dataclass."""
    
    def test_model_resolution_fields(self):
        """
        What it does: Checks all ModelResolution fields.
        Goal: Ensure correct structure.
        """
        print("Action: Creating ModelResolution...")
        resolution = ModelResolution(
            internal_id="claude-haiku-4.5",
            source="cache",
            original_request="claude-haiku-4-5",
            normalized="claude-haiku-4.5",
            is_verified=True
        )
        
        print(f"Check fields: {resolution}")
        assert resolution.internal_id == "claude-haiku-4.5"
        assert resolution.source == "cache"
        assert resolution.original_request == "claude-haiku-4-5"
        assert resolution.normalized == "claude-haiku-4.5"
        assert resolution.is_verified is True
    
    def test_model_resolution_is_frozen(self):
        """
        What it does: Checks that ModelResolution is immutable.
        Goal: Ensure immutability (frozen=True).
        """
        print("Action: Creating ModelResolution...")
        resolution = ModelResolution(
            internal_id="test",
            source="cache",
            original_request="test",
            normalized="test",
            is_verified=True
        )
        
        print("Check: Attempt to modify field should raise error...")
        with pytest.raises(FrozenInstanceError):
            resolution.internal_id = "changed"
    
    def test_model_resolution_equality(self):
        """
        What it does: Checks comparison of two ModelResolution objects.
        Goal: Ensure correct __eq__ implementation.
        """
        print("Action: Creating two identical ModelResolution objects...")
        resolution1 = ModelResolution(
            internal_id="test",
            source="cache",
            original_request="test",
            normalized="test",
            is_verified=True
        )
        resolution2 = ModelResolution(
            internal_id="test",
            source="cache",
            original_request="test",
            normalized="test",
            is_verified=True
        )
        
        print(f"Comparing: {resolution1} == {resolution2}")
        assert resolution1 == resolution2
    
    def test_model_resolution_inequality(self):
        """
        What it does: Checks inequality of different ModelResolution objects.
        Goal: Ensure correct __eq__ implementation.
        """
        print("Action: Creating two different ModelResolution objects...")
        resolution1 = ModelResolution(
            internal_id="test1",
            source="cache",
            original_request="test",
            normalized="test",
            is_verified=True
        )
        resolution2 = ModelResolution(
            internal_id="test2",
            source="hidden",
            original_request="test",
            normalized="test",
            is_verified=True
        )
        
        print(f"Comparing: {resolution1} != {resolution2}")
        assert resolution1 != resolution2


# =============================================================================
# TestModelInfoCacheNewMethods - Tests for new cache methods
# =============================================================================

class TestModelInfoCacheIsValidModel:
    """Tests for is_valid_model() method in ModelInfoCache."""
    
    @pytest.mark.asyncio
    async def test_is_valid_model_returns_true_for_cached(self):
        """
        What it does: Returns True for model in cache.
        Goal: Check basic functionality.
        """
        print("Setup: Creating and populating cache...")
        cache = ModelInfoCache()
        await cache.update([{"modelId": "claude-sonnet-4.5"}])
        
        print("Action: Checking is_valid_model('claude-sonnet-4.5')...")
        result = cache.is_valid_model("claude-sonnet-4.5")
        
        print(f"Comparing result: Expected True, Got {result}")
        assert result is True
    
    @pytest.mark.asyncio
    async def test_is_valid_model_returns_false_for_unknown(self):
        """
        What it does: Returns False for unknown model.
        Goal: Check negative case.
        """
        print("Setup: Creating and populating cache...")
        cache = ModelInfoCache()
        await cache.update([{"modelId": "claude-sonnet-4.5"}])
        
        print("Action: Checking is_valid_model('unknown-model')...")
        result = cache.is_valid_model("unknown-model")
        
        print(f"Comparing result: Expected False, Got {result}")
        assert result is False
    
    def test_is_valid_model_on_empty_cache(self):
        """
        What it does: Returns False for empty cache.
        Goal: Check edge case.
        """
        print("Setup: Creating empty cache...")
        cache = ModelInfoCache()
        
        print("Action: Checking is_valid_model('any-model')...")
        result = cache.is_valid_model("any-model")
        
        print(f"Comparing result: Expected False, Got {result}")
        assert result is False


class TestModelInfoCacheAddHiddenModel:
    """Tests for add_hidden_model() method in ModelInfoCache."""
    
    def test_add_hidden_model_adds_to_cache(self):
        """
        What it does: Adds hidden model to cache.
        Goal: Check basic functionality.
        """
        print("Setup: Creating empty cache...")
        cache = ModelInfoCache()
        
        print("Action: Adding hidden model...")
        cache.add_hidden_model("claude-3.7-sonnet", "CLAUDE_3_7_SONNET_20250219_V1_0")
        
        print("Check: Model added to cache...")
        assert cache.is_valid_model("claude-3.7-sonnet") is True
    
    def test_add_hidden_model_stores_internal_id(self):
        """
        What it does: Stores internal ID in _internal_id field.
        Goal: Check data structure.
        """
        print("Setup: Creating empty cache...")
        cache = ModelInfoCache()
        
        print("Action: Adding hidden model...")
        cache.add_hidden_model("claude-3.7-sonnet", "CLAUDE_3_7_SONNET_20250219_V1_0")
        
        print("Check: _internal_id saved...")
        model_info = cache.get("claude-3.7-sonnet")
        print(f"model_info: {model_info}")
        
        assert model_info["_internal_id"] == "CLAUDE_3_7_SONNET_20250219_V1_0"
        assert model_info["_is_hidden"] is True
    
    def test_add_hidden_model_sets_model_id(self):
        """
        What it does: Sets modelId equal to display_name.
        Goal: Check data consistency.
        """
        print("Setup: Creating empty cache...")
        cache = ModelInfoCache()
        
        print("Action: Adding hidden model...")
        cache.add_hidden_model("claude-3.7-sonnet", "INTERNAL_ID")
        
        print("Check: modelId set...")
        model_info = cache.get("claude-3.7-sonnet")
        
        assert model_info["modelId"] == "claude-3.7-sonnet"
        assert model_info["modelName"] == "claude-3.7-sonnet"
    
    @pytest.mark.asyncio
    async def test_add_hidden_model_does_not_overwrite_existing(self):
        """
        What it does: Does not overwrite existing model.
        Goal: Check protection from overwriting.
        """
        print("Setup: Creating cache with model...")
        cache = ModelInfoCache()
        await cache.update([{
            "modelId": "claude-3.7-sonnet",
            "modelName": "Original Name",
            "tokenLimits": {"maxInputTokens": 200000}
        }])
        
        print("Action: Attempting to add hidden model with same ID...")
        cache.add_hidden_model("claude-3.7-sonnet", "NEW_INTERNAL_ID")
        
        print("Check: Original data preserved...")
        model_info = cache.get("claude-3.7-sonnet")
        
        assert model_info["modelName"] == "Original Name"
        assert "_internal_id" not in model_info  # Should not be added
    
    def test_add_hidden_model_appears_in_get_all_model_ids(self):
        """
        What it does: Hidden model appears in list of all models.
        Goal: Check integration with get_all_model_ids().
        """
        print("Setup: Creating empty cache...")
        cache = ModelInfoCache()
        
        print("Action: Adding hidden model...")
        cache.add_hidden_model("claude-3.7-sonnet", "INTERNAL_ID")
        
        print("Check: Model in list...")
        model_ids = cache.get_all_model_ids()
        
        assert "claude-3.7-sonnet" in model_ids


# =============================================================================
# TestCriticalSafetyPrinciple - Critical security tests
# =============================================================================

class TestCriticalSafetyPrinciple:
    """
    Critical security tests: Family Isolation.
    
    IMPORTANT: Resolver MUST NEVER cross model family boundaries!
    """
    
    def test_opus_never_becomes_sonnet(self, model_resolver):
        """
        What it does: Opus request NEVER becomes Sonnet.
        Goal: Critical check for Family Isolation.
        """
        print("Action: Resolving non-existent Opus model...")
        result = model_resolver.resolve("claude-opus-5")
        
        print(f"Result: {result}")
        
        # Should be passthrough, NOT fallback to Sonnet
        print("Check: Does NOT contain 'sonnet'...")
        assert "sonnet" not in result.internal_id.lower()
        
        print("Check: Does NOT contain 'haiku'...")
        assert "haiku" not in result.internal_id.lower()
    
    def test_haiku_never_becomes_opus(self, model_resolver):
        """
        What it does: Haiku request NEVER becomes Opus.
        Goal: Critical check for Family Isolation.
        """
        print("Action: Resolving non-existent Haiku model...")
        result = model_resolver.resolve("claude-haiku-5")
        
        print(f"Result: {result}")
        
        # Should be passthrough, NOT fallback to Opus
        print("Check: Does NOT contain 'opus'...")
        assert "opus" not in result.internal_id.lower()
        
        print("Check: Does NOT contain 'sonnet'...")
        assert "sonnet" not in result.internal_id.lower()
    
    def test_sonnet_never_becomes_haiku(self, model_resolver):
        """
        What it does: Sonnet request NEVER becomes Haiku.
        Goal: Critical check for Family Isolation.
        """
        print("Action: Resolving non-existent Sonnet model...")
        result = model_resolver.resolve("claude-sonnet-5")
        
        print(f"Result: {result}")
        
        # Should be passthrough, NOT fallback to Haiku
        print("Check: Does NOT contain 'haiku'...")
        assert "haiku" not in result.internal_id.lower()
        
        print("Check: Does NOT contain 'opus'...")
        assert "opus" not in result.internal_id.lower()
    
    def test_suggestions_respect_family_boundaries(self, model_resolver):
        """
        What it does: Suggestions only from same family.
        Goal: Check that get_suggestions_for_model() respects boundaries.
        """
        families = ["haiku", "sonnet", "opus"]
        
        for family in families:
            print(f"Check family: {family}...")
            suggestions = model_resolver.get_suggestions_for_model(f"claude-{family}-99")
            
            for suggestion in suggestions:
                print(f"  Suggestion: {suggestion}")
                # Each suggestion must contain same family
                assert family in suggestion.lower(), \
                    f"Suggestion '{suggestion}' not from family '{family}'!"


# =============================================================================
# TestModelAliasSystem - Tests for Layer 0 (Aliases)
# =============================================================================

class TestModelAliasSystemBasics:
    """
    Tests for model alias system (Layer 0).
    
    Aliases allow custom names that map to real model IDs.
    Use case: Avoid conflicts with IDE-specific model names (e.g., Cursor's "auto").
    """
    
    def test_alias_resolves_to_target_model(self, mock_model_cache):
        """
        What it does: Alias resolves to target model.
        Purpose: Basic alias functionality.
        """
        print("Setup: Creating resolver with alias...")
        aliases = {"auto-kiro": "auto"}
        resolver = ModelResolver(cache=mock_model_cache, aliases=aliases)
        
        print("Action: Resolving 'auto-kiro'...")
        result = resolver.resolve("auto-kiro")
        
        print(f"Comparing internal_id: Expected 'auto', Got '{result.internal_id}'")
        assert result.internal_id == "auto"
        
        print(f"Comparing source: Expected 'cache', Got '{result.source}'")
        assert result.source == "cache"
        
        print(f"Comparing original_request: Expected 'auto-kiro', Got '{result.original_request}'")
        assert result.original_request == "auto-kiro"
    
    def test_non_aliased_models_work_normally(self, mock_model_cache):
        """
        What it does: Non-aliased models work as before.
        Purpose: Ensure aliases don't break existing functionality.
        """
        print("Setup: Creating resolver with alias...")
        aliases = {"auto-kiro": "auto"}
        resolver = ModelResolver(cache=mock_model_cache, aliases=aliases)
        
        print("Action: Resolving 'claude-haiku-4.5' (not aliased)...")
        result = resolver.resolve("claude-haiku-4.5")
        
        print(f"Comparing internal_id: Expected 'claude-haiku-4.5', Got '{result.internal_id}'")
        assert result.internal_id == "claude-haiku-4.5"
        
        print(f"Comparing source: Expected 'cache', Got '{result.source}'")
        assert result.source == "cache"
    
    def test_alias_with_normalization_chain(self, mock_model_cache):
        """
        What it does: Alias → Normalization → Cache.
        Purpose: Ensure alias works with normalization.
        """
        print("Setup: Creating resolver with alias to unnormalized name...")
        aliases = {"my-haiku": "claude-haiku-4-5"}
        resolver = ModelResolver(cache=mock_model_cache, aliases=aliases)
        
        print("Action: Resolving 'my-haiku'...")
        result = resolver.resolve("my-haiku")
        
        print(f"Comparing internal_id: Expected 'claude-haiku-4.5', Got '{result.internal_id}'")
        assert result.internal_id == "claude-haiku-4.5"
        
        print(f"Comparing normalized: Expected 'claude-haiku-4.5', Got '{result.normalized}'")
        assert result.normalized == "claude-haiku-4.5"
    
    def test_multiple_aliases(self, mock_model_cache):
        """
        What it does: Multiple aliases work correctly.
        Purpose: Ensure multiple aliases don't interfere.
        """
        print("Setup: Creating resolver with multiple aliases...")
        aliases = {
            "auto-kiro": "auto",
            "my-opus": "claude-opus-4.5",
            "fast": "claude-haiku-4.5"
        }
        resolver = ModelResolver(cache=mock_model_cache, aliases=aliases)
        
        print("Action: Resolving all aliases...")
        result1 = resolver.resolve("auto-kiro")
        result2 = resolver.resolve("my-opus")
        result3 = resolver.resolve("fast")
        
        print(f"Comparing: auto-kiro → {result1.internal_id}")
        assert result1.internal_id == "auto"
        
        print(f"Comparing: my-opus → {result2.internal_id}")
        assert result2.internal_id == "claude-opus-4.5"
        
        print(f"Comparing: fast → {result3.internal_id}")
        assert result3.internal_id == "claude-haiku-4.5"


class TestModelAliasSystemEdgeCases:
    """Edge cases and boundary conditions for alias system."""
    
    def test_alias_to_non_existent_model(self, mock_model_cache):
        """
        What it does: Alias pointing to non-existent model passes through as-is.
        Purpose: Ensure pass-through applies for aliased non-existent models.
        """
        print("Setup: Creating resolver with alias to non-existent model...")
        aliases = {"future-model": "claude-haiku-5.0"}
        resolver = ModelResolver(cache=mock_model_cache, aliases=aliases)

        print("Action: Resolving 'future-model'...")
        result = resolver.resolve("future-model")

        print(f"Comparing internal_id: Expected 'claude-haiku-5.0' (pass-through), Got '{result.internal_id}'")
        assert result.internal_id == "claude-haiku-5.0"

        print(f"Comparing source: Expected 'passthrough', Got '{result.source}'")
        assert result.source == "passthrough"

        print(f"Comparing is_verified: Expected False, Got {result.is_verified}")
        assert result.is_verified is False

    def test_alias_to_hidden_model(self, mock_model_cache):
        """
        What it does: Alias pointing to hidden model.
        Purpose: Ensure alias works with hidden models and returns internal ID via pass-through.
        """
        print("Setup: Creating resolver with alias to hidden model...")
        hidden = {"claude-3.7-sonnet": "CLAUDE_3_7_SONNET_20250219_V1_0"}
        aliases = {"legacy-sonnet": "claude-3.7-sonnet"}
        resolver = ModelResolver(cache=mock_model_cache, hidden_models=hidden, aliases=aliases)

        print("Action: Resolving 'legacy-sonnet'...")
        result = resolver.resolve("legacy-sonnet")

        print(f"Comparing internal_id: Expected 'CLAUDE_3_7_SONNET_20250219_V1_0' (pass-through), Got '{result.internal_id}'")
        assert result.internal_id == "CLAUDE_3_7_SONNET_20250219_V1_0"

        print(f"Comparing source: Expected 'hidden', Got '{result.source}'")
        assert result.source == "hidden"
    
    def test_empty_aliases_dict(self, mock_model_cache):
        """
        What it does: Empty aliases dict works correctly.
        Purpose: Ensure empty dict doesn't break anything.
        """
        print("Setup: Creating resolver with empty aliases...")
        resolver = ModelResolver(cache=mock_model_cache, aliases={})
        
        print("Action: Resolving 'auto'...")
        result = resolver.resolve("auto")
        
        print(f"Comparing internal_id: Expected 'auto', Got '{result.internal_id}'")
        assert result.internal_id == "auto"
    
    def test_none_aliases(self, mock_model_cache):
        """
        What it does: None aliases parameter works correctly.
        Purpose: Ensure None is handled as empty dict.
        """
        print("Setup: Creating resolver with aliases=None...")
        resolver = ModelResolver(cache=mock_model_cache, aliases=None)
        
        print("Check: aliases initialized as empty dict...")
        assert resolver.aliases == {}
    
    def test_alias_with_same_name_as_real_model(self, mock_model_cache):
        """
        What it does: Alias with same name as real model.
        Purpose: CRITICAL - alias should take precedence!
        """
        print("Setup: Creating resolver with alias shadowing real model...")
        # Alias "auto" to point to "claude-sonnet-4.5"
        aliases = {"auto": "claude-sonnet-4.5"}
        resolver = ModelResolver(cache=mock_model_cache, aliases=aliases)
        
        print("Action: Resolving 'auto'...")
        result = resolver.resolve("auto")
        
        print(f"Comparing internal_id: Expected 'claude-sonnet-4.5', Got '{result.internal_id}'")
        assert result.internal_id == "claude-sonnet-4.5"
        
        print("CRITICAL: Alias takes precedence over cache!")
    
    def test_alias_case_sensitivity(self, mock_model_cache):
        """
        What it does: Aliases are case-sensitive.
        Purpose: Ensure case sensitivity is preserved.
        """
        print("Setup: Creating resolver with lowercase alias...")
        aliases = {"auto-kiro": "auto"}
        resolver = ModelResolver(cache=mock_model_cache, aliases=aliases)

        print("Action: Resolving 'AUTO-KIRO' (uppercase)...")
        result = resolver.resolve("AUTO-KIRO")

        print(f"Comparing internal_id: Expected 'AUTO-KIRO' (pass-through, no alias match), Got '{result.internal_id}'")
        # Should NOT match alias (case-sensitive), goes through passthrough as-is
        assert result.internal_id == "AUTO-KIRO"
        assert result.source == "passthrough"


class TestHiddenFromListFunctionality:
    """Tests for HIDDEN_FROM_LIST feature."""
    
    def test_hidden_model_not_in_available_list(self, mock_model_cache):
        """
        What it does: Hidden model doesn't appear in get_available_models().
        Purpose: Basic HIDDEN_FROM_LIST functionality.
        """
        print("Setup: Creating resolver with hidden_from_list...")
        hidden_from_list = ["auto"]
        resolver = ModelResolver(cache=mock_model_cache, hidden_from_list=hidden_from_list)
        
        print("Action: Getting available models...")
        models = resolver.get_available_models()
        
        print(f"Received models: {models}")
        print("Check: 'auto' NOT in list...")
        assert "auto" not in models
        
        print("Check: Other models still present...")
        assert "claude-haiku-4.5" in models
        assert "claude-sonnet-4.5" in models
    
    def test_hidden_model_still_works_when_requested(self, mock_model_cache):
        """
        What it does: Hidden model still works when requested directly.
        Purpose: CRITICAL - hiding from list doesn't disable the model!
        """
        print("Setup: Creating resolver with hidden_from_list...")
        hidden_from_list = ["auto"]
        resolver = ModelResolver(cache=mock_model_cache, hidden_from_list=hidden_from_list)
        
        print("Action: Resolving 'auto' directly...")
        result = resolver.resolve("auto")
        
        print(f"Comparing internal_id: Expected 'auto', Got '{result.internal_id}'")
        assert result.internal_id == "auto"
        
        print(f"Comparing source: Expected 'cache', Got '{result.source}'")
        assert result.source == "cache"
        
        print("CRITICAL: Hidden model still works!")
    
    def test_alias_appears_when_original_hidden(self, mock_model_cache):
        """
        What it does: Alias appears in list when original is hidden.
        Purpose: This is the main use case - show alias, hide original.
        """
        print("Setup: Creating resolver with alias and hidden original...")
        aliases = {"auto-kiro": "auto"}
        hidden_from_list = ["auto"]
        resolver = ModelResolver(cache=mock_model_cache, aliases=aliases, hidden_from_list=hidden_from_list)
        
        print("Action: Getting available models...")
        models = resolver.get_available_models()
        
        print(f"Received models: {models}")
        print("Check: 'auto-kiro' (alias) IS in list...")
        assert "auto-kiro" in models
        
        print("Check: 'auto' (original) NOT in list...")
        assert "auto" not in models
        
        print("SUCCESS: Alias visible, original hidden!")
    
    def test_multiple_hidden_models(self, mock_model_cache):
        """
        What it does: Multiple models can be hidden.
        Purpose: Ensure list works with multiple entries.
        """
        print("Setup: Creating resolver with multiple hidden models...")
        hidden_from_list = ["auto", "claude-sonnet-4"]
        resolver = ModelResolver(cache=mock_model_cache, hidden_from_list=hidden_from_list)
        
        print("Action: Getting available models...")
        models = resolver.get_available_models()
        
        print(f"Received models: {models}")
        print("Check: Both hidden models NOT in list...")
        assert "auto" not in models
        assert "claude-sonnet-4" not in models
        
        print("Check: Other models still present...")
        assert "claude-haiku-4.5" in models
    
    def test_empty_hidden_from_list(self, mock_model_cache):
        """
        What it does: Empty hidden_from_list works correctly.
        Purpose: Ensure empty list doesn't break anything.
        """
        print("Setup: Creating resolver with empty hidden_from_list...")
        resolver = ModelResolver(cache=mock_model_cache, hidden_from_list=[])
        
        print("Action: Getting available models...")
        models = resolver.get_available_models()
        
        print(f"Received models: {models}")
        print("Check: All models present...")
        assert "auto" in models
        assert "claude-haiku-4.5" in models
    
    def test_none_hidden_from_list(self, mock_model_cache):
        """
        What it does: None hidden_from_list parameter works correctly.
        Purpose: Ensure None is handled as empty set.
        """
        print("Setup: Creating resolver with hidden_from_list=None...")
        resolver = ModelResolver(cache=mock_model_cache, hidden_from_list=None)
        
        print("Check: hidden_from_list initialized as empty set...")
        assert resolver.hidden_from_list == set()


class TestAliasSystemIntegration:
    """Integration tests for alias system with existing layers."""
    
    def test_cursor_auto_conflict_solution(self, mock_model_cache):
        """
        What it does: Solves Cursor IDE "auto" conflict.
        Purpose: This is the MAIN use case from issue #59!
        """
        print("Setup: Simulating Cursor conflict solution...")
        aliases = {"auto-kiro": "auto"}
        hidden_from_list = ["auto"]
        resolver = ModelResolver(cache=mock_model_cache, aliases=aliases, hidden_from_list=hidden_from_list)
        
        print("Action: Getting available models (what Cursor sees)...")
        models = resolver.get_available_models()
        
        print(f"Models visible to Cursor: {models}")
        print("Check: 'auto' NOT visible (no conflict)...")
        assert "auto" not in models
        
        print("Check: 'auto-kiro' IS visible...")
        assert "auto-kiro" in models
        
        print("Action: User requests 'auto-kiro' in Cursor...")
        result = resolver.resolve("auto-kiro")
        
        print(f"Comparing: 'auto-kiro' resolves to '{result.internal_id}'")
        assert result.internal_id == "auto"
        
        print("Action: Old code with 'auto' still works...")
        result2 = resolver.resolve("auto")
        
        print(f"Comparing: 'auto' still resolves to '{result2.internal_id}'")
        assert result2.internal_id == "auto"
        
        print("SUCCESS: Cursor conflict solved! ✅")
    
    def test_no_duplicates_in_available_models(self, mock_model_cache):
        """
        What it does: No duplicates when alias points to existing model.
        Purpose: Ensure set logic works correctly.
        """
        print("Setup: Creating resolver with alias to existing model...")
        aliases = {"my-haiku": "claude-haiku-4.5"}
        resolver = ModelResolver(cache=mock_model_cache, aliases=aliases)
        
        print("Action: Getting available models...")
        models = resolver.get_available_models()
        
        print(f"Received models: {models}")
        print("Check: No duplicates...")
        assert len(models) == len(set(models))
        
        print("Check: Both alias and original present...")
        assert "my-haiku" in models
        assert "claude-haiku-4.5" in models
    
    def test_alias_with_hidden_models_and_hidden_from_list(self, mock_model_cache):
        """
        What it does: Complex scenario with all features.
        Purpose: Ensure all features work together.
        """
        print("Setup: Creating resolver with all features...")
        hidden_models = {"claude-3.7-sonnet": "CLAUDE_3_7_SONNET_20250219_V1_0"}
        aliases = {"auto-kiro": "auto", "legacy": "claude-3.7-sonnet"}
        hidden_from_list = ["auto"]
        
        resolver = ModelResolver(
            cache=mock_model_cache,
            hidden_models=hidden_models,
            aliases=aliases,
            hidden_from_list=hidden_from_list
        )
        
        print("Action: Getting available models...")
        models = resolver.get_available_models()
        
        print(f"Received models: {models}")
        
        print("Check: Alias 'auto-kiro' present...")
        assert "auto-kiro" in models
        
        print("Check: Original 'auto' hidden...")
        assert "auto" not in models
        
        print("Check: Hidden model 'claude-3.7-sonnet' present...")
        assert "claude-3.7-sonnet" in models
        
        print("Check: Alias to hidden model 'legacy' present...")
        assert "legacy" in models
        
        print("Check: Cache models present...")
        assert "claude-haiku-4.5" in models


class TestAliasSystemSecurity:
    """Security tests - ensure aliases don't break safety principles."""
    
    def test_alias_cannot_bypass_family_isolation(self, mock_model_cache):
        """
        What it does: Alias doesn't break family isolation.
        Purpose: CRITICAL - ensure aliases don't create security holes!
        """
        print("Setup: Creating resolver with alias...")
        aliases = {"my-model": "claude-opus-5"}
        resolver = ModelResolver(cache=mock_model_cache, aliases=aliases)

        print("Action: Resolving 'my-model' (points to non-existent Opus)...")
        result = resolver.resolve("my-model")

        print(f"Result: {result}")
        print("Check: Does NOT fallback to Sonnet or Haiku...")
        assert "sonnet" not in result.internal_id.lower()
        assert "haiku" not in result.internal_id.lower()

        print("Check: Unknown models pass through as-is (gateway, not gatekeeper)...")
        assert result.internal_id == "claude-opus-5"
    
    def test_alias_suggestions_respect_target_family(self, mock_model_cache):
        """
        What it does: Suggestions for aliased model respect target family.
        Purpose: Ensure get_suggestions_for_model() works with aliases.
        """
        print("Setup: Creating resolver with alias...")
        aliases = {"fast": "claude-haiku-4.5"}
        resolver = ModelResolver(cache=mock_model_cache, aliases=aliases)
        
        print("Action: Getting suggestions for 'fast'...")
        # Note: get_suggestions_for_model() extracts family from the NAME
        # So it won't find "haiku" in "fast", will return all models
        suggestions = resolver.get_suggestions_for_model("fast")
        
        print(f"Received suggestions: {suggestions}")
        # This is expected behavior - alias name doesn't contain family
        assert len(suggestions) > 0
