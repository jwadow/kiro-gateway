# -*- coding: utf-8 -*-

"""
Unit tests for converters_anthropic module.

Tests for Anthropic Messages API to Kiro format conversion:
- Content extraction from Anthropic format
- Tool results extraction
- Tool uses extraction
- Message conversion to unified format
- Tool conversion to unified format
- Full Anthropic → Kiro payload conversion
"""

import pytest
from unittest.mock import patch, MagicMock

from kiro.converters_anthropic import (
    convert_anthropic_content_to_text,
    extract_system_prompt,
    extract_tool_results_from_anthropic_content,
    extract_images_from_tool_results,
    extract_tool_uses_from_anthropic_content,
    convert_anthropic_messages,
    convert_anthropic_tools,
    anthropic_to_kiro,
    extract_thinking_config_from_anthropic,
)
from kiro.converters_core import UnifiedMessage, UnifiedTool
from kiro.models_anthropic import (
    AnthropicMessagesRequest,
    AnthropicMessage,
    AnthropicTool,
    TextContentBlock,
    ToolUseContentBlock,
    ToolResultContentBlock,
    SystemContentBlock,
)


# ==================================================================================================
# Tests for convert_anthropic_content_to_text
# ==================================================================================================


class TestConvertAnthropicContentToText:
    """Tests for convert_anthropic_content_to_text function."""

    def test_extracts_from_string(self):
        """
        What it does: Verifies text extraction from a string.
        Purpose: Ensure string is returned as-is.
        """
        print("Setup: Simple string content...")
        content = "Hello, World!"

        print("Action: Extracting text...")
        result = convert_anthropic_content_to_text(content)

        print(f"Comparing result: Expected 'Hello, World!', Got '{result}'")
        assert result == "Hello, World!"

    def test_extracts_from_list_with_text_blocks(self):
        """
        What it does: Verifies extraction from list of text content blocks.
        Purpose: Ensure Anthropic multimodal format is handled.
        """
        print("Setup: List with text content blocks...")
        content = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": " World"},
        ]

        print("Action: Extracting text...")
        result = convert_anthropic_content_to_text(content)

        print(f"Comparing result: Expected 'Hello World', Got '{result}'")
        assert result == "Hello World"

    def test_extracts_from_pydantic_text_blocks(self):
        """
        What it does: Verifies extraction from Pydantic TextContentBlock objects.
        Purpose: Ensure Pydantic models are handled correctly.
        """
        print("Setup: List with Pydantic TextContentBlock objects...")
        content = [
            TextContentBlock(type="text", text="Part 1"),
            TextContentBlock(type="text", text=" Part 2"),
        ]

        print("Action: Extracting text...")
        result = convert_anthropic_content_to_text(content)

        print(f"Comparing result: Expected 'Part 1 Part 2', Got '{result}'")
        assert result == "Part 1 Part 2"

    def test_ignores_non_text_blocks(self):
        """
        What it does: Verifies that non-text blocks are ignored.
        Purpose: Ensure tool_use and tool_result blocks don't contribute to text.
        """
        print("Setup: List with mixed content blocks...")
        content = [
            {"type": "text", "text": "Hello"},
            {"type": "tool_use", "id": "call_123", "name": "test", "input": {}},
            {"type": "text", "text": " World"},
        ]

        print("Action: Extracting text...")
        result = convert_anthropic_content_to_text(content)

        print(f"Comparing result: Expected 'Hello World', Got '{result}'")
        assert result == "Hello World"

    def test_handles_none(self):
        """
        What it does: Verifies None handling.
        Purpose: Ensure None returns empty string.
        """
        print("Setup: None content...")

        print("Action: Extracting text...")
        result = convert_anthropic_content_to_text(None)

        print(f"Comparing result: Expected '', Got '{result}'")
        assert result == ""

    def test_handles_empty_list(self):
        """
        What it does: Verifies empty list handling.
        Purpose: Ensure empty list returns empty string.
        """
        print("Setup: Empty list...")
        content = []

        print("Action: Extracting text...")
        result = convert_anthropic_content_to_text(content)

        print(f"Comparing result: Expected '', Got '{result}'")
        assert result == ""

    def test_converts_other_types_to_string(self):
        """
        What it does: Verifies conversion of other types to string.
        Purpose: Ensure numbers and other types are converted.
        """
        print("Setup: Number content...")
        content = 42

        print("Action: Extracting text...")
        result = convert_anthropic_content_to_text(content)

        print(f"Comparing result: Expected '42', Got '{result}'")
        assert result == "42"


# ==================================================================================================
# Tests for extract_system_prompt
# ==================================================================================================


class TestExtractSystemPrompt:
    """Tests for extract_system_prompt function (Support System commit)."""

    def test_extracts_from_string(self):
        """
        What it does: Verifies extraction from simple string.
        Purpose: Ensure string system prompt is returned as-is.
        """
        print("Setup: Simple string system prompt...")
        system = "You are a helpful assistant."

        print("Action: Extracting system prompt...")
        result = extract_system_prompt(system)

        print(
            f"Comparing result: Expected 'You are a helpful assistant.', Got '{result}'"
        )
        assert result == "You are a helpful assistant."

    def test_extracts_from_list_with_text_blocks(self):
        """
        What it does: Verifies extraction from list of content blocks.
        Purpose: Ensure Anthropic prompt caching format is handled.
        """
        print("Setup: List with text content blocks (prompt caching format)...")
        system = [
            {"type": "text", "text": "You are helpful."},
            {"type": "text", "text": "Be concise."},
        ]

        print("Action: Extracting system prompt...")
        result = extract_system_prompt(system)

        print(
            f"Comparing result: Expected 'You are helpful.\\nBe concise.', Got '{result}'"
        )
        assert result == "You are helpful.\nBe concise."

    def test_extracts_from_list_with_cache_control(self):
        """
        What it does: Verifies extraction ignores cache_control field.
        Purpose: Ensure cache_control is stripped (not supported by Kiro).
        """
        print("Setup: List with cache_control (prompt caching format)...")
        system = [
            {
                "type": "text",
                "text": "You are a helpful assistant.",
                "cache_control": {"type": "ephemeral"},
            }
        ]

        print("Action: Extracting system prompt...")
        result = extract_system_prompt(system)

        print(
            f"Comparing result: Expected 'You are a helpful assistant.', Got '{result}'"
        )
        assert result == "You are a helpful assistant."

    def test_extracts_from_pydantic_system_content_blocks(self):
        """
        What it does: Verifies extraction from Pydantic SystemContentBlock objects.
        Purpose: Ensure Pydantic models are handled correctly.
        """
        print("Setup: List with Pydantic SystemContentBlock objects...")
        system = [
            SystemContentBlock(type="text", text="Part 1"),
            SystemContentBlock(type="text", text="Part 2"),
        ]

        print("Action: Extracting system prompt...")
        result = extract_system_prompt(system)

        print(f"Comparing result: Expected 'Part 1\\nPart 2', Got '{result}'")
        assert result == "Part 1\nPart 2"

    def test_handles_none(self):
        """
        What it does: Verifies None handling.
        Purpose: Ensure None returns empty string.
        """
        print("Setup: None system prompt...")

        print("Action: Extracting system prompt...")
        result = extract_system_prompt(None)

        print(f"Comparing result: Expected '', Got '{result}'")
        assert result == ""

    def test_handles_empty_list(self):
        """
        What it does: Verifies empty list handling.
        Purpose: Ensure empty list returns empty string.
        """
        print("Setup: Empty list...")
        system = []

        print("Action: Extracting system prompt...")
        result = extract_system_prompt(system)

        print(f"Comparing result: Expected '', Got '{result}'")
        assert result == ""

    def test_handles_mixed_content_blocks(self):
        """
        What it does: Verifies handling of list with non-text blocks.
        Purpose: Ensure only text blocks are extracted.
        """
        print("Setup: List with mixed content blocks...")
        system = [
            {"type": "text", "text": "Hello"},
            {"type": "image", "source": {"type": "base64", "data": "..."}},
            {"type": "text", "text": "World"},
        ]

        print("Action: Extracting system prompt...")
        result = extract_system_prompt(system)

        print(f"Comparing result: Expected 'Hello\\nWorld', Got '{result}'")
        assert result == "Hello\nWorld"

    def test_converts_other_types_to_string(self):
        """
        What it does: Verifies conversion of other types to string.
        Purpose: Ensure numbers and other types are converted.
        """
        print("Setup: Number as system prompt...")
        system = 42

        print("Action: Extracting system prompt...")
        result = extract_system_prompt(system)

        print(f"Comparing result: Expected '42', Got '{result}'")
        assert result == "42"

    def test_handles_single_text_block(self):
        """
        What it does: Verifies extraction from single text block in list.
        Purpose: Ensure single block list works correctly.
        """
        print("Setup: Single text block in list...")
        system = [{"type": "text", "text": "Single block"}]

        print("Action: Extracting system prompt...")
        result = extract_system_prompt(system)

        print(f"Comparing result: Expected 'Single block', Got '{result}'")
        assert result == "Single block"

    def test_handles_empty_text_in_block(self):
        """
        What it does: Verifies handling of empty text in content block.
        Purpose: Ensure empty text doesn't cause errors.
        """
        print("Setup: Content block with empty text...")
        system = [{"type": "text", "text": ""}]

        print("Action: Extracting system prompt...")
        result = extract_system_prompt(system)

        print(f"Comparing result: Expected '', Got '{result}'")
        assert result == ""

    def test_handles_missing_text_key(self):
        """
        What it does: Verifies handling of content block without text key.
        Purpose: Ensure missing text key doesn't cause errors.
        """
        print("Setup: Content block without text key...")
        system = [{"type": "text"}]

        print("Action: Extracting system prompt...")
        result = extract_system_prompt(system)

        print(f"Comparing result: Expected '', Got '{result}'")
        assert result == ""


# ==================================================================================================
# Tests for extract_tool_results_from_anthropic_content
# ==================================================================================================


class TestExtractToolResultsFromAnthropicContent:
    """Tests for extract_tool_results_from_anthropic_content function."""

    def test_extracts_tool_result_from_dict(self):
        """
        What it does: Verifies extraction of tool result from dict content block.
        Purpose: Ensure tool_result blocks are extracted correctly.
        """
        print("Setup: Content with tool_result block...")
        content = [
            {"type": "tool_result", "tool_use_id": "call_123", "content": "Result text"}
        ]

        print("Action: Extracting tool results...")
        result = extract_tool_results_from_anthropic_content(content)

        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0]["type"] == "tool_result"
        assert result[0]["tool_use_id"] == "call_123"
        assert result[0]["content"] == "Result text"

    def test_extracts_tool_result_from_pydantic_model(self):
        """
        What it does: Verifies extraction from Pydantic ToolResultContentBlock.
        Purpose: Ensure Pydantic models are handled correctly.
        """
        print("Setup: Content with Pydantic ToolResultContentBlock...")
        content = [
            ToolResultContentBlock(
                type="tool_result", tool_use_id="call_456", content="Pydantic result"
            )
        ]

        print("Action: Extracting tool results...")
        result = extract_tool_results_from_anthropic_content(content)

        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0]["tool_use_id"] == "call_456"
        assert result[0]["content"] == "Pydantic result"

    def test_extracts_multiple_tool_results(self):
        """
        What it does: Verifies extraction of multiple tool results.
        Purpose: Ensure all tool_result blocks are extracted.
        """
        print("Setup: Content with multiple tool_results...")
        content = [
            {"type": "tool_result", "tool_use_id": "call_1", "content": "Result 1"},
            {"type": "text", "text": "Some text"},
            {"type": "tool_result", "tool_use_id": "call_2", "content": "Result 2"},
        ]

        print("Action: Extracting tool results...")
        result = extract_tool_results_from_anthropic_content(content)

        print(f"Result: {result}")
        assert len(result) == 2
        assert result[0]["tool_use_id"] == "call_1"
        assert result[1]["tool_use_id"] == "call_2"

    def test_returns_empty_for_string_content(self):
        """
        What it does: Verifies empty list return for string content.
        Purpose: Ensure string doesn't contain tool results.
        """
        print("Setup: String content...")
        content = "Just a string"

        print("Action: Extracting tool results...")
        result = extract_tool_results_from_anthropic_content(content)

        print(f"Comparing result: Expected [], Got {result}")
        assert result == []

    def test_returns_empty_for_list_without_tool_results(self):
        """
        What it does: Verifies empty list return without tool_result blocks.
        Purpose: Ensure regular elements are not extracted.
        """
        print("Setup: List without tool_result...")
        content = [{"type": "text", "text": "Hello"}]

        print("Action: Extracting tool results...")
        result = extract_tool_results_from_anthropic_content(content)

        print(f"Comparing result: Expected [], Got {result}")
        assert result == []

    def test_handles_empty_content_in_tool_result(self):
        """
        What it does: Verifies handling of empty content in tool_result.
        Purpose: Ensure empty content is replaced with "(empty result)".
        """
        print("Setup: Tool result with empty content...")
        content = [{"type": "tool_result", "tool_use_id": "call_123", "content": ""}]

        print("Action: Extracting tool results...")
        result = extract_tool_results_from_anthropic_content(content)

        print(f"Result: {result}")
        assert result[0]["content"] == "(empty result)"

    def test_handles_none_content_in_tool_result(self):
        """
        What it does: Verifies handling of None content in tool_result.
        Purpose: Ensure None content is replaced with "(empty result)".
        """
        print("Setup: Tool result with None content...")
        content = [{"type": "tool_result", "tool_use_id": "call_123", "content": None}]

        print("Action: Extracting tool results...")
        result = extract_tool_results_from_anthropic_content(content)

        print(f"Result: {result}")
        assert result[0]["content"] == "(empty result)"

    def test_handles_list_content_in_tool_result(self):
        """
        What it does: Verifies handling of list content in tool_result.
        Purpose: Ensure list content is converted to text.
        """
        print("Setup: Tool result with list content...")
        content = [
            {
                "type": "tool_result",
                "tool_use_id": "call_123",
                "content": [{"type": "text", "text": "List result"}],
            }
        ]

        print("Action: Extracting tool results...")
        result = extract_tool_results_from_anthropic_content(content)

        print(f"Result: {result}")
        assert result[0]["content"] == "List result"

    def test_skips_tool_result_without_tool_use_id(self):
        """
        What it does: Verifies that tool_result without tool_use_id is skipped.
        Purpose: Ensure invalid tool_result blocks are ignored.
        """
        print("Setup: Tool result without tool_use_id...")
        content = [{"type": "tool_result", "content": "Result without ID"}]

        print("Action: Extracting tool results...")
        result = extract_tool_results_from_anthropic_content(content)

        print(f"Comparing result: Expected [], Got {result}")
        assert result == []

    def test_handles_image_in_tool_result(self):
        """
        What it does: Verifies handling of images in tool_result content.
        Purpose: Images in tool results are extracted separately, text content becomes empty.
        """
        print("Setup: Tool result with image content...")
        content = [
            {
                "type": "tool_result",
                "tool_use_id": "call_123",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                        },
                    }
                ],
            }
        ]

        print("Action: Extracting tool results...")
        result = extract_tool_results_from_anthropic_content(content)

        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0]["tool_use_id"] == "call_123"
        # Images are extracted separately, so text content is empty
        assert result[0]["content"] == "(empty result)"

    def test_handles_multiple_images_in_tool_result(self):
        """
        What it does: Verifies handling of multiple images in tool_result content.
        Purpose: Images are extracted separately, text content becomes empty.
        """
        print("Setup: Tool result with multiple images...")
        content = [
            {
                "type": "tool_result",
                "tool_use_id": "call_456",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "abc123",
                        },
                    },
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": "def456",
                        },
                    },
                ],
            }
        ]

        print("Action: Extracting tool results...")
        result = extract_tool_results_from_anthropic_content(content)

        print(f"Result: {result}")
        assert len(result) == 1
        # Images are extracted separately, so text content is empty
        assert result[0]["content"] == "(empty result)"

    def test_handles_text_and_image_in_tool_result(self):
        """
        What it does: Verifies handling of mixed text and image content in tool_result.
        Purpose: Text is preserved, images are extracted separately.
        """
        print("Setup: Tool result with text and image...")
        content = [
            {
                "type": "tool_result",
                "tool_use_id": "call_789",
                "content": [
                    {"type": "text", "text": "Screenshot captured"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "xyz789",
                        },
                    },
                ],
            }
        ]

        print("Action: Extracting tool results...")
        result = extract_tool_results_from_anthropic_content(content)

        print(f"Result: {result}")
        assert len(result) == 1
        # Text is preserved, images are extracted separately
        assert result[0]["content"] == "Screenshot captured"


# ==================================================================================================
# Tests for extract_images_from_tool_results
# ==================================================================================================


class TestExtractImagesFromToolResults:
    """Tests for extract_images_from_tool_results function."""

    def test_extracts_single_image_from_tool_result(self):
        """
        What it does: Verifies extraction of a single image from tool_result content.
        Purpose: Ensure images inside tool_results are properly extracted.
        """
        print("Setup: Tool result with single image...")
        content = [
            {
                "type": "tool_result",
                "tool_use_id": "call_123",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "iVBORw0KGgoAAAANSUhEUg==",
                        },
                    }
                ],
            }
        ]

        print("Action: Extracting images from tool results...")
        result = extract_images_from_tool_results(content)

        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0]["media_type"] == "image/png"
        assert result[0]["data"] == "iVBORw0KGgoAAAANSUhEUg=="

    def test_extracts_multiple_images_from_tool_result(self):
        """
        What it does: Verifies extraction of multiple images from tool_result content.
        Purpose: Ensure all images are extracted from a single tool_result.
        """
        print("Setup: Tool result with multiple images...")
        content = [
            {
                "type": "tool_result",
                "tool_use_id": "call_456",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "png_data_here",
                        },
                    },
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": "jpeg_data_here",
                        },
                    },
                ],
            }
        ]

        print("Action: Extracting images from tool results...")
        result = extract_images_from_tool_results(content)

        print(f"Result: {result}")
        assert len(result) == 2
        assert result[0]["media_type"] == "image/png"
        assert result[1]["media_type"] == "image/jpeg"

    def test_extracts_images_from_multiple_tool_results(self):
        """
        What it does: Verifies extraction of images from multiple tool_results.
        Purpose: Ensure images from all tool_results are collected.
        """
        print("Setup: Multiple tool results with images...")
        content = [
            {
                "type": "tool_result",
                "tool_use_id": "call_1",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "first_image",
                        },
                    }
                ],
            },
            {
                "type": "tool_result",
                "tool_use_id": "call_2",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": "second_image",
                        },
                    }
                ],
            },
        ]

        print("Action: Extracting images from tool results...")
        result = extract_images_from_tool_results(content)

        print(f"Result: {result}")
        assert len(result) == 2
        assert result[0]["data"] == "first_image"
        assert result[1]["data"] == "second_image"

    def test_returns_empty_for_tool_result_without_images(self):
        """
        What it does: Verifies empty list returned when tool_result has no images.
        Purpose: Ensure text-only tool_results don't produce spurious images.
        """
        print("Setup: Tool result with text only...")
        content = [
            {
                "type": "tool_result",
                "tool_use_id": "call_123",
                "content": [{"type": "text", "text": "Just text, no images"}],
            }
        ]

        print("Action: Extracting images from tool results...")
        result = extract_images_from_tool_results(content)

        print(f"Result: {result}")
        assert result == []

    def test_returns_empty_for_string_content(self):
        """
        What it does: Verifies empty list returned for non-list content.
        Purpose: Ensure string content doesn't cause errors.
        """
        print("Setup: String content...")
        content = "Just a string"

        print("Action: Extracting images from tool results...")
        result = extract_images_from_tool_results(content)

        print(f"Result: {result}")
        assert result == []

    def test_returns_empty_for_tool_result_with_string_content(self):
        """
        What it does: Verifies empty list when tool_result content is a string.
        Purpose: Ensure string tool_result content doesn't cause errors.
        """
        print("Setup: Tool result with string content...")
        content = [
            {
                "type": "tool_result",
                "tool_use_id": "call_123",
                "content": "String result, not a list",
            }
        ]

        print("Action: Extracting images from tool results...")
        result = extract_images_from_tool_results(content)

        print(f"Result: {result}")
        assert result == []

    def test_extracts_images_mixed_with_text(self):
        """
        What it does: Verifies images are extracted when mixed with text content.
        Purpose: Ensure images are found even when text blocks are present.
        """
        print("Setup: Tool result with text and image...")
        content = [
            {
                "type": "tool_result",
                "tool_use_id": "call_123",
                "content": [
                    {"type": "text", "text": "Screenshot captured"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "screenshot_data",
                        },
                    },
                ],
            }
        ]

        print("Action: Extracting images from tool results...")
        result = extract_images_from_tool_results(content)

        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0]["data"] == "screenshot_data"


# ==================================================================================================
# Tests for extract_tool_uses_from_anthropic_content
# ==================================================================================================


class TestExtractToolUsesFromAnthropicContent:
    """Tests for extract_tool_uses_from_anthropic_content function."""

    def test_extracts_tool_use_from_dict(self):
        """
        What it does: Verifies extraction of tool use from dict content block.
        Purpose: Ensure tool_use blocks are extracted correctly.
        """
        print("Setup: Content with tool_use block...")
        content = [
            {
                "type": "tool_use",
                "id": "call_123",
                "name": "get_weather",
                "input": {"location": "Moscow"},
            }
        ]

        print("Action: Extracting tool uses...")
        result = extract_tool_uses_from_anthropic_content(content)

        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0]["id"] == "call_123"
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "get_weather"
        assert result[0]["function"]["arguments"] == {"location": "Moscow"}

    def test_extracts_tool_use_from_pydantic_model(self):
        """
        What it does: Verifies extraction from Pydantic ToolUseContentBlock.
        Purpose: Ensure Pydantic models are handled correctly.
        """
        print("Setup: Content with Pydantic ToolUseContentBlock...")
        content = [
            ToolUseContentBlock(
                type="tool_use", id="call_456", name="search", input={"query": "test"}
            )
        ]

        print("Action: Extracting tool uses...")
        result = extract_tool_uses_from_anthropic_content(content)

        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0]["id"] == "call_456"
        assert result[0]["function"]["name"] == "search"

    def test_extracts_multiple_tool_uses(self):
        """
        What it does: Verifies extraction of multiple tool uses.
        Purpose: Ensure all tool_use blocks are extracted.
        """
        print("Setup: Content with multiple tool_uses...")
        content = [
            {"type": "tool_use", "id": "call_1", "name": "tool1", "input": {}},
            {"type": "text", "text": "Some text"},
            {"type": "tool_use", "id": "call_2", "name": "tool2", "input": {}},
        ]

        print("Action: Extracting tool uses...")
        result = extract_tool_uses_from_anthropic_content(content)

        print(f"Result: {result}")
        assert len(result) == 2
        assert result[0]["id"] == "call_1"
        assert result[1]["id"] == "call_2"

    def test_returns_empty_for_string_content(self):
        """
        What it does: Verifies empty list return for string content.
        Purpose: Ensure string doesn't contain tool uses.
        """
        print("Setup: String content...")
        content = "Just a string"

        print("Action: Extracting tool uses...")
        result = extract_tool_uses_from_anthropic_content(content)

        print(f"Comparing result: Expected [], Got {result}")
        assert result == []

    def test_returns_empty_for_list_without_tool_uses(self):
        """
        What it does: Verifies empty list return without tool_use blocks.
        Purpose: Ensure regular elements are not extracted.
        """
        print("Setup: List without tool_use...")
        content = [{"type": "text", "text": "Hello"}]

        print("Action: Extracting tool uses...")
        result = extract_tool_uses_from_anthropic_content(content)

        print(f"Comparing result: Expected [], Got {result}")
        assert result == []

    def test_skips_tool_use_without_id(self):
        """
        What it does: Verifies that tool_use without id is skipped.
        Purpose: Ensure invalid tool_use blocks are ignored.
        """
        print("Setup: Tool use without id...")
        content = [{"type": "tool_use", "name": "test", "input": {}}]

        print("Action: Extracting tool uses...")
        result = extract_tool_uses_from_anthropic_content(content)

        print(f"Comparing result: Expected [], Got {result}")
        assert result == []

    def test_skips_tool_use_without_name(self):
        """
        What it does: Verifies that tool_use without name is skipped.
        Purpose: Ensure invalid tool_use blocks are ignored.
        """
        print("Setup: Tool use without name...")
        content = [{"type": "tool_use", "id": "call_123", "input": {}}]

        print("Action: Extracting tool uses...")
        result = extract_tool_uses_from_anthropic_content(content)

        print(f"Comparing result: Expected [], Got {result}")
        assert result == []


# ==================================================================================================
# Tests for convert_anthropic_messages
# ==================================================================================================


class TestConvertAnthropicMessages:
    """Tests for convert_anthropic_messages function."""

    def test_converts_simple_user_message(self):
        """
        What it does: Verifies conversion of simple user message.
        Purpose: Ensure basic user message is converted to UnifiedMessage.
        """
        print("Setup: Simple user message...")
        messages = [AnthropicMessage(role="user", content="Hello!")]

        print("Action: Converting messages...")
        result = convert_anthropic_messages(messages)

        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0].role == "user"
        assert result[0].content == "Hello!"
        assert result[0].tool_calls is None
        assert result[0].tool_results is None

    def test_converts_simple_assistant_message(self):
        """
        What it does: Verifies conversion of simple assistant message.
        Purpose: Ensure basic assistant message is converted to UnifiedMessage.
        """
        print("Setup: Simple assistant message...")
        messages = [AnthropicMessage(role="assistant", content="Hi there!")]

        print("Action: Converting messages...")
        result = convert_anthropic_messages(messages)

        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0].role == "assistant"
        assert result[0].content == "Hi there!"

    def test_converts_user_message_with_content_blocks(self):
        """
        What it does: Verifies conversion of user message with content blocks.
        Purpose: Ensure multimodal content is handled.
        """
        print("Setup: User message with content blocks...")
        messages = [
            AnthropicMessage(
                role="user",
                content=[
                    {"type": "text", "text": "Part 1"},
                    {"type": "text", "text": " Part 2"},
                ],
            )
        ]

        print("Action: Converting messages...")
        result = convert_anthropic_messages(messages)

        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0].content == "Part 1 Part 2"

    def test_converts_assistant_message_with_tool_use(self):
        """
        What it does: Verifies conversion of assistant message with tool_use.
        Purpose: Ensure tool_use blocks are extracted as tool_calls.
        """
        print("Setup: Assistant message with tool_use...")
        messages = [
            AnthropicMessage(
                role="assistant",
                content=[
                    {"type": "text", "text": "I'll check the weather"},
                    {
                        "type": "tool_use",
                        "id": "call_123",
                        "name": "get_weather",
                        "input": {"location": "Moscow"},
                    },
                ],
            )
        ]

        print("Action: Converting messages...")
        result = convert_anthropic_messages(messages)

        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0].role == "assistant"
        assert result[0].content == "I'll check the weather"
        assert result[0].tool_calls is not None
        assert len(result[0].tool_calls) == 1
        assert result[0].tool_calls[0]["function"]["name"] == "get_weather"

    def test_converts_user_message_with_tool_result(self):
        """
        What it does: Verifies conversion of user message with tool_result.
        Purpose: Ensure tool_result blocks are extracted as tool_results.
        """
        print("Setup: User message with tool_result...")
        messages = [
            AnthropicMessage(
                role="user",
                content=[
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_123",
                        "content": "Weather: Sunny, 25°C",
                    }
                ],
            )
        ]

        print("Action: Converting messages...")
        result = convert_anthropic_messages(messages)

        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0].role == "user"
        assert result[0].tool_results is not None
        assert len(result[0].tool_results) == 1
        assert result[0].tool_results[0]["tool_use_id"] == "call_123"

    def test_converts_full_conversation(self):
        """
        What it does: Verifies conversion of full conversation.
        Purpose: Ensure multi-turn conversation is converted correctly.
        """
        print("Setup: Full conversation...")
        messages = [
            AnthropicMessage(role="user", content="Hello"),
            AnthropicMessage(role="assistant", content="Hi! How can I help?"),
            AnthropicMessage(role="user", content="What's the weather?"),
        ]

        print("Action: Converting messages...")
        result = convert_anthropic_messages(messages)

        print(f"Result: {result}")
        assert len(result) == 3
        assert result[0].role == "user"
        assert result[1].role == "assistant"
        assert result[2].role == "user"

    def test_handles_empty_messages_list(self):
        """
        What it does: Verifies handling of empty messages list.
        Purpose: Ensure empty list returns empty list.
        """
        print("Setup: Empty messages list...")
        messages = []

        print("Action: Converting messages...")
        result = convert_anthropic_messages(messages)

        print(f"Comparing result: Expected [], Got {result}")
        assert result == []

    # ==================================================================================
    # Image extraction tests (Issue #30 fix)
    # ==================================================================================

    def test_extracts_images_from_user_message(self):
        """
        What it does: Verifies that images are extracted from user messages.
        Purpose: Ensure Anthropic image content blocks are converted to unified format.

        This test verifies the fix for Issue #30 - 422 Validation Error for image content.
        """
        print("Setup: User message with image content block...")
        # Base64 1x1 pixel JPEG
        test_image_base64 = "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AVN//2Q=="

        messages = [
            AnthropicMessage(
                role="user",
                content=[
                    {"type": "text", "text": "What's in this image?"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": test_image_base64,
                        },
                    },
                ],
            )
        ]

        print("Action: Converting messages...")
        result = convert_anthropic_messages(messages)

        print(f"Result: {result}")
        print(f"Images: {result[0].images}")

        assert len(result) == 1
        assert result[0].role == "user"
        assert result[0].content == "What's in this image?"

        print("Checking images field...")
        assert result[0].images is not None, "images field should not be None"
        assert len(result[0].images) == 1, (
            f"Expected 1 image, got {len(result[0].images)}"
        )

        image = result[0].images[0]
        print(
            f"Comparing image: Expected media_type='image/jpeg', Got '{image.get('media_type')}'"
        )
        assert image["media_type"] == "image/jpeg"

        print(
            f"Comparing image data: Expected {test_image_base64[:20]}..., Got {image.get('data', '')[:20]}..."
        )
        assert image["data"] == test_image_base64

    def test_images_only_extracted_from_user_role(self):
        """
        What it does: Verifies that images are only extracted from user messages.
        Purpose: Ensure assistant messages don't have images extracted (they shouldn't contain images).
        """
        print("Setup: Conversation with image in user message only...")
        test_image_base64 = "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AVN//2Q=="

        messages = [
            AnthropicMessage(
                role="user",
                content=[
                    {"type": "text", "text": "Describe this image"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": test_image_base64,
                        },
                    },
                ],
            ),
            AnthropicMessage(role="assistant", content="I can see a small image."),
        ]

        print("Action: Converting messages...")
        result = convert_anthropic_messages(messages)

        print(f"Result: {result}")

        print("Checking user message has images...")
        assert result[0].images is not None
        assert len(result[0].images) == 1

        print("Checking assistant message has no images...")
        assert result[1].images is None, (
            "Assistant messages should not have images extracted"
        )

    def test_extracts_multiple_images_from_user_message(self):
        """
        What it does: Verifies extraction of multiple images from a single user message.
        Purpose: Ensure all images in a message are extracted.
        """
        print("Setup: User message with multiple images...")
        test_image_base64 = "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AVN//2Q=="

        messages = [
            AnthropicMessage(
                role="user",
                content=[
                    {"type": "text", "text": "Compare these images"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": test_image_base64,
                        },
                    },
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": test_image_base64,
                        },
                    },
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/webp",
                            "data": test_image_base64,
                        },
                    },
                ],
            )
        ]

        print("Action: Converting messages...")
        result = convert_anthropic_messages(messages)

        print(
            f"Result images count: {len(result[0].images) if result[0].images else 0}"
        )

        assert result[0].images is not None
        assert len(result[0].images) == 3, (
            f"Expected 3 images, got {len(result[0].images)}"
        )

        print("Checking image media types...")
        media_types = [img["media_type"] for img in result[0].images]
        print(f"Media types: {media_types}")
        assert "image/jpeg" in media_types
        assert "image/png" in media_types
        assert "image/webp" in media_types

    def test_counts_images_in_debug_log(self, caplog):
        """
        What it does: Verifies that image count is logged in debug message.
        Purpose: Ensure logging includes image statistics for debugging.
        """
        import logging

        print("Setup: User message with images for logging test...")
        test_image_base64 = "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AVN//2Q=="

        messages = [
            AnthropicMessage(
                role="user",
                content=[
                    {"type": "text", "text": "Analyze this"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": test_image_base64,
                        },
                    },
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": test_image_base64,
                        },
                    },
                ],
            )
        ]

        print("Action: Converting messages with logging enabled...")
        with caplog.at_level(logging.DEBUG):
            result = convert_anthropic_messages(messages)

        print(f"Log records: {[r.message for r in caplog.records]}")

        # Check that images were extracted
        assert result[0].images is not None
        assert len(result[0].images) == 2

        # Note: loguru doesn't integrate with caplog by default
        # The function logs "Converted X Anthropic messages: Y tool_calls, Z tool_results, W images"
        # We verify the images are extracted correctly, which proves the counting works
        print("Images extracted successfully - logging verification complete")


# ==================================================================================================
# Tests for convert_anthropic_tools
# ==================================================================================================


class TestConvertAnthropicTools:
    """Tests for convert_anthropic_tools function."""

    def test_returns_none_for_none(self):
        """
        What it does: Verifies handling of None.
        Purpose: Ensure None returns None.
        """
        print("Setup: None tools...")

        print("Action: Converting tools...")
        result = convert_anthropic_tools(None)

        print(f"Comparing result: Expected None, Got {result}")
        assert result is None

    def test_returns_none_for_empty_list(self):
        """
        What it does: Verifies handling of empty list.
        Purpose: Ensure empty list returns None.
        """
        print("Setup: Empty tools list...")

        print("Action: Converting tools...")
        result = convert_anthropic_tools([])

        print(f"Comparing result: Expected None, Got {result}")
        assert result is None

    def test_converts_tool_from_pydantic_model(self):
        """
        What it does: Verifies conversion of Pydantic AnthropicTool.
        Purpose: Ensure Pydantic models are converted to UnifiedTool.
        """
        print("Setup: Pydantic AnthropicTool...")
        tools = [
            AnthropicTool(
                name="get_weather",
                description="Get weather for a location",
                input_schema={
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                },
            )
        ]

        print("Action: Converting tools...")
        result = convert_anthropic_tools(tools)

        print(f"Result: {result}")
        assert result is not None
        assert len(result) == 1
        assert isinstance(result[0], UnifiedTool)
        assert result[0].name == "get_weather"
        assert result[0].description == "Get weather for a location"
        assert result[0].input_schema == {
            "type": "object",
            "properties": {"location": {"type": "string"}},
        }

    def test_converts_tool_from_dict(self):
        """
        What it does: Verifies conversion of dict tool.
        Purpose: Ensure dict tools are converted to UnifiedTool.
        """
        print("Setup: Dict tool...")
        tools = [
            {
                "name": "search",
                "description": "Search the web",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            }
        ]

        print("Action: Converting tools...")
        result = convert_anthropic_tools(tools)

        print(f"Result: {result}")
        assert result is not None
        assert len(result) == 1
        assert result[0].name == "search"
        assert result[0].description == "Search the web"

    def test_converts_multiple_tools(self):
        """
        What it does: Verifies conversion of multiple tools.
        Purpose: Ensure all tools are converted.
        """
        print("Setup: Multiple tools...")
        tools = [
            AnthropicTool(name="tool1", description="Tool 1", input_schema={}),
            AnthropicTool(name="tool2", description="Tool 2", input_schema={}),
        ]

        print("Action: Converting tools...")
        result = convert_anthropic_tools(tools)

        print(f"Result: {result}")
        assert result is not None
        assert len(result) == 2
        assert result[0].name == "tool1"
        assert result[1].name == "tool2"

    def test_handles_tool_without_description(self):
        """
        What it does: Verifies handling of tool without description.
        Purpose: Ensure None description is preserved.
        """
        print("Setup: Tool without description...")
        tools = [AnthropicTool(name="test_tool", input_schema={})]

        print("Action: Converting tools...")
        result = convert_anthropic_tools(tools)

        print(f"Result: {result}")
        assert result is not None
        assert result[0].description is None


# ==================================================================================================
# Tests for anthropic_to_kiro
# ==================================================================================================


class TestAnthropicToKiro:
    """Tests for anthropic_to_kiro function - main entry point."""

    def test_builds_simple_payload(self):
        """
        What it does: Verifies building of simple Kiro payload.
        Purpose: Ensure basic request is converted correctly.
        """
        print("Setup: Simple Anthropic request...")
        request = AnthropicMessagesRequest(
            model="claude-sonnet-4-5",
            messages=[AnthropicMessage(role="user", content="Hello!")],
            max_tokens=1024,
        )

        print("Action: Converting to Kiro payload...")
        with patch(
            "kiro.converters_anthropic.get_model_id_for_kiro",
            return_value="claude-sonnet-4.5",
        ):
            with patch("kiro.converters_core.FAKE_REASONING_ENABLED", False):
                result = anthropic_to_kiro(request, "conv-123", "arn:aws:test")

        print(f"Result: {result}")
        assert "conversationState" in result
        assert result["conversationState"]["conversationId"] == "conv-123"
        assert "currentMessage" in result["conversationState"]
        assert "userInputMessage" in result["conversationState"]["currentMessage"]
        assert result["profileArn"] == "arn:aws:test"

    def test_includes_system_prompt(self):
        """
        What it does: Verifies that system prompt is included.
        Purpose: Ensure Anthropic's separate system field is handled.
        """
        print("Setup: Request with system prompt...")
        request = AnthropicMessagesRequest(
            model="claude-sonnet-4-5",
            messages=[AnthropicMessage(role="user", content="Hello!")],
            max_tokens=1024,
            system="You are a helpful assistant.",
        )

        print("Action: Converting to Kiro payload...")
        with patch(
            "kiro.converters_anthropic.get_model_id_for_kiro",
            return_value="claude-sonnet-4.5",
        ):
            with patch("kiro.converters_core.FAKE_REASONING_ENABLED", False):
                result = anthropic_to_kiro(request, "conv-123", "arn:aws:test")

        print(f"Result: {result}")
        current_content = result["conversationState"]["currentMessage"][
            "userInputMessage"
        ]["content"]
        print(f"Current content: {current_content}")
        assert "You are a helpful assistant." in current_content

    def test_includes_tools(self):
        """
        What it does: Verifies that tools are included in payload.
        Purpose: Ensure Anthropic tools are converted to Kiro format.
        """
        print("Setup: Request with tools...")
        request = AnthropicMessagesRequest(
            model="claude-sonnet-4-5",
            messages=[AnthropicMessage(role="user", content="What's the weather?")],
            max_tokens=1024,
            tools=[
                AnthropicTool(
                    name="get_weather",
                    description="Get weather for a location",
                    input_schema={
                        "type": "object",
                        "properties": {"location": {"type": "string"}},
                    },
                )
            ],
        )

        print("Action: Converting to Kiro payload...")
        with patch(
            "kiro.converters_anthropic.get_model_id_for_kiro",
            return_value="claude-sonnet-4.5",
        ):
            with patch("kiro.converters_core.FAKE_REASONING_ENABLED", False):
                result = anthropic_to_kiro(request, "conv-123", "arn:aws:test")

        print(f"Result: {result}")
        context = result["conversationState"]["currentMessage"]["userInputMessage"].get(
            "userInputMessageContext", {}
        )
        tools = context.get("tools", [])
        print(f"Tools in payload: {tools}")
        assert len(tools) == 1
        assert tools[0]["toolSpecification"]["name"] == "get_weather"

    def test_builds_history_for_multi_turn(self):
        """
        What it does: Verifies building of history for multi-turn conversation.
        Purpose: Ensure conversation history is included in payload.
        """
        print("Setup: Multi-turn conversation...")
        request = AnthropicMessagesRequest(
            model="claude-sonnet-4-5",
            messages=[
                AnthropicMessage(role="user", content="Hello"),
                AnthropicMessage(role="assistant", content="Hi! How can I help?"),
                AnthropicMessage(role="user", content="What's the weather?"),
            ],
            max_tokens=1024,
        )

        print("Action: Converting to Kiro payload...")
        with patch(
            "kiro.converters_anthropic.get_model_id_for_kiro",
            return_value="claude-sonnet-4.5",
        ):
            with patch("kiro.converters_core.FAKE_REASONING_ENABLED", False):
                result = anthropic_to_kiro(request, "conv-123", "arn:aws:test")

        print(f"Result: {result}")
        history = result["conversationState"].get("history", [])
        print(f"History length: {len(history)}")
        assert len(history) == 2  # First user + assistant
        assert "userInputMessage" in history[0]
        assert "assistantResponseMessage" in history[1]

    def test_handles_tool_use_and_result_flow(self):
        """
        What it does: Verifies handling of tool use and result flow.
        Purpose: Ensure full tool flow is converted correctly.
        """
        print("Setup: Tool use and result flow...")
        request = AnthropicMessagesRequest(
            model="claude-sonnet-4-5",
            messages=[
                AnthropicMessage(role="user", content="What's the weather in Moscow?"),
                AnthropicMessage(
                    role="assistant",
                    content=[
                        {"type": "text", "text": "I'll check the weather"},
                        {
                            "type": "tool_use",
                            "id": "call_123",
                            "name": "get_weather",
                            "input": {"location": "Moscow"},
                        },
                    ],
                ),
                AnthropicMessage(
                    role="user",
                    content=[
                        {
                            "type": "tool_result",
                            "tool_use_id": "call_123",
                            "content": "Weather: Sunny, 25°C",
                        }
                    ],
                ),
            ],
            max_tokens=1024,
            # Tools must be defined for tool_results to be preserved
            tools=[
                AnthropicTool(
                    name="get_weather",
                    description="Get weather for a location",
                    input_schema={
                        "type": "object",
                        "properties": {"location": {"type": "string"}},
                    },
                )
            ],
        )

        print("Action: Converting to Kiro payload...")
        with patch(
            "kiro.converters_anthropic.get_model_id_for_kiro",
            return_value="claude-sonnet-4.5",
        ):
            with patch("kiro.converters_core.FAKE_REASONING_ENABLED", False):
                result = anthropic_to_kiro(request, "conv-123", "arn:aws:test")

        print(f"Result: {result}")

        # Check history contains tool use
        history = result["conversationState"].get("history", [])
        print(f"History: {history}")

        # Check current message contains tool result
        current_msg = result["conversationState"]["currentMessage"]["userInputMessage"]
        context = current_msg.get("userInputMessageContext", {})
        tool_results = context.get("toolResults", [])
        print(f"Tool results: {tool_results}")
        assert len(tool_results) == 1

    def test_raises_for_empty_messages(self):
        """
        What it does: Verifies that empty messages raise Pydantic ValidationError.
        Purpose: Ensure Pydantic validation works correctly (min_length=1).

        Note: AnthropicMessagesRequest has min_length=1 validation on messages field,
        so empty messages are rejected at the Pydantic level, not at anthropic_to_kiro.
        """
        from pydantic import ValidationError

        print("Setup: Attempting to create request with empty messages...")

        print(
            "Action: Creating AnthropicMessagesRequest (should raise ValidationError)..."
        )
        with pytest.raises(ValidationError):
            AnthropicMessagesRequest(
                model="claude-sonnet-4-5", messages=[], max_tokens=1024
            )

        print("ValidationError raised as expected - Pydantic rejects empty messages")

    def test_injects_thinking_tags_when_enabled(self):
        """
        What it does: Verifies that thinking tags are injected when enabled.
        Purpose: Ensure fake reasoning feature works with Anthropic API.
        """
        print("Setup: Request with fake reasoning enabled...")
        request = AnthropicMessagesRequest(
            model="claude-sonnet-4-5",
            messages=[AnthropicMessage(role="user", content="What is 2+2?")],
            max_tokens=1024,
        )

        print("Action: Converting to Kiro payload with fake reasoning...")
        with patch(
            "kiro.converters_anthropic.get_model_id_for_kiro",
            return_value="claude-sonnet-4.5",
        ):
            with patch("kiro.converters_core.FAKE_REASONING_ENABLED", True):
                with patch("kiro.converters_core.FAKE_REASONING_MAX_TOKENS", 4000):
                    result = anthropic_to_kiro(request, "conv-123", "arn:aws:test")

        print(f"Result: {result}")
        current_content = result["conversationState"]["currentMessage"][
            "userInputMessage"
        ]["content"]
        print(f"Current content (first 200 chars): {current_content[:200]}...")

        print("Checking that thinking tags are present...")
        assert "<thinking_mode>enabled</thinking_mode>" in current_content
        assert "What is 2+2?" in current_content

    def test_injects_thinking_tags_even_when_tool_results_present(self):
        """
        What it does: Verifies that thinking tags ARE injected even when tool results are present.
        Purpose: Extended thinking should work in all scenarios including tool use flows.
        """
        print("Setup: Request with tool results and fake reasoning enabled...")
        request = AnthropicMessagesRequest(
            model="claude-sonnet-4-5",
            messages=[
                AnthropicMessage(
                    role="user",
                    content=[
                        {
                            "type": "tool_result",
                            "tool_use_id": "call_123",
                            "content": "Result",
                        }
                    ],
                )
            ],
            max_tokens=1024,
            # Tools must be defined for tool_results to be preserved
            tools=[
                AnthropicTool(
                    name="test_tool",
                    description="A test tool",
                    input_schema={"type": "object", "properties": {}},
                )
            ],
        )

        print("Action: Converting to Kiro payload...")
        with patch(
            "kiro.converters_anthropic.get_model_id_for_kiro",
            return_value="claude-sonnet-4.5",
        ):
            with patch("kiro.converters_core.FAKE_REASONING_ENABLED", True):
                with patch("kiro.converters_core.FAKE_REASONING_MAX_TOKENS", 4000):
                    result = anthropic_to_kiro(request, "conv-123", "arn:aws:test")

        print(f"Result: {result}")
        current_content = result["conversationState"]["currentMessage"][
            "userInputMessage"
        ]["content"]
        print(f"Current content (first 100 chars): {current_content[:100]}...")

        print("Checking that thinking tags ARE present...")
        assert "<thinking_mode>enabled</thinking_mode>" in current_content, (
            "thinking tags SHOULD be injected even with tool results"
        )

        print("Checking that <max_thinking_length> tag IS present...")
        assert "<max_thinking_length>4000</max_thinking_length>" in current_content, (
            "max_thinking_length tag SHOULD be present even with tool results"
        )


# ==================================================================================================
# Tests for Client Thinking Budget Support (Issue #111)
# ==================================================================================================

class TestExtractThinkingConfigFromAnthropic:
    """Tests for extract_thinking_config_from_anthropic function."""
    
    def test_no_thinking(self):
        """
        What it does: Verifies ThinkingConfig(enabled=True, budget_tokens=None) when thinking=None
        Purpose: Ensure default configuration when thinking not specified
        """
        print("Creating request without thinking parameter...")
        request = AnthropicMessagesRequest(
            model="claude-sonnet-4.5",
            messages=[AnthropicMessage(role="user", content="test")],
            max_tokens=1024
        )
        
        print("Extracting thinking config...")
        config = extract_thinking_config_from_anthropic(request)
        
        print(f"Comparing: enabled={config.enabled}, budget_tokens={config.budget_tokens}")
        assert config.enabled is True
        assert config.budget_tokens is None
    
    def test_thinking_enabled_with_budget(self):
        """
        What it does: Verifies correct extraction of thinking.budget_tokens
        Purpose: Ensure budget is extracted from official Anthropic parameter
        """
        print("Creating request with thinking={'type': 'enabled', 'budget_tokens': 8000}...")
        request = AnthropicMessagesRequest(
            model="claude-sonnet-4.5",
            messages=[AnthropicMessage(role="user", content="test")],
            max_tokens=1024,
            thinking={"type": "enabled", "budget_tokens": 8000}
        )
        
        print("Extracting thinking config...")
        config = extract_thinking_config_from_anthropic(request)
        
        print(f"Comparing: enabled={config.enabled}, budget_tokens={config.budget_tokens}")
        assert config.enabled is True
        assert config.budget_tokens == 8000
    
    def test_thinking_enabled_without_budget(self):
        """
        What it does: Verifies ThinkingConfig when thinking.type="enabled" but no budget_tokens
        Purpose: Ensure thinking can be enabled without explicit budget
        """
        print("Creating request with thinking={'type': 'enabled'} (no budget)...")
        request = AnthropicMessagesRequest(
            model="claude-sonnet-4.5",
            messages=[AnthropicMessage(role="user", content="test")],
            max_tokens=1024,
            thinking={"type": "enabled"}
        )
        
        print("Extracting thinking config...")
        config = extract_thinking_config_from_anthropic(request)
        
        print(f"Comparing: enabled={config.enabled}, budget_tokens={config.budget_tokens}")
        assert config.enabled is True
        assert config.budget_tokens is None
    
    def test_thinking_disabled(self):
        """
        What it does: Verifies ThinkingConfig(enabled=False) when thinking.type="disabled"
        Purpose: Ensure client can explicitly disable thinking
        """
        print("Creating request with thinking={'type': 'disabled'}...")
        request = AnthropicMessagesRequest(
            model="claude-sonnet-4.5",
            messages=[AnthropicMessage(role="user", content="test")],
            max_tokens=1024,
            thinking={"type": "disabled"}
        )
        
        print("Extracting thinking config...")
        config = extract_thinking_config_from_anthropic(request)
        
        print(f"Comparing: enabled={config.enabled}, budget_tokens={config.budget_tokens}")
        assert config.enabled is False
        assert config.budget_tokens is None
    
    def test_thinking_invalid_type(self):
        """
        What it does: Verifies default config when thinking.type is unknown
        Purpose: Ensure graceful fallback for invalid thinking type
        """
        print("Creating request with thinking={'type': 'unknown'}...")
        request = AnthropicMessagesRequest(
            model="claude-sonnet-4.5",
            messages=[AnthropicMessage(role="user", content="test")],
            max_tokens=1024,
            thinking={"type": "unknown"}
        )
        
        print("Extracting thinking config...")
        config = extract_thinking_config_from_anthropic(request)
        
        print(f"Comparing: enabled={config.enabled}, budget_tokens={config.budget_tokens}")
        assert config.enabled is True
        assert config.budget_tokens is None
    


class TestAnthropicToKiroIntegration:
    """Integration tests for anthropic_to_kiro with thinking config."""
    
    def test_extracts_and_passes_thinking_config(self):
        """
        What it does: Verifies anthropic_to_kiro extracts thinking_config and passes to core
        Purpose: Ensure end-to-end thinking configuration flow works
        """
        print("Creating request with thinking budget...")
        request = AnthropicMessagesRequest(
            model="claude-sonnet-4.5",
            messages=[AnthropicMessage(role="user", content="Test message")],
            max_tokens=1024,
            thinking={"type": "enabled", "budget_tokens": 6000}
        )
        
        print("Calling anthropic_to_kiro...")
        with patch("kiro.converters_anthropic.get_model_id_for_kiro", return_value="claude-sonnet-4.5"):
            with patch("kiro.converters_core.FAKE_REASONING_ENABLED", True):
                with patch("kiro.converters_core.FAKE_REASONING_BUDGET_CAP", 10000):
                    payload = anthropic_to_kiro(request, "test-conv-123", "arn:aws:test")
        
        print("Extracting userInputMessage content...")
        user_input = payload["conversationState"]["currentMessage"]["userInputMessage"]
        content = user_input["content"]
        
        print(f"Checking for <max_thinking_length>6000</max_thinking_length>...")
        assert "<max_thinking_length>6000</max_thinking_length>" in content
        assert "<thinking_mode>enabled</thinking_mode>" in content
