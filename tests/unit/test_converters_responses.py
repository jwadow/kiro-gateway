# -*- coding: utf-8 -*-

"""
Unit tests for converters_responses module (OpenAI Responses API / Codex CLI).

Tests for Responses-specific conversion logic:
- Converting Responses `input` items to unified format
- Converting Responses tools (flat format) to unified format
- Reasoning effort -> thinking config
- Building Kiro payload end to end
"""

import json

import pytest

from kiro.converters_responses import (
    build_kiro_payload,
    convert_responses_input_to_unified,
    convert_responses_tools_to_unified,
    collect_unified_tools,
    collect_custom_tool_names,
    extract_thinking_config_from_responses,
    _normalize_content_parts,
)
from kiro.models_responses import ResponsesRequest, ResponsesTool


# ==================================================================================================
# convert_responses_input_to_unified
# ==================================================================================================

class TestConvertResponsesInput:
    """Tests for convert_responses_input_to_unified."""

    def test_plain_string_input_becomes_user_message(self):
        """
        What it does: A bare string `input` becomes a single user message.
        Purpose: Codex may send simple string prompts.
        """
        req = ResponsesRequest(model="claude-sonnet-4.5", input="Hello there")
        system, unified = convert_responses_input_to_unified(req)

        assert system == ""
        assert len(unified) == 1
        assert unified[0].role == "user"
        assert unified[0].content == "Hello there"

    def test_instructions_become_system_prompt(self):
        """
        What it does: `instructions` is extracted as the system prompt.
        Purpose: Responses uses instructions instead of a system message.
        """
        req = ResponsesRequest(
            model="m", instructions="You are Codex", input="hi"
        )
        system, unified = convert_responses_input_to_unified(req)

        assert system == "You are Codex"
        assert len(unified) == 1

    def test_message_items_with_typed_content_parts(self):
        """
        What it does: message items with input_text/output_text parts are normalized.
        Purpose: Responses content parts differ from Chat Completions.
        """
        req = ResponsesRequest(model="m", input=[
            {"type": "message", "role": "user",
             "content": [{"type": "input_text", "text": "question"}]},
            {"type": "message", "role": "assistant",
             "content": [{"type": "output_text", "text": "answer"}]},
        ])
        system, unified = convert_responses_input_to_unified(req)

        assert len(unified) == 2
        assert unified[0].role == "user"
        assert unified[1].role == "assistant"

    def test_system_and_developer_messages_fold_into_system_prompt(self):
        """
        What it does: system/developer input messages join the system prompt.
        Purpose: Kiro only supports user/assistant history.
        """
        req = ResponsesRequest(model="m", instructions="Base", input=[
            {"type": "message", "role": "developer",
             "content": [{"type": "input_text", "text": "Dev rule"}]},
            {"type": "message", "role": "user",
             "content": [{"type": "input_text", "text": "hi"}]},
        ])
        system, unified = convert_responses_input_to_unified(req)

        assert "Base" in system
        assert "Dev rule" in system
        assert len(unified) == 1
        assert unified[0].role == "user"

    def test_function_call_becomes_assistant_tool_call(self):
        """
        What it does: a function_call item becomes an assistant message with tool_calls.
        Purpose: Responses tool calls are top-level items.
        """
        req = ResponsesRequest(model="m", input=[
            {"type": "message", "role": "user",
             "content": [{"type": "input_text", "text": "run ls"}]},
            {"type": "function_call", "call_id": "call_1", "name": "shell",
             "arguments": '{"cmd":"ls"}'},
        ])
        system, unified = convert_responses_input_to_unified(req)

        assistant_msgs = [m for m in unified if m.role == "assistant"]
        assert len(assistant_msgs) == 1
        tc = assistant_msgs[0].tool_calls[0]
        assert tc["id"] == "call_1"
        assert tc["function"]["name"] == "shell"
        assert tc["function"]["arguments"] == '{"cmd":"ls"}'

    def test_function_call_output_becomes_user_tool_result(self):
        """
        What it does: a function_call_output item becomes a user message tool_result.
        Purpose: call_id must be preserved to pair with the tool call.
        """
        req = ResponsesRequest(model="m", input=[
            {"type": "function_call_output", "call_id": "call_1", "output": "file1.txt"},
        ])
        system, unified = convert_responses_input_to_unified(req)

        tr = unified[0].tool_results[0]
        assert tr["tool_use_id"] == "call_1"
        assert tr["content"] == "file1.txt"

    def test_reasoning_items_are_ignored(self):
        """
        What it does: reasoning items (rs_...) are dropped, not passed through.
        Purpose: Kiro has no encrypted reasoning; passing rs_ ids back errors.
        """
        req = ResponsesRequest(model="m", input=[
            {"type": "reasoning", "id": "rs_abc", "encrypted_content": "xxxx",
             "summary": []},
            {"type": "message", "role": "user",
             "content": [{"type": "input_text", "text": "hi"}]},
        ])
        system, unified = convert_responses_input_to_unified(req)

        assert len(unified) == 1
        assert unified[0].role == "user"

    def test_function_call_dict_arguments_serialized(self):
        """
        What it does: object arguments are serialized to a JSON string.
        Purpose: Some clients send arguments as objects, Kiro expects strings.
        """
        req = ResponsesRequest(model="m", input=[
            {"type": "function_call", "call_id": "c", "name": "f",
             "arguments": {"a": 1}},
        ])
        _, unified = convert_responses_input_to_unified(req)
        args = unified[0].tool_calls[0]["function"]["arguments"]
        assert json.loads(args) == {"a": 1}

    def test_custom_tool_call_wraps_freeform_input(self):
        """
        What it does: a custom_tool_call's freeform `input` is wrapped as
        {"input": "<raw text>"} in the unified tool_call arguments.
        Purpose: keep Kiro history consistent with the synthesized schema so a
        replayed exec call round-trips correctly.
        """
        from kiro.converters_responses import CUSTOM_TOOL_INPUT_KEY
        req = ResponsesRequest(model="m", input=[
            {"type": "custom_tool_call", "call_id": "ctc_1", "name": "exec",
             "input": 'print("hi")'},
        ])
        _, unified = convert_responses_input_to_unified(req)
        assistant = [m for m in unified if m.role == "assistant"]
        assert len(assistant) == 1
        tc = assistant[0].tool_calls[0]
        assert tc["id"] == "ctc_1"
        assert tc["function"]["name"] == "exec"
        assert json.loads(tc["function"]["arguments"]) == {CUSTOM_TOOL_INPUT_KEY: 'print("hi")'}

    def test_custom_tool_call_output_becomes_tool_result(self):
        """
        What it does: a custom_tool_call_output becomes a user tool_result.
        Purpose: exec results must pair back with the call_id.
        """
        req = ResponsesRequest(model="m", input=[
            {"type": "custom_tool_call_output", "call_id": "ctc_1", "output": "hi\n"},
        ])
        _, unified = convert_responses_input_to_unified(req)
        tr = unified[0].tool_results[0]
        assert tr["tool_use_id"] == "ctc_1"
        assert tr["content"] == "hi\n"


# ==================================================================================================
# _normalize_content_parts
# ==================================================================================================

class TestNormalizeContentParts:
    def test_input_image_becomes_image_url_block(self):
        """
        What it does: input_image with a data URL becomes an image_url block.
        Purpose: core extract_images_from_content understands image_url.
        """
        parts = _normalize_content_parts([
            {"type": "input_image", "image_url": "data:image/png;base64,ABC"},
        ])
        assert parts[0]["type"] == "image_url"
        assert parts[0]["image_url"]["url"] == "data:image/png;base64,ABC"

    def test_string_passthrough(self):
        assert _normalize_content_parts("hi") == "hi"

    def test_none_becomes_empty(self):
        assert _normalize_content_parts(None) == ""


# ==================================================================================================
# convert_responses_tools_to_unified
# ==================================================================================================

class TestConvertResponsesTools:
    def test_flat_function_tool(self):
        """
        What it does: flat-format function tool converts to a UnifiedTool.
        Purpose: Responses tools have no nested `function` object.
        """
        tools = [ResponsesTool(type="function", name="shell",
                               description="run", parameters={"type": "object"})]
        unified = convert_responses_tools_to_unified(tools)
        assert len(unified) == 1
        assert unified[0].name == "shell"
        assert unified[0].input_schema == {"type": "object"}

    def test_non_function_tools_skipped(self):
        """
        What it does: built-in tools (web_search etc.) are skipped.
        Purpose: Kiro only accepts custom function tools.
        """
        tools = [ResponsesTool(type="web_search"),
                 ResponsesTool(type="function", name="f")]
        unified = convert_responses_tools_to_unified(tools)
        assert len(unified) == 1
        assert unified[0].name == "f"

    def test_empty_returns_none(self):
        assert convert_responses_tools_to_unified(None) is None
        assert convert_responses_tools_to_unified([]) is None

    def test_namespace_tool_is_flattened(self):
        """
        What it does: a `namespace` tool's sub-tools are flattened by bare name.
        Purpose: Codex groups sub-agent tools under a namespace; the model calls
        them by bare name, so no prefix must be added.
        """
        tools = [{
            "type": "namespace",
            "name": "collaboration",
            "tools": [
                {"type": "function", "name": "spawn_agent",
                 "parameters": {"type": "object"}},
                {"type": "function", "name": "list_agents",
                 "parameters": {"type": "object"}},
            ],
        }]
        unified = convert_responses_tools_to_unified(tools)
        assert len(unified) == 2
        assert {t.name for t in unified} == {"spawn_agent", "list_agents"}

    def test_custom_grammar_tool_is_synthesized(self):
        """
        What it does: grammar-based `custom` tools (e.g. exec) are synthesized
        into a JSON-schema function with a single `input` string field.
        Purpose: Kiro only accepts JSON-schema functions; we wrap the freeform
        payload so the tool remains usable instead of being dropped.
        """
        from kiro.converters_responses import CUSTOM_TOOL_INPUT_KEY
        tools = [
            {"type": "custom", "name": "exec",
             "description": "Run JS",
             "format": {"type": "grammar", "syntax": "lark", "definition": "..."}},
            {"type": "function", "name": "wait", "parameters": {"type": "object"}},
        ]
        unified = convert_responses_tools_to_unified(tools)
        assert {t.name for t in unified} == {"exec", "wait"}
        exec_tool = next(t for t in unified if t.name == "exec")
        # synthesized schema: single required string field
        props = exec_tool.input_schema["properties"]
        assert CUSTOM_TOOL_INPUT_KEY in props
        assert props[CUSTOM_TOOL_INPUT_KEY]["type"] == "string"
        assert exec_tool.input_schema["required"] == [CUSTOM_TOOL_INPUT_KEY]
        # original description is preserved in the synthesized one
        assert "Run JS" in exec_tool.description

    def test_mixed_dicts_and_tool_objects(self):
        """
        What it does: raw dicts and ResponsesTool objects mix freely.
        Purpose: additional_tools carries raw dicts; top-level uses objects.
        """
        tools = [
            ResponsesTool(type="function", name="a", parameters={"type": "object"}),
            {"type": "function", "name": "b", "parameters": {"type": "object"}},
        ]
        unified = convert_responses_tools_to_unified(tools)
        assert {t.name for t in unified} == {"a", "b"}


# ==================================================================================================
# collect_unified_tools (Codex additional_tools support)
# ==================================================================================================

class TestCollectUnifiedTools:
    def test_additional_tools_item_is_collected(self):
        """
        What it does: tools embedded in an `additional_tools` input item are found.
        Purpose: Codex CLI does NOT use the top-level `tools` field - it embeds
        tools in input[0]. This is the root cause of "tool not found" in Codex.
        """
        req = ResponsesRequest(model="m", input=[
            {
                "type": "additional_tools",
                "role": "developer",
                "tools": [
                    {"type": "custom", "name": "exec",
                     "format": {"type": "grammar", "syntax": "lark", "definition": "x"}},
                    {"type": "function", "name": "wait",
                     "parameters": {"type": "object"}},
                    {"type": "function", "name": "request_user_input",
                     "parameters": {"type": "object"}},
                    {"type": "namespace", "name": "collaboration", "tools": [
                        {"type": "function", "name": "followup_task",
                         "parameters": {"type": "object"}},
                        {"type": "function", "name": "spawn_agent",
                         "parameters": {"type": "object"}},
                    ]},
                ],
            },
            {"type": "message", "role": "user",
             "content": [{"type": "input_text", "text": "hi"}]},
        ])
        unified = collect_unified_tools(req)
        # exec (custom) synthesized; + wait + request_user_input + 2 namespace = 5
        assert unified is not None
        names = {t.name for t in unified}
        assert names == {"exec", "wait", "request_user_input", "followup_task", "spawn_agent"}

    def test_top_level_and_additional_tools_merge(self):
        """
        What it does: tools from top-level `tools` and `additional_tools` combine.
        Purpose: don't lose either source.
        """
        req = ResponsesRequest(
            model="m",
            tools=[ResponsesTool(type="function", name="top",
                                 parameters={"type": "object"})],
            input=[{
                "type": "additional_tools", "role": "developer",
                "tools": [{"type": "function", "name": "embedded",
                           "parameters": {"type": "object"}}],
            }],
        )
        unified = collect_unified_tools(req)
        assert {t.name for t in unified} == {"top", "embedded"}

    def test_no_tools_returns_none(self):
        req = ResponsesRequest(model="m", input="hello")
        assert collect_unified_tools(req) is None


class TestCollectCustomToolNames:
    def test_finds_custom_tools_in_additional_tools(self):
        """
        What it does: custom tool names are collected from additional_tools,
        descending into namespaces; function tools are NOT included.
        Purpose: the streaming layer needs this set to emit custom_tool_call
        events for the right tools.
        """
        req = ResponsesRequest(model="m", input=[
            {"type": "additional_tools", "role": "developer", "tools": [
                {"type": "custom", "name": "exec", "format": {"type": "text"}},
                {"type": "function", "name": "wait", "parameters": {"type": "object"}},
                {"type": "namespace", "name": "ns", "tools": [
                    {"type": "custom", "name": "apply_patch", "format": {"type": "text"}},
                    {"type": "function", "name": "spawn_agent",
                     "parameters": {"type": "object"}},
                ]},
            ]},
        ])
        names = collect_custom_tool_names(req)
        assert names == {"exec", "apply_patch"}

    def test_empty_when_no_custom_tools(self):
        req = ResponsesRequest(model="m", input="hi")
        assert collect_custom_tool_names(req) == set()


# ==================================================================================================
# extract_thinking_config_from_responses
# ==================================================================================================

class TestThinkingConfig:
    def test_no_reasoning_uses_default(self):
        req = ResponsesRequest(model="m", input="x")
        cfg = extract_thinking_config_from_responses(req)
        assert cfg.enabled is True
        assert cfg.budget_tokens is None

    def test_effort_none_disables(self):
        req = ResponsesRequest(model="m", input="x", reasoning={"effort": "none"})
        cfg = extract_thinking_config_from_responses(req)
        assert cfg.enabled is False

    def test_effort_high_sets_budget(self):
        req = ResponsesRequest(model="m", input="x",
                               reasoning={"effort": "high"}, max_output_tokens=4096)
        cfg = extract_thinking_config_from_responses(req)
        assert cfg.enabled is True
        assert cfg.budget_tokens == int(4096 * 0.8)

    def test_unknown_effort_falls_back_to_default(self):
        req = ResponsesRequest(model="m", input="x", reasoning={"effort": "bogus"})
        cfg = extract_thinking_config_from_responses(req)
        assert cfg.enabled is True
        assert cfg.budget_tokens is None


# ==================================================================================================
# build_kiro_payload (end to end)
# ==================================================================================================

class TestBuildKiroPayload:
    def test_basic_payload_structure(self):
        """
        What it does: builds a valid Kiro payload from a simple request.
        Purpose: end-to-end sanity of the Responses adapter.
        """
        req = ResponsesRequest(model="claude-sonnet-4.5",
                               instructions="be brief", input="hello")
        payload = build_kiro_payload(req, "conv-1", "arn:test")

        assert "conversationState" in payload
        cs = payload["conversationState"]
        assert cs["conversationId"] == "conv-1"
        assert payload["profileArn"] == "arn:test"
        current = cs["currentMessage"]["userInputMessage"]
        # system prompt is folded into the current message when history is empty
        assert "be brief" in current["content"]

    def test_tool_round_trip_payload(self):
        """
        What it does: a full call/result round trip produces tools + toolResults.
        Purpose: verify tool calls survive conversion into Kiro format.
        """
        req = ResponsesRequest(model="m", input=[
            {"type": "message", "role": "user",
             "content": [{"type": "input_text", "text": "run ls"}]},
            {"type": "function_call", "call_id": "c1", "name": "shell",
             "arguments": '{"cmd":"ls"}'},
            {"type": "function_call_output", "call_id": "c1", "output": "a.txt"},
        ], tools=[ResponsesTool(type="function", name="shell",
                                parameters={"type": "object"})])
        payload = build_kiro_payload(req, "conv-1", "arn:test")

        body = json.dumps(payload)
        assert "shell" in body
        assert "toolResults" in body or "toolUses" in body

    def test_tool_choice_none_omits_tools_from_payload(self):
        """
        What it does: tool_choice=none removes declared tools from the Kiro request.
        Purpose: Responses `none` prohibits new tool calls; merely accepting the
        field while still advertising tools would violate that contract.
        """
        req = ResponsesRequest(
            model="m",
            input="Answer directly",
            tool_choice="none",
            tools=[ResponsesTool(
                type="function",
                name="shell",
                parameters={"type": "object"},
            )],
        )

        payload = build_kiro_payload(req, "conv-1", "arn:test")
        current = payload["conversationState"]["currentMessage"]["userInputMessage"]

        assert "userInputMessageContext" not in current
        assert "shell" not in json.dumps(payload)


# ==================================================================================================
# routes_responses helpers (#3 tool_choice, #5 fallback tokens, #6 error code)
# ==================================================================================================

class TestRouteHelpers:
    def test_error_response_code_is_null_not_http_int(self):
        """
        What it does: _error_response emits error.code = null (not the HTTP int).
        Purpose: OpenAI-style errors use string/null codes; HTTP status carries
        the numeric status. Strict-typed clients would mis-parse an int code.
        """
        import json as _json
        from kiro.routes_responses import _error_response
        resp = _error_response(400, "bad request")
        body = _json.loads(bytes(resp.body))
        assert resp.status_code == 400
        assert body["error"]["code"] is None
        assert body["error"]["message"] == "bad request"

    def test_tool_choice_auto_and_none_allowed(self):
        """auto / none / unset are implemented and therefore accepted."""
        from kiro.routes_responses import _unsupported_tool_choice_error
        assert _unsupported_tool_choice_error(None) is None
        assert _unsupported_tool_choice_error("auto") is None
        assert _unsupported_tool_choice_error("none") is None

    def test_tool_choice_required_rejected(self):
        """`required` forces a tool call Kiro cannot guarantee -> rejected."""
        from kiro.routes_responses import _unsupported_tool_choice_error
        msg = _unsupported_tool_choice_error("required")
        assert msg is not None and "not supported" in msg

    def test_tool_choice_specific_tool_rejected(self):
        """Forcing a named tool -> rejected."""
        from kiro.routes_responses import _unsupported_tool_choice_error
        msg = _unsupported_tool_choice_error({"type": "function", "name": "shell"})
        assert msg is not None
        assert "shell" in msg

    @pytest.mark.parametrize("field,value", [
        ("temperature", 0.5),
        ("top_p", 0.9),
        ("max_output_tokens", 1024),
    ])
    def test_unsupported_generation_parameters_are_rejected(self, field, value):
        """
        What it does: generation controls without Kiro equivalents return errors.
        Purpose: accepted parameters must not be silently discarded.
        """
        from kiro.routes_responses import _unsupported_generation_parameter_error
        req = ResponsesRequest(model="m", input="hello", **{field: value})

        message = _unsupported_generation_parameter_error(req)

        assert message is not None
        assert field in message

    def test_default_generation_parameters_are_allowed(self):
        """Absent optional generation controls require no rejection."""
        from kiro.routes_responses import _unsupported_generation_parameter_error
        req = ResponsesRequest(model="m", input="hello")
        assert _unsupported_generation_parameter_error(req) is None

    def test_tool_choice_none_omits_tools_from_tokenizer_input(self):
        """Fallback token counting matches the actual no-tools Kiro payload."""
        from kiro.routes_responses import _build_tokenizer_inputs
        req = ResponsesRequest(
            model="m",
            input="hello",
            tool_choice="none",
            tools=[ResponsesTool(type="function", name="shell")],
        )

        _messages, tools = _build_tokenizer_inputs(req)

        assert tools is None

    def test_fallback_tokenizer_includes_tool_history(self):
        """
        What it does: _build_tokenizer_inputs folds tool_calls/tool_results text
        into the per-message content used for fallback token counting.
        Purpose: multi-turn Codex tool conversations must not be undercounted when
        upstream context usage is missing.
        """
        from kiro.routes_responses import _build_tokenizer_inputs
        req = ResponsesRequest(model="m", input=[
            {"type": "function_call", "call_id": "c1", "name": "shell",
             "arguments": '{"cmd":"ls -la /var/log"}'},
            {"type": "function_call_output", "call_id": "c1",
             "output": "total 42 drwxr-xr-x syslog"},
        ])
        messages, _tools = _build_tokenizer_inputs(req)
        blob = "".join(m["content"] for m in messages)
        # tool name, arguments, and result content all present in counted text
        assert "shell" in blob
        assert "ls -la /var/log" in blob
        assert "syslog" in blob
