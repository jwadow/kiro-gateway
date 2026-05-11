# -*- coding: utf-8 -*-

"""
End-to-end simulation tests for file write tool flow.

Simulates the complete round-trip for file write operations as used by
Claude Code (Anthropic API) and OpenCode (OpenAI API):

  Turn 1: client sends user message + tool definitions
       → gateway builds Kiro payload with tools
       → Kiro streams tool_start/tool_input/tool_stop events
       → gateway parses tool call, emits to client

  Turn 2: client sends tool_result (file written successfully)
       → gateway converts tool_result to Kiro toolResults
       → NO thinking tags injected (fix for "Improperly formed request")
       → Kiro streams next assistant response
       → gateway emits to client

These tests exercise the two bugs that were fixed:
  Bug 1 (parsers.py): empty dict in tool_start corrupted JSON fragments
  Bug 2 (converters_core.py): thinking tags injected into tool_result messages
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from typing import AsyncGenerator

from kiro.parsers import AwsEventStreamParser
from kiro.converters_core import (
    UnifiedMessage,
    UnifiedTool,
    ThinkingConfig,
    build_kiro_payload,
)
from kiro.converters_openai import (
    convert_openai_messages_to_unified,
    convert_openai_tools_to_unified,
    build_kiro_payload as openai_build_kiro_payload,
)
from kiro.converters_anthropic import (
    convert_anthropic_messages,
    convert_anthropic_tools,
    anthropic_to_kiro,
)
from kiro.models_openai import ChatMessage, ChatCompletionRequest, Tool, ToolFunction
from kiro.models_anthropic import AnthropicMessagesRequest, AnthropicMessage, AnthropicTool


# ==================================================================================================
# Helpers: simulate Kiro SSE stream bytes for a tool call
# ==================================================================================================

def make_kiro_tool_stream(tool_name: str, tool_use_id: str, arguments: dict) -> bytes:
    """
    Build a minimal Kiro SSE byte stream that delivers a tool call via
    tool_start (empty input) + tool_input (JSON fragments) + tool_stop.

    This matches the real Kiro API protocol for file-write tools.
    """
    full_json = json.dumps(arguments)
    # Split into two fragments to exercise the concatenation path
    mid = len(full_json) // 2
    frag1 = full_json[:mid]
    frag2 = full_json[mid:]

    def esc(s: str) -> str:
        """Escape a string for embedding inside a JSON string value."""
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    events = (
        f'{{"name":"{tool_name}","toolUseId":"{tool_use_id}","input":{{}}}}'
        f'{{"input":"{esc(frag1)}"}}'
        f'{{"input":"{esc(frag2)}"}}'
        f'{{"stop":true}}'
        f'{{"contextUsagePercentage":10}}'
    )
    return events.encode()


def make_kiro_text_stream(text: str) -> bytes:
    """Build a minimal Kiro SSE byte stream that delivers plain text content."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return (
        f'{{"content":"{escaped}"}}'
        f'{{"contextUsagePercentage":5}}'
    ).encode()


# ==================================================================================================
# Test: Parser correctly assembles tool arguments from fragments (Bug 1)
# ==================================================================================================

class TestParserToolFragmentAssembly:
    """
    Verifies that AwsEventStreamParser correctly assembles tool arguments
    from tool_start (empty dict) + tool_input (string fragments).
    """

    def test_str_replace_based_edit_create(self):
        """
        Simulates Claude Code's str_replace_based_edit tool with a file create command.
        The tool_start carries input={} and fragments follow via tool_input events.
        """
        args = {
            "command": "create",
            "path": "/workspace/hello.py",
            "file_text": "def hello():\n    print('Hello, world!')\n\nhello()\n"
        }
        stream = make_kiro_tool_stream("str_replace_based_edit", "toolu_abc123", args)

        parser = AwsEventStreamParser()
        parser.feed(stream)
        tool_calls = parser.get_tool_calls()

        assert len(tool_calls) == 1
        tc = tool_calls[0]
        assert tc["function"]["name"] == "str_replace_based_edit"
        assert tc["id"] == "toolu_abc123"

        parsed_args = json.loads(tc["function"]["arguments"])
        assert parsed_args["command"] == "create"
        assert parsed_args["path"] == "/workspace/hello.py"
        assert "Hello, world!" in parsed_args["file_text"]

    def test_str_replace_based_edit_str_replace(self):
        """
        Simulates str_replace_based_edit with old_str/new_str (the most common
        file-edit operation in Claude Code).
        """
        args = {
            "command": "str_replace",
            "path": "/workspace/app.py",
            "old_str": "def old_function():\n    return 1",
            "new_str": "def new_function():\n    return 42\n\ndef helper():\n    pass"
        }
        stream = make_kiro_tool_stream("str_replace_based_edit", "toolu_edit01", args)

        parser = AwsEventStreamParser()
        parser.feed(stream)
        tool_calls = parser.get_tool_calls()

        assert len(tool_calls) == 1
        parsed = json.loads(tool_calls[0]["function"]["arguments"])
        assert parsed["command"] == "str_replace"
        assert "old_function" in parsed["old_str"]
        assert "new_function" in parsed["new_str"]

    def test_write_file_tool(self):
        """
        Simulates OpenCode's write_file tool with large content.
        """
        content = "import os\nimport sys\n\n" + ("x = 1\n" * 200)
        args = {"path": "/tmp/large_file.py", "content": content}
        stream = make_kiro_tool_stream("write_file", "call_wf001", args)

        parser = AwsEventStreamParser()
        parser.feed(stream)
        tool_calls = parser.get_tool_calls()

        assert len(tool_calls) == 1
        parsed = json.loads(tool_calls[0]["function"]["arguments"])
        assert parsed["path"] == "/tmp/large_file.py"
        assert parsed["content"] == content


# ==================================================================================================
# Test: Thinking tags NOT injected into tool_result messages (Bug 2)
# ==================================================================================================

class TestNoThinkingTagsInToolResultMessages:
    """
    Verifies that thinking tags are NOT injected when the current (last) message
    contains tool_results — which is the case after a file write tool completes.
    """

    def _build_payload_with_tool_result(self, thinking_enabled: bool, monkeypatch) -> dict:
        """Helper: build Kiro payload for Turn 2 (tool_result message is last)."""
        monkeypatch.setattr("kiro.converters_core.FAKE_REASONING_ENABLED", thinking_enabled)
        monkeypatch.setattr("kiro.converters_core.FAKE_REASONING_BUDGET_CAP", 0)

        messages = [
            UnifiedMessage(role="user", content="Create a Python file"),
            UnifiedMessage(
                role="assistant",
                content="",
                tool_calls=[{
                    "id": "toolu_abc",
                    "type": "function",
                    "function": {
                        "name": "str_replace_based_edit",
                        "arguments": '{"command":"create","path":"/foo.py","file_text":"x=1"}'
                    }
                }]
            ),
            UnifiedMessage(
                role="user",
                content="",
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "toolu_abc",
                    "content": "File created successfully at /foo.py"
                }]
            ),
        ]
        tools = [UnifiedTool(
            name="str_replace_based_edit",
            description="Edit files",
            input_schema={"type": "object", "properties": {}}
        )]
        result = build_kiro_payload(
            messages=messages,
            system_prompt="You are a coding assistant.",
            model_id="claude-sonnet-4.5",
            tools=tools,
            conversation_id="conv-test-001",
            profile_arn="",
            thinking_config=ThinkingConfig(enabled=thinking_enabled, budget_tokens=8000)
        )
        return result.payload

    def test_no_thinking_tags_when_thinking_enabled(self, monkeypatch):
        """
        With FAKE_REASONING_ENABLED=True, thinking tags must NOT appear in the
        tool_result message (Turn 2 of a file write flow).
        """
        payload = self._build_payload_with_tool_result(True, monkeypatch)
        current = payload["conversationState"]["currentMessage"]["userInputMessage"]

        assert "<thinking_mode>" not in current["content"], (
            "Thinking tags must not be injected into tool_result messages"
        )
        ctx = current.get("userInputMessageContext", {})
        assert "toolResults" in ctx, "toolResults must be present in context"
        assert ctx["toolResults"][0]["toolUseId"] == "toolu_abc"

    def test_tool_results_correctly_forwarded(self, monkeypatch):
        """
        The tool_result content must be forwarded to Kiro API correctly.
        """
        payload = self._build_payload_with_tool_result(False, monkeypatch)
        ctx = payload["conversationState"]["currentMessage"]["userInputMessage"].get(
            "userInputMessageContext", {}
        )
        assert ctx["toolResults"][0]["content"][0]["text"] == "File created successfully at /foo.py"

    def test_history_contains_tool_call(self, monkeypatch):
        """
        The assistant's tool call must appear in history (Turn 1 → history).
        """
        payload = self._build_payload_with_tool_result(False, monkeypatch)
        history = payload["conversationState"].get("history", [])
        assert len(history) >= 2  # user turn + assistant turn

        assistant_entry = next(
            (h for h in history if "assistantResponseMessage" in h), None
        )
        assert assistant_entry is not None
        tool_uses = assistant_entry["assistantResponseMessage"].get("toolUses", [])
        assert len(tool_uses) == 1
        assert tool_uses[0]["name"] == "str_replace_based_edit"


# ==================================================================================================
# Test: Full OpenAI-format round-trip (OpenCode)
# ==================================================================================================

class TestOpenCodeFileWriteRoundTrip:
    """
    Simulates the complete OpenCode file write flow using the OpenAI API path.

    Turn 1: user asks to create a file → model calls write_file tool
    Turn 2: tool result sent back → model responds with confirmation
    """

    def _make_turn1_request(self) -> ChatCompletionRequest:
        return ChatCompletionRequest(
            model="claude-sonnet-4-5",
            messages=[
                ChatMessage(role="user", content="Create /tmp/hello.py with print('hi')")
            ],
            tools=[Tool(
                type="function",
                function=ToolFunction(
                    name="write_file",
                    description="Write content to a file",
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"}
                        },
                        "required": ["path", "content"]
                    }
                )
            )]
        )

    def _make_turn2_request(self) -> ChatCompletionRequest:
        return ChatCompletionRequest(
            model="claude-sonnet-4-5",
            messages=[
                ChatMessage(role="user", content="Create /tmp/hello.py with print('hi')"),
                ChatMessage(
                    role="assistant",
                    content="",
                    tool_calls=[{
                        "id": "call_wf001",
                        "type": "function",
                        "function": {
                            "name": "write_file",
                            "arguments": '{"path":"/tmp/hello.py","content":"print(\'hi\')"}'
                        }
                    }]
                ),
                ChatMessage(
                    role="tool",
                    tool_call_id="call_wf001",
                    content="File written successfully to /tmp/hello.py"
                ),
            ],
            tools=[Tool(
                type="function",
                function=ToolFunction(
                    name="write_file",
                    description="Write content to a file",
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"}
                        },
                        "required": ["path", "content"]
                    }
                )
            )]
        )

    def test_turn1_payload_has_tools(self):
        """Turn 1: Kiro payload must include tool definitions."""
        req = self._make_turn1_request()
        payload = openai_build_kiro_payload(req, "conv-oc-001", "")

        current = payload["conversationState"]["currentMessage"]["userInputMessage"]
        ctx = current.get("userInputMessageContext", {})
        assert "tools" in ctx
        assert ctx["tools"][0]["toolSpecification"]["name"] == "write_file"

    def test_turn2_payload_has_tool_results_not_thinking_tags(self, monkeypatch):
        """
        Turn 2: Kiro payload must have toolResults and NO thinking tags.
        This is the critical fix — thinking tags in tool_result messages caused
        "Improperly formed request" errors from Kiro API.
        """
        monkeypatch.setattr("kiro.converters_core.FAKE_REASONING_ENABLED", True)
        monkeypatch.setattr("kiro.converters_core.FAKE_REASONING_BUDGET_CAP", 0)

        req = self._make_turn2_request()
        payload = openai_build_kiro_payload(req, "conv-oc-001", "")

        current = payload["conversationState"]["currentMessage"]["userInputMessage"]
        content = current["content"]
        ctx = current.get("userInputMessageContext", {})

        assert "<thinking_mode>" not in content, (
            "Thinking tags must NOT appear in tool_result message"
        )
        assert "toolResults" in ctx
        assert ctx["toolResults"][0]["toolUseId"] == "call_wf001"
        assert "successfully" in ctx["toolResults"][0]["content"][0]["text"]

    def test_turn2_history_has_assistant_tool_call(self):
        """Turn 2: history must contain the assistant's tool call from Turn 1."""
        req = self._make_turn2_request()
        payload = openai_build_kiro_payload(req, "conv-oc-001", "")

        history = payload["conversationState"].get("history", [])
        assistant_msgs = [h for h in history if "assistantResponseMessage" in h]
        assert len(assistant_msgs) >= 1

        tool_uses = assistant_msgs[-1]["assistantResponseMessage"].get("toolUses", [])
        assert len(tool_uses) == 1
        assert tool_uses[0]["name"] == "write_file"
        assert tool_uses[0]["input"]["path"] == "/tmp/hello.py"


# ==================================================================================================
# Test: Full Anthropic-format round-trip (Claude Code)
# ==================================================================================================

class TestClaudeCodeFileWriteRoundTrip:
    """
    Simulates the complete Claude Code file write flow using the Anthropic API path.

    Turn 1: user asks to create a file → model calls str_replace_based_edit
    Turn 2: tool_result sent back → model responds with confirmation
    """

    def _make_turn1_request(self) -> AnthropicMessagesRequest:
        return AnthropicMessagesRequest(
            model="claude-sonnet-4-5",
            max_tokens=4096,
            messages=[
                AnthropicMessage(role="user", content="Create /workspace/app.py")
            ],
            tools=[AnthropicTool(
                name="str_replace_based_edit",
                description="Edit files",
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "path": {"type": "string"},
                        "file_text": {"type": "string"}
                    },
                    "required": ["command", "path"]
                }
            )]
        )

    def _make_turn2_request(self) -> AnthropicMessagesRequest:
        return AnthropicMessagesRequest(
            model="claude-sonnet-4-5",
            max_tokens=4096,
            messages=[
                AnthropicMessage(role="user", content="Create /workspace/app.py"),
                AnthropicMessage(
                    role="assistant",
                    content=[{
                        "type": "tool_use",
                        "id": "toolu_cc001",
                        "name": "str_replace_based_edit",
                        "input": {
                            "command": "create",
                            "path": "/workspace/app.py",
                            "file_text": "print('hello')\n"
                        }
                    }]
                ),
                AnthropicMessage(
                    role="user",
                    content=[{
                        "type": "tool_result",
                        "tool_use_id": "toolu_cc001",
                        "content": "File created at /workspace/app.py"
                    }]
                ),
            ],
            tools=[AnthropicTool(
                name="str_replace_based_edit",
                description="Edit files",
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "path": {"type": "string"},
                        "file_text": {"type": "string"}
                    },
                    "required": ["command", "path"]
                }
            )]
        )

    def test_turn1_payload_has_tools(self):
        """Turn 1: Kiro payload must include tool definitions."""
        req = self._make_turn1_request()
        payload = anthropic_to_kiro(req, "conv-cc-001", "")

        current = payload["conversationState"]["currentMessage"]["userInputMessage"]
        ctx = current.get("userInputMessageContext", {})
        assert "tools" in ctx
        assert ctx["tools"][0]["toolSpecification"]["name"] == "str_replace_based_edit"

    def test_turn2_payload_has_tool_results_not_thinking_tags(self, monkeypatch):
        """
        Turn 2: Kiro payload must have toolResults and NO thinking tags.
        """
        monkeypatch.setattr("kiro.converters_core.FAKE_REASONING_ENABLED", True)
        monkeypatch.setattr("kiro.converters_core.FAKE_REASONING_BUDGET_CAP", 0)

        req = self._make_turn2_request()
        payload = anthropic_to_kiro(req, "conv-cc-001", "")

        current = payload["conversationState"]["currentMessage"]["userInputMessage"]
        content = current["content"]
        ctx = current.get("userInputMessageContext", {})

        assert "<thinking_mode>" not in content, (
            "Thinking tags must NOT appear in tool_result message"
        )
        assert "toolResults" in ctx
        assert ctx["toolResults"][0]["toolUseId"] == "toolu_cc001"
        assert "app.py" in ctx["toolResults"][0]["content"][0]["text"]

    def test_turn2_history_has_assistant_tool_use(self):
        """Turn 2: history must contain the assistant's tool_use from Turn 1."""
        req = self._make_turn2_request()
        payload = anthropic_to_kiro(req, "conv-cc-001", "")

        history = payload["conversationState"].get("history", [])
        assistant_msgs = [h for h in history if "assistantResponseMessage" in h]
        assert len(assistant_msgs) >= 1

        tool_uses = assistant_msgs[-1]["assistantResponseMessage"].get("toolUses", [])
        assert len(tool_uses) == 1
        assert tool_uses[0]["name"] == "str_replace_based_edit"
        assert tool_uses[0]["input"]["command"] == "create"
