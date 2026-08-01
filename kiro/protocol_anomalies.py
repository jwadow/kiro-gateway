# -*- coding: utf-8 -*-

"""Pure classifiers for high-confidence protocol anomalies."""

import re
from typing import Optional


RECIPIENT_MARKER = re.compile(
    r"assistant\s+to\s*=\s*(?:functions|multi_tool_use)\.[A-Za-z0-9_.-]+",
    re.IGNORECASE,
)
RAW_ENVELOPE_MARKERS = (
    "<|channel|>",
    "<|recipient|>",
    "<|constrain|>",
    "<|end|>",
)
SELF_REFERENTIAL_MARKERS = (
    "assistant to=functions.",
    "assistant to=multi_tool_use.",
    "recipient=functions.",
    "recipient=multi_tool_use.",
)


def classify_protocol_text(text: str) -> Optional[str]:
    """Return a signature name only for high-confidence transport-text leakage."""
    if not text:
        return None

    recipient_matches = RECIPIENT_MARKER.findall(text)
    raw_envelope_count = sum(text.count(marker) for marker in RAW_ENVELOPE_MARKERS)
    lowered = text.lower()
    self_reference_count = sum(
        lowered.count(marker) for marker in SELF_REFERENTIAL_MARKERS
    )

    if len(recipient_matches) >= 2:
        return "repeated_tool_recipient_syntax"
    if recipient_matches and raw_envelope_count >= 1:
        return "raw_transport_envelope"
    if raw_envelope_count >= 2:
        return "repeated_transport_envelope"
    if self_reference_count >= 3:
        return "tool_serialization_loop"

    return None
