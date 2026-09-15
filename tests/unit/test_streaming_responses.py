# -*- coding: utf-8 -*-

"""
Unit tests for streaming_responses module (OpenAI Responses API SSE).

Tests the KiroEvent -> Responses SSE state machine by feeding a fake Kiro
event stream through the internal generator and parsing the emitted events.
"""

import json
from types import SimpleNamespace

import pytest

from kiro.streaming_core import KiroEvent
from kiro import streaming_responses


class _FakeResponse:
    """Minimal stand-in for httpx.Response.aclose()."""
    status_code = 200

    async def aclose(self):
        return None


def _parse_sse(chunks):
    """Parse a list of SSE strings into [(event_type, data_dict), ...]."""
    events = []
    for chunk in chunks:
        lines = chunk.strip().split("\n")
        event_type = None
        data = None
        for line in lines:
            if line.startswith("event: "):
                event_type = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if event_type is not None:
            events.append((event_type, data))
    return events


async def _run(
    events,
    monkeypatch,
    model="claude-sonnet-4.5",
    custom_tool_names=None,
    parallel_tool_calls=None,
):
    """Drive the internal generator with a fake parse_kiro_stream."""
    async def fake_parse_kiro_stream(response, first_token_timeout, *a, **kw):
        for e in events:
            yield e

    monkeypatch.setattr(streaming_responses, "parse_kiro_stream", fake_parse_kiro_stream)

    class _Cache:
        def get_max_input_tokens(self, model):
            return 200000

    chunks = []
    async for chunk in streaming_responses.stream_kiro_to_responses_internal(
        client=None, response=_FakeResponse(), model=model,
        model_cache=_Cache(), auth_manager=None,
        custom_tool_names=custom_tool_names,
        parallel_tool_calls=parallel_tool_calls,
    ):
        chunks.append(chunk)
    return _parse_sse(chunks)


@pytest.mark.asyncio
class TestResponsesStreaming:

    async def test_text_only_event_sequence(self, monkeypatch):
        """
        What it does: content events produce a well-formed message item lifecycle.
        Purpose: Codex expects created -> item.added -> deltas -> done -> completed.
        """
        events = [
            KiroEvent(type="content", content="Hello "),
            KiroEvent(type="content", content="world"),
            KiroEvent(type="context_usage", context_usage_percentage=1.0),
        ]
        parsed = await _run(events, monkeypatch)
        types = [t for t, _ in parsed]

        assert types[0] == "response.created"
        assert "response.output_item.added" in types
        assert "response.content_part.added" in types
        assert types.count("response.output_text.delta") == 2
        assert "response.output_text.done" in types
        assert "response.output_item.done" in types
        assert types[-1] == "response.completed"

    async def test_deltas_carry_text(self, monkeypatch):
        """
        What it does: output_text.delta events carry the exact content chunks.
        """
        events = [KiroEvent(type="content", content="abc")]
        parsed = await _run(events, monkeypatch)
        deltas = [d["delta"] for t, d in parsed if t == "response.output_text.delta"]
        assert deltas == ["abc"]

    async def test_completed_has_usage_and_output(self, monkeypatch):
        """
        What it does: response.completed carries usage (input/output tokens) and output items.
        Purpose: Codex reads final usage and output from this event.
        """
        events = [
            KiroEvent(type="content", content="hi"),
            KiroEvent(type="context_usage", context_usage_percentage=2.0),
        ]
        parsed = await _run(events, monkeypatch)
        _, completed = [e for e in parsed if e[0] == "response.completed"][0]
        assert "usage" in completed["response"]
        assert "input_tokens" in completed["response"]["usage"]
        assert "output_tokens" in completed["response"]["usage"]
        assert completed["response"]["status"] == "completed"
        assert len(completed["response"]["output"]) == 1

    async def test_reasoning_then_text(self, monkeypatch):
        """
        What it does: thinking events open a reasoning item, then content opens a message.
        Purpose: reasoning and message are distinct output items.
        """
        events = [
            KiroEvent(type="thinking", thinking_content="let me think"),
            KiroEvent(type="content", content="answer"),
        ]
        parsed = await _run(events, monkeypatch)
        types = [t for t, _ in parsed]

        assert "response.reasoning_summary_text.delta" in types
        assert "response.output_text.delta" in types
        # reasoning item closes before the message item opens
        assert types.index("response.reasoning_summary_text.done") < \
               types.index("response.output_text.delta")

    async def test_function_call_events(self, monkeypatch):
        """
        What it does: a tool_use event produces a function_call item with args.
        Purpose: Codex needs function_call items to run tools.
        """
        events = [
            KiroEvent(type="content", content="calling"),
            KiroEvent(type="tool_use", tool_use={
                "id": "call_1", "type": "function",
                "function": {"name": "shell", "arguments": '{"cmd":"ls"}'},
            }),
        ]
        parsed = await _run(events, monkeypatch)
        types = [t for t, _ in parsed]

        assert "response.function_call_arguments.delta" in types
        assert "response.function_call_arguments.done" in types

        # the completed response includes a function_call output item
        _, completed = [e for e in parsed if e[0] == "response.completed"][0]
        fc = [i for i in completed["response"]["output"] if i["type"] == "function_call"]
        assert len(fc) == 1
        assert fc[0]["call_id"] == "call_1"
        assert fc[0]["name"] == "shell"
        assert fc[0]["arguments"] == '{"cmd":"ls"}'

    async def test_custom_tool_call_events(self, monkeypatch):
        """
        What it does: a tool_use whose name is in custom_tool_names produces a
        custom_tool_call item with unwrapped freeform input (not a function_call).
        Purpose: Codex custom tools (e.g. exec) use custom_tool_call_input.* events
        and expect raw text in `input`, not JSON arguments.
        """
        events = [
            KiroEvent(type="tool_use", tool_use={
                "id": "call_x", "type": "function",
                "function": {"name": "exec", "arguments": '{"input": "print(1)"}'},
            }),
        ]
        parsed = await _run(events, monkeypatch, custom_tool_names={"exec"})
        types = [t for t, _ in parsed]

        # custom event names, NOT function_call ones
        assert "response.custom_tool_call_input.delta" in types
        assert "response.custom_tool_call_input.done" in types
        assert "response.function_call_arguments.delta" not in types

        # the delta carries the UNWRAPPED raw text
        delta = [d["delta"] for t, d in parsed if t == "response.custom_tool_call_input.delta"][0]
        assert delta == "print(1)"

        # completed output has a custom_tool_call item with raw input
        _, completed = [e for e in parsed if e[0] == "response.completed"][0]
        ctc = [i for i in completed["response"]["output"] if i["type"] == "custom_tool_call"]
        assert len(ctc) == 1
        assert ctc[0]["call_id"] == "call_x"
        assert ctc[0]["name"] == "exec"
        assert ctc[0]["input"] == "print(1)"

    async def test_non_custom_tool_still_function_call(self, monkeypatch):
        """
        What it does: a tool NOT in custom_tool_names stays a function_call even
        when custom_tool_names is non-empty.
        Purpose: only the designated custom tools switch event shape.
        """
        events = [
            KiroEvent(type="tool_use", tool_use={
                "id": "c1", "type": "function",
                "function": {"name": "shell", "arguments": '{"cmd":"ls"}'},
            }),
        ]
        parsed = await _run(events, monkeypatch, custom_tool_names={"exec"})
        types = [t for t, _ in parsed]
        assert "response.function_call_arguments.done" in types
        assert "response.custom_tool_call_input.done" not in types

    async def test_pure_tool_call_starts_with_created(self, monkeypatch):
        """
        What it does: a tool call with NO preceding text/reasoning still emits
        response.created before any output item events.
        Purpose: Codex's state machine requires response.created first; otherwise
        it may ignore the tool call or hang. Regression guard for the ordering bug.
        """
        events = [
            KiroEvent(type="tool_use", tool_use={
                "id": "c1", "type": "function",
                "function": {"name": "shell", "arguments": '{"cmd":"ls"}'},
            }),
        ]
        parsed = await _run(events, monkeypatch)
        types = [t for t, _ in parsed]
        assert types[0] == "response.created"
        assert types.index("response.created") < types.index("response.output_item.added")
        assert types[-1] == "response.completed"

    async def test_pure_custom_tool_call_starts_with_created(self, monkeypatch):
        """Same ordering guarantee for a pure custom_tool_call (e.g. exec)."""
        events = [
            KiroEvent(type="tool_use", tool_use={
                "id": "cx", "type": "function",
                "function": {"name": "exec", "arguments": '{"input": "x"}'},
            }),
        ]
        parsed = await _run(events, monkeypatch, custom_tool_names={"exec"})
        types = [t for t, _ in parsed]
        assert types[0] == "response.created"
        assert types.index("response.created") < types.index("response.output_item.added")

    async def test_tool_call_counts_output_tokens(self, monkeypatch):
        """
        What it does: a pure tool-call response reports output_tokens > 0.
        Purpose: tool name + arguments must count toward output tokens; a pure
        tool call must not report output_tokens=0.
        """
        events = [
            KiroEvent(type="tool_use", tool_use={
                "id": "c1", "type": "function",
                "function": {"name": "shell", "arguments": '{"cmd":"ls -la /tmp"}'},
            }),
            KiroEvent(type="context_usage", context_usage_percentage=1.0),
        ]
        parsed = await _run(events, monkeypatch)
        _, completed = [e for e in parsed if e[0] == "response.completed"][0]
        assert completed["response"]["usage"]["output_tokens"] > 0

    async def test_mid_stream_error_emits_response_failed(self, monkeypatch):
        """
        What it does: an upstream error after SSE has started emits a terminal
        response.failed event instead of dropping the connection.
        Purpose: once HTTP 200 is sent, failure can only be signalled in-band;
        Codex should get a clean terminal event, not an EOF/reset.
        """
        async def failing_parse(response, first_token_timeout, *a, **kw):
            yield KiroEvent(type="content", content="partial")
            raise RuntimeError("upstream exploded")

        monkeypatch.setattr(streaming_responses, "parse_kiro_stream", failing_parse)

        class _Cache:
            def get_max_input_tokens(self, model):
                return 200000

        chunks = []
        async for chunk in streaming_responses.stream_kiro_to_responses_internal(
            client=None, response=_FakeResponse(), model="claude-sonnet-4.5",
            model_cache=_Cache(), auth_manager=None,
        ):
            chunks.append(chunk)
        parsed = _parse_sse(chunks)
        types = [t for t, _ in parsed]

        # created was emitted, and the stream ends with a failed terminal event
        assert "response.created" in types
        assert types[-1] == "response.failed"
        _, failed = parsed[-1]
        assert failed["response"]["status"] == "failed"
        assert "upstream exploded" in failed["response"]["error"]["message"]
        assert failed["response"]["error"]["code"] is None

    async def test_mid_stream_error_does_not_complete_partial_item(self, monkeypatch):
        """
        What it does: a failed partial message is abandoned without done events.
        Purpose: truncated output must not be advertised as a completed item.
        """
        async def failing_parse(response, first_token_timeout, *args, **kwargs):
            yield KiroEvent(type="content", content="partial")
            raise RuntimeError("upstream exploded")

        monkeypatch.setattr(streaming_responses, "parse_kiro_stream", failing_parse)

        class _Cache:
            def get_max_input_tokens(self, model):
                return 200000

        chunks = []
        async for chunk in streaming_responses.stream_kiro_to_responses_internal(
            client=None, response=_FakeResponse(), model="m",
            model_cache=_Cache(), auth_manager=None,
        ):
            chunks.append(chunk)

        types = [event_type for event_type, _ in _parse_sse(chunks)]
        assert "response.output_text.done" not in types
        assert "response.content_part.done" not in types
        assert "response.output_item.done" not in types
        assert types[-1] == "response.failed"

    async def test_parallel_tool_calls_false_returns_one_call(self, monkeypatch):
        """
        What it does: two generated calls become one when parallel calls are disabled.
        Purpose: Codex sends parallel_tool_calls=false and must not receive a
        parallel batch it explicitly prohibited.
        """
        events = [
            KiroEvent(type="tool_use", tool_use={
                "id": "c1", "type": "function",
                "function": {"name": "first", "arguments": "{}"},
            }),
            KiroEvent(type="tool_use", tool_use={
                "id": "c2", "type": "function",
                "function": {"name": "second", "arguments": "{}"},
            }),
        ]

        parsed = await _run(
            events, monkeypatch, parallel_tool_calls=False,
        )
        completed = next(data for event_type, data in parsed if event_type == "response.completed")
        calls = [item for item in completed["response"]["output"] if item["type"] == "function_call"]

        assert len(calls) == 1
        assert calls[0]["name"] == "first"

    async def test_non_streaming_parallel_tool_calls_false_returns_one_call(
        self, monkeypatch
    ):
        """Non-streaming responses enforce the same serial tool-call policy."""
        result = SimpleNamespace(
            thinking_content="",
            content="",
            tool_calls=[
                {
                    "id": "c1",
                    "function": {"name": "first", "arguments": "{}"},
                },
                {
                    "id": "c2",
                    "function": {"name": "second", "arguments": "{}"},
                },
            ],
            context_usage_percentage=None,
        )

        async def fake_collect_stream_to_result(response):
            return result

        monkeypatch.setattr(
            "kiro.streaming_core.collect_stream_to_result",
            fake_collect_stream_to_result,
        )

        response = await streaming_responses.collect_responses_response(
            client=None, response=_FakeResponse(), model="m",
            model_cache=None, auth_manager=None, parallel_tool_calls=False,
        )
        calls = [item for item in response["output"] if item["type"] == "function_call"]

        assert len(calls) == 1
        assert calls[0]["name"] == "first"

    async def test_retry_exhaustion_emits_failed_sequence(self, monkeypatch):
        """
        What it does: exhausted first-token retries end with response.failed.
        Purpose: StreamingResponse headers are already 200, so raising an HTTP
        exception would only produce an unexplained EOF for Codex.
        """
        async def failing_retry_core(**kwargs):
            if False:
                yield ""
            raise kwargs["on_all_retries_failed"](2, 0.01)

        monkeypatch.setattr(
            streaming_responses,
            "stream_with_first_token_retry_core",
            failing_retry_core,
        )

        async def make_request():
            return _FakeResponse()

        chunks = []
        async for chunk in streaming_responses.stream_responses_with_first_token_retry(
            make_request=make_request, client=None, model="m",
            model_cache=None, auth_manager=None, max_retries=2,
            first_token_timeout=0.01,
        ):
            chunks.append(chunk)

        parsed = _parse_sse(chunks)
        types = [event_type for event_type, _ in parsed]
        assert types == ["response.created", "response.in_progress", "response.failed"]
        assert parsed[-1][1]["response"]["status"] == "failed"
        assert "2 attempts" in parsed[-1][1]["response"]["error"]["message"]

    async def test_retry_http_error_emits_failed_sequence(self):
        """A non-200 retry response is converted to an in-band failure."""
        class _ErrorResponse(_FakeResponse):
            status_code = 503

            async def aread(self):
                return b"temporarily unavailable"

        async def make_request():
            return _ErrorResponse()

        chunks = []
        async for chunk in streaming_responses.stream_responses_with_first_token_retry(
            make_request=make_request, client=None, model="m",
            model_cache=None, auth_manager=None, initial_response=None,
            max_retries=1, first_token_timeout=0.01,
        ):
            chunks.append(chunk)

        parsed = _parse_sse(chunks)
        types = [event_type for event_type, _ in parsed]
        assert types == ["response.created", "response.in_progress", "response.failed"]
        assert "503" not in parsed[-1][1]["response"]["error"]["message"]
        assert "temporarily unavailable" in parsed[-1][1]["response"]["error"]["message"]

    async def test_sequence_numbers_monotonic(self, monkeypatch):
        """
        What it does: every event carries a strictly increasing sequence_number.
        Purpose: Codex relies on ordered sequence numbers.
        """
        events = [
            KiroEvent(type="thinking", thinking_content="t"),
            KiroEvent(type="content", content="c"),
        ]
        parsed = await _run(events, monkeypatch)
        seqs = [d["sequence_number"] for _, d in parsed]
        assert seqs == list(range(len(seqs)))
