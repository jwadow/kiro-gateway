# -*- coding: utf-8 -*-

"""
Unit tests for converters_responses.py (OpenAI Responses API <-> Chat Completions).

Covers:
- Request translation (instructions, string/list input, all item types, tools, tool_choice, params)
- Malformed/unsupported input rejection
- Non-streaming response building
- Streaming event translation (text, tool calls, reasoning, mixed, errors)
"""

import json
from typing import Any, Dict, List

import pytest
from fastapi import HTTPException

from kiro.converters_responses import (
    ResponsesConversionError,
    ResponsesStreamTranslator,
    build_usage,
    chat_completion_to_response,
    convert_input_items,
    convert_tool_choice,
    convert_tools,
    format_sse_event,
    responses_request_to_chat,
    status_from_finish_reason,
    stream_chat_to_responses,
)
from kiro.models_responses import ResponsesRequest


def make_request(**kwargs: Any) -> ResponsesRequest:
    """Build a ResponsesRequest with sensible defaults."""
    kwargs.setdefault("model", "claude-sonnet-4.5")
    kwargs.setdefault("input", "Hello")
    return ResponsesRequest(**kwargs)


def chunk(delta: Dict[str, Any], finish_reason: Any = None, usage: Any = None) -> Dict[str, Any]:
    """Build a chat.completion.chunk dict."""
    data: Dict[str, Any] = {
        "id": "chatcmpl-1",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    if usage is not None:
        data["usage"] = usage
    return data


def sse(data: Dict[str, Any]) -> str:
    """Format a chat chunk as an SSE frame."""
    return f"data: {json.dumps(data)}\n\n"


def parse_events(frames: List[str]) -> List[Dict[str, Any]]:
    """Parse Responses SSE frames into event dicts, checking the event: line matches."""
    events = []
    for frame in "".join(frames).split("\n\n"):
        if not frame.strip():
            continue
        lines = frame.split("\n")
        assert lines[0].startswith("event: ")
        assert lines[1].startswith("data: ")
        event = json.loads(lines[1][6:])
        assert event["type"] == lines[0][7:]
        events.append(event)
    return events


async def agen(items: List[Any]):
    """Async generator over a list."""
    for item in items:
        yield item


async def collect(stream) -> List[str]:
    """Collect an async iterator into a list."""
    return [x async for x in stream]


# =============================================================================
# Request translation
# =============================================================================

class TestRequestTranslationSuccess:
    """Tests for successful Responses -> Chat translation."""

    def test_string_input_becomes_single_user_message(self):
        """
        What it does: Translates string input.
        Purpose: Simplest Responses request maps to one user message.
        """
        chat = responses_request_to_chat(make_request(input="Hi there"))
        assert len(chat.messages) == 1
        assert chat.messages[0].role == "user"
        assert chat.messages[0].content == "Hi there"

    def test_instructions_become_leading_system_message(self):
        """
        What it does: Translates instructions.
        Purpose: instructions must be prepended as system message.
        """
        chat = responses_request_to_chat(make_request(instructions="Be terse", input="Hi"))
        assert [m.role for m in chat.messages] == ["system", "user"]
        assert chat.messages[0].content == "Be terse"

    def test_generation_params_are_mapped(self):
        """
        What it does: Maps max_output_tokens, temperature, top_p, stream, parallel_tool_calls, tool_choice.
        Purpose: Ensure scalar params reach the chat pipeline.
        """
        chat = responses_request_to_chat(make_request(
            max_output_tokens=123, temperature=0.3, top_p=0.9, stream=True,
            parallel_tool_calls=False, tool_choice="required", user="u1",
        ))
        assert chat.max_tokens == 123
        assert chat.temperature == 0.3
        assert chat.top_p == 0.9
        assert chat.stream is True
        assert chat.parallel_tool_calls is False
        assert chat.tool_choice == "required"
        assert chat.user == "u1"

    def test_reasoning_effort_is_mapped(self):
        """
        What it does: Maps reasoning.effort to reasoning_effort.
        Purpose: Enable extended thinking via Responses reasoning config.
        """
        chat = responses_request_to_chat(make_request(reasoning={"effort": "high"}))
        assert chat.reasoning_effort == "high"

    def test_store_true_is_ignored(self):
        """
        What it does: Accepts store=true.
        Purpose: Clients (e.g. SDK defaults) send store; it must not fail.
        """
        chat = responses_request_to_chat(make_request(store=True))
        assert chat.messages[0].content == "Hello"

    @pytest.mark.parametrize("role,expected", [
        ("user", "user"), ("assistant", "assistant"), ("system", "system"), ("developer", "system"),
    ])
    def test_message_roles_are_mapped(self, role, expected):
        """
        What it does: Maps every supported role.
        Purpose: developer must become system; others pass through.
        """
        messages = convert_input_items([{"type": "message", "role": role, "content": "x"}])
        assert messages[0].role == expected

    def test_message_without_type_is_treated_as_message(self):
        """
        What it does: Accepts EasyInputMessage ({role, content} without type).
        Purpose: Common shorthand from SDKs.
        """
        messages = convert_input_items([{"role": "user", "content": "hi"}])
        assert messages[0].role == "user"
        assert messages[0].content == "hi"

    def test_text_parts_are_joined_into_string(self):
        """
        What it does: Converts input_text/output_text parts.
        Purpose: Text-only content becomes a plain string.
        """
        messages = convert_input_items([
            {"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": "a"}, {"type": "input_text", "text": "b"}]},
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "c"}]},
        ])
        assert messages[0].content == "a\nb"
        assert messages[1].content == "c"

    def test_input_image_becomes_image_url_part(self):
        """
        What it does: Converts input_image with image_url.
        Purpose: Images must reach the chat pipeline in image_url format.
        """
        messages = convert_input_items([{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "what is this"},
            {"type": "input_image", "image_url": "data:image/png;base64,AAAA", "detail": "high"},
        ]}])
        assert messages[0].content == [
            {"type": "text", "text": "what is this"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA", "detail": "high"}},
        ]

    def test_input_image_with_object_url(self):
        """
        What it does: Accepts image_url given as {"url": ...}.
        Purpose: Tolerate chat-style image objects.
        """
        messages = convert_input_items([{"role": "user", "content": [
            {"type": "input_image", "image_url": {"url": "https://x/y.png"}}]}])
        assert messages[0].content[0]["image_url"]["url"] == "https://x/y.png"

    def test_function_call_and_output_round_trip(self):
        """
        What it does: Converts function_call and function_call_output items.
        Purpose: Tool-use history must map to assistant tool_calls + tool messages.
        """
        messages = convert_input_items([
            {"role": "user", "content": "weather?"},
            {"type": "function_call", "call_id": "call_1", "name": "get_weather", "arguments": '{"city":"Paris"}'},
            {"type": "function_call_output", "call_id": "call_1", "output": "sunny"},
        ])
        assert [m.role for m in messages] == ["user", "assistant", "tool"]
        assert messages[1].tool_calls == [{
            "id": "call_1", "type": "function",
            "function": {"name": "get_weather", "arguments": '{"city":"Paris"}'},
        }]
        assert messages[2].tool_call_id == "call_1"
        assert messages[2].content == "sunny"

    def test_consecutive_function_calls_merge_into_one_assistant_message(self):
        """
        What it does: Merges parallel function_call items.
        Purpose: Chat format expects parallel calls in one assistant message.
        """
        messages = convert_input_items([
            {"type": "function_call", "call_id": "a", "name": "f", "arguments": "{}"},
            {"type": "function_call", "call_id": "b", "name": "g", "arguments": "{}"},
            {"type": "function_call_output", "call_id": "a", "output": "1"},
            {"type": "function_call_output", "call_id": "b", "output": "2"},
        ])
        assert [m.role for m in messages] == ["assistant", "tool", "tool"]
        assert [tc["id"] for tc in messages[0].tool_calls] == ["a", "b"]

    def test_function_call_attaches_to_preceding_assistant_message(self):
        """
        What it does: Attaches a function_call to the assistant text before it.
        Purpose: Assistant text + tool call is a single chat message.
        """
        messages = convert_input_items([
            {"role": "assistant", "content": "Let me check."},
            {"type": "function_call", "call_id": "a", "name": "f", "arguments": "{}"},
        ])
        assert len(messages) == 1
        assert messages[0].content == "Let me check."
        assert messages[0].tool_calls[0]["id"] == "a"

    def test_function_call_after_user_message_starts_new_assistant(self):
        """
        What it does: Does not attach tool calls to user messages.
        Purpose: Guard against merging across roles.
        """
        messages = convert_input_items([
            {"role": "user", "content": "x"},
            {"type": "function_call", "call_id": "a", "name": "f"},
        ])
        assert [m.role for m in messages] == ["user", "assistant"]
        assert messages[1].tool_calls[0]["function"]["arguments"] == "{}"

    def test_function_call_dict_arguments_are_serialized(self):
        """
        What it does: Serializes object arguments to JSON.
        Purpose: Tolerate clients sending parsed arguments.
        """
        messages = convert_input_items([
            {"type": "function_call", "call_id": "a", "name": "f", "arguments": {"k": 1}}])
        assert json.loads(messages[0].tool_calls[0]["function"]["arguments"]) == {"k": 1}

    def test_function_call_output_list_and_dict(self):
        """
        What it does: Converts list and dict outputs.
        Purpose: output may be content parts or a JSON object.
        """
        messages = convert_input_items([
            {"type": "function_call_output", "call_id": "a", "output": [{"type": "input_text", "text": "t"}]},
            {"type": "function_call_output", "call_id": "b", "output": {"ok": True}},
            {"type": "function_call_output", "call_id": "c", "output": None},
        ])
        assert messages[0].content == "t"
        assert json.loads(messages[1].content) == {"ok": True}
        assert messages[2].content == ""

    def test_reasoning_items_are_skipped(self):
        """
        What it does: Skips reasoning input items.
        Purpose: Codex-style clients echo reasoning items back; they must not fail.
        """
        messages = convert_input_items([
            {"type": "reasoning", "id": "rs_1", "summary": []},
            {"role": "user", "content": "x"},
        ])
        assert len(messages) == 1

    def test_function_tools_are_converted(self):
        """
        What it does: Converts flat function tools to chat tools.
        Purpose: Responses tools differ in shape from chat tools.
        """
        tools = convert_tools([{
            "type": "function", "name": "get_weather", "description": "d",
            "parameters": {"type": "object", "properties": {}}, "strict": True,
        }])
        assert len(tools) == 1
        assert tools[0].type == "function"
        assert tools[0].function.name == "get_weather"
        assert tools[0].function.description == "d"
        assert tools[0].function.parameters == {"type": "object", "properties": {}}

    def test_builtin_tools_are_ignored(self):
        """
        What it does: Drops non-function tools.
        Purpose: web_search/file_search have no Kiro equivalent.
        """
        tools = convert_tools([{"type": "web_search_preview"}, {"type": "file_search"}])
        assert tools is None

    def test_mixed_tools_keep_only_functions(self):
        """
        What it does: Keeps function tools when mixed with built-ins.
        Purpose: Partial support must not drop valid tools.
        """
        tools = convert_tools([{"type": "web_search"}, {"type": "function", "name": "f"}])
        assert [t.function.name for t in tools] == ["f"]

    def test_empty_tools_returns_none(self):
        """
        What it does: Handles empty tools.
        Purpose: Avoid sending an empty tool list.
        """
        assert convert_tools(None) is None
        assert convert_tools([]) is None

    @pytest.mark.parametrize("value,expected", [
        (None, None), ("auto", "auto"), ("none", "none"), ("required", "required"),
        ({"type": "function", "name": "f"}, {"type": "function", "function": {"name": "f"}}),
        ({"type": "file_search"}, None),
    ])
    def test_tool_choice_mapping(self, value, expected):
        """
        What it does: Maps all tool_choice forms.
        Purpose: Function choice shape differs between APIs.
        """
        assert convert_tool_choice(value) == expected


class TestRequestTranslationErrors:
    """Tests for rejected Responses requests."""

    def test_previous_response_id_is_rejected(self):
        """
        What it does: Rejects previous_response_id.
        Purpose: Gateway is stateless; silently ignoring would drop context.
        """
        with pytest.raises(ResponsesConversionError) as exc:
            responses_request_to_chat(make_request(previous_response_id="resp_1"))
        assert exc.value.param == "previous_response_id"
        assert "full conversation" in exc.value.message

    def test_conversation_is_rejected(self):
        """
        What it does: Rejects conversation param.
        Purpose: Same stateless constraint as previous_response_id.
        """
        with pytest.raises(ResponsesConversionError) as exc:
            responses_request_to_chat(make_request(conversation="conv_1"))
        assert exc.value.param == "conversation"

    def test_empty_input_list_is_rejected(self):
        """
        What it does: Rejects input=[] without instructions.
        Purpose: Kiro needs at least one message.
        """
        with pytest.raises(ResponsesConversionError) as exc:
            responses_request_to_chat(make_request(input=[]))
        assert exc.value.param == "input"

    def test_invalid_reasoning_effort_is_rejected(self):
        """
        What it does: Rejects unknown reasoning effort.
        Purpose: Surface validation error as 400 with param name.
        """
        with pytest.raises(ResponsesConversionError) as exc:
            responses_request_to_chat(make_request(reasoning={"effort": "extreme"}))
        assert exc.value.param == "reasoning.effort"

    @pytest.mark.parametrize("items,param", [
        (["just a string"], "input[0]"),
        ([{"type": "message", "role": "robot", "content": "x"}], "input[0].role"),
        ([{"type": "message", "role": "user", "content": 5}], "input[0].content"),
        ([{"type": "message", "role": "user", "content": None}], "input[0].content"),
        ([{"role": "user", "content": [42]}], "input[0].content[0]"),
        ([{"role": "user", "content": [{"type": "input_text"}]}], "input[0].content[0]"),
        ([{"role": "user", "content": [{"type": "input_audio"}]}], "input[0].content[0]"),
        ([{"role": "user", "content": [{"type": "input_image", "file_id": "f"}]}], "input[0].content[0]"),
        ([{"type": "function_call", "name": "f"}], "input[0].call_id"),
        ([{"type": "function_call", "call_id": "a"}], "input[0].name"),
        ([{"type": "function_call", "call_id": "a", "name": "f", "arguments": 5}], "input[0].arguments"),
        ([{"type": "function_call_output", "output": "x"}], "input[0].call_id"),
        ([{"type": "function_call_output", "call_id": "a", "output": 3}], "input[0].output"),
        ([{"type": "item_reference", "id": "msg_1"}], "input[0]"),
        ([{"type": "computer_call"}], "input[0].type"),
        ([{"content": "no role no type"}], "input[0].type"),
    ])
    def test_malformed_items_raise_with_param(self, items, param):
        """
        What it does: Rejects every malformed item shape.
        Purpose: Errors must point at the offending item.
        """
        with pytest.raises(ResponsesConversionError) as exc:
            convert_input_items(items)
        assert exc.value.param == param

    @pytest.mark.parametrize("tools,param", [
        (["f"], "tools[0]"),
        ([{"type": "function"}], "tools[0].name"),
        ([{"type": "function", "name": "f", "parameters": "bad"}], "tools[0].parameters"),
    ])
    def test_malformed_tools_raise(self, tools, param):
        """
        What it does: Rejects malformed function tools.
        Purpose: Fail early instead of sending invalid schemas to Kiro.
        """
        with pytest.raises(ResponsesConversionError) as exc:
            convert_tools(tools)
        assert exc.value.param == param

    def test_function_tool_choice_without_name_raises(self):
        """
        What it does: Rejects tool_choice function without name.
        Purpose: Prevent ambiguous forced tool calls.
        """
        with pytest.raises(ResponsesConversionError):
            convert_tool_choice({"type": "function"})


# =============================================================================
# Non-streaming response building
# =============================================================================

def chat_response(message: Dict[str, Any], finish_reason: str = "stop", usage: Any = None) -> Dict[str, Any]:
    """Build a chat.completion dict."""
    return {
        "id": "chatcmpl-1", "object": "chat.completion", "created": 1700000000, "model": "m",
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


class TestNonStreamingResponse:
    """Tests for chat_completion_to_response."""

    def test_text_only_response(self):
        """
        What it does: Converts a text completion.
        Purpose: Core response shape must match the Responses API.
        """
        req = make_request(metadata={"k": "v"})
        resp = chat_completion_to_response(chat_response({"role": "assistant", "content": "Hi!"}), req)
        assert resp["id"].startswith("resp_")
        assert resp["object"] == "response"
        assert resp["created_at"] == 1700000000
        assert resp["status"] == "completed"
        assert resp["incomplete_details"] is None
        assert resp["model"] == "claude-sonnet-4.5"
        assert resp["metadata"] == {"k": "v"}
        assert len(resp["output"]) == 1
        msg = resp["output"][0]
        assert msg["type"] == "message"
        assert msg["id"].startswith("msg_")
        assert msg["status"] == "completed"
        assert msg["role"] == "assistant"
        assert msg["content"] == [{"type": "output_text", "text": "Hi!", "annotations": []}]
        assert resp["usage"]["input_tokens"] == 10
        assert resp["usage"]["output_tokens"] == 5
        assert resp["usage"]["total_tokens"] == 15

    def test_tool_calls_only_response_has_no_empty_message(self):
        """
        What it does: Converts a tool-call completion without text.
        Purpose: No empty message item should be emitted alongside function calls.
        """
        resp = chat_completion_to_response(chat_response({
            "role": "assistant", "content": "",
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "f", "arguments": '{"a":1}'}},
                {"id": "call_2", "type": "function", "function": {"name": "g", "arguments": None}},
            ],
        }, finish_reason="tool_calls"), make_request())
        assert [o["type"] for o in resp["output"]] == ["function_call", "function_call"]
        fc = resp["output"][0]
        assert fc["id"].startswith("fc_")
        assert fc["call_id"] == "call_1"
        assert fc["name"] == "f"
        assert fc["arguments"] == '{"a":1}'
        assert fc["status"] == "completed"
        assert resp["output"][1]["arguments"] == "{}"
        assert resp["status"] == "completed"

    def test_mixed_reasoning_text_and_tools_order(self):
        """
        What it does: Converts reasoning + text + tool call.
        Purpose: Output order must be reasoning, message, function_call.
        """
        resp = chat_completion_to_response(chat_response({
            "role": "assistant", "content": "Checking", "reasoning_content": "think",
            "tool_calls": [{"id": "c", "function": {"name": "f", "arguments": "{}"}}],
        }), make_request())
        assert [o["type"] for o in resp["output"]] == ["reasoning", "message", "function_call"]
        assert resp["output"][0]["summary"] == [{"type": "summary_text", "text": "think"}]

    def test_length_finish_reason_is_incomplete(self):
        """
        What it does: Maps finish_reason=length to incomplete.
        Purpose: Clients detect truncation via status/incomplete_details.
        """
        resp = chat_completion_to_response(
            chat_response({"role": "assistant", "content": "trunc"}, finish_reason="length"), make_request())
        assert resp["status"] == "incomplete"
        assert resp["incomplete_details"] == {"reason": "max_output_tokens"}
        assert resp["output"][0]["status"] == "incomplete"

    def test_empty_content_still_emits_message(self):
        """
        What it does: Handles empty completion.
        Purpose: output must not be empty for a completed text response.
        """
        resp = chat_completion_to_response(chat_response({"role": "assistant", "content": None}), make_request())
        assert resp["output"][0]["content"][0]["text"] == ""

    def test_missing_choices_and_usage_are_tolerated(self):
        """
        What it does: Handles a degenerate chat response.
        Purpose: Never crash while converting.
        """
        resp = chat_completion_to_response({"choices": [], "usage": None}, make_request())
        assert resp["status"] == "completed"
        assert resp["usage"]["total_tokens"] == 0

    def test_build_usage_computes_total_when_missing(self):
        """
        What it does: Sums tokens when total_tokens absent.
        Purpose: usage.total_tokens must always be present.
        """
        assert build_usage({"prompt_tokens": 3, "completion_tokens": 4})["total_tokens"] == 7
        assert build_usage(None)["input_tokens"] == 0

    @pytest.mark.parametrize("reason,expected", [
        ("stop", ("completed", None)), ("tool_calls", ("completed", None)), (None, ("completed", None)),
        ("length", ("incomplete", {"reason": "max_output_tokens"})),
        ("content_filter", ("incomplete", {"reason": "content_filter"})),
    ])
    def test_status_from_finish_reason(self, reason, expected):
        """
        What it does: Maps finish reasons to status.
        Purpose: Cover every branch of the status mapping.
        """
        assert status_from_finish_reason(reason) == expected


# =============================================================================
# Streaming
# =============================================================================

def event_types(events: List[Dict[str, Any]]) -> List[str]:
    """Extract event type names."""
    return [e["type"] for e in events]


class TestStreamTranslation:
    """Tests for stream_chat_to_responses and ResponsesStreamTranslator."""

    @pytest.mark.asyncio
    async def test_text_only_event_sequence(self):
        """
        What it does: Translates a text-only chat stream.
        Purpose: Event order and payloads must match the Responses spec.
        """
        stream = agen([
            sse(chunk({"role": "assistant", "content": "Hel"})),
            sse(chunk({"content": "lo"})),
            sse(chunk({}, finish_reason="stop", usage={"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5})),
            "data: [DONE]\n\n",
        ])
        events = parse_events(await collect(stream_chat_to_responses(stream, make_request(stream=True))))
        assert event_types(events) == [
            "response.created", "response.in_progress",
            "response.output_item.added", "response.content_part.added",
            "response.output_text.delta", "response.output_text.delta",
            "response.output_text.done", "response.content_part.done", "response.output_item.done",
            "response.completed",
        ]
        assert [e["sequence_number"] for e in events] == list(range(len(events)))
        assert events[0]["response"]["status"] == "in_progress"
        assert [e["delta"] for e in events if e["type"] == "response.output_text.delta"] == ["Hel", "lo"]
        assert events[6]["text"] == "Hello"
        item_id = events[2]["item"]["id"]
        assert all(e["item_id"] == item_id for e in events[3:8])
        completed = events[-1]["response"]
        assert completed["status"] == "completed"
        assert completed["id"] == events[0]["response"]["id"]
        assert completed["output"][0]["content"][0]["text"] == "Hello"
        assert completed["usage"] == build_usage({"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5})

    @pytest.mark.asyncio
    async def test_tool_call_event_sequence(self):
        """
        What it does: Translates a tool-call-only chat stream.
        Purpose: function_call items with argument events must be emitted.
        """
        stream = agen([
            sse(chunk({"tool_calls": [
                {"index": 0, "id": "call_1", "type": "function", "function": {"name": "f", "arguments": '{"a":1}'}},
                {"index": 1, "id": "call_2", "type": "function", "function": {"name": "g", "arguments": "{}"}},
            ]})),
            sse(chunk({}, finish_reason="tool_calls", usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})),
            "data: [DONE]\n\n",
        ])
        events = parse_events(await collect(stream_chat_to_responses(stream, make_request(stream=True))))
        assert event_types(events) == [
            "response.created", "response.in_progress",
            "response.output_item.added", "response.function_call_arguments.delta",
            "response.output_item.added", "response.function_call_arguments.delta",
            "response.function_call_arguments.done", "response.output_item.done",
            "response.function_call_arguments.done", "response.output_item.done",
            "response.completed",
        ]
        added = events[2]["item"]
        assert added["type"] == "function_call"
        assert added["call_id"] == "call_1"
        assert added["name"] == "f"
        assert added["status"] == "in_progress"
        assert events[6]["arguments"] == '{"a":1}'
        output = events[-1]["response"]["output"]
        assert [(o["call_id"], o["arguments"], o["status"]) for o in output] == [
            ("call_1", '{"a":1}', "completed"), ("call_2", "{}", "completed")]

    @pytest.mark.asyncio
    async def test_incremental_tool_arguments_accumulate(self):
        """
        What it does: Accumulates argument fragments sent per index.
        Purpose: Support incremental tool_call deltas, not just complete ones.
        """
        stream = agen([
            sse(chunk({"tool_calls": [{"index": 0, "id": "c", "function": {"name": "f", "arguments": '{"a"'}}]})),
            sse(chunk({"tool_calls": [{"index": 0, "function": {"arguments": ":1}"}}]})),
            sse(chunk({}, finish_reason="tool_calls")),
        ])
        events = parse_events(await collect(stream_chat_to_responses(stream, make_request())))
        assert sum(e["type"] == "response.output_item.added" for e in events) == 1
        assert [e["delta"] for e in events if e["type"] == "response.function_call_arguments.delta"] == ['{"a"', ":1}"]
        assert events[-1]["response"]["output"][0]["arguments"] == '{"a":1}'

    @pytest.mark.asyncio
    async def test_mixed_reasoning_text_tool_sequence(self):
        """
        What it does: Translates reasoning, then text, then a tool call.
        Purpose: Each item must be closed before the next opens, with correct output_index.
        """
        stream = agen([
            sse(chunk({"reasoning_content": "hmm"})),
            sse(chunk({"content": "Let me look"})),
            sse(chunk({"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "f", "arguments": "{}"}}]})),
            sse(chunk({}, finish_reason="tool_calls")),
            "data: [DONE]\n\n",
        ])
        events = parse_events(await collect(stream_chat_to_responses(stream, make_request())))
        assert event_types(events) == [
            "response.created", "response.in_progress",
            "response.output_item.added", "response.reasoning_summary_part.added",
            "response.reasoning_summary_text.delta",
            "response.reasoning_summary_text.done", "response.reasoning_summary_part.done",
            "response.output_item.done",
            "response.output_item.added", "response.content_part.added", "response.output_text.delta",
            "response.output_text.done", "response.content_part.done", "response.output_item.done",
            "response.output_item.added", "response.function_call_arguments.delta",
            "response.function_call_arguments.done", "response.output_item.done",
            "response.completed",
        ]
        added = [e for e in events if e["type"] == "response.output_item.added"]
        assert [e["output_index"] for e in added] == [0, 1, 2]
        assert [o["type"] for o in events[-1]["response"]["output"]] == ["reasoning", "message", "function_call"]

    @pytest.mark.asyncio
    async def test_length_finish_emits_incomplete(self):
        """
        What it does: Maps finish_reason=length in streaming.
        Purpose: Streaming must report truncation like non-streaming.
        """
        stream = agen([sse(chunk({"content": "x"})), sse(chunk({}, finish_reason="length"))])
        events = parse_events(await collect(stream_chat_to_responses(stream, make_request())))
        assert events[-1]["type"] == "response.incomplete"
        assert events[-1]["response"]["incomplete_details"] == {"reason": "max_output_tokens"}
        done = [e for e in events if e["type"] == "response.output_item.done"][0]
        assert done["item"]["status"] == "incomplete"

    @pytest.mark.asyncio
    async def test_upstream_error_emits_response_failed(self):
        """
        What it does: Converts a mid-stream exception into response.failed.
        Purpose: Clients must get a terminal event instead of a hung stream.
        """
        async def failing():
            yield sse(chunk({"content": "partial"}))
            yield "data: [DONE]\n\n"
            raise RuntimeError("Kiro connection reset")

        events = parse_events(await collect(stream_chat_to_responses(failing(), make_request())))
        assert events[-1]["type"] == "response.failed"
        assert events[-1]["response"]["status"] == "failed"
        assert events[-1]["response"]["error"]["message"] == "Kiro connection reset"
        assert "response.completed" not in event_types(events)

    @pytest.mark.asyncio
    async def test_http_exception_detail_is_used_in_failure(self):
        """
        What it does: Uses HTTPException.detail as failure message.
        Purpose: First-token timeout errors are HTTPExceptions with useful detail.
        """
        async def failing():
            raise HTTPException(status_code=504, detail="Model did not respond in time")
            yield  # pragma: no cover

        events = parse_events(await collect(stream_chat_to_responses(failing(), make_request())))
        assert event_types(events) == ["response.created", "response.in_progress", "response.failed"]
        assert events[-1]["response"]["error"]["message"] == "Model did not respond in time"

    @pytest.mark.asyncio
    async def test_bytes_split_frames_and_malformed_chunks(self):
        """
        What it does: Parses SSE split across byte chunks, skipping garbage.
        Purpose: The parser must not depend on chunk boundaries or crash on bad JSON.
        """
        payload = sse(chunk({"content": "ab"}))
        stream = agen([
            payload[:10].encode(), payload[10:].encode(),
            "data: {not json}\n\n", "data: [1, 2]\n\n", ": keepalive\n\n",
            sse(chunk({}, finish_reason="stop")).rstrip("\n"),
        ])
        events = parse_events(await collect(stream_chat_to_responses(stream, make_request())))
        assert events[-1]["type"] == "response.completed"
        assert events[-1]["response"]["output"][0]["content"][0]["text"] == "ab"

    @pytest.mark.asyncio
    async def test_empty_stream_completes_with_no_output(self):
        """
        What it does: Handles a stream with only [DONE].
        Purpose: Lifecycle events must still be complete.
        """
        events = parse_events(await collect(stream_chat_to_responses(agen(["data: [DONE]\n\n"]), make_request())))
        assert event_types(events) == ["response.created", "response.in_progress", "response.completed"]
        assert events[-1]["response"]["output"] == []

    @pytest.mark.asyncio
    async def test_chat_stream_is_closed(self):
        """
        What it does: Closes the upstream generator.
        Purpose: Upstream cleanup (http client close, debug flush) must run.
        """
        closed = {"value": False}

        async def upstream():
            try:
                yield "data: [DONE]\n\n"
            finally:
                closed["value"] = True

        await collect(stream_chat_to_responses(upstream(), make_request()))
        assert closed["value"] is True

    def test_finish_and_fail_are_idempotent(self):
        """
        What it does: Calls finish/fail twice.
        Purpose: Never emit two terminal events.
        """
        translator = ResponsesStreamTranslator(make_request())
        translator.start()
        assert len(translator.finish()) == 1
        assert translator.finish() == []
        assert translator.fail("x") == []

    def test_chunk_without_choices_only_records_usage(self):
        """
        What it does: Processes a usage-only chunk.
        Purpose: Usage from choice-less chunks must still reach response.completed.
        """
        translator = ResponsesStreamTranslator(make_request())
        assert translator.process_chunk({"choices": [], "usage": {"prompt_tokens": 9}}) == []
        final = translator.finish()[-1]
        assert final["response"]["usage"]["input_tokens"] == 9

    def test_format_sse_event(self):
        """
        What it does: Formats an SSE frame.
        Purpose: event: line must match data.type.
        """
        assert format_sse_event({"type": "a.b", "x": 1}) == 'event: a.b\ndata: {"type": "a.b", "x": 1}\n\n'
