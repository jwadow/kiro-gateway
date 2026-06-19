# -*- coding: utf-8 -*-

"""
Regression tests for KIRO_API_KEY headless auth and Claude Code (MCP) compatibility.

Covers the behavior added for headless API-key authentication and the
compatibility fixes that let Claude Code drive the gateway:

- AuthType.API_KEY: key used directly as the bearer token, no expiry/refresh
- get_kiro_headers emits the "tokentype: API_KEY" header in API-key mode
- system messages inside messages[] are hoisted to the top-level system field
- unknown content blocks (server_tool_use / advisor_tool_result) are dropped
- tool names over Kiro's 64-char limit are aliased deterministically
- tool input-schema root is coerced to type "object"
- management host helper for API-key model discovery
"""

import pytest

from kiro.auth import KiroAuthManager, AuthType
from kiro.utils import get_kiro_headers
from kiro.config import get_kiro_management_host
from kiro.converters_core import (
    UnifiedTool,
    shorten_tool_name,
    build_tool_name_reverse_map,
    convert_tools_to_kiro_format,
)
from kiro.models_anthropic import (
    AnthropicMessage,
    AnthropicMessagesRequest,
    KNOWN_CONTENT_BLOCK_TYPES,
)


# =============================================================================
# API-key authentication
# =============================================================================

class TestApiKeyAuth:
    """KIRO_API_KEY is used directly as the bearer token (no exchange/refresh)."""

    def test_api_key_detected_as_auth_type(self):
        am = KiroAuthManager(api_key="ksk_testkey")
        assert am.auth_type == AuthType.API_KEY

    def test_api_key_takes_priority_over_refresh_token(self):
        am = KiroAuthManager(api_key="ksk_testkey", refresh_token="rt_should_be_ignored")
        assert am.auth_type == AuthType.API_KEY

    def test_api_key_never_expires(self):
        am = KiroAuthManager(api_key="ksk_testkey")
        assert am.is_token_expiring_soon() is False
        assert am.is_token_expired() is False

    @pytest.mark.asyncio
    async def test_get_access_token_returns_key_verbatim(self):
        am = KiroAuthManager(api_key="ksk_testkey")
        assert await am.get_access_token() == "ksk_testkey"

    @pytest.mark.asyncio
    async def test_force_refresh_is_noop_returns_key(self):
        am = KiroAuthManager(api_key="ksk_testkey")
        # force_refresh must not attempt a network refresh; it returns the key as-is
        assert await am.force_refresh() == "ksk_testkey"

    def test_api_key_uses_runtime_host(self):
        am = KiroAuthManager(api_key="ksk_testkey")
        assert am.api_host == "https://runtime.us-east-1.kiro.dev"

    def test_management_host_available(self):
        am = KiroAuthManager(api_key="ksk_testkey")
        assert am.management_host == "https://management.us-east-1.kiro.dev"

    def test_api_region_override(self):
        am = KiroAuthManager(api_key="ksk_testkey", api_region="eu-central-1")
        assert am.api_host == "https://runtime.eu-central-1.kiro.dev"
        assert am.management_host == "https://management.eu-central-1.kiro.dev"


class TestApiKeyHeaders:
    """get_kiro_headers adds the tokentype header only in API-key mode."""

    def test_api_key_mode_adds_tokentype_header(self):
        am = KiroAuthManager(api_key="ksk_testkey")
        headers = get_kiro_headers(am, "ksk_testkey")
        assert headers["Authorization"] == "Bearer ksk_testkey"
        assert headers.get("tokentype") == "API_KEY"

    def test_non_api_key_mode_has_no_tokentype_header(self):
        am = KiroAuthManager(refresh_token="rt_dummy")
        headers = get_kiro_headers(am, "sometoken")
        assert "tokentype" not in headers
        assert am.auth_type == AuthType.KIRO_DESKTOP


class TestManagementHost:
    """Management host helper used for API-key model discovery."""

    def test_management_host_template(self):
        assert get_kiro_management_host("us-east-1") == "https://management.us-east-1.kiro.dev"
        assert get_kiro_management_host("eu-central-1") == "https://management.eu-central-1.kiro.dev"


# =============================================================================
# System message hoisting
# =============================================================================

class TestSystemMessageHoist:
    """role=system messages in messages[] are moved to the top-level system field."""

    def test_hoist_system_message_from_array(self):
        req = AnthropicMessagesRequest.model_validate({
            "model": "claude-opus-4.8", "max_tokens": 100,
            "messages": [
                {"role": "user", "content": "ctx"},
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "hi"},
            ],
        })
        assert req.system == "You are helpful"
        assert [m.role for m in req.messages] == ["user", "user"]

    def test_hoist_merges_with_existing_system(self):
        req = AnthropicMessagesRequest.model_validate({
            "model": "x", "max_tokens": 10, "system": "BASE",
            "messages": [
                {"role": "system", "content": [{"type": "text", "text": "EXTRA"}]},
                {"role": "user", "content": "hi"},
            ],
        })
        assert req.system == "BASE\n\nEXTRA"

    def test_wellformed_request_untouched(self):
        req = AnthropicMessagesRequest.model_validate({
            "model": "x", "max_tokens": 10, "system": "BASE",
            "messages": [{"role": "user", "content": "hi"}],
        })
        assert req.system == "BASE"
        assert len(req.messages) == 1


# =============================================================================
# Unknown content block filtering
# =============================================================================

class TestUnknownContentBlocks:
    """Server-side content blocks the gateway doesn't understand are dropped."""

    def test_known_block_types_constant(self):
        assert KNOWN_CONTENT_BLOCK_TYPES == {
            "text", "thinking", "image",
            "tool_use", "tool_result", "tool_reference",
        }

    def test_drops_server_tool_use_and_advisor_result(self):
        msg = AnthropicMessage.model_validate({
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "x", "signature": "sig"},
                {"type": "text", "text": "hello"},
                {"type": "server_tool_use", "id": "srv_1", "name": "advisor", "input": {}},
                {"type": "advisor_tool_result", "tool_use_id": "srv_1",
                 "content": {"type": "advisor_tool_result_error", "error_code": "overloaded"}},
                {"type": "tool_use", "id": "tu_1", "name": "Bash", "input": {"command": "ls"}},
            ],
        })
        assert [b.type for b in msg.content] == ["thinking", "text", "tool_use"]

    def test_known_blocks_only_unchanged(self):
        msg = AnthropicMessage.model_validate({
            "role": "assistant",
            "content": [
                {"type": "text", "text": "a"},
                {"type": "tool_use", "id": "t1", "name": "x", "input": {}},
            ],
        })
        assert [b.type for b in msg.content] == ["text", "tool_use"]

    def test_string_content_unaffected(self):
        msg = AnthropicMessage.model_validate({"role": "user", "content": "plain"})
        assert msg.content == "plain"

    def test_full_request_with_server_blocks_parses(self):
        req = AnthropicMessagesRequest.model_validate({
            "model": "claude-opus-4.8", "max_tokens": 50,
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": [
                    {"type": "text", "text": "ok"},
                    {"type": "server_tool_use", "id": "s1", "name": "advisor", "input": {}},
                ]},
                {"role": "user", "content": "go"},
            ],
        })
        assert [b.type for b in req.messages[1].content] == ["text"]


# =============================================================================
# Tool name aliasing (Kiro 64-char limit)
# =============================================================================

class TestToolNameAliasing:
    """Tool names over 64 chars are aliased deterministically and reversibly."""

    LONG = "mcp__plugin_cloudflare_cloudflare_observability__complete_authentication"  # 72 chars

    def test_short_name_unchanged(self):
        assert shorten_tool_name("get_weather") == "get_weather"

    def test_boundary_64_unchanged_65_shortened(self):
        name_64 = "a" * 64
        name_65 = "a" * 65
        assert shorten_tool_name(name_64) == name_64
        assert shorten_tool_name(name_65) != name_65
        assert len(shorten_tool_name(name_65)) == 64

    def test_long_name_becomes_64_chars(self):
        alias = shorten_tool_name(self.LONG)
        assert len(alias) == 64

    def test_alias_is_deterministic(self):
        assert shorten_tool_name(self.LONG) == shorten_tool_name(self.LONG)

    def test_alias_charset_is_safe(self):
        import re
        assert re.fullmatch(r"[A-Za-z0-9_-]+", shorten_tool_name(self.LONG))

    def test_reverse_map_round_trips(self):
        rmap = build_tool_name_reverse_map([self.LONG, "short_tool"])
        alias = shorten_tool_name(self.LONG)
        assert rmap[alias] == self.LONG
        # short names that didn't change are not in the reverse map
        assert "short_tool" not in rmap

    def test_kiro_payload_uses_aliased_name(self):
        # Aliasing happens in build_kiro_payload (which renames tools before
        # convert_tools_to_kiro_format), not in convert_tools_to_kiro_format itself.
        from kiro.converters_core import (
            build_kiro_payload, UnifiedMessage, ThinkingConfig,
        )
        tool = UnifiedTool(
            name=self.LONG, description="d",
            input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
        )
        result = build_kiro_payload(
            messages=[UnifiedMessage(role="user", content="hi")],
            system_prompt="",
            model_id="claude-opus-4.8",
            tools=[tool],
            conversation_id="conv-1",
            profile_arn="",
            thinking_config=ThinkingConfig(enabled=False, budget_tokens=None),
        )
        tools_in_payload = (
            result.payload["conversationState"]["currentMessage"]
            ["userInputMessage"]["userInputMessageContext"]["tools"]
        )
        spec = tools_in_payload[0]["toolSpecification"]
        assert spec["name"] == shorten_tool_name(self.LONG)
        assert len(spec["name"]) == 64


# =============================================================================
# Tool input-schema root coercion
# =============================================================================

class TestToolSchemaCoercion:
    """Tool input-schema root is always an object schema (Kiro/Bedrock requirement)."""

    def _root(self, input_schema):
        tool = UnifiedTool(name="t", description="d", input_schema=input_schema)
        return convert_tools_to_kiro_format([tool])[0]["toolSpecification"]["inputSchema"]["json"]

    def test_empty_schema_coerced(self):
        j = self._root({})
        assert j["type"] == "object"
        assert j["properties"] == {}

    def test_none_schema_coerced(self):
        j = self._root(None)
        assert j["type"] == "object"
        assert "properties" in j

    def test_missing_type_coerced(self):
        j = self._root({"properties": {"x": {"type": "string"}}})
        assert j["type"] == "object"
        assert "x" in j["properties"]

    def test_valid_object_schema_preserved(self):
        j = self._root({
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": ["x"],
        })
        assert j["type"] == "object"
        assert j["required"] == ["x"]
        assert "x" in j["properties"]
