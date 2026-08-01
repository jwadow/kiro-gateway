# -*- coding: utf-8 -*-

"""Tests for high-confidence protocol anomaly classification."""

import pytest

from kiro.protocol_anomalies import classify_protocol_text


@pytest.mark.parametrize(
    ("text", "signature"),
    [
        (
            "assistant to=functions.Read then assistant to=functions.Edit",
            "repeated_tool_recipient_syntax",
        ),
        (
            "assistant to=functions.Read <|channel|>commentary",
            "raw_transport_envelope",
        ),
        (
            "<|channel|>analysis <|recipient|>functions.Read",
            "repeated_transport_envelope",
        ),
        (
            "recipient=functions.Read recipient=functions.Edit "
            "recipient=multi_tool_use.parallel",
            "tool_serialization_loop",
        ),
    ],
)
def test_classifies_high_confidence_protocol_leaks(text, signature):
    assert classify_protocol_text(text) == signature


@pytest.mark.parametrize(
    "text",
    [
        "",
        "The functions.Read API accepts a file path.",
        "A transcript may contain assistant to=functions.Read as an example.",
        "The literal marker <|channel|> can be discussed in documentation.",
    ],
)
def test_ordinary_protocol_discussion_does_not_trigger(text):
    assert classify_protocol_text(text) is None
