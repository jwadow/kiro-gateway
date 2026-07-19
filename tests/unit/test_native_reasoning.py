# -*- coding: utf-8 -*-

"""
Unit tests for catalog-driven native reasoning.

Covers parsing per-model additionalModelRequestFieldsSchema into effort descriptors,
clamping requested effort onto the advertised set, and the end-to-end payload built by
build_native_effort_fields when a live catalog is (and isn't) registered.
"""

import pytest

from kiro import native_reasoning as nr
from kiro.converters_core import build_native_effort_fields


# Real advertised schema for claude-opus-4.6 (effort enum: low/medium/high/max).
OPUS_46 = {
    "modelId": "claude-opus-4.6",
    "additionalModelRequestFieldsSchema": {
        "type": "object",
        "properties": {
            "thinking": {
                "type": "object",
                "properties": {
                    "type": {"enum": ["adaptive", "disabled"]},
                    "display": {"enum": ["summarized", "omitted"]},
                },
            },
            "output_config": {
                "type": "object",
                "properties": {
                    "effort": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "max"],
                        "default": "high",
                    }
                },
            },
            "max_tokens": {"type": "integer", "minimum": 1024, "maximum": 64000},
        },
        "additionalProperties": False,
    },
}

REASONING_MODEL = {
    "modelId": "gpt-5.6-sol",
    "additionalModelRequestFieldsSchema": {
        "type": "object",
        "properties": {
            "reasoning": {
                "type": "object",
                "properties": {"effort": {"type": "string", "enum": ["low", "high"]}},
            }
        },
    },
}

NO_SCHEMA_MODEL = {"modelId": "claude-sonnet-4", "description": "no schema"}


@pytest.fixture(autouse=True)
def _clear_registry():
    """Each test starts from an empty registry and leaves it empty."""
    nr.register_from_catalog([])
    yield
    nr.register_from_catalog([])


class TestRegisterFromCatalog:
    def test_parses_output_config_schema(self):
        nr.register_from_catalog([OPUS_46])
        d = nr.get_descriptor("claude-opus-4.6")
        assert d is not None
        assert d.schema_type == "output_config"
        assert d.valid_efforts == ["low", "medium", "high", "max"]
        assert d.default_effort == "high"

    def test_parses_reasoning_schema(self):
        nr.register_from_catalog([REASONING_MODEL])
        d = nr.get_descriptor("gpt-5.6-sol")
        assert d.schema_type == "reasoning"
        assert d.valid_efforts == ["low", "high"]

    def test_models_without_schema_are_absent(self):
        nr.register_from_catalog([OPUS_46, NO_SCHEMA_MODEL])
        assert nr.get_descriptor("claude-sonnet-4") is None
        assert nr.has_catalog() is True

    def test_refresh_replaces_prior_contents(self):
        nr.register_from_catalog([OPUS_46])
        nr.register_from_catalog([REASONING_MODEL])
        assert nr.get_descriptor("claude-opus-4.6") is None
        assert nr.get_descriptor("gpt-5.6-sol") is not None

    def test_empty_catalog_clears(self):
        nr.register_from_catalog([OPUS_46])
        nr.register_from_catalog([])
        assert nr.has_catalog() is False


class TestClampEffort:
    EFFORTS = ["low", "medium", "high", "max"]

    def test_exact_match_passthrough(self):
        assert nr.clamp_effort("high", self.EFFORTS) == "high"

    def test_xhigh_snaps_up_to_max(self):
        # xhigh sits between high and max; tie-break prefers the higher level.
        assert nr.clamp_effort("xhigh", self.EFFORTS) == "max"

    def test_minimal_snaps_to_low(self):
        assert nr.clamp_effort("minimal", ["medium", "high"]) == "medium"

    def test_unknown_token_falls_back_to_highest(self):
        assert nr.clamp_effort("bogus", self.EFFORTS) == "max"

    def test_empty_efforts_returns_none(self):
        assert nr.clamp_effort("high", []) is None


class TestBuildNativeEffortFields:
    def test_catalog_xhigh_clamped_not_rejected(self):
        nr.register_from_catalog([OPUS_46])
        fields = build_native_effort_fields("claude-opus-4.6", "xhigh")
        assert fields == {
            "thinking": {"type": "adaptive", "display": "summarized"},
            "output_config": {"effort": "max"},
        }

    def test_catalog_reasoning_schema_shape(self):
        nr.register_from_catalog([REASONING_MODEL])
        fields = build_native_effort_fields("gpt-5.6-sol", "high")
        assert fields == {"reasoning": {"effort": "high"}}

    def test_unsupported_model_returns_none(self):
        nr.register_from_catalog([OPUS_46])
        assert build_native_effort_fields("claude-sonnet-4", "high") is None

    def test_no_effort_returns_none(self):
        nr.register_from_catalog([OPUS_46])
        assert build_native_effort_fields("claude-opus-4.6", None) is None

    def test_static_fallback_when_no_catalog(self):
        # Empty registry -> falls back to the static config table (auto is output_config).
        fields = build_native_effort_fields("auto", "high")
        assert fields == {
            "thinking": {"type": "adaptive", "display": "summarized"},
            "output_config": {"effort": "high"},
        }
