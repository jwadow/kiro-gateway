"""
Catalog-driven native reasoning registry.

The Kiro control plane (``management.{region}.kiro.dev``) advertises, per model, an
``additionalModelRequestFieldsSchema`` that declares whether the model supports native
adaptive thinking and which effort levels it accepts. For example, ``claude-opus-4.6``
advertises::

    {
      "type": "object",
      "properties": {
        "thinking": {"type": "object", "properties": {
            "type": {"enum": ["adaptive", "disabled"]},
            "display": {"enum": ["summarized", "omitted"]}}},
        "output_config": {"type": "object", "properties": {
            "effort": {"enum": ["low", "medium", "high", "max"], "default": "high"}}},
        "max_tokens": {"type": "integer", "minimum": 1024, "maximum": 64000}
      },
      "additionalProperties": false
    }

This module turns that advertised schema into ``NativeEffortDescriptor`` objects and keeps
a process-global registry keyed by model id. It is populated from the live catalog by the
account manager (``register_from_catalog``) and consulted by the converter pipeline when
building ``additionalModelRequestFields``. When the live catalog is unavailable (e.g. the
runtime endpoint returned only static fallback models), callers fall back to the static
config tables — this module only holds what the backend actually advertised.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("kiro-gateway.native_reasoning")

# Canonical ordering of effort levels from least to most effort. Used to clamp a client
# requested effort onto the set a model actually accepts (e.g. "xhigh" -> "max" when the
# model only advertises low/medium/high/max).
EFFORT_ORDER: List[str] = ["minimal", "low", "medium", "high", "xhigh", "max"]


@dataclass
class NativeEffortDescriptor:
    """
    Describes how a single model accepts native reasoning effort, derived from the model's
    advertised ``additionalModelRequestFieldsSchema``.

    Attributes:
        schema_type: Where effort rides in ``additionalModelRequestFields`` —
            ``"output_config"`` (``output_config.effort`` alongside a ``thinking`` block) or
            ``"reasoning"`` (``reasoning.effort``).
        valid_efforts: The effort strings the backend advertised in the enum, in advertised
            order. The server strictly validates against this set.
        default_effort: The advertised default effort, if any.
    """

    schema_type: str
    valid_efforts: List[str] = field(default_factory=list)
    default_effort: Optional[str] = None


# Process-global registry, keyed by model id (dot form, e.g. "claude-opus-4.6").
_REGISTRY: Dict[str, NativeEffortDescriptor] = {}


def _descriptor_from_schema(schema: Dict[str, Any]) -> Optional[NativeEffortDescriptor]:
    """
    Parse a single model's ``additionalModelRequestFieldsSchema`` into a descriptor.

    Returns None when the schema does not advertise a native effort field (i.e. the model
    does not support native reasoning).
    """
    if not isinstance(schema, dict):
        return None

    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return None

    # Two known shapes: output_config.effort (Claude adaptive) and reasoning.effort.
    for schema_type in ("output_config", "reasoning"):
        block = properties.get(schema_type)
        if not isinstance(block, dict):
            continue
        effort = (block.get("properties") or {}).get("effort")
        if not isinstance(effort, dict):
            continue
        enum = effort.get("enum")
        valid = [str(e) for e in enum] if isinstance(enum, list) and enum else []
        return NativeEffortDescriptor(
            schema_type=schema_type,
            valid_efforts=valid,
            default_effort=effort.get("default"),
        )

    return None


def register_from_catalog(models: List[Dict[str, Any]]) -> None:
    """
    Rebuild the registry from a freshly fetched model catalog.

    Each entry is a model dict as returned by ``ListAvailableModels``; those that advertise
    an ``additionalModelRequestFieldsSchema`` with a native effort field are registered.
    Replaces any prior contents so stale models don't linger across a refresh.

    Args:
        models: List of model dicts from the control-plane catalog.
    """
    new_registry: Dict[str, NativeEffortDescriptor] = {}
    for model in models:
        if not isinstance(model, dict):
            continue
        model_id = model.get("modelId")
        schema = model.get("additionalModelRequestFieldsSchema")
        if not model_id or not schema:
            continue
        descriptor = _descriptor_from_schema(schema)
        if descriptor is not None:
            new_registry[model_id] = descriptor

    _REGISTRY.clear()
    _REGISTRY.update(new_registry)
    if new_registry:
        logger.info(
            "Native reasoning catalog: %d model(s) advertise effort — %s",
            len(new_registry),
            ", ".join(
                f"{m}({d.schema_type}:{'/'.join(d.valid_efforts) or '?'})"
                for m, d in new_registry.items()
            ),
        )
    else:
        logger.debug("Native reasoning catalog: no models advertised effort schema")


def get_descriptor(model_id: str) -> Optional[NativeEffortDescriptor]:
    """Return the advertised descriptor for a model, or None if the catalog had none."""
    return _REGISTRY.get(model_id)


def has_catalog() -> bool:
    """True if any model advertised a native effort schema (live catalog was parsed)."""
    return bool(_REGISTRY)


def clamp_effort(requested: str, valid_efforts: List[str]) -> Optional[str]:
    """
    Map a client-requested effort onto the set a model actually accepts.

    Exact matches pass through. Otherwise the requested level is snapped to the nearest
    advertised level by position in ``EFFORT_ORDER``, preferring the higher level on a tie
    (so ``xhigh`` against ``[low, medium, high, max]`` resolves to ``max``, honoring the
    intent of "more than high"). Returns None only when the model advertised no efforts.

    Args:
        requested: The client's requested effort (already alias-normalized).
        valid_efforts: The effort levels the model advertised.

    Returns:
        A valid effort string, or None if ``valid_efforts`` is empty.
    """
    if not valid_efforts:
        return None
    if requested in valid_efforts:
        return requested

    if requested not in EFFORT_ORDER:
        # Unknown token — fall back to the model's default or its highest advertised level.
        return valid_efforts[-1]

    target = EFFORT_ORDER.index(requested)

    def distance(level: str) -> tuple[int, int]:
        # Primary: absolute distance. Tie-break: prefer higher position (negative index).
        pos = EFFORT_ORDER.index(level) if level in EFFORT_ORDER else 0
        return (abs(pos - target), -pos)

    return min(valid_efforts, key=distance)
