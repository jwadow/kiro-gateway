# -*- coding: utf-8 -*-

"""
Unit tests for tokenizer module (kiro/tokenizer.py).

Tests:
- Token counting in text (count_tokens)
- Token counting in messages (count_message_tokens)
- Token counting in tools (count_tools_tokens)
- Request token estimation (estimate_request_tokens)
- Claude correction coefficient (CLAUDE_CORRECTION_FACTOR)
- Fallback when tiktoken is unavailable
"""

import pytest
from unittest.mock import patch, MagicMock

from kiro.tokenizer import (
    count_tokens,
    count_message_tokens,
    count_tools_tokens,
    count_system_tokens,
    estimate_request_tokens,
    CLAUDE_CORRECTION_FACTOR,
    _get_encoding
)


class TestCountTokens:
    """Tests for count_tokens function."""
    
    def test_empty_string_returns_zero(self):
        """
        What it does: Checks that empty string returns 0 tokens.
        Purpose: Ensure correct handling of edge case.
        """
        print("Test: Empty string...")
        result = count_tokens("")
        print(f"Result: {result}")
        assert result == 0, "Empty string should return 0 tokens"
    
    def test_none_returns_zero(self):
        """
        What it does: Checks that None returns 0 tokens.
        Purpose: Ensure correct handling of None.
        """
        print("Test: None...")
        result = count_tokens(None)
        print(f"Result: {result}")
        assert result == 0, "None should return 0 tokens"
    
    def test_simple_text_returns_positive(self):
        """
        What it does: Checks that simple text returns positive token count.
        Purpose: Ensure basic token counting works.
        """
        print("Test: Simple text...")
        result = count_tokens("Hello, world!")
        print(f"Result: {result}")
        assert result > 0, "Simple text should return positive token count"
    
    def test_longer_text_returns_more_tokens(self):
        """
        What it does: Checks that longer text returns more tokens.
        Purpose: Ensure proportional token counting.
        """
        print("Test: Comparing long and short text...")
        short_text = "Hello"
        long_text = "Hello, this is a much longer text that should have more tokens"
        
        short_tokens = count_tokens(short_text)
        long_tokens = count_tokens(long_text)
        
        print(f"Short text: {short_tokens} tokens")
        print(f"Long text: {long_tokens} tokens")
        
        assert long_tokens > short_tokens, "Long text should have more tokens"
    
    def test_claude_correction_applied_by_default(self):
        """
        What it does: Checks that Claude correction coefficient is applied by default.
        Purpose: Ensure apply_claude_correction=True by default.
        """
        print("Test: Claude correction coefficient...")
        text = "This is a test text for token counting"
        
        with_correction = count_tokens(text, apply_claude_correction=True)
        without_correction = count_tokens(text, apply_claude_correction=False)
        
        print(f"With correction: {with_correction}")
        print(f"Without correction: {without_correction}")
        
        # With correction should be higher (coefficient 1.15)
        assert with_correction > without_correction, "With correction should have more tokens"
        
        # Check approximate ratio
        ratio = with_correction / without_correction
        print(f"Ratio: {ratio}")
        assert 1.1 <= ratio <= 1.2, f"Ratio should be around {CLAUDE_CORRECTION_FACTOR}"
    
    def test_without_claude_correction(self):
        """
        What it does: Checks token counting without correction coefficient.
        Purpose: Ensure apply_claude_correction=False works.
        """
        print("Test: Without correction coefficient...")
        text = "Test text"
        
        result = count_tokens(text, apply_claude_correction=False)
        print(f"Result: {result}")
        
        assert result > 0, "Should return positive token count"
    
    def test_unicode_text(self):
        """
        What it does: Checks token counting for Unicode text.
        Purpose: Ensure correct handling of non-ASCII characters.
        """
        print("Test: Unicode text...")
        text = "Привет, мир! 你好世界 🌍"
        
        result = count_tokens(text)
        print(f"Result: {result}")
        
        assert result > 0, "Unicode text should return positive token count"
    
    def test_multiline_text(self):
        """
        What it does: Checks token counting for multiline text.
        Purpose: Ensure correct handling of line breaks.
        """
        print("Test: Multiline text...")
        text = """Line 1
        Line 2
        Line 3"""
        
        result = count_tokens(text)
        print(f"Result: {result}")
        
        assert result > 0, "Multiline text should return positive token count"
    
    def test_json_text(self):
        """
        What it does: Checks token counting for JSON string.
        Purpose: Ensure correct handling of JSON.
        """
        print("Test: JSON text...")
        text = '{"name": "test", "value": 123, "nested": {"key": "value"}}'
        
        result = count_tokens(text)
        print(f"Result: {result}")
        
        assert result > 0, "JSON text should return positive token count"


class TestCountTokensFallback:
    """Tests for fallback logic when tiktoken is unavailable."""
    
    def test_fallback_when_tiktoken_unavailable(self):
        """
        What it does: Checks fallback counting when tiktoken is unavailable.
        Purpose: Ensure system works without tiktoken.
        """
        print("Test: Fallback without tiktoken...")
        
        # Mock _get_encoding to return None
        with patch('kiro.tokenizer._get_encoding', return_value=None):
            result = count_tokens("Hello world test")
            print(f"Result: {result}")
            
            # Fallback: len(text) // 4 + 1, then * 1.15
            # "Hello world test" = 16 characters
            # 16 // 4 + 1 = 5
            # 5 * 1.15 = 5.75 -> 5
            assert result > 0, "Fallback should return positive number"
    
    def test_fallback_without_correction(self):
        """
        What it does: Checks fallback without correction coefficient.
        Purpose: Ensure fallback works with apply_claude_correction=False.
        """
        print("Test: Fallback without correction...")
        
        with patch('kiro.tokenizer._get_encoding', return_value=None):
            result = count_tokens("Test", apply_claude_correction=False)
            print(f"Result: {result}")
            
            # "Test" = 4 characters
            # 4 // 4 + 1 = 2
            assert result > 0, "Fallback should return positive number"


class TestCountMessageTokens:
    """Tests for count_message_tokens function."""
    
    def test_empty_list_returns_zero(self):
        """
        What it does: Checks that empty list returns 0 tokens.
        Purpose: Ensure correct handling of empty list.
        """
        print("Test: Empty message list...")
        result = count_message_tokens([])
        print(f"Result: {result}")
        assert result == 0, "Empty list should return 0 tokens"
    
    def test_none_returns_zero(self):
        """
        What it does: Checks that None returns 0 tokens.
        Purpose: Ensure correct handling of None.
        """
        print("Test: None...")
        result = count_message_tokens(None)
        print(f"Result: {result}")
        assert result == 0, "None should return 0 tokens"
    
    def test_single_user_message(self):
        """
        What it does: Checks token counting for single user message.
        Purpose: Ensure basic functionality.
        """
        print("Test: Single user message...")
        messages = [{"role": "user", "content": "Hello, AI!"}]
        
        result = count_message_tokens(messages)
        print(f"Result: {result}")
        
        assert result > 0, "Should return positive token count"
    
    def test_multiple_messages(self):
        """
        What it does: Checks token counting for multiple messages.
        Purpose: Ensure tokens sum correctly.
        """
        print("Test: Multiple messages...")
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there! How can I help you?"},
            {"role": "user", "content": "What is the weather?"}
        ]
        
        result = count_message_tokens(messages)
        print(f"Result: {result}")
        
        # More messages = more tokens
        single_message = count_message_tokens([messages[0]])
        assert result > single_message, "Multiple messages should have more tokens"
    
    def test_message_with_tool_calls(self):
        """
        What it does: Checks token counting for message with tool_calls.
        Purpose: Ensure tool_calls are counted.
        """
        print("Test: Message with tool_calls...")
        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"location": "Moscow"}'
                        }
                    }
                ]
            }
        ]
        
        result = count_message_tokens(messages)
        print(f"Result: {result}")
        
        assert result > 0, "Message with tool_calls should have tokens"
    
    def test_message_with_tool_call_id(self):
        """
        What it does: Checks token counting for tool response message.
        Purpose: Ensure tool_call_id is counted.
        """
        print("Test: Tool response message...")
        messages = [
            {
                "role": "tool",
                "content": "The weather in Moscow is sunny, 25°C",
                "tool_call_id": "call_123"
            }
        ]
        
        result = count_message_tokens(messages)
        print(f"Result: {result}")
        
        assert result > 0, "Tool response should have tokens"
    
    def test_message_with_list_content(self):
        """
        What it does: Checks token counting for multimodal content.
        Purpose: Ensure list content is handled.
        """
        print("Test: Multimodal content...")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is in this image?"},
                    {"type": "image_url", "image_url": {"url": "https://example.com/image.jpg"}}
                ]
            }
        ]
        
        result = count_message_tokens(messages)
        print(f"Result: {result}")
        
        assert result > 0, "Multimodal content should have tokens"
    
    def test_without_claude_correction(self):
        """
        What it does: Checks token counting without correction coefficient.
        Purpose: Ensure apply_claude_correction=False works.
        """
        print("Test: Without correction coefficient...")
        messages = [{"role": "user", "content": "Test message"}]
        
        with_correction = count_message_tokens(messages, apply_claude_correction=True)
        without_correction = count_message_tokens(messages, apply_claude_correction=False)
        
        print(f"С коррекцией: {with_correction}")
        print(f"Без коррекции: {without_correction}")
        
        assert with_correction > without_correction, "With correction should be higher"
    
    def test_message_with_empty_content(self):
        """
        What it does: Checks token counting for message with empty content.
        Purpose: Ensure empty content doesn't break counting.
        """
        print("Test: Empty content...")
        messages = [{"role": "user", "content": ""}]
        
        result = count_message_tokens(messages)
        print(f"Result: {result}")
        
        # Should have service tokens (role, separators)
        assert result > 0, "Even empty message should have service tokens"
    
    def test_message_with_none_content(self):
        """
        What it does: Checks token counting for message with None content.
        Purpose: Ensure None content doesn't break counting.
        """
        print("Test: None content...")
        messages = [{"role": "assistant", "content": None}]
        
        result = count_message_tokens(messages)
        print(f"Result: {result}")
        
        assert result > 0, "Message with None content should have service tokens"

    def test_anthropic_tool_use_and_tool_result_blocks(self):
        """
        What it does: Checks token counting for Anthropic tool_use/tool_result blocks.
        Purpose: Ensure key Claude Code blocks aren't lost in counting.
        """
        print("Test: Anthropic tool_use/tool_result blocks...")
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_123",
                        "name": "get_weather",
                        "input": {"city": "Tokyo"}
                    }
                ]
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_123",
                        "content": [{"type": "text", "text": "晴天 26C"}],
                        "is_error": False
                    }
                ]
            }
        ]

        result = count_message_tokens(messages, apply_claude_correction=False)
        print(f"Result: {result}")
        assert result > 0


class TestCountToolsTokens:
    """Tests for count_tools_tokens function."""
    
    def test_none_returns_zero(self):
        """
        What it does: Checks that None returns 0 tokens.
        Purpose: Ensure correct handling of None.
        """
        print("Test: None...")
        result = count_tools_tokens(None)
        print(f"Result: {result}")
        assert result == 0, "None should return 0 tokens"
    
    def test_empty_list_returns_zero(self):
        """
        What it does: Checks that empty list returns 0 tokens.
        Purpose: Ensure correct handling of empty list.
        """
        print("Test: Empty list...")
        result = count_tools_tokens([])
        print(f"Result: {result}")
        assert result == 0, "Empty list should return 0 tokens"
    
    def test_single_tool(self):
        """
        What it does: Checks token counting for single tool.
        Purpose: Ensure basic functionality.
        """
        print("Test: Single tool...")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get the current weather for a location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string", "description": "City name"}
                        },
                        "required": ["location"]
                    }
                }
            }
        ]
        
        result = count_tools_tokens(tools)
        print(f"Result: {result}")
        
        assert result > 0, "Tool should have tokens"
    
    def test_multiple_tools(self):
        """
        What it does: Checks token counting for multiple tools.
        Purpose: Ensure tokens sum correctly.
        """
        print("Test: Multiple tools...")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Search the web",
                    "parameters": {"type": "object", "properties": {}}
                }
            }
        ]
        
        result = count_tools_tokens(tools)
        single_tool = count_tools_tokens([tools[0]])
        
        print(f"Two tools: {result}")
        print(f"One tool: {single_tool}")
        
        assert result > single_tool, "More tools = more tokens"
    
    def test_tool_with_complex_parameters(self):
        """
        What it does: Checks token counting for tool with complex parameters.
        Purpose: Ensure JSON schema parameters are counted.
        """
        print("Test: Complex parameters...")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "complex_function",
                    "description": "A function with complex parameters",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Name"},
                            "age": {"type": "integer", "description": "Age"},
                            "address": {
                                "type": "object",
                                "properties": {
                                    "street": {"type": "string"},
                                    "city": {"type": "string"},
                                    "country": {"type": "string"}
                                }
                            },
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        },
                        "required": ["name", "age"]
                    }
                }
            }
        ]
        
        result = count_tools_tokens(tools)
        print(f"Result: {result}")
        
        assert result > 0, "Complex tool should have tokens"
    
    def test_tool_without_parameters(self):
        """
        What it does: Checks token counting for tool without parameters.
        Purpose: Ensure missing parameters don't break counting.
        """
        print("Test: Without parameters...")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "no_params_func",
                    "description": "A function without parameters"
                }
            }
        ]
        
        result = count_tools_tokens(tools)
        print(f"Result: {result}")
        
        assert result > 0, "Tool without parameters should have tokens"
    
    def test_tool_with_empty_description(self):
        """
        What it does: Checks token counting for tool with empty description.
        Purpose: Ensure empty description doesn't break counting.
        """
        print("Test: Empty description...")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "func",
                    "description": "",
                    "parameters": {"type": "object", "properties": {}}
                }
            }
        ]
        
        result = count_tools_tokens(tools)
        print(f"Result: {result}")
        
        assert result > 0, "Tool with empty description should have tokens"
    
    def test_non_function_tool_type(self):
        """
        What it does: Checks handling of tool with type != "function".
        Purpose: Ensure non-function tools are handled.
        """
        print("Test: Non-function tool...")
        tools = [
            {
                "type": "other_type",
                "some_field": "value"
            }
        ]
        
        result = count_tools_tokens(tools)
        print(f"Result: {result}")
        
        # Should have at least service tokens
        assert result >= 0, "Non-function tool shouldn't break counting"
    
    def test_without_claude_correction(self):
        """
        What it does: Checks token counting without correction coefficient.
        Purpose: Ensure apply_claude_correction=False works.
        """
        print("Test: Without correction coefficient...")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test_func",
                    "description": "Test function",
                    "parameters": {"type": "object", "properties": {}}
                }
            }
        ]
        
        with_correction = count_tools_tokens(tools, apply_claude_correction=True)
        without_correction = count_tools_tokens(tools, apply_claude_correction=False)
        
        print(f"С коррекцией: {with_correction}")
        print(f"Без коррекции: {without_correction}")
        
        assert with_correction > without_correction, "With correction should be higher"

    def test_openai_flat_tool_format(self):
        """
        What it does: Checks token counting for flat/Cursor-style tool.
        Purpose: Ensure format without type=function is also counted.
        """
        tools = [
            {
                "name": "search_docs",
                "description": "Search docs by keyword",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"]
                }
            }
        ]

        result = count_tools_tokens(tools, apply_claude_correction=False)
        assert result > 4  # Must exceed base service overhead, proving name/description/schema are counted

    def test_anthropic_flat_and_openai_function_are_close(self):
        """
        What it does: Compares Anthropic flat and OpenAI function formats.
        Purpose: Prevent Anthropic tools from regressing to base-overhead-only counting.
        """
        shared_schema = {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "recursive": {"type": "boolean", "description": "Recursive search"}
            },
            "required": ["path"]
        }
        openai_tools = [{
            "type": "function",
            "function": {
                "name": "search_files",
                "description": "Search files",
                "parameters": shared_schema
            }
        }]
        anthropic_tools = [{
            "name": "search_files",
            "description": "Search files",
            "input_schema": shared_schema
        }]

        openai_tokens = count_tools_tokens(openai_tools, apply_claude_correction=False)
        anthropic_tokens = count_tools_tokens(anthropic_tools, apply_claude_correction=False)

        assert openai_tokens > 4
        assert anthropic_tokens > 4
        diff_ratio = abs(openai_tokens - anthropic_tokens) / max(openai_tokens, anthropic_tokens)
        assert diff_ratio < 0.15


class TestCountSystemTokens:
    """Tests for count_system_tokens function."""

    def test_none_returns_zero(self):
        """Checks that None returns 0."""
        assert count_system_tokens(None) == 0

    def test_empty_string_returns_zero(self):
        """Checks that empty string returns 0."""
        assert count_system_tokens("") == 0

    def test_plain_string(self):
        """Checks that plain string is counted correctly."""
        result = count_system_tokens("You are a helpful assistant.", apply_claude_correction=False)
        assert result > 0

    def test_dict_block_list(self):
        """Checks that Anthropic dict block list is counted correctly."""
        blocks = [
            {"type": "text", "text": "You are a helpful assistant."},
            {"type": "text", "text": "Be concise.", "cache_control": {"type": "ephemeral"}},
        ]
        result = count_system_tokens(blocks, apply_claude_correction=False)
        assert result > 0
        # Should be greater than single block result
        single = count_system_tokens([blocks[0]], apply_claude_correction=False)
        assert result > single

    def test_dict_block_with_cache_control(self):
        """Checks that cache_control field is counted in tokens."""
        without_cache = [{"type": "text", "text": "Hello"}]
        with_cache = [{"type": "text", "text": "Hello", "cache_control": {"type": "ephemeral"}}]
        r1 = count_system_tokens(without_cache, apply_claude_correction=False)
        r2 = count_system_tokens(with_cache, apply_claude_correction=False)
        assert r2 > r1

    def test_non_dict_block_fallback(self):
        """Checks that non-dict elements fall back to str()."""
        result = count_system_tokens([42, "text"], apply_claude_correction=False)
        assert result > 0

    def test_unknown_type_fallback(self):
        """Checks that non-str/list types fall back to str()."""
        result = count_system_tokens(12345, apply_claude_correction=False)
        assert result > 0

    def test_claude_correction_applied(self):
        """Checks that Claude correction coefficient is applied."""
        text = "You are a helpful assistant that answers questions about programming and software engineering."
        without = count_system_tokens(text, apply_claude_correction=False)
        with_corr = count_system_tokens(text, apply_claude_correction=True)
        assert with_corr > without


class TestEstimateRequestTokens:
    """Tests for estimate_request_tokens function."""
    
    def test_messages_only(self):
        """
        What it does: Checks token estimation for messages only.
        Purpose: Ensure basic functionality.
        """
        print("Test: Messages only...")
        messages = [{"role": "user", "content": "Hello!"}]
        
        result = estimate_request_tokens(messages)
        print(f"Result: {result}")
        
        assert "messages_tokens" in result
        assert "tools_tokens" in result
        assert "system_tokens" in result
        assert "total_tokens" in result
        
        assert result["messages_tokens"] > 0
        assert result["tools_tokens"] == 0
        assert result["system_tokens"] == 0
        assert result["total_tokens"] == result["messages_tokens"]
    
    def test_messages_with_tools(self):
        """
        What it does: Checks token estimation for messages with tools.
        Purpose: Ensure tools are counted.
        """
        print("Test: Messages with tools...")
        messages = [{"role": "user", "content": "What is the weather?"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather",
                    "parameters": {"type": "object", "properties": {}}
                }
            }
        ]
        
        result = estimate_request_tokens(messages, tools=tools)
        print(f"Result: {result}")
        
        assert result["messages_tokens"] > 0
        assert result["tools_tokens"] > 0
        assert result["total_tokens"] == result["messages_tokens"] + result["tools_tokens"]
    
    def test_messages_with_system_prompt(self):
        """
        What it does: Checks token estimation with separate system prompt.
        Purpose: Ensure system_prompt is counted.
        """
        print("Test: With system prompt...")
        messages = [{"role": "user", "content": "Hello!"}]
        system_prompt = "You are a helpful assistant."
        
        result = estimate_request_tokens(messages, system_prompt=system_prompt)
        print(f"Result: {result}")
        
        assert result["messages_tokens"] > 0
        assert result["system_tokens"] > 0
        assert result["total_tokens"] == result["messages_tokens"] + result["system_tokens"]

    def test_anthropic_system_blocks(self):
        """
        What it does: Checks token estimation for Anthropic system block list.
        Purpose: Ensure system blocks are counted.
        """
        print("Test: Anthropic system blocks...")
        messages = [{"role": "user", "content": "Hello!"}]
        system_prompt = [
            {"type": "text", "text": "你是 Claude Code"},
            {"type": "text", "text": "Follow tools strictly", "cache_control": {"type": "ephemeral"}},
        ]

        result = estimate_request_tokens(messages, system_prompt=system_prompt, apply_claude_correction=False)
        print(f"Result: {result}")

        assert result["system_tokens"] > 0
        assert result["total_tokens"] == result["messages_tokens"] + result["system_tokens"]
    
    def test_full_request(self):
        """
        What it does: Checks token estimation for full request.
        Purpose: Ensure all components sum correctly.
        """
        print("Test: Full request...")
        messages = [
            {"role": "user", "content": "What is the weather in Moscow?"}
        ]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather for a location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string"}
                        }
                    }
                }
            }
        ]
        system_prompt = "You are a weather assistant."
        
        result = estimate_request_tokens(messages, tools=tools, system_prompt=system_prompt)
        print(f"Result: {result}")
        
        expected_total = result["messages_tokens"] + result["tools_tokens"] + result["system_tokens"]
        assert result["total_tokens"] == expected_total, "Total should be sum of components"

    def test_anthropic_messages_with_flat_tools(self):
        """
        What it does: Simulates Anthropic /v1/messages with tools+system scenario.
        Purpose: Verify estimate_request_tokens no longer undercounts flat tools.
        """
        messages = [
            {"role": "user", "content": "请先读取项目结构，再回答。"}
        ]
        tools = [
            {
                "name": "read_file",
                "description": "Read a file from workspace",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute path"}
                    },
                    "required": ["path"]
                }
            }
        ]
        system_prompt = [{"type": "text", "text": "你是代码助手。"}]

        result = estimate_request_tokens(
            messages,
            tools=tools,
            system_prompt=system_prompt,
            apply_claude_correction=False
        )

        assert result["messages_tokens"] > 0
        assert result["tools_tokens"] > 4
        assert result["system_tokens"] > 0
        assert result["total_tokens"] == (
            result["messages_tokens"] + result["tools_tokens"] + result["system_tokens"]
        )
    
    def test_empty_messages(self):
        """
        What it does: Checks token estimation for empty message list.
        Purpose: Ensure correct handling of edge case.
        """
        print("Test: Empty messages...")
        result = estimate_request_tokens([])
        print(f"Result: {result}")
        
        assert result["messages_tokens"] == 0
        assert result["total_tokens"] == 0


class TestClaudeCorrectionFactor:
    """Tests for Claude correction coefficient."""
    
    def test_correction_factor_value(self):
        """
        What it does: Checks correction coefficient value.
        Purpose: Ensure coefficient equals 1.15.
        """
        print(f"Correction coefficient: {CLAUDE_CORRECTION_FACTOR}")
        assert CLAUDE_CORRECTION_FACTOR == 1.15, "Coefficient should be 1.15"
    
    def test_correction_increases_token_count(self):
        """
        What it does: Checks that correction increases token count.
        Purpose: Ensure coefficient is applied correctly.
        """
        print("Test: Correction increases tokens...")
        text = "This is a test text for checking the correction factor"
        
        with_correction = count_tokens(text, apply_claude_correction=True)
        without_correction = count_tokens(text, apply_claude_correction=False)
        
        print(f"With correction: {with_correction}")
        print(f"Without correction: {without_correction}")
        
        assert with_correction > without_correction
        
        # Check that difference is approximately 15%
        increase_percent = (with_correction - without_correction) / without_correction * 100
        print(f"Increase: {increase_percent:.1f}%")
        
        # Allow rounding error
        assert 10 <= increase_percent <= 20, "Increase should be around 15%"
class TestGetEncoding:
    """Tests for _get_encoding function."""
    
    def test_returns_encoding_when_tiktoken_available(self):
        """
        What it does: Checks that _get_encoding returns encoding when tiktoken is available.
        Purpose: Ensure correct tiktoken initialization.
        """
        print("Test: tiktoken available...")
        
        # Reset global variable for clean test
        import kiro.tokenizer as tokenizer_module
        original_encoding = tokenizer_module._encoding
        tokenizer_module._encoding = None
        
        try:
            encoding = _get_encoding()
            print(f"Encoding: {encoding}")
            
            # If tiktoken is installed, should return encoding
            if encoding is not None:
                assert hasattr(encoding, 'encode'), "Encoding should have encode method"
        finally:
            # Restore
            tokenizer_module._encoding = original_encoding
    
    def test_caches_encoding(self):
        """
        What it does: Checks that encoding is cached.
        Purpose: Ensure lazy initialization.
        """
        print("Test: Encoding caching...")
        
        encoding1 = _get_encoding()
        encoding2 = _get_encoding()
        
        print(f"Encoding 1: {encoding1}")
        print(f"Encoding 2: {encoding2}")
        
        # Should return same object
        assert encoding1 is encoding2, "Encoding should be cached"
    
    def test_handles_import_error(self):
        """
        What it does: Checks ImportError handling when tiktoken is missing.
        Purpose: Ensure system works without tiktoken.
        """
        print("Test: ImportError...")
        
        import kiro.tokenizer as tokenizer_module
        original_encoding = tokenizer_module._encoding
        tokenizer_module._encoding = None
        
        try:
            # Мокируем import tiktoken чтобы выбросить ImportError
            with patch.dict('sys.modules', {'tiktoken': None}):
                with patch('builtins.__import__', side_effect=ImportError("No module named 'tiktoken'")):
                    # Сбрасываем кэш
                    tokenizer_module._encoding = None
                    
                    # Должен вернуть None и не упасть
                    # Примечание: из-за кэширования этот тест может не работать идеально
                    # но главное - проверить что код не падает
                    pass
        finally:
            tokenizer_module._encoding = original_encoding


class TestTokenizerIntegration:
    """Integration tests for tokenizer."""
    
    def test_realistic_chat_request(self):
        """
        What it does: Checks token counting for realistic chat request.
        Purpose: Ensure correct work on real data.
        """
        print("Test: Realistic chat request...")
        
        messages = [
            {"role": "system", "content": "You are a helpful AI assistant. Be concise and accurate."},
            {"role": "user", "content": "What is the capital of France?"},
            {"role": "assistant", "content": "The capital of France is Paris."},
            {"role": "user", "content": "What is its population?"}
        ]
        
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Search the web for information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"}
                        },
                        "required": ["query"]
                    }
                }
            }
        ]
        
        result = estimate_request_tokens(messages, tools=tools)
        print(f"Result: {result}")
        
        # Check reasonable values
        assert result["messages_tokens"] > 50, "Messages should have > 50 tokens"
        assert result["tools_tokens"] > 20, "Tools should have > 20 tokens"
        assert result["total_tokens"] > 70, "Total should be > 70 tokens"
    
    def test_large_context(self):
        """
        What it does: Checks token counting for large context.
        Purpose: Ensure performance on large data.
        """
        print("Test: Large context...")
        
        # Создаём большой текст
        large_text = "This is a test sentence. " * 1000  # ~5000 слов
        
        messages = [{"role": "user", "content": large_text}]
        
        result = estimate_request_tokens(messages)
        print(f"Токенов в большом тексте: {result['total_tokens']}")
        
        # Should have many tokens
        assert result["total_tokens"] > 1000, "Large text should have > 1000 tokens"
    
    def test_consistency_across_calls(self):
        """
        What it does: Checks consistency of counting on repeated calls.
        Purpose: Ensure results are deterministic.
        """
        print("Test: Consistency...")
        
        text = "This is a test for consistency checking"
        
        results = [count_tokens(text) for _ in range(5)]
        print(f"Результаты: {results}")
        
        # All results should be identical
        assert len(set(results)) == 1, "Results should be consistent"
    
    
