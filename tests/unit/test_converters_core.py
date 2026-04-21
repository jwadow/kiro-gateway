# -*- coding: utf-8 -*-

"""
Unit tests for converters_core module.

Tests for shared conversion logic used by both OpenAI and Anthropic adapters:
- Text content extraction
- Message merging
- JSON Schema sanitization
- Tool processing
- Thinking tag injection
"""

import os
import pytest
from unittest.mock import patch

from kiro.converters_core import (
    extract_text_content,
    extract_images_from_content,
    convert_images_to_kiro_format,
    merge_adjacent_messages,
    ensure_first_message_is_user,
    normalize_message_roles,
    ensure_alternating_roles,
    ensure_assistant_before_tool_results,
    strip_all_tool_content,
    build_kiro_history,
    build_kiro_payload,
    process_tools_with_long_descriptions,
    inject_thinking_tags,
    extract_tool_results_from_content,
    extract_tool_uses_from_message,
    sanitize_json_schema,
    convert_tools_to_kiro_format,
    convert_tool_results_to_kiro_format,
    tool_calls_to_text,
    tool_results_to_text,
    UnifiedMessage,
    UnifiedTool,
    ThinkingConfig,
)

# Test data for images - 1x1 pixel JPEG
TEST_IMAGE_BASE64 = "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AVN//2Q=="


# ==================================================================================================
# Tests for extract_text_content
# ==================================================================================================

class TestExtractTextContent:
    """Tests for extract_text_content function."""
    
    def test_extracts_from_string(self):
        """
        What it does: Verifies text extraction from a string.
        Purpose: Ensure string is returned as-is.
        """
        print("Setup: Simple string...")
        content = "Hello, World!"
        
        print("Action: Extracting text...")
        result = extract_text_content(content)
        
        print(f"Comparing result: Expected 'Hello, World!', Got '{result}'")
        assert result == "Hello, World!"
    
    def test_extracts_from_none(self):
        """
        What it does: Verifies None handling.
        Purpose: Ensure None returns empty string.
        """
        print("Setup: None...")
        
        print("Action: Extracting text...")
        result = extract_text_content(None)
        
        print(f"Comparing result: Expected '', Got '{result}'")
        assert result == ""
    
    def test_extracts_from_list_with_text_type(self):
        """
        What it does: Verifies extraction from list with type=text.
        Purpose: Ensure multimodal format is handled.
        """
        print("Setup: List with type=text...")
        content = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": " World"}
        ]
        
        print("Action: Extracting text...")
        result = extract_text_content(content)
        
        print(f"Comparing result: Expected 'Hello World', Got '{result}'")
        assert result == "Hello World"
    
    def test_extracts_from_list_with_text_key(self):
        """
        What it does: Verifies extraction from list with text key.
        Purpose: Ensure alternative format is handled.
        """
        print("Setup: List with text key...")
        content = [{"text": "Hello"}, {"text": " World"}]
        
        print("Action: Extracting text...")
        result = extract_text_content(content)
        
        print(f"Comparing result: Expected 'Hello World', Got '{result}'")
        assert result == "Hello World"
    
    def test_extracts_from_list_with_strings(self):
        """
        What it does: Verifies extraction from list of strings.
        Purpose: Ensure string list is concatenated.
        """
        print("Setup: List of strings...")
        content = ["Hello", " ", "World"]
        
        print("Action: Extracting text...")
        result = extract_text_content(content)
        
        print(f"Comparing result: Expected 'Hello World', Got '{result}'")
        assert result == "Hello World"
    
    def test_extracts_from_mixed_list(self):
        """
        What it does: Verifies extraction from mixed list.
        Purpose: Ensure different formats in one list are handled.
        """
        print("Setup: Mixed list...")
        content = [
            {"type": "text", "text": "Part1"},
            "Part2",
            {"text": "Part3"}
        ]
        
        print("Action: Extracting text...")
        result = extract_text_content(content)
        
        print(f"Comparing result: Expected 'Part1Part2Part3', Got '{result}'")
        assert result == "Part1Part2Part3"
    
    def test_converts_other_types_to_string(self):
        """
        What it does: Verifies conversion of other types to string.
        Purpose: Ensure numbers and other types are converted.
        """
        print("Setup: Number...")
        content = 42
        
        print("Action: Extracting text...")
        result = extract_text_content(content)
        
        print(f"Comparing result: Expected '42', Got '{result}'")
        assert result == "42"
    
    def test_handles_empty_list(self):
        """
        What it does: Verifies empty list handling.
        Purpose: Ensure empty list returns empty string.
        """
        print("Setup: Empty list...")
        content = []
        
        print("Action: Extracting text...")
        result = extract_text_content(content)
        
        print(f"Comparing result: Expected '', Got '{result}'")
        assert result == ""
    
    def test_extracts_from_pydantic_text_content_block(self):
        """
        What it does: Verifies extraction from Pydantic TextContentBlock objects.
        Purpose: Ensure Pydantic models are handled correctly (Issue #46/#50 fix).
        
        This is the critical test for Issue #46/#50 - the original bug was that
        Pydantic TextContentBlock objects weren't being handled, causing MCP tool
        results to return "(empty result)" instead of actual data.
        """
        from kiro.models_anthropic import TextContentBlock
        
        print("Setup: Pydantic TextContentBlock...")
        content = [
            TextContentBlock(type="text", text="Hello from MCP")
        ]
        
        print("Action: Extracting text...")
        result = extract_text_content(content)
        
        print(f"Result: '{result}'")
        print(f"Comparing result: Expected 'Hello from MCP', Got '{result}'")
        assert result == "Hello from MCP"
    
    def test_extracts_from_multiple_pydantic_text_blocks(self):
        """
        What it does: Verifies extraction from multiple Pydantic TextContentBlock objects.
        Purpose: Ensure multiple Pydantic models are concatenated correctly.
        """
        from kiro.models_anthropic import TextContentBlock
        
        print("Setup: Multiple Pydantic TextContentBlocks...")
        content = [
            TextContentBlock(type="text", text="Part 1"),
            TextContentBlock(type="text", text=" Part 2"),
            TextContentBlock(type="text", text=" Part 3")
        ]
        
        print("Action: Extracting text...")
        result = extract_text_content(content)
        
        print(f"Result: '{result}'")
        print(f"Comparing result: Expected 'Part 1 Part 2 Part 3', Got '{result}'")
        assert result == "Part 1 Part 2 Part 3"
    
    def test_extracts_from_mixed_dict_and_pydantic(self):
        """
        What it does: Verifies extraction from mixed dict and Pydantic content.
        Purpose: Ensure dict and Pydantic models can coexist in the same list.
        
        This simulates real-world scenarios where some content is parsed as dict
        and some as Pydantic models.
        """
        from kiro.models_anthropic import TextContentBlock
        
        print("Setup: Mixed dict and Pydantic content...")
        content = [
            {"type": "text", "text": "Dict text"},
            TextContentBlock(type="text", text=" Pydantic text"),
            " String text"
        ]
        
        print("Action: Extracting text...")
        result = extract_text_content(content)
        
        print(f"Result: '{result}'")
        print(f"Comparing result: Expected 'Dict text Pydantic text String text', Got '{result}'")
        assert result == "Dict text Pydantic text String text"
    
    def test_handles_pydantic_with_empty_text(self):
        """
        What it does: Verifies handling of Pydantic TextContentBlock with empty text.
        Purpose: Ensure empty text in Pydantic models doesn't cause errors.
        """
        from kiro.models_anthropic import TextContentBlock
        
        print("Setup: Pydantic TextContentBlock with empty text...")
        content = [
            TextContentBlock(type="text", text="")
        ]
        
        print("Action: Extracting text...")
        result = extract_text_content(content)
        
        print(f"Result: '{result}'")
        print(f"Comparing result: Expected '', Got '{result}'")
        assert result == ""
    
    def test_extracts_text_ignoring_other_pydantic_types(self):
        """
        What it does: Verifies that only text-containing Pydantic models are extracted.
        Purpose: Ensure non-text Pydantic models (like ToolUseContentBlock) are ignored.
        
        This simulates MCP tool results that contain both text and tool_use blocks.
        """
        from kiro.models_anthropic import TextContentBlock, ToolUseContentBlock
        
        print("Setup: Mixed Pydantic content with text and tool_use...")
        content = [
            TextContentBlock(type="text", text="Before tool"),
            ToolUseContentBlock(type="tool_use", id="call_123", name="test_tool", input={}),
            TextContentBlock(type="text", text="After tool")
        ]
        
        print("Action: Extracting text...")
        result = extract_text_content(content)
        
        print(f"Result: '{result}'")
        print(f"Comparing result: Expected 'Before toolAfter tool', Got '{result}'")
        assert result == "Before toolAfter tool"

    def test_skips_tool_reference_blocks(self):
        """
        What it does: Verifies that tool_reference blocks are skipped during text extraction.
        Purpose: Ensure Claude Code deferred tool references don't pollute text output.
        """
        print("Setup: Content with tool_reference blocks...")
        content = [
            {"type": "text", "text": "Loaded tools:"},
            {"type": "tool_reference", "tool_name": "mcp__slack__read_channel"},
            {"type": "tool_reference", "tool_name": "Read"},
            {"type": "text", "text": " done"}
        ]

        print("Action: Extracting text...")
        result = extract_text_content(content)

        print(f"Comparing result: Expected 'Loaded tools: done', Got '{result}'")
        assert result == "Loaded tools: done"


# ==================================================================================================
# Tests for extract_images_from_content (Issue #30 fix)
# ==================================================================================================

class TestExtractImagesFromContent:
    """
    Tests for extract_images_from_content function.
    
    This function extracts images from message content in unified format.
    Supports both OpenAI (image_url with data URL) and Anthropic (image with source) formats.
    
    This is a critical function for Issue #30 fix - 422 Validation Error for image content blocks.
    """
    
    def test_extracts_from_openai_format_data_url(self):
        """
        What it does: Verifies extraction from OpenAI image_url format with data URL.
        Purpose: Ensure OpenAI Vision API format is handled correctly.
        
        OpenAI format: {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
        """
        print("Setup: OpenAI format image content...")
        content = [
            {"type": "text", "text": "What's in this image?"},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{TEST_IMAGE_BASE64}"}
            }
        ]
        
        print("Action: Extracting images...")
        result = extract_images_from_content(content)
        
        print(f"Result: {result}")
        print(f"Comparing count: Expected 1, Got {len(result)}")
        assert len(result) == 1
        
        print("Checking media_type...")
        assert result[0]["media_type"] == "image/jpeg"
        
        print("Checking data...")
        assert result[0]["data"] == TEST_IMAGE_BASE64
    
    def test_extracts_from_anthropic_format_base64(self):
        """
        What it does: Verifies extraction from Anthropic image format with base64 source.
        Purpose: Ensure Anthropic Messages API format is handled correctly.
        
        Anthropic format: {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "..."}}
        """
        print("Setup: Anthropic format image content...")
        content = [
            {"type": "text", "text": "Describe this image"},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": TEST_IMAGE_BASE64
                }
            }
        ]
        
        print("Action: Extracting images...")
        result = extract_images_from_content(content)
        
        print(f"Result: {result}")
        print(f"Comparing count: Expected 1, Got {len(result)}")
        assert len(result) == 1
        
        print("Checking media_type...")
        assert result[0]["media_type"] == "image/png"
        
        print("Checking data...")
        assert result[0]["data"] == TEST_IMAGE_BASE64
    
    def test_extracts_from_mixed_content(self):
        """
        What it does: Verifies extraction from mixed content (text + multiple images).
        Purpose: Ensure all images are extracted from multimodal content.
        """
        print("Setup: Mixed content with multiple images...")
        content = [
            {"type": "text", "text": "Compare these images:"},
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": "image1_data"}
            },
            {"type": "text", "text": "and"},
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": "image2_data"}
            }
        ]
        
        print("Action: Extracting images...")
        result = extract_images_from_content(content)
        
        print(f"Result: {result}")
        print(f"Comparing count: Expected 2, Got {len(result)}")
        assert len(result) == 2
        
        print("Checking first image...")
        assert result[0]["media_type"] == "image/jpeg"
        assert result[0]["data"] == "image1_data"
        
        print("Checking second image...")
        assert result[1]["media_type"] == "image/png"
        assert result[1]["data"] == "image2_data"
    
    def test_returns_empty_for_string_content(self):
        """
        What it does: Verifies empty list return for string content.
        Purpose: Ensure string content doesn't contain images.
        """
        print("Setup: String content...")
        content = "Just a text message"
        
        print("Action: Extracting images...")
        result = extract_images_from_content(content)
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_returns_empty_for_empty_content(self):
        """
        What it does: Verifies empty list return for empty content.
        Purpose: Ensure empty list returns empty list.
        """
        print("Setup: Empty list...")
        content = []
        
        print("Action: Extracting images...")
        result = extract_images_from_content(content)
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_returns_empty_for_none_content(self):
        """
        What it does: Verifies empty list return for None content.
        Purpose: Ensure None doesn't cause errors.
        """
        print("Setup: None content...")
        content = None
        
        print("Action: Extracting images...")
        result = extract_images_from_content(content)
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_returns_empty_for_text_only_content(self):
        """
        What it does: Verifies empty list return for text-only content.
        Purpose: Ensure text blocks don't produce images.
        """
        print("Setup: Text-only content...")
        content = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "World"}
        ]
        
        print("Action: Extracting images...")
        result = extract_images_from_content(content)
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_handles_url_images_with_warning(self):
        """
        What it does: Verifies URL-based images are skipped with warning.
        Purpose: Ensure URL images don't crash but are logged as unsupported.
        
        URL-based images require fetching and are not supported by Kiro API directly.
        """
        print("Setup: URL-based image content...")
        content = [
            {
                "type": "image_url",
                "image_url": {"url": "https://example.com/image.jpg"}
            }
        ]
        
        print("Action: Extracting images (should skip URL images)...")
        result = extract_images_from_content(content)
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []  # URL images are skipped
    
    def test_handles_anthropic_url_source_with_warning(self):
        """
        What it does: Verifies Anthropic URL source images are skipped with warning.
        Purpose: Ensure Anthropic URL format doesn't crash but is logged as unsupported.
        """
        print("Setup: Anthropic URL source image...")
        content = [
            {
                "type": "image",
                "source": {
                    "type": "url",
                    "url": "https://example.com/image.png"
                }
            }
        ]
        
        print("Action: Extracting images (should skip URL images)...")
        result = extract_images_from_content(content)
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []  # URL images are skipped
    
    def test_handles_invalid_data_url(self):
        """
        What it does: Verifies handling of invalid data URL format.
        Purpose: Ensure malformed data URLs don't crash the function.
        """
        print("Setup: Invalid data URL...")
        content = [
            {
                "type": "image_url",
                "image_url": {"url": "data:invalid_format_without_comma"}
            }
        ]
        
        print("Action: Extracting images (should handle gracefully)...")
        result = extract_images_from_content(content)
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []  # Invalid data URL is skipped
    
    def test_handles_empty_data_in_image(self):
        """
        What it does: Verifies handling of image with empty data.
        Purpose: Ensure images with empty data are skipped.
        """
        print("Setup: Image with empty data...")
        content = [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": ""}
            }
        ]
        
        print("Action: Extracting images...")
        result = extract_images_from_content(content)
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []  # Empty data is skipped
    
    def test_extracts_from_pydantic_image_content_block(self):
        """
        What it does: Verifies extraction from Pydantic ImageContentBlock objects.
        Purpose: Ensure Pydantic models are handled correctly (Issue #30 fix).
        
        This is the critical test for Issue #30 - the original bug was that
        Pydantic ImageContentBlock objects weren't being handled.
        """
        from kiro.models_anthropic import ImageContentBlock, Base64ImageSource
        
        print("Setup: Pydantic ImageContentBlock...")
        content = [
            ImageContentBlock(
                type="image",
                source=Base64ImageSource(
                    type="base64",
                    media_type="image/webp",
                    data=TEST_IMAGE_BASE64
                )
            )
        ]
        
        print("Action: Extracting images...")
        result = extract_images_from_content(content)
        
        print(f"Result: {result}")
        print(f"Comparing count: Expected 1, Got {len(result)}")
        assert len(result) == 1
        
        print("Checking media_type...")
        assert result[0]["media_type"] == "image/webp"
        
        print("Checking data...")
        assert result[0]["data"] == TEST_IMAGE_BASE64
    
    def test_extracts_from_pydantic_url_image_source(self):
        """
        What it does: Verifies handling of Pydantic URLImageSource objects.
        Purpose: Ensure Pydantic URL sources are skipped with warning.
        """
        from kiro.models_anthropic import ImageContentBlock, URLImageSource
        
        print("Setup: Pydantic ImageContentBlock with URL source...")
        content = [
            ImageContentBlock(
                type="image",
                source=URLImageSource(
                    type="url",
                    url="https://example.com/image.gif"
                )
            )
        ]
        
        print("Action: Extracting images (should skip URL images)...")
        result = extract_images_from_content(content)
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []  # URL images are skipped
    
    def test_extracts_multiple_formats_mixed(self):
        """
        What it does: Verifies extraction from mixed OpenAI and Anthropic formats.
        Purpose: Ensure both formats can coexist in the same content list.
        """
        print("Setup: Mixed OpenAI and Anthropic formats...")
        content = [
            # OpenAI format
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,openai_image_data"}
            },
            # Anthropic format
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": "anthropic_image_data"}
            }
        ]
        
        print("Action: Extracting images...")
        result = extract_images_from_content(content)
        
        print(f"Result: {result}")
        print(f"Comparing count: Expected 2, Got {len(result)}")
        assert len(result) == 2
        
        print("Checking OpenAI image...")
        assert result[0]["media_type"] == "image/jpeg"
        assert result[0]["data"] == "openai_image_data"
        
        print("Checking Anthropic image...")
        assert result[1]["media_type"] == "image/png"
        assert result[1]["data"] == "anthropic_image_data"
    
    def test_handles_missing_source_in_anthropic_format(self):
        """
        What it does: Verifies handling of Anthropic image without source.
        Purpose: Ensure malformed Anthropic images don't crash.
        """
        print("Setup: Anthropic image without source...")
        content = [
            {"type": "image"}  # Missing source
        ]
        
        print("Action: Extracting images...")
        result = extract_images_from_content(content)
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_handles_missing_image_url_in_openai_format(self):
        """
        What it does: Verifies handling of OpenAI image_url without image_url field.
        Purpose: Ensure malformed OpenAI images don't crash.
        """
        print("Setup: OpenAI image_url without image_url field...")
        content = [
            {"type": "image_url"}  # Missing image_url
        ]
        
        print("Action: Extracting images...")
        result = extract_images_from_content(content)
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_extracts_gif_format(self):
        """
        What it does: Verifies extraction of GIF images.
        Purpose: Ensure GIF format is supported.
        """
        print("Setup: GIF image...")
        content = [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/gif", "data": "gif_data"}
            }
        ]
        
        print("Action: Extracting images...")
        result = extract_images_from_content(content)
        
        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0]["media_type"] == "image/gif"
    
    def test_extracts_webp_format(self):
        """
        What it does: Verifies extraction of WebP images.
        Purpose: Ensure WebP format is supported.
        """
        print("Setup: WebP image...")
        content = [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/webp", "data": "webp_data"}
            }
        ]
        
        print("Action: Extracting images...")
        result = extract_images_from_content(content)
        
        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0]["media_type"] == "image/webp"
    
    def test_uses_default_media_type_when_missing(self):
        """
        What it does: Verifies default media_type is used when not specified.
        Purpose: Ensure missing media_type defaults to image/jpeg.
        """
        print("Setup: Image without media_type...")
        content = [
            {
                "type": "image",
                "source": {"type": "base64", "data": "some_data"}  # No media_type
            }
        ]
        
        print("Action: Extracting images...")
        result = extract_images_from_content(content)
        
        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0]["media_type"] == "image/jpeg"  # Default


# ==================================================================================================
# Tests for convert_images_to_kiro_format
# ==================================================================================================

class TestConvertImagesToKiroFormat:
    """
    Tests for convert_images_to_kiro_format function.
    
    This function converts unified images to Kiro API format.
    
    Unified format: [{"media_type": "image/jpeg", "data": "base64..."}]
    Kiro format: [{"format": "jpeg", "source": {"bytes": "base64..."}}]
    """
    
    def test_converts_single_image(self):
        """
        What it does: Verifies conversion of a single image.
        Purpose: Ensure basic conversion from unified to Kiro format works.
        """
        print("Setup: Single image in unified format...")
        images = [{"media_type": "image/jpeg", "data": TEST_IMAGE_BASE64}]
        
        print("Action: Converting to Kiro format...")
        result = convert_images_to_kiro_format(images)
        
        print(f"Result: {result}")
        print(f"Comparing count: Expected 1, Got {len(result)}")
        assert len(result) == 1
        
        print("Checking format...")
        assert result[0]["format"] == "jpeg"
        
        print("Checking source.bytes...")
        assert result[0]["source"]["bytes"] == TEST_IMAGE_BASE64
    
    def test_converts_multiple_images(self):
        """
        What it does: Verifies conversion of multiple images.
        Purpose: Ensure all images are converted correctly.
        """
        print("Setup: Multiple images...")
        images = [
            {"media_type": "image/jpeg", "data": "jpeg_data"},
            {"media_type": "image/png", "data": "png_data"},
            {"media_type": "image/gif", "data": "gif_data"}
        ]
        
        print("Action: Converting to Kiro format...")
        result = convert_images_to_kiro_format(images)
        
        print(f"Result: {result}")
        print(f"Comparing count: Expected 3, Got {len(result)}")
        assert len(result) == 3
        
        print("Checking formats...")
        assert result[0]["format"] == "jpeg"
        assert result[1]["format"] == "png"
        assert result[2]["format"] == "gif"
    
    def test_returns_empty_for_none(self):
        """
        What it does: Verifies handling of None.
        Purpose: Ensure None returns empty list.
        """
        print("Setup: None images...")
        
        print("Action: Converting to Kiro format...")
        result = convert_images_to_kiro_format(None)
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_returns_empty_for_empty_list(self):
        """
        What it does: Verifies handling of empty list.
        Purpose: Ensure empty list returns empty list.
        """
        print("Setup: Empty images list...")
        
        print("Action: Converting to Kiro format...")
        result = convert_images_to_kiro_format([])
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_skips_images_with_empty_data(self):
        """
        What it does: Verifies skipping of images with empty data.
        Purpose: Ensure images without data are not included.
        """
        print("Setup: Image with empty data...")
        images = [
            {"media_type": "image/jpeg", "data": ""},
            {"media_type": "image/png", "data": "valid_data"}
        ]
        
        print("Action: Converting to Kiro format...")
        result = convert_images_to_kiro_format(images)
        
        print(f"Result: {result}")
        print(f"Comparing count: Expected 1, Got {len(result)}")
        assert len(result) == 1
        assert result[0]["format"] == "png"
    
    def test_extracts_format_from_media_type(self):
        """
        What it does: Verifies extraction of format from media_type.
        Purpose: Ensure "image/jpeg" becomes "jpeg".
        """
        print("Setup: Various media types...")
        images = [
            {"media_type": "image/jpeg", "data": "data1"},
            {"media_type": "image/png", "data": "data2"},
            {"media_type": "image/gif", "data": "data3"},
            {"media_type": "image/webp", "data": "data4"}
        ]
        
        print("Action: Converting to Kiro format...")
        result = convert_images_to_kiro_format(images)
        
        print(f"Result formats: {[r['format'] for r in result]}")
        assert result[0]["format"] == "jpeg"
        assert result[1]["format"] == "png"
        assert result[2]["format"] == "gif"
        assert result[3]["format"] == "webp"
    
    def test_handles_media_type_without_slash(self):
        """
        What it does: Verifies handling of media_type without slash.
        Purpose: Ensure edge case media_type is handled.
        """
        print("Setup: Media type without slash...")
        images = [{"media_type": "jpeg", "data": "data"}]
        
        print("Action: Converting to Kiro format...")
        result = convert_images_to_kiro_format(images)
        
        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0]["format"] == "jpeg"
    
    def test_uses_default_media_type_when_missing(self):
        """
        What it does: Verifies default media_type is used when not specified.
        Purpose: Ensure missing media_type defaults to image/jpeg.
        """
        print("Setup: Image without media_type...")
        images = [{"data": "some_data"}]  # No media_type
        
        print("Action: Converting to Kiro format...")
        result = convert_images_to_kiro_format(images)
        
        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0]["format"] == "jpeg"  # Default from "image/jpeg"
    
    def test_preserves_large_image_data(self):
        """
        What it does: Verifies large image data is preserved.
        Purpose: Ensure large images are not truncated.
        """
        print("Setup: Large image data...")
        large_data = "A" * 100000  # 100KB of data
        images = [{"media_type": "image/png", "data": large_data}]
        
        print("Action: Converting to Kiro format...")
        result = convert_images_to_kiro_format(images)
        
        print(f"Result data length: {len(result[0]['source']['bytes'])}")
        assert len(result[0]["source"]["bytes"]) == 100000
    
    # ==================================================================================
    # Data URL Prefix Stripping Tests (Issue #32 fix)
    # ==================================================================================
    
    def test_strips_data_url_prefix_jpeg(self):
        """
        What it does: Verifies that data URL prefix is stripped from JPEG image data.
        Purpose: Ensure Kiro API receives pure base64 without the data URL prefix (Issue #32 fix).
        
        Some clients send the full data URL in the data field instead of pure base64.
        Kiro API expects pure base64 without the "data:image/jpeg;base64," prefix.
        """
        print("Setup: Image with data URL prefix (JPEG)...")
        pure_base64 = "/9j/4AAQSkZJRg=="  # Sample JPEG base64
        images = [{"media_type": "image/jpeg", "data": f"data:image/jpeg;base64,{pure_base64}"}]
        
        print("Action: Converting to Kiro format...")
        result = convert_images_to_kiro_format(images)
        
        print(f"Result: {result}")
        print(f"Comparing bytes: Expected '{pure_base64}', Got '{result[0]['source']['bytes']}'")
        assert result[0]["source"]["bytes"] == pure_base64
        assert result[0]["format"] == "jpeg"
    
    def test_strips_data_url_prefix_png(self):
        """
        What it does: Verifies that data URL prefix is stripped from PNG image data.
        Purpose: Ensure PNG images with data URL prefix are handled correctly (Issue #32 fix).
        """
        print("Setup: Image with data URL prefix (PNG)...")
        pure_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        images = [{"media_type": "image/png", "data": f"data:image/png;base64,{pure_base64}"}]
        
        print("Action: Converting to Kiro format...")
        result = convert_images_to_kiro_format(images)
        
        print(f"Result: {result}")
        print(f"Comparing bytes: Expected pure base64, Got '{result[0]['source']['bytes'][:50]}...'")
        assert result[0]["source"]["bytes"] == pure_base64
        assert result[0]["format"] == "png"
    
    def test_extracts_media_type_from_data_url(self):
        """
        What it does: Verifies that media_type is extracted from data URL header.
        Purpose: Ensure media_type from data URL overrides the original media_type (Issue #32 fix).
        
        When data URL contains media type info, it should be used instead of the
        original media_type field (which might be incorrect or generic).
        """
        print("Setup: Image with mismatched media_type and data URL...")
        pure_base64 = "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"  # GIF
        # Original media_type says jpeg, but data URL says gif
        images = [{"media_type": "image/jpeg", "data": f"data:image/gif;base64,{pure_base64}"}]
        
        print("Action: Converting to Kiro format...")
        result = convert_images_to_kiro_format(images)
        
        print(f"Result: {result}")
        print("Checking that media_type from data URL is used...")
        assert result[0]["format"] == "gif"  # Should use gif from data URL, not jpeg
        assert result[0]["source"]["bytes"] == pure_base64
    
    def test_handles_malformed_data_url_no_comma(self):
        """
        What it does: Verifies graceful handling of malformed data URL without comma.
        Purpose: Ensure function doesn't crash on malformed data URLs (Issue #32 fix).
        
        If data URL is malformed (no comma separator), the function should
        log a warning and use the original data as-is.
        """
        print("Setup: Malformed data URL without comma...")
        malformed_data = "data:image/jpeg;base64_without_comma"
        images = [{"media_type": "image/jpeg", "data": malformed_data}]
        
        print("Action: Converting to Kiro format (should handle gracefully)...")
        result = convert_images_to_kiro_format(images)
        
        print(f"Result: {result}")
        # The function should still produce output, using the malformed data as-is
        # (since split(",", 1) will fail and the except block will catch it)
        assert len(result) == 1
        # After the fix, malformed data URL should be preserved as-is
        assert result[0]["source"]["bytes"] == malformed_data
    
    def test_preserves_pure_base64_data(self):
        """
        What it does: Verifies that pure base64 data (without prefix) is preserved.
        Purpose: Ensure normal base64 data is not modified (Issue #32 fix).
        
        When data is already pure base64 (doesn't start with "data:"),
        it should be passed through unchanged.
        """
        print("Setup: Pure base64 data without prefix...")
        pure_base64 = TEST_IMAGE_BASE64
        images = [{"media_type": "image/jpeg", "data": pure_base64}]
        
        print("Action: Converting to Kiro format...")
        result = convert_images_to_kiro_format(images)
        
        print(f"Result: {result}")
        print("Checking that pure base64 is preserved unchanged...")
        assert result[0]["source"]["bytes"] == pure_base64
        assert result[0]["format"] == "jpeg"
    
    def test_strips_data_url_prefix_webp(self):
        """
        What it does: Verifies that data URL prefix is stripped from WebP image data.
        Purpose: Ensure WebP images with data URL prefix are handled correctly (Issue #32 fix).
        """
        print("Setup: Image with data URL prefix (WebP)...")
        pure_base64 = "UklGRh4AAABXRUJQVlA4TBEAAAAvAAAAAAfQ//73v/+BiOh/AAA="
        images = [{"media_type": "image/webp", "data": f"data:image/webp;base64,{pure_base64}"}]
        
        print("Action: Converting to Kiro format...")
        result = convert_images_to_kiro_format(images)
        
        print(f"Result: {result}")
        assert result[0]["source"]["bytes"] == pure_base64
        assert result[0]["format"] == "webp"
    
    def test_handles_data_url_with_empty_base64(self):
        """
        What it does: Verifies handling of data URL with empty base64 part.
        Purpose: Ensure empty data after prefix is handled correctly (Issue #32 fix).
        
        Note: The function strips the prefix but doesn't re-check for empty data after stripping.
        This means an image with "data:image/jpeg;base64," will result in empty bytes.
        This is acceptable behavior as Kiro API will handle the validation.
        """
        print("Setup: Data URL with empty base64 part...")
        images = [{"media_type": "image/jpeg", "data": "data:image/jpeg;base64,"}]
        
        print("Action: Converting to Kiro format...")
        result = convert_images_to_kiro_format(images)
        
        print(f"Result: {result}")
        print("Checking that image is converted (with empty bytes)...")
        # The function strips the prefix but doesn't re-check for empty data
        # This results in an image with empty bytes
        assert len(result) == 1
        assert result[0]["source"]["bytes"] == ""
        assert result[0]["format"] == "jpeg"


# ==================================================================================================
# Tests for merge_adjacent_messages
# ==================================================================================================

class TestMergeAdjacentMessages:
    """Tests for merge_adjacent_messages function using UnifiedMessage."""
    
    def test_merges_adjacent_user_messages(self):
        """
        What it does: Verifies merging of adjacent user messages.
        Purpose: Ensure messages with the same role are merged.
        """
        print("Setup: Two consecutive user messages...")
        messages = [
            UnifiedMessage(role="user", content="Hello"),
            UnifiedMessage(role="user", content="World")
        ]
        
        print("Action: Merging messages...")
        result = merge_adjacent_messages(messages)
        
        print(f"Comparing length: Expected 1, Got {len(result)}")
        assert len(result) == 1
        assert "Hello" in result[0].content
        assert "World" in result[0].content
    
    def test_preserves_alternating_messages(self):
        """
        What it does: Verifies preservation of alternating messages.
        Purpose: Ensure different roles are not merged.
        """
        print("Setup: Alternating messages...")
        messages = [
            UnifiedMessage(role="user", content="Hello"),
            UnifiedMessage(role="assistant", content="Hi"),
            UnifiedMessage(role="user", content="How are you?")
        ]
        
        print("Action: Merging messages...")
        result = merge_adjacent_messages(messages)
        
        print(f"Comparing length: Expected 3, Got {len(result)}")
        assert len(result) == 3
    
    def test_handles_empty_list(self):
        """
        What it does: Verifies empty list handling.
        Purpose: Ensure empty list doesn't cause errors.
        """
        print("Setup: Empty list...")
        
        print("Action: Merging messages...")
        result = merge_adjacent_messages([])
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_handles_single_message(self):
        """
        What it does: Verifies single message handling.
        Purpose: Ensure single message is returned as-is.
        """
        print("Setup: Single message...")
        messages = [UnifiedMessage(role="user", content="Hello")]
        
        print("Action: Merging messages...")
        result = merge_adjacent_messages(messages)
        
        print(f"Comparing length: Expected 1, Got {len(result)}")
        assert len(result) == 1
        assert result[0].content == "Hello"
    
    def test_merges_multiple_adjacent_groups(self):
        """
        What it does: Verifies merging of multiple groups.
        Purpose: Ensure multiple groups of adjacent messages are merged.
        """
        print("Setup: Multiple groups of adjacent messages...")
        messages = [
            UnifiedMessage(role="user", content="A"),
            UnifiedMessage(role="user", content="B"),
            UnifiedMessage(role="assistant", content="C"),
            UnifiedMessage(role="assistant", content="D"),
            UnifiedMessage(role="user", content="E")
        ]
        
        print("Action: Merging messages...")
        result = merge_adjacent_messages(messages)
        
        print(f"Comparing length: Expected 3, Got {len(result)}")
        assert len(result) == 3
        assert result[0].role == "user"
        assert result[1].role == "assistant"
        assert result[2].role == "user"
    
    def test_merges_list_contents_correctly(self):
        """
        What it does: Verifies merging of list contents.
        Purpose: Ensure lists are merged correctly.
        """
        print("Setup: Two user messages with list content...")
        messages = [
            UnifiedMessage(role="user", content=[{"type": "text", "text": "Part 1"}]),
            UnifiedMessage(role="user", content=[{"type": "text", "text": "Part 2"}])
        ]
        
        print("Action: Merging messages...")
        result = merge_adjacent_messages(messages)
        
        print(f"Result: {result}")
        assert len(result) == 1
        assert isinstance(result[0].content, list)
        assert len(result[0].content) == 2
    
    def test_merges_adjacent_assistant_tool_calls(self):
        """
        What it does: Verifies merging of tool_calls when merging adjacent assistant messages.
        Purpose: Ensure tool_calls from all assistant messages are preserved when merging.
        
        This is a critical test for a bug where multiple assistant messages with tool_calls
        were sent in a row, and the second tool_call was lost.
        """
        print("Setup: Two assistant messages with different tool_calls...")
        messages = [
            UnifiedMessage(
                role="assistant",
                content="",
                tool_calls=[{
                    "id": "tooluse_first",
                    "type": "function",
                    "function": {"name": "shell", "arguments": '{"command": ["ls"]}'}
                }]
            ),
            UnifiedMessage(
                role="assistant",
                content="",
                tool_calls=[{
                    "id": "tooluse_second",
                    "type": "function",
                    "function": {"name": "shell", "arguments": '{"command": ["pwd"]}'}
                }]
            )
        ]
        
        print("Action: Merging messages...")
        result = merge_adjacent_messages(messages)
        
        print(f"Result: {result}")
        print(f"Comparing length: Expected 1, Got {len(result)}")
        assert len(result) == 1
        assert result[0].role == "assistant"
        
        print("Checking that both tool_calls are preserved...")
        assert result[0].tool_calls is not None
        print(f"Comparing tool_calls count: Expected 2, Got {len(result[0].tool_calls)}")
        assert len(result[0].tool_calls) == 2
        
        tool_ids = [tc["id"] for tc in result[0].tool_calls]
        print(f"Tool IDs: {tool_ids}")
        assert "tooluse_first" in tool_ids
        assert "tooluse_second" in tool_ids
    
    def test_merges_three_adjacent_assistant_tool_calls(self):
        """
        What it does: Verifies merging of tool_calls from three assistant messages.
        Purpose: Ensure all tool_calls are preserved when merging more than two messages.
        """
        print("Setup: Three assistant messages with tool_calls...")
        messages = [
            UnifiedMessage(role="assistant", content="", tool_calls=[
                {"id": "call_1", "type": "function", "function": {"name": "tool1", "arguments": "{}"}}
            ]),
            UnifiedMessage(role="assistant", content="", tool_calls=[
                {"id": "call_2", "type": "function", "function": {"name": "tool2", "arguments": "{}"}}
            ]),
            UnifiedMessage(role="assistant", content="", tool_calls=[
                {"id": "call_3", "type": "function", "function": {"name": "tool3", "arguments": "{}"}}
            ])
        ]
        
        print("Action: Merging messages...")
        result = merge_adjacent_messages(messages)
        
        print(f"Result: {result}")
        assert len(result) == 1
        assert len(result[0].tool_calls) == 3
        
        tool_ids = [tc["id"] for tc in result[0].tool_calls]
        print(f"Comparing tool IDs: Expected ['call_1', 'call_2', 'call_3'], Got {tool_ids}")
        assert tool_ids == ["call_1", "call_2", "call_3"]
    
    def test_merges_assistant_with_and_without_tool_calls(self):
        """
        What it does: Verifies merging of assistant with and without tool_calls.
        Purpose: Ensure tool_calls are correctly initialized when merging.
        """
        print("Setup: Assistant without tool_calls + assistant with tool_calls...")
        messages = [
            UnifiedMessage(role="assistant", content="Thinking...", tool_calls=None),
            UnifiedMessage(role="assistant", content="", tool_calls=[
                {"id": "call_1", "type": "function", "function": {"name": "tool1", "arguments": "{}"}}
            ])
        ]
        
        print("Action: Merging messages...")
        result = merge_adjacent_messages(messages)
        
        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0].tool_calls is not None
        print(f"Comparing tool_calls count: Expected 1, Got {len(result[0].tool_calls)}")
        assert len(result[0].tool_calls) == 1
        assert result[0].tool_calls[0]["id"] == "call_1"
    
    def test_merges_user_messages_with_tool_results(self):
        """
        What it does: Verifies merging of user messages with tool_results.
        Purpose: Ensure tool_results are preserved when merging user messages.
        """
        print("Setup: Two user messages with tool_results...")
        messages = [
            UnifiedMessage(role="user", content="", tool_results=[
                {"type": "tool_result", "tool_use_id": "call_1", "content": "Result 1"}
            ]),
            UnifiedMessage(role="user", content="", tool_results=[
                {"type": "tool_result", "tool_use_id": "call_2", "content": "Result 2"}
            ])
        ]
        
        print("Action: Merging messages...")
        result = merge_adjacent_messages(messages)
        
        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0].tool_results is not None
        assert len(result[0].tool_results) == 2


# ==================================================================================================
# Tests for ensure_first_message_is_user
# ==================================================================================================

class TestEnsureFirstMessageIsUser:
    """
    Tests for ensure_first_message_is_user function.
    
    This function ensures that conversations start with a user message, as required by Kiro API.
    If the first message is from assistant (or any non-user role), a minimal synthetic user
    message is prepended. This fixes issue #60 where conversations starting with assistant
    messages cause "Improperly formed request" errors.
    """
    
    def test_preserves_messages_starting_with_user(self):
        """
        What it does: Verifies that messages starting with user are unchanged.
        Purpose: Ensure correct conversations pass through unmodified.
        """
        print("Setup: Messages starting with user...")
        messages = [
            UnifiedMessage(role="user", content="Hello"),
            UnifiedMessage(role="assistant", content="Hi there")
        ]
        
        print("Action: Ensuring first message is user...")
        result = ensure_first_message_is_user(messages)
        
        print(f"Comparing length: Expected 2, Got {len(result)}")
        assert len(result) == 2
        assert result[0].role == "user"
        assert result[0].content == "Hello"
        assert result[1].role == "assistant"
    
    def test_prepends_synthetic_user_when_first_is_assistant(self):
        """
        What it does: Verifies synthetic user message is prepended when first message is assistant.
        Purpose: Fix issue #60 - conversations starting with assistant cause 400 errors.
        """
        print("Setup: Messages starting with assistant...")
        messages = [
            UnifiedMessage(role="assistant", content="Hello! I'm here to help."),
            UnifiedMessage(role="user", content="Hi, can you help me?")
        ]
        
        print("Action: Ensuring first message is user...")
        result = ensure_first_message_is_user(messages)
        
        print(f"Comparing length: Expected 3 (synthetic + 2 original), Got {len(result)}")
        assert len(result) == 3
        
        print("Checking first message is synthetic user...")
        assert result[0].role == "user"
        assert result[0].content == "(empty)"
        
        print("Checking original messages are preserved...")
        assert result[1].role == "assistant"
        assert result[1].content == "Hello! I'm here to help."
        assert result[2].role == "user"
        assert result[2].content == "Hi, can you help me?"
    
    def test_handles_empty_list(self):
        """
        What it does: Verifies empty list handling.
        Purpose: Ensure empty input returns empty output without errors.
        """
        print("Setup: Empty list...")
        
        print("Action: Ensuring first message is user...")
        result = ensure_first_message_is_user([])
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_handles_single_assistant_message(self):
        """
        What it does: Verifies single assistant message gets synthetic user prepended.
        Purpose: Handle edge case of conversation with only assistant message.
        """
        print("Setup: Single assistant message...")
        messages = [
            UnifiedMessage(role="assistant", content="Previous response to continue...")
        ]
        
        print("Action: Ensuring first message is user...")
        result = ensure_first_message_is_user(messages)
        
        print(f"Comparing length: Expected 2 (synthetic + original), Got {len(result)}")
        assert len(result) == 2
        assert result[0].role == "user"
        assert result[0].content == "(empty)"
        assert result[1].role == "assistant"
    
    def test_handles_assistant_user_assistant_sequence(self):
        """
        What it does: Verifies synthetic user is prepended for assistant-first sequences.
        Purpose: Ensure complex conversation structures are handled correctly.
        """
        print("Setup: Assistant → User → Assistant sequence...")
        messages = [
            UnifiedMessage(role="assistant", content="First response"),
            UnifiedMessage(role="user", content="Question"),
            UnifiedMessage(role="assistant", content="Second response")
        ]
        
        print("Action: Ensuring first message is user...")
        result = ensure_first_message_is_user(messages)
        
        print(f"Comparing length: Expected 4 (synthetic + 3 original), Got {len(result)}")
        assert len(result) == 4
        assert result[0].role == "user"
        assert result[0].content == "(empty)"
        assert result[1].role == "assistant"
        assert result[2].role == "user"
        assert result[3].role == "assistant"
    
    def test_preserves_tool_calls_in_assistant_message(self):
        """
        What it does: Verifies tool_calls are preserved when prepending synthetic user.
        Purpose: Ensure tool calling functionality is not broken by the fix.
        """
        print("Setup: Assistant message with tool_calls...")
        messages = [
            UnifiedMessage(
                role="assistant",
                content="Let me check that for you.",
                tool_calls=[{
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"location": "Moscow"}'}
                }]
            )
        ]
        
        print("Action: Ensuring first message is user...")
        result = ensure_first_message_is_user(messages)
        
        print("Checking synthetic user was prepended...")
        assert len(result) == 2
        assert result[0].role == "user"
        assert result[0].content == "(empty)"
        
        print("Checking tool_calls are preserved...")
        assert result[1].role == "assistant"
        assert result[1].tool_calls is not None
        assert len(result[1].tool_calls) == 1
        assert result[1].tool_calls[0]["id"] == "call_123"
    
    def test_preserves_images_in_messages(self):
        """
        What it does: Verifies images are preserved when prepending synthetic user.
        Purpose: Ensure multimodal functionality is not broken by the fix.
        """
        print("Setup: Assistant message followed by user with images...")
        messages = [
            UnifiedMessage(role="assistant", content="What's in this image?"),
            UnifiedMessage(
                role="user",
                content="Here it is",
                images=[{"media_type": "image/jpeg", "data": "base64data"}]
            )
        ]
        
        print("Action: Ensuring first message is user...")
        result = ensure_first_message_is_user(messages)
        
        print("Checking images are preserved...")
        assert len(result) == 3
        assert result[0].role == "user"  # Synthetic
        assert result[2].images is not None
        assert len(result[2].images) == 1
    
    def test_uses_minimal_content_for_synthetic_message(self):
        """
        What it does: Verifies synthetic message uses minimal content ("(empty)").
        Purpose: Ensure minimal token usage and avoid disrupting conversation context.
        """
        print("Setup: Assistant-first conversation...")
        messages = [
            UnifiedMessage(role="assistant", content="Hello")
        ]
        
        print("Action: Ensuring first message is user...")
        result = ensure_first_message_is_user(messages)
        
        print("Checking synthetic message content...")
        assert result[0].content == "(empty)"
        print("✓ Synthetic message uses minimal content (matches LiteLLM behavior)")


# ==================================================================================================
# Tests for normalize_message_roles
# ==================================================================================================

class TestNormalizeMessageRoles:
    """
    Tests for normalize_message_roles function.
    
    This function converts all unknown roles (developer, system, moderator, etc.)
    to 'user' role to maintain Kiro API compatibility. This is part of the fix
    for Issue #64 where Codex App sends 'developer' role messages.
    """
    
    def test_converts_developer_role_to_user(self):
        """
        What it does: Verifies conversion of 'developer' role to 'user'.
        Purpose: Fix for Issue #64 - Codex App uses 'developer' role which must be
                 converted to 'user' to maintain Kiro API compatibility.
        """
        print("Setup: Message with 'developer' role (Codex App)...")
        messages = [
            UnifiedMessage(role="developer", content="<permissions>sandbox enabled</permissions>"),
            UnifiedMessage(role="user", content="test")
        ]
        
        print("Action: Normalizing roles...")
        result = normalize_message_roles(messages)
        
        print(f"Comparing length: Expected 2, Got {len(result)}")
        assert len(result) == 2
        print("Checking that developer was converted to user...")
        assert result[0].role == "user"
        assert result[0].content == "<permissions>sandbox enabled</permissions>"
        print("Checking that original user role is preserved...")
        assert result[1].role == "user"
    
    def test_converts_multiple_unknown_roles_to_user(self):
        """
        What it does: Verifies conversion of multiple different unknown roles.
        Purpose: Ensure all unknown roles (developer, system, moderator) are normalized.
        """
        print("Setup: Messages with multiple unknown roles...")
        messages = [
            UnifiedMessage(role="developer", content="Dev context"),
            UnifiedMessage(role="system", content="System context"),
            UnifiedMessage(role="moderator", content="Moderation note"),
            UnifiedMessage(role="user", content="Question")
        ]
        
        print("Action: Normalizing roles...")
        result = normalize_message_roles(messages)
        
        print(f"Comparing length: Expected 4, Got {len(result)}")
        assert len(result) == 4
        print("Checking that all roles are now 'user'...")
        assert all(msg.role == "user" for msg in result)
        print("Checking that content is preserved...")
        assert result[0].content == "Dev context"
        assert result[1].content == "System context"
        assert result[2].content == "Moderation note"
        assert result[3].content == "Question"
    
    def test_preserves_user_and_assistant_roles(self):
        """
        What it does: Verifies that user and assistant roles are not modified.
        Purpose: Ensure only unknown roles are converted, not valid ones.
        """
        print("Setup: Messages with valid roles...")
        messages = [
            UnifiedMessage(role="user", content="Hello"),
            UnifiedMessage(role="assistant", content="Hi"),
            UnifiedMessage(role="user", content="How are you?")
        ]
        
        print("Action: Normalizing roles...")
        result = normalize_message_roles(messages)
        
        print(f"Comparing length: Expected 3, Got {len(result)}")
        assert len(result) == 3
        print("Checking that roles are unchanged...")
        assert result[0].role == "user"
        assert result[1].role == "assistant"
        assert result[2].role == "user"
        print("Checking that content is unchanged...")
        assert result[0].content == "Hello"
        assert result[1].content == "Hi"
        assert result[2].content == "How are you?"
    
    def test_preserves_tool_calls_when_normalizing(self):
        """
        What it does: Verifies tool_calls are preserved when converting role.
        Purpose: Ensure all message fields are preserved during normalization.
        """
        print("Setup: Developer message with tool_calls...")
        messages = [
            UnifiedMessage(
                role="developer",
                content="Context",
                tool_calls=[{"id": "call_123", "function": {"name": "bash", "arguments": "{}"}}]
            )
        ]
        
        print("Action: Normalizing roles...")
        result = normalize_message_roles(messages)
        
        print(f"Comparing length: Expected 1, Got {len(result)}")
        assert len(result) == 1
        print("Checking that role was converted...")
        assert result[0].role == "user"
        print("Checking that tool_calls are preserved...")
        assert result[0].tool_calls is not None
        assert len(result[0].tool_calls) == 1
        assert result[0].tool_calls[0]["id"] == "call_123"
    
    def test_preserves_tool_results_when_normalizing(self):
        """
        What it does: Verifies tool_results are preserved when converting role.
        Purpose: Ensure tool_results field is preserved during normalization.
        """
        print("Setup: Developer message with tool_results...")
        messages = [
            UnifiedMessage(
                role="developer",
                content="Result",
                tool_results=[{"type": "tool_result", "tool_use_id": "call_123", "content": "Output"}]
            )
        ]
        
        print("Action: Normalizing roles...")
        result = normalize_message_roles(messages)
        
        print(f"Comparing length: Expected 1, Got {len(result)}")
        assert len(result) == 1
        print("Checking that role was converted...")
        assert result[0].role == "user"
        print("Checking that tool_results are preserved...")
        assert result[0].tool_results is not None
        assert len(result[0].tool_results) == 1
        assert result[0].tool_results[0]["tool_use_id"] == "call_123"
    
    def test_preserves_images_when_normalizing(self):
        """
        What it does: Verifies images are preserved when converting role.
        Purpose: Ensure images field is preserved during normalization.
        """
        print("Setup: Developer message with images...")
        messages = [
            UnifiedMessage(
                role="developer",
                content="Screenshot",
                images=[{"media_type": "image/png", "data": "base64data"}]
            )
        ]
        
        print("Action: Normalizing roles...")
        result = normalize_message_roles(messages)
        
        print(f"Comparing length: Expected 1, Got {len(result)}")
        assert len(result) == 1
        print("Checking that role was converted...")
        assert result[0].role == "user"
        print("Checking that images are preserved...")
        assert result[0].images is not None
        assert len(result[0].images) == 1
        assert result[0].images[0]["media_type"] == "image/png"
    
    def test_handles_empty_list(self):
        """
        What it does: Verifies empty list handling.
        Purpose: Ensure empty input returns empty output.
        """
        print("Setup: Empty list...")
        
        print("Action: Normalizing roles...")
        result = normalize_message_roles([])
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_handles_single_message(self):
        """
        What it does: Verifies single message handling.
        Purpose: Ensure single message is processed correctly.
        """
        print("Setup: Single developer message...")
        messages = [UnifiedMessage(role="developer", content="Solo")]
        
        print("Action: Normalizing roles...")
        result = normalize_message_roles(messages)
        
        print(f"Comparing length: Expected 1, Got {len(result)}")
        assert len(result) == 1
        print("Checking that role was converted...")
        assert result[0].role == "user"
        assert result[0].content == "Solo"


# ==================================================================================================
# Tests for ensure_alternating_roles
# ==================================================================================================

class TestEnsureAlternatingRoles:
    """
    Tests for ensure_alternating_roles function.
    
    This function ensures alternating user/assistant roles by inserting synthetic
    assistant messages with "(empty)" content between consecutive user messages.
    This is part of the fix for Issue #64 where multiple 'developer' roles
    (converted to 'user') create consecutive userInputMessage entries.
    """
    
    def test_inserts_synthetic_assistant_between_two_consecutive_users(self):
        """
        What it does: Verifies insertion of synthetic assistant between two user messages.
        Purpose: Ensure Kiro API requirement of alternating roles is maintained.
        """
        print("Setup: Two consecutive user messages...")
        messages = [
            UnifiedMessage(role="user", content="First"),
            UnifiedMessage(role="user", content="Second")
        ]
        
        print("Action: Ensuring alternating roles...")
        result = ensure_alternating_roles(messages)
        
        print(f"Comparing length: Expected 3 (2 user + 1 synthetic), Got {len(result)}")
        assert len(result) == 3
        print("Checking alternation pattern...")
        assert result[0].role == "user"
        assert result[0].content == "First"
        assert result[1].role == "assistant"
        assert result[1].content == "(empty)"
        assert result[2].role == "user"
        assert result[2].content == "Second"
    
    def test_inserts_multiple_synthetic_assistants_for_four_consecutive_users(self):
        """
        What it does: Verifies insertion of multiple synthetic assistants.
        Purpose: Fix for Issue #64 - handle multiple consecutive developer messages.
        """
        print("Setup: Four consecutive user messages...")
        messages = [
            UnifiedMessage(role="user", content="First"),
            UnifiedMessage(role="user", content="Second"),
            UnifiedMessage(role="user", content="Third"),
            UnifiedMessage(role="user", content="Fourth")
        ]
        
        print("Action: Ensuring alternating roles...")
        result = ensure_alternating_roles(messages)
        
        print(f"Comparing length: Expected 7 (4 user + 3 synthetic), Got {len(result)}")
        assert len(result) == 7
        print("Checking alternation pattern...")
        assert result[0].role == "user" and result[0].content == "First"
        assert result[1].role == "assistant" and result[1].content == "(empty)"
        assert result[2].role == "user" and result[2].content == "Second"
        assert result[3].role == "assistant" and result[3].content == "(empty)"
        assert result[4].role == "user" and result[4].content == "Third"
        assert result[5].role == "assistant" and result[5].content == "(empty)"
        assert result[6].role == "user" and result[6].content == "Fourth"
    
    def test_preserves_already_alternating_messages(self):
        """
        What it does: Verifies already alternating messages are not modified.
        Purpose: Ensure function only inserts synthetic messages when needed.
        """
        print("Setup: Already alternating messages...")
        messages = [
            UnifiedMessage(role="user", content="Hello"),
            UnifiedMessage(role="assistant", content="Hi"),
            UnifiedMessage(role="user", content="How are you?"),
            UnifiedMessage(role="assistant", content="Fine")
        ]
        
        print("Action: Ensuring alternating roles...")
        result = ensure_alternating_roles(messages)
        
        print(f"Comparing length: Expected 4 (no changes), Got {len(result)}")
        assert len(result) == 4
        print("Checking that messages are unchanged...")
        assert result[0].role == "user" and result[0].content == "Hello"
        assert result[1].role == "assistant" and result[1].content == "Hi"
        assert result[2].role == "user" and result[2].content == "How are you?"
        assert result[3].role == "assistant" and result[3].content == "Fine"
    
    def test_handles_multiple_groups_of_consecutive_users(self):
        """
        What it does: Verifies handling of multiple groups of consecutive users.
        Purpose: Ensure function handles complex conversation patterns.
        """
        print("Setup: Multiple groups of consecutive users...")
        messages = [
            UnifiedMessage(role="user", content="A"),
            UnifiedMessage(role="user", content="B"),
            UnifiedMessage(role="assistant", content="C"),
            UnifiedMessage(role="user", content="D"),
            UnifiedMessage(role="user", content="E"),
            UnifiedMessage(role="user", content="F")
        ]
        
        print("Action: Ensuring alternating roles...")
        result = ensure_alternating_roles(messages)
        
        print(f"Comparing length: Expected 9 (6 original + 3 synthetic), Got {len(result)}")
        assert len(result) == 9
        print("Checking first group (A, synthetic, B)...")
        assert result[0].role == "user" and result[0].content == "A"
        assert result[1].role == "assistant" and result[1].content == "(empty)"
        assert result[2].role == "user" and result[2].content == "B"
        print("Checking real assistant...")
        assert result[3].role == "assistant" and result[3].content == "C"
        print("Checking second group (D, synthetic, E, synthetic, F)...")
        assert result[4].role == "user" and result[4].content == "D"
        assert result[5].role == "assistant" and result[5].content == "(empty)"
        assert result[6].role == "user" and result[6].content == "E"
        assert result[7].role == "assistant" and result[7].content == "(empty)"
        assert result[8].role == "user" and result[8].content == "F"
    
    def test_handles_empty_list(self):
        """
        What it does: Verifies empty list handling.
        Purpose: Ensure empty input returns empty output.
        """
        print("Setup: Empty list...")
        
        print("Action: Ensuring alternating roles...")
        result = ensure_alternating_roles([])
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_handles_single_message(self):
        """
        What it does: Verifies single message handling.
        Purpose: Ensure single message is returned unchanged.
        """
        print("Setup: Single user message...")
        messages = [UnifiedMessage(role="user", content="Solo")]
        
        print("Action: Ensuring alternating roles...")
        result = ensure_alternating_roles(messages)
        
        print(f"Comparing length: Expected 1 (no changes), Got {len(result)}")
        assert len(result) == 1
        assert result[0].role == "user"
        assert result[0].content == "Solo"
    
    def test_preserves_tool_results_in_original_messages(self):
        """
        What it does: Verifies tool_results are preserved in original messages.
        Purpose: Ensure synthetic assistants don't have tool content, but originals do.
        """
        print("Setup: Two consecutive user messages with tool_results...")
        messages = [
            UnifiedMessage(
                role="user",
                content="First",
                tool_results=[{"type": "tool_result", "tool_use_id": "call_1", "content": "Result 1"}]
            ),
            UnifiedMessage(
                role="user",
                content="Second",
                tool_results=[{"type": "tool_result", "tool_use_id": "call_2", "content": "Result 2"}]
            )
        ]
        
        print("Action: Ensuring alternating roles...")
        result = ensure_alternating_roles(messages)
        
        print(f"Comparing length: Expected 3, Got {len(result)}")
        assert len(result) == 3
        print("Checking that synthetic assistant has no tool_results...")
        assert result[1].role == "assistant"
        assert result[1].tool_results is None
        print("Checking that original messages preserved tool_results...")
        assert result[0].tool_results is not None
        assert len(result[0].tool_results) == 1
        assert result[2].tool_results is not None
        assert len(result[2].tool_results) == 1
    
    def test_preserves_images_in_original_messages(self):
        """
        What it does: Verifies images are preserved in original messages.
        Purpose: Ensure synthetic assistants don't have images, but originals do.
        """
        print("Setup: Two consecutive user messages with images...")
        messages = [
            UnifiedMessage(
                role="user",
                content="First",
                images=[{"media_type": "image/png", "data": "data1"}]
            ),
            UnifiedMessage(
                role="user",
                content="Second",
                images=[{"media_type": "image/jpeg", "data": "data2"}]
            )
        ]
        
        print("Action: Ensuring alternating roles...")
        result = ensure_alternating_roles(messages)
        
        print(f"Comparing length: Expected 3, Got {len(result)}")
        assert len(result) == 3
        print("Checking that synthetic assistant has no images...")
        assert result[1].role == "assistant"
        assert result[1].images is None
        print("Checking that original messages preserved images...")
        assert result[0].images is not None
        assert len(result[0].images) == 1
        assert result[2].images is not None
        assert len(result[2].images) == 1


# ==================================================================================================
# Tests for normalize_message_roles + ensure_alternating_roles integration
# ==================================================================================================

class TestNormalizeAndAlternatingIntegration:
    """
    Integration tests for normalize_message_roles + ensure_alternating_roles.
    
    These tests verify the complete pipeline for Issue #64 fix:
    1. Unknown roles (developer, system) are normalized to 'user'
    2. Consecutive user messages get synthetic assistant messages inserted
    """
    
    def test_developer_messages_are_normalized_and_alternated(self):
        """
        What it does: Verifies complete pipeline for Issue #64.
        Purpose: Ensure multiple developer messages are normalized and alternated correctly.
        """
        print("Setup: Multiple developer messages + user question...")
        messages = [
            UnifiedMessage(role="developer", content="Context 1"),
            UnifiedMessage(role="developer", content="Context 2"),
            UnifiedMessage(role="developer", content="Context 3"),
            UnifiedMessage(role="user", content="Question")
        ]
        
        print("Action: Normalizing roles...")
        normalized = normalize_message_roles(messages)
        print(f"After normalization: {[msg.role for msg in normalized]}")
        
        print("Action: Ensuring alternating roles...")
        result = ensure_alternating_roles(normalized)
        
        print(f"Comparing length: Expected 7 (4 user + 3 synthetic), Got {len(result)}")
        assert len(result) == 7
        print("Checking alternation pattern...")
        assert result[0].role == "user" and result[0].content == "Context 1"
        assert result[1].role == "assistant" and result[1].content == "(empty)"
        assert result[2].role == "user" and result[2].content == "Context 2"
        assert result[3].role == "assistant" and result[3].content == "(empty)"
        assert result[4].role == "user" and result[4].content == "Context 3"
        assert result[5].role == "assistant" and result[5].content == "(empty)"
        assert result[6].role == "user" and result[6].content == "Question"
    
    def test_mixed_roles_are_normalized_and_alternated(self):
        """
        What it does: Verifies pipeline with mixed roles (developer, system, user, assistant).
        Purpose: Ensure complex conversation patterns are handled correctly.
        """
        print("Setup: Mixed roles conversation...")
        messages = [
            UnifiedMessage(role="system", content="System"),
            UnifiedMessage(role="developer", content="Dev"),
            UnifiedMessage(role="user", content="User1"),
            UnifiedMessage(role="assistant", content="Assistant1"),
            UnifiedMessage(role="developer", content="Dev2"),
            UnifiedMessage(role="user", content="User2")
        ]
        
        print("Action: Normalizing roles...")
        normalized = normalize_message_roles(messages)
        print(f"After normalization: {[msg.role for msg in normalized]}")
        
        print("Action: Ensuring alternating roles...")
        result = ensure_alternating_roles(normalized)
        
        print(f"Result length: {len(result)}")
        print(f"Result roles: {[msg.role for msg in result]}")
        
        # After normalization: all system/developer → user
        # [user, user, user, assistant, user, user]
        # After alternation: insert synthetic between consecutive users
        # [user, synthetic, user, synthetic, user, assistant, user, synthetic, user]
        assert len(result) == 9
        print("Checking that all system/developer were converted to user...")
        assert result[0].role == "user" and result[0].content == "System"
        assert result[1].role == "assistant" and result[1].content == "(empty)"
        assert result[2].role == "user" and result[2].content == "Dev"
        assert result[3].role == "assistant" and result[3].content == "(empty)"
        assert result[4].role == "user" and result[4].content == "User1"
        assert result[5].role == "assistant" and result[5].content == "Assistant1"
        assert result[6].role == "user" and result[6].content == "Dev2"
        assert result[7].role == "assistant" and result[7].content == "(empty)"
        assert result[8].role == "user" and result[8].content == "User2"


# ==================================================================================================
# Tests for ensure_assistant_before_tool_results
# ==================================================================================================

class TestEnsureAssistantBeforeToolResults:
    """
    Tests for ensure_assistant_before_tool_results function.
    
    This function handles the case when clients (like Cline/Roo/Cursor) send truncated
    conversations with tool_results but without the preceding assistant message
    that contains the tool_calls. Since we don't know the original tool name,
    we strip the orphaned tool_results to avoid Kiro API rejection.
    """
    
    def test_returns_empty_list_for_empty_input(self):
        """
        What it does: Verifies empty list handling.
        Purpose: Ensure empty input returns empty output.
        """
        print("Setup: Empty list...")
        
        print("Action: Processing messages...")
        result, stripped = ensure_assistant_before_tool_results([])
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
        assert stripped is False
    
    def test_preserves_messages_without_tool_results(self):
        """
        What it does: Verifies messages without tool_results are unchanged.
        Purpose: Ensure regular messages pass through unmodified.
        """
        print("Setup: Messages without tool_results...")
        messages = [
            UnifiedMessage(role="user", content="Hello"),
            UnifiedMessage(role="assistant", content="Hi there"),
            UnifiedMessage(role="user", content="How are you?")
        ]
        
        print("Action: Processing messages...")
        result, stripped = ensure_assistant_before_tool_results(messages)
        
        print(f"Comparing length: Expected 3, Got {len(result)}")
        assert len(result) == 3
        assert result[0].content == "Hello"
        assert result[1].content == "Hi there"
        assert result[2].content == "How are you?"
        assert stripped is False
    
    def test_preserves_tool_results_with_preceding_assistant(self):
        """
        What it does: Verifies tool_results are preserved when assistant with tool_calls precedes.
        Purpose: Ensure valid tool_results are not stripped.
        """
        print("Setup: Valid conversation with assistant tool_calls followed by user tool_results...")
        messages = [
            UnifiedMessage(role="user", content="Call a tool"),
            UnifiedMessage(
                role="assistant",
                content="",
                tool_calls=[{
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"location": "Moscow"}'}
                }]
            ),
            UnifiedMessage(
                role="user",
                content="",
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "call_123",
                    "content": "Weather is sunny"
                }]
            )
        ]
        
        print("Action: Processing messages...")
        result, stripped = ensure_assistant_before_tool_results(messages)
        
        print(f"Result: {result}")
        print(f"Comparing length: Expected 3, Got {len(result)}")
        assert len(result) == 3
        
        print("Checking that tool_results are preserved...")
        assert result[2].tool_results is not None
        assert len(result[2].tool_results) == 1
        assert result[2].tool_results[0]["tool_use_id"] == "call_123"
        assert stripped is False
    
    def test_strips_orphaned_tool_results_at_start(self):
        """
        What it does: Verifies orphaned tool_results at the start are converted to text.
        Purpose: Ensure tool_results without preceding assistant are converted to text representation.
        
        This is the critical bug fix test - when a client sends a truncated
        conversation starting with tool_results, they should be converted to text.
        """
        print("Setup: Conversation starting with orphaned tool_results...")
        messages = [
            UnifiedMessage(
                role="user",
                content="",
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "call_orphan",
                    "content": "Orphaned result"
                }]
            ),
            UnifiedMessage(role="user", content="Continue the conversation")
        ]
        
        print("Action: Processing messages...")
        result, converted = ensure_assistant_before_tool_results(messages)
        
        print(f"Result: {result}")
        print(f"Comparing length: Expected 2, Got {len(result)}")
        assert len(result) == 2
        
        print("Checking that orphaned tool_results are converted to text...")
        assert result[0].tool_results is None
        
        print("Checking that content now contains the tool result as text...")
        print(f"Content: '{result[0].content}'")
        assert "[Tool Result (call_orphan)]" in result[0].content
        assert "Orphaned result" in result[0].content
        
        assert result[1].content == "Continue the conversation"
        assert converted is True
    
    def test_converts_tool_results_after_assistant_without_tool_calls(self):
        """
        What it does: Verifies tool_results are converted when preceding assistant has no tool_calls.
        Purpose: Ensure tool_results require assistant with tool_calls, not just any assistant.
        """
        print("Setup: Assistant without tool_calls followed by user with tool_results...")
        messages = [
            UnifiedMessage(role="user", content="Hello"),
            UnifiedMessage(role="assistant", content="Let me think...", tool_calls=None),
            UnifiedMessage(
                role="user",
                content="",
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "call_123",
                    "content": "Result"
                }]
            )
        ]
        
        print("Action: Processing messages...")
        result, converted = ensure_assistant_before_tool_results(messages)
        
        print(f"Result: {result}")
        print("Checking that tool_results are converted to text...")
        assert result[2].tool_results is None
        
        print(f"Content after conversion: '{result[2].content}'")
        assert "[Tool Result (call_123)]" in result[2].content
        assert "Result" in result[2].content
        
        assert converted is True
    
    def test_converts_tool_results_after_user_message(self):
        """
        What it does: Verifies tool_results are converted when preceded by user message.
        Purpose: Ensure tool_results require assistant, not user.
        """
        print("Setup: User message followed by user with tool_results...")
        messages = [
            UnifiedMessage(role="user", content="First message"),
            UnifiedMessage(
                role="user",
                content="",
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "call_123",
                    "content": "Result"
                }]
            )
        ]
        
        print("Action: Processing messages...")
        result, converted = ensure_assistant_before_tool_results(messages)
        
        print(f"Result: {result}")
        print("Checking that tool_results are converted to text...")
        assert result[1].tool_results is None
        
        print(f"Content after conversion: '{result[1].content}'")
        assert "[Tool Result (call_123)]" in result[1].content
        assert "Result" in result[1].content
        
        assert converted is True
    
    def test_preserves_content_when_converting_tool_results(self):
        """
        What it does: Verifies message content is preserved and tool_results are appended as text.
        Purpose: Ensure original content is kept and tool_results are converted to text representation.
        """
        print("Setup: Message with both content and orphaned tool_results...")
        messages = [
            UnifiedMessage(
                role="user",
                content="Here is some context",
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "call_123",
                    "content": "Result"
                }]
            )
        ]
        
        print("Action: Processing messages...")
        result, converted = ensure_assistant_before_tool_results(messages)
        
        print(f"Result: {result}")
        print(f"Content after conversion: '{result[0].content}'")
        
        print("Checking that original content is preserved...")
        assert "Here is some context" in result[0].content
        
        print("Checking that tool_results are converted to text and appended...")
        assert "[Tool Result (call_123)]" in result[0].content
        assert "Result" in result[0].content
        
        print("Checking that tool_results field is removed...")
        assert result[0].tool_results is None
        
        assert converted is True
    
    def test_preserves_tool_calls_when_converting_tool_results(self):
        """
        What it does: Verifies tool_calls are preserved when tool_results are converted.
        Purpose: Ensure only tool_results are converted, tool_calls stay.
        """
        print("Setup: Message with tool_calls and orphaned tool_results...")
        messages = [
            UnifiedMessage(
                role="assistant",
                content="",
                tool_calls=[{
                    "id": "call_new",
                    "type": "function",
                    "function": {"name": "new_tool", "arguments": "{}"}
                }],
                tool_results=[{  # This shouldn't happen but let's test it
                    "type": "tool_result",
                    "tool_use_id": "call_old",
                    "content": "Old result"
                }]
            )
        ]
        
        print("Action: Processing messages...")
        result, converted = ensure_assistant_before_tool_results(messages)
        
        print(f"Result: {result}")
        print("Checking that tool_calls are preserved...")
        assert result[0].tool_calls is not None
        assert len(result[0].tool_calls) == 1
        
        print("Checking that tool_results are converted to text...")
        assert result[0].tool_results is None
        assert "[Tool Result (call_old)]" in result[0].content
        assert "Old result" in result[0].content
        
        assert converted is True
    
    def test_handles_multiple_orphaned_tool_results(self):
        """
        What it does: Verifies multiple orphaned tool_results are all converted.
        Purpose: Ensure all tool_results in the list are converted to text.
        """
        print("Setup: Message with multiple orphaned tool_results...")
        messages = [
            UnifiedMessage(
                role="user",
                content="",
                tool_results=[
                    {"type": "tool_result", "tool_use_id": "call_1", "content": "Result 1"},
                    {"type": "tool_result", "tool_use_id": "call_2", "content": "Result 2"},
                    {"type": "tool_result", "tool_use_id": "call_3", "content": "Result 3"}
                ]
            )
        ]
        
        print("Action: Processing messages...")
        result, converted = ensure_assistant_before_tool_results(messages)
        
        print(f"Result: {result}")
        print(f"Content after conversion: '{result[0].content}'")
        
        print("Checking that all tool_results are converted to text...")
        assert result[0].tool_results is None
        assert "[Tool Result (call_1)]" in result[0].content
        assert "Result 1" in result[0].content
        assert "[Tool Result (call_2)]" in result[0].content
        assert "Result 2" in result[0].content
        assert "[Tool Result (call_3)]" in result[0].content
        assert "Result 3" in result[0].content
        
        assert converted is True
    
    # ==================================================================================
    # New tests for tool_results conversion (PR #49)
    # ==================================================================================
    
    def test_conversion_preserves_images(self):
        """
        What it does: Verifies that images field is preserved when converting tool_results.
        Purpose: Ensure images=msg.images is set correctly in converted message.
        """
        print("Setup: Message with images and orphaned tool_results...")
        messages = [
            UnifiedMessage(
                role="user",
                content="Here's an image and tool result",
                images=[{"media_type": "image/jpeg", "data": "image_data"}],
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "call_123",
                    "content": "Tool output"
                }]
            )
        ]
        
        print("Action: Processing messages...")
        result, converted = ensure_assistant_before_tool_results(messages)
        
        print(f"Result: {result}")
        print("Checking that images are preserved...")
        assert result[0].images is not None
        assert len(result[0].images) == 1
        assert result[0].images[0]["media_type"] == "image/jpeg"
        
        print("Checking that tool_results are converted...")
        assert result[0].tool_results is None
        assert "[Tool Result" in result[0].content
        
        assert converted is True
    
    def test_conversion_appends_to_existing_content(self):
        """
        What it does: Verifies tool_results are appended with double newline.
        Purpose: Ensure formatting: "original\\n\\n[Tool Result]\\ndata".
        """
        print("Setup: Message with content and orphaned tool_results...")
        messages = [
            UnifiedMessage(
                role="user",
                content="Original content here",
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "call_abc",
                    "content": "Tool data"
                }]
            )
        ]
        
        print("Action: Processing messages...")
        result, converted = ensure_assistant_before_tool_results(messages)
        
        print(f"Result content: '{result[0].content}'")
        
        print("Checking formatting...")
        assert "Original content here" in result[0].content
        assert "[Tool Result (call_abc)]" in result[0].content
        assert "Tool data" in result[0].content
        
        # Check double newline separator
        assert "\n\n" in result[0].content
        
        assert converted is True
    
    def test_conversion_handles_empty_original_content(self):
        """
        What it does: Verifies conversion works when original content is empty.
        Purpose: Ensure that only tool_results text is used when content is empty.
        """
        print("Setup: Message with empty content and orphaned tool_results...")
        messages = [
            UnifiedMessage(
                role="user",
                content="",
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "call_xyz",
                    "content": "Only tool result"
                }]
            )
        ]
        
        print("Action: Processing messages...")
        result, converted = ensure_assistant_before_tool_results(messages)
        
        print(f"Result content: '{result[0].content}'")
        
        print("Checking that only tool result text is present...")
        assert "[Tool Result (call_xyz)]" in result[0].content
        assert "Only tool result" in result[0].content
        
        # Should not have leading/trailing whitespace from empty original content
        assert result[0].content.strip() == result[0].content
        
        assert converted is True
    
    def test_conversion_returns_correct_flag(self):
        """
        What it does: Verifies that converted_any_tool_results flag is returned correctly.
        Purpose: Ensure return value accurately reflects whether conversion happened.
        """
        print("Setup: Two scenarios - with and without orphaned tool_results...")
        
        # Scenario 1: With orphaned tool_results (should return True)
        messages_with_orphaned = [
            UnifiedMessage(
                role="user",
                content="Test",
                tool_results=[{"type": "tool_result", "tool_use_id": "call_1", "content": "Result"}]
            )
        ]
        
        print("Action: Processing messages with orphaned tool_results...")
        result1, converted1 = ensure_assistant_before_tool_results(messages_with_orphaned)
        
        print(f"Comparing converted flag: Expected True, Got {converted1}")
        assert converted1 is True
        
        # Scenario 2: Without orphaned tool_results (should return False)
        messages_without_orphaned = [
            UnifiedMessage(role="user", content="Hello"),
            UnifiedMessage(
                role="assistant",
                content="",
                tool_calls=[{"id": "call_1", "type": "function", "function": {"name": "tool", "arguments": "{}"}}]
            ),
            UnifiedMessage(
                role="user",
                content="",
                tool_results=[{"type": "tool_result", "tool_use_id": "call_1", "content": "Result"}]
            )
        ]
        
        print("Action: Processing messages without orphaned tool_results...")
        result2, converted2 = ensure_assistant_before_tool_results(messages_without_orphaned)
        
        print(f"Comparing converted flag: Expected False, Got {converted2}")
        assert converted2 is False
    
    def test_normal_tool_results_unchanged(self):
        """
        What it does: Verifies that normal (non-orphaned) tool_results are NOT converted.
        Purpose: CRITICAL - ensure 99% of cases (normal tool use) have zero change.
        
        This is the most important backward compatibility test. Normal tool_results
        (with preceding assistant message with tool_calls) should pass through unchanged.
        """
        print("Setup: Normal conversation with valid tool_results...")
        messages = [
            UnifiedMessage(role="user", content="Call a tool"),
            UnifiedMessage(
                role="assistant",
                content="",
                tool_calls=[{
                    "id": "call_valid",
                    "type": "function",
                    "function": {"name": "test_tool", "arguments": "{}"}
                }]
            ),
            UnifiedMessage(
                role="user",
                content="",
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "call_valid",
                    "content": "Tool executed successfully"
                }]
            )
        ]
        
        print("Action: Processing messages...")
        result, converted = ensure_assistant_before_tool_results(messages)
        
        print(f"Result: {result}")
        print(f"Comparing converted flag: Expected False, Got {converted}")
        assert converted is False  # No conversion happened
        
        print("Checking that tool_results are preserved (NOT converted)...")
        assert result[2].tool_results is not None  # Still has tool_results
        assert len(result[2].tool_results) == 1
        assert result[2].tool_results[0]["tool_use_id"] == "call_valid"
        assert result[2].tool_results[0]["content"] == "Tool executed successfully"
        
        print("Checking that content is NOT modified...")
        assert result[2].content == ""  # Original empty content preserved
        assert "[Tool Result" not in result[2].content  # NOT converted to text
    
    def test_mixed_valid_and_orphaned_tool_results(self):
        """
        What it does: Verifies correct handling of mixed valid and orphaned tool_results.
        Purpose: Ensure valid tool_results are preserved while orphaned are stripped.
        """
        print("Setup: Mixed conversation with valid and orphaned tool_results...")
        messages = [
            # Orphaned tool_results at start
            UnifiedMessage(
                role="user",
                content="",
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "call_orphan",
                    "content": "Orphaned"
                }]
            ),
            # Valid assistant with tool_calls
            UnifiedMessage(
                role="assistant",
                content="",
                tool_calls=[{
                    "id": "call_valid",
                    "type": "function",
                    "function": {"name": "valid_tool", "arguments": "{}"}
                }]
            ),
            # Valid tool_results
            UnifiedMessage(
                role="user",
                content="",
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "call_valid",
                    "content": "Valid result"
                }]
            )
        ]
        
        print("Action: Processing messages...")
        result, stripped = ensure_assistant_before_tool_results(messages)
        
        print(f"Result: {result}")
        print("Checking orphaned tool_results are stripped...")
        assert result[0].tool_results is None
        
        print("Checking valid tool_results are preserved...")
        assert result[2].tool_results is not None
        assert result[2].tool_results[0]["tool_use_id"] == "call_valid"
        assert stripped is True  # Because orphaned ones were stripped
    
    def test_single_message_with_tool_results(self):
        """
        What it does: Verifies handling of single message with tool_results.
        Purpose: Ensure single orphaned message is handled correctly.
        """
        print("Setup: Single message with tool_results...")
        messages = [
            UnifiedMessage(
                role="user",
                content="",
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "call_123",
                    "content": "Result"
                }]
            )
        ]
        
        print("Action: Processing messages...")
        result, stripped = ensure_assistant_before_tool_results(messages)
        
        print(f"Result: {result}")
        print("Checking that tool_results are stripped...")
        assert len(result) == 1
        assert result[0].tool_results is None
        assert stripped is True


# ==================================================================================================
# Tests for sanitize_json_schema
# ==================================================================================================

class TestSanitizeJsonSchema:
    """
    Tests for sanitize_json_schema function.
    
    This function cleans JSON Schema from fields that Kiro API doesn't accept:
    - Empty required arrays []
    - additionalProperties
    """
    
    def test_returns_empty_dict_for_none(self):
        """
        What it does: Verifies handling of None.
        Purpose: Ensure None returns empty dict.
        """
        print("Setup: None schema...")
        
        print("Action: Sanitizing schema...")
        result = sanitize_json_schema(None)
        
        print(f"Comparing result: Expected {{}}, Got {result}")
        assert result == {}
    
    def test_returns_empty_dict_for_empty_dict(self):
        """
        What it does: Verifies handling of empty dict.
        Purpose: Ensure empty dict is returned as-is.
        """
        print("Setup: Empty dict...")
        
        print("Action: Sanitizing schema...")
        result = sanitize_json_schema({})
        
        print(f"Comparing result: Expected {{}}, Got {result}")
        assert result == {}
    
    def test_removes_empty_required_array(self):
        """
        What it does: Verifies removal of empty required array.
        Purpose: Ensure required: [] is removed from schema.
        
        This is a critical test for a bug where tools with required: []
        caused a 400 "Improperly formed request" error from Kiro API.
        """
        print("Setup: Schema with empty required...")
        schema = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        print("Action: Sanitizing schema...")
        result = sanitize_json_schema(schema)
        
        print(f"Result: {result}")
        print("Checking that required is removed...")
        assert "required" not in result
        assert result["type"] == "object"
        assert result["properties"] == {}
    
    def test_preserves_non_empty_required_array(self):
        """
        What it does: Verifies preservation of non-empty required array.
        Purpose: Ensure required with elements is preserved.
        """
        print("Setup: Schema with non-empty required...")
        schema = {
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"]
        }
        
        print("Action: Sanitizing schema...")
        result = sanitize_json_schema(schema)
        
        print(f"Result: {result}")
        print("Checking that required is preserved...")
        assert "required" in result
        assert result["required"] == ["location"]
    
    def test_removes_additional_properties(self):
        """
        What it does: Verifies removal of additionalProperties.
        Purpose: Ensure additionalProperties is removed from schema.
        
        Kiro API doesn't support additionalProperties in JSON Schema.
        """
        print("Setup: Schema with additionalProperties...")
        schema = {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
        
        print("Action: Sanitizing schema...")
        result = sanitize_json_schema(schema)
        
        print(f"Result: {result}")
        print("Checking that additionalProperties is removed...")
        assert "additionalProperties" not in result
        assert result["type"] == "object"
    
    def test_removes_both_empty_required_and_additional_properties(self):
        """
        What it does: Verifies removal of both problematic fields.
        Purpose: Ensure both fields are removed simultaneously.
        """
        print("Setup: Schema with both problematic fields...")
        schema = {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False
        }
        
        print("Action: Sanitizing schema...")
        result = sanitize_json_schema(schema)
        
        print(f"Result: {result}")
        print("Checking that both fields are removed...")
        assert "required" not in result
        assert "additionalProperties" not in result
        assert result == {"type": "object", "properties": {}}
    
    def test_recursively_sanitizes_nested_properties(self):
        """
        What it does: Verifies recursive sanitization of nested properties.
        Purpose: Ensure nested schemas are also sanitized.
        """
        print("Setup: Schema with nested properties...")
        schema = {
            "type": "object",
            "properties": {
                "nested": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False
                }
            }
        }
        
        print("Action: Sanitizing schema...")
        result = sanitize_json_schema(schema)
        
        print(f"Result: {result}")
        print("Checking nested object...")
        nested = result["properties"]["nested"]
        assert "required" not in nested
        assert "additionalProperties" not in nested
    
    def test_sanitizes_items_in_lists(self):
        """
        What it does: Verifies sanitization of items in lists (anyOf, oneOf).
        Purpose: Ensure list elements are also sanitized.
        """
        print("Setup: Schema with anyOf...")
        schema = {
            "anyOf": [
                {"type": "string", "additionalProperties": False},
                {"type": "number", "required": []}
            ]
        }
        
        print("Action: Sanitizing schema...")
        result = sanitize_json_schema(schema)
        
        print(f"Result: {result}")
        print("Checking anyOf elements...")
        assert "additionalProperties" not in result["anyOf"][0]
        assert "required" not in result["anyOf"][1]
    
    def test_preserves_non_dict_list_items(self):
        """
        What it does: Verifies preservation of non-dict list items.
        Purpose: Ensure strings and other types in lists are preserved.
        """
        print("Setup: Schema with enum...")
        schema = {
            "type": "string",
            "enum": ["value1", "value2", "value3"]
        }
        
        print("Action: Sanitizing schema...")
        result = sanitize_json_schema(schema)
        
        print(f"Result: {result}")
        print("Checking enum is preserved...")
        assert result["enum"] == ["value1", "value2", "value3"]
    
    def test_complex_real_world_schema(self):
        """
        What it does: Verifies sanitization of real complex schema.
        Purpose: Ensure real schemas are handled correctly.
        """
        print("Setup: Real schema...")
        schema = {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The question to ask"},
                "options": {"type": "string", "description": "Array of options"}
            },
            "required": ["question", "options"],
            "additionalProperties": False
        }
        
        print("Action: Sanitizing schema...")
        result = sanitize_json_schema(schema)
        
        print(f"Result: {result}")
        print("Checking result...")
        assert "additionalProperties" not in result
        assert result["required"] == ["question", "options"]  # Non-empty required is preserved
        assert result["properties"]["question"]["type"] == "string"


# ==================================================================================================
# Tests for extract_tool_results_from_content
# ==================================================================================================

class TestExtractToolResults:
    """Tests for extract_tool_results_from_content function."""
    
    def test_extracts_tool_results_from_list(self):
        """
        What it does: Verifies extraction of tool results from list.
        Purpose: Ensure tool_result elements are extracted.
        """
        print("Setup: List with tool_result...")
        content = [
            {"type": "tool_result", "tool_use_id": "call_123", "content": "Result text"}
        ]
        
        print("Action: Extracting tool results...")
        result = extract_tool_results_from_content(content)
        
        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0]["toolUseId"] == "call_123"
        assert result[0]["status"] == "success"
    
    def test_returns_empty_for_string_content(self):
        """
        What it does: Verifies empty list return for string.
        Purpose: Ensure string doesn't contain tool results.
        """
        print("Setup: String...")
        content = "Just a string"
        
        print("Action: Extracting tool results...")
        result = extract_tool_results_from_content(content)
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_returns_empty_for_list_without_tool_results(self):
        """
        What it does: Verifies empty list return without tool_result.
        Purpose: Ensure regular elements are not extracted.
        """
        print("Setup: List without tool_result...")
        content = [{"type": "text", "text": "Hello"}]
        
        print("Action: Extracting tool results...")
        result = extract_tool_results_from_content(content)
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_extracts_multiple_tool_results(self):
        """
        What it does: Verifies extraction of multiple tool results.
        Purpose: Ensure all tool_result elements are extracted.
        """
        print("Setup: List with multiple tool_results...")
        content = [
            {"type": "tool_result", "tool_use_id": "call_1", "content": "Result 1"},
            {"type": "text", "text": "Some text"},
            {"type": "tool_result", "tool_use_id": "call_2", "content": "Result 2"}
        ]
        
        print("Action: Extracting tool results...")
        result = extract_tool_results_from_content(content)
        
        print(f"Result: {result}")
        assert len(result) == 2
        assert result[0]["toolUseId"] == "call_1"
        assert result[1]["toolUseId"] == "call_2"


# ==================================================================================================
# Tests for convert_tool_results_to_kiro_format
# ==================================================================================================

class TestConvertToolResultsToKiroFormat:
    """
    Tests for convert_tool_results_to_kiro_format function.
    
    This function converts unified tool results format (snake_case) to Kiro API format (camelCase).
    
    Unified format: {"type": "tool_result", "tool_use_id": "...", "content": "..."}
    Kiro format: {"content": [{"text": "..."}], "status": "success", "toolUseId": "..."}
    
    This is a critical function for fixing the 400 "Improperly formed request" bug
    where tool_results were sent in unified format instead of Kiro format.
    """
    
    def test_converts_single_tool_result(self):
        """
        What it does: Verifies conversion of a single tool result.
        Purpose: Ensure basic conversion from unified to Kiro format works.
        """
        print("Setup: Single tool result in unified format...")
        tool_results = [
            {"type": "tool_result", "tool_use_id": "call_123", "content": "Result text"}
        ]
        
        print("Action: Converting to Kiro format...")
        result = convert_tool_results_to_kiro_format(tool_results)
        
        print(f"Result: {result}")
        print("Checking structure...")
        assert len(result) == 1
        
        print("Checking toolUseId (camelCase)...")
        assert result[0]["toolUseId"] == "call_123"
        
        print("Checking status...")
        assert result[0]["status"] == "success"
        
        print("Checking content structure...")
        assert "content" in result[0]
        assert isinstance(result[0]["content"], list)
        assert len(result[0]["content"]) == 1
        assert result[0]["content"][0]["text"] == "Result text"
    
    def test_converts_multiple_tool_results(self):
        """
        What it does: Verifies conversion of multiple tool results.
        Purpose: Ensure all tool results are converted correctly.
        """
        print("Setup: Multiple tool results...")
        tool_results = [
            {"type": "tool_result", "tool_use_id": "call_1", "content": "Result 1"},
            {"type": "tool_result", "tool_use_id": "call_2", "content": "Result 2"},
            {"type": "tool_result", "tool_use_id": "call_3", "content": "Result 3"}
        ]
        
        print("Action: Converting to Kiro format...")
        result = convert_tool_results_to_kiro_format(tool_results)
        
        print(f"Result: {result}")
        print(f"Comparing count: Expected 3, Got {len(result)}")
        assert len(result) == 3
        
        print("Checking all toolUseIds...")
        assert result[0]["toolUseId"] == "call_1"
        assert result[1]["toolUseId"] == "call_2"
        assert result[2]["toolUseId"] == "call_3"
        
        print("Checking all contents...")
        assert result[0]["content"][0]["text"] == "Result 1"
        assert result[1]["content"][0]["text"] == "Result 2"
        assert result[2]["content"][0]["text"] == "Result 3"
    
    def test_returns_empty_list_for_empty_input(self):
        """
        What it does: Verifies empty list handling.
        Purpose: Ensure empty input returns empty output.
        """
        print("Setup: Empty list...")
        
        print("Action: Converting to Kiro format...")
        result = convert_tool_results_to_kiro_format([])
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_replaces_empty_content_with_placeholder(self):
        """
        What it does: Verifies empty content is replaced with placeholder.
        Purpose: Ensure Kiro API receives non-empty content (required by API).
        """
        print("Setup: Tool result with empty content...")
        tool_results = [
            {"type": "tool_result", "tool_use_id": "call_123", "content": ""}
        ]
        
        print("Action: Converting to Kiro format...")
        result = convert_tool_results_to_kiro_format(tool_results)
        
        print(f"Result: {result}")
        print("Checking that empty content is replaced with placeholder...")
        assert result[0]["content"][0]["text"] == "(empty result)"
    
    def test_replaces_none_content_with_placeholder(self):
        """
        What it does: Verifies None content is replaced with placeholder.
        Purpose: Ensure Kiro API receives non-empty content when content is None.
        """
        print("Setup: Tool result with None content...")
        tool_results = [
            {"type": "tool_result", "tool_use_id": "call_123", "content": None}
        ]
        
        print("Action: Converting to Kiro format...")
        result = convert_tool_results_to_kiro_format(tool_results)
        
        print(f"Result: {result}")
        print("Checking that None content is replaced with placeholder...")
        assert result[0]["content"][0]["text"] == "(empty result)"
    
    def test_handles_missing_content_key(self):
        """
        What it does: Verifies handling of missing content key.
        Purpose: Ensure function doesn't crash when content key is missing.
        """
        print("Setup: Tool result without content key...")
        tool_results = [
            {"type": "tool_result", "tool_use_id": "call_123"}
        ]
        
        print("Action: Converting to Kiro format...")
        result = convert_tool_results_to_kiro_format(tool_results)
        
        print(f"Result: {result}")
        print("Checking that missing content is replaced with placeholder...")
        assert result[0]["content"][0]["text"] == "(empty result)"
    
    def test_handles_missing_tool_use_id(self):
        """
        What it does: Verifies handling of missing tool_use_id.
        Purpose: Ensure function returns empty string for missing tool_use_id.
        """
        print("Setup: Tool result without tool_use_id...")
        tool_results = [
            {"type": "tool_result", "content": "Result text"}
        ]
        
        print("Action: Converting to Kiro format...")
        result = convert_tool_results_to_kiro_format(tool_results)
        
        print(f"Result: {result}")
        print("Checking that missing tool_use_id becomes empty string...")
        assert result[0]["toolUseId"] == ""
        assert result[0]["content"][0]["text"] == "Result text"
    
    def test_extracts_text_from_list_content(self):
        """
        What it does: Verifies extraction of text from list content.
        Purpose: Ensure multimodal content format is handled correctly.
        """
        print("Setup: Tool result with list content...")
        tool_results = [
            {
                "type": "tool_result",
                "tool_use_id": "call_123",
                "content": [
                    {"type": "text", "text": "Part 1"},
                    {"type": "text", "text": " Part 2"}
                ]
            }
        ]
        
        print("Action: Converting to Kiro format...")
        result = convert_tool_results_to_kiro_format(tool_results)
        
        print(f"Result: {result}")
        print("Checking that list content is extracted correctly...")
        assert result[0]["content"][0]["text"] == "Part 1 Part 2"
    
    def test_preserves_long_content(self):
        """
        What it does: Verifies long content is preserved.
        Purpose: Ensure large tool results are not truncated.
        """
        print("Setup: Tool result with long content...")
        long_content = "A" * 10000
        tool_results = [
            {"type": "tool_result", "tool_use_id": "call_123", "content": long_content}
        ]
        
        print("Action: Converting to Kiro format...")
        result = convert_tool_results_to_kiro_format(tool_results)
        
        print(f"Result content length: {len(result[0]['content'][0]['text'])}")
        print("Checking that long content is preserved...")
        assert result[0]["content"][0]["text"] == long_content
        assert len(result[0]["content"][0]["text"]) == 10000
    
    def test_all_results_have_success_status(self):
        """
        What it does: Verifies all results have status="success".
        Purpose: Ensure Kiro API receives correct status field.
        """
        print("Setup: Multiple tool results...")
        tool_results = [
            {"type": "tool_result", "tool_use_id": "call_1", "content": "Result 1"},
            {"type": "tool_result", "tool_use_id": "call_2", "content": "Result 2"}
        ]
        
        print("Action: Converting to Kiro format...")
        result = convert_tool_results_to_kiro_format(tool_results)
        
        print("Checking all statuses...")
        for i, r in enumerate(result):
            print(f"Result {i}: status = {r['status']}")
            assert r["status"] == "success"
    
    def test_handles_unicode_content(self):
        """
        What it does: Verifies Unicode content is preserved.
        Purpose: Ensure non-ASCII characters are handled correctly.
        """
        print("Setup: Tool result with Unicode content...")
        tool_results = [
            {"type": "tool_result", "tool_use_id": "call_123", "content": "Привет мир! 你好世界! 🎉"}
        ]
        
        print("Action: Converting to Kiro format...")
        result = convert_tool_results_to_kiro_format(tool_results)
        
        print(f"Result: {result}")
        print("Checking that Unicode content is preserved...")
        assert result[0]["content"][0]["text"] == "Привет мир! 你好世界! 🎉"


# ==================================================================================================
# Tests for extract_tool_uses_from_message
# ==================================================================================================

class TestExtractToolUses:
    """Tests for extract_tool_uses_from_message function."""
    
    def test_extracts_from_tool_calls_field(self):
        """
        What it does: Verifies extraction from tool_calls field.
        Purpose: Ensure OpenAI tool_calls format is handled.
        """
        print("Setup: tool_calls list...")
        tool_calls = [{
            "id": "call_123",
            "function": {
                "name": "get_weather",
                "arguments": '{"location": "Moscow"}'
            }
        }]
        
        print("Action: Extracting tool uses...")
        result = extract_tool_uses_from_message(content="", tool_calls=tool_calls)
        
        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0]["name"] == "get_weather"
        assert result[0]["toolUseId"] == "call_123"
    
    def test_extracts_from_content_list(self):
        """
        What it does: Verifies extraction from content list.
        Purpose: Ensure tool_use in content is handled (Anthropic format).
        """
        print("Setup: Content with tool_use...")
        content = [{
            "type": "tool_use",
            "id": "call_456",
            "name": "search",
            "input": {"query": "test"}
        }]
        
        print("Action: Extracting tool uses...")
        result = extract_tool_uses_from_message(content=content, tool_calls=None)
        
        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0]["name"] == "search"
        assert result[0]["toolUseId"] == "call_456"
    
    def test_returns_empty_for_no_tool_uses(self):
        """
        What it does: Verifies empty list return without tool uses.
        Purpose: Ensure regular message doesn't contain tool uses.
        """
        print("Setup: Regular content...")
        
        print("Action: Extracting tool uses...")
        result = extract_tool_uses_from_message(content="Hello", tool_calls=None)
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_extracts_from_both_sources(self):
        """
        What it does: Verifies extraction from both tool_calls and content.
        Purpose: Ensure both sources are combined.
        """
        print("Setup: Both tool_calls and content with tool_use...")
        tool_calls = [{
            "id": "call_1",
            "function": {"name": "tool1", "arguments": "{}"}
        }]
        content = [{
            "type": "tool_use",
            "id": "call_2",
            "name": "tool2",
            "input": {}
        }]
        
        print("Action: Extracting tool uses...")
        result = extract_tool_uses_from_message(content=content, tool_calls=tool_calls)
        
        print(f"Result: {result}")
        assert len(result) == 2


# ==================================================================================================
# Tests for process_tools_with_long_descriptions
# ==================================================================================================

class TestProcessToolsWithLongDescriptions:
    """Tests for process_tools_with_long_descriptions function using UnifiedTool."""
    
    def test_returns_none_and_empty_string_for_none_tools(self):
        """
        What it does: Verifies handling of None instead of tools list.
        Purpose: Ensure None returns (None, "").
        """
        print("Setup: None instead of tools...")
        
        print("Action: Processing tools...")
        processed, doc = process_tools_with_long_descriptions(None)
        
        print(f"Comparing result: Expected (None, ''), Got ({processed}, '{doc}')")
        assert processed is None
        assert doc == ""
    
    def test_returns_none_and_empty_string_for_empty_list(self):
        """
        What it does: Verifies handling of empty tools list.
        Purpose: Ensure empty list returns (None, "").
        """
        print("Setup: Empty tools list...")
        
        print("Action: Processing tools...")
        processed, doc = process_tools_with_long_descriptions([])
        
        print(f"Comparing result: Expected (None, ''), Got ({processed}, '{doc}')")
        assert processed is None
        assert doc == ""
    
    def test_short_description_unchanged(self):
        """
        What it does: Verifies short descriptions are unchanged.
        Purpose: Ensure tools with short descriptions remain as-is.
        """
        print("Setup: Tool with short description...")
        tools = [UnifiedTool(
            name="get_weather",
            description="Get weather for a location",
            input_schema={"type": "object", "properties": {}}
        )]
        
        print("Action: Processing tools...")
        with patch('kiro.converters_core.TOOL_DESCRIPTION_MAX_LENGTH', 10000):
            processed, doc = process_tools_with_long_descriptions(tools)
        
        print(f"Comparing description: Expected 'Get weather for a location', Got '{processed[0].description}'")
        assert len(processed) == 1
        assert processed[0].description == "Get weather for a location"
        assert doc == ""
    
    def test_long_description_moved_to_system_prompt(self):
        """
        What it does: Verifies moving long description to system prompt.
        Purpose: Ensure long descriptions are moved correctly.
        """
        print("Setup: Tool with very long description...")
        long_description = "A" * 15000  # 15000 chars - exceeds limit
        tools = [UnifiedTool(
            name="bash",
            description=long_description,
            input_schema={"type": "object", "properties": {"command": {"type": "string"}}}
        )]
        
        print("Action: Processing tools with limit 10000...")
        with patch('kiro.converters_core.TOOL_DESCRIPTION_MAX_LENGTH', 10000):
            processed, doc = process_tools_with_long_descriptions(tools)
        
        print("Checking reference in description...")
        assert len(processed) == 1
        assert "[Full documentation in system prompt under '## Tool: bash']" in processed[0].description
        
        print("Checking documentation in system prompt...")
        assert "## Tool: bash" in doc
        assert long_description in doc
        assert "# Tool Documentation" in doc
    
    def test_mixed_short_and_long_descriptions(self):
        """
        What it does: Verifies handling of mixed tools list.
        Purpose: Ensure short ones stay, long ones are moved.
        """
        print("Setup: Two tools - short and long...")
        short_desc = "Short description"
        long_desc = "B" * 15000
        tools = [
            UnifiedTool(name="short_tool", description=short_desc, input_schema={}),
            UnifiedTool(name="long_tool", description=long_desc, input_schema={})
        ]
        
        print("Action: Processing tools...")
        with patch('kiro.converters_core.TOOL_DESCRIPTION_MAX_LENGTH', 10000):
            processed, doc = process_tools_with_long_descriptions(tools)
        
        print(f"Checking tools count: Expected 2, Got {len(processed)}")
        assert len(processed) == 2
        
        print("Checking short tool...")
        assert processed[0].description == short_desc
        
        print("Checking long tool...")
        assert "[Full documentation in system prompt" in processed[1].description
        assert "## Tool: long_tool" in doc
        assert long_desc in doc
    
    def test_disabled_when_limit_is_zero(self):
        """
        What it does: Verifies function is disabled when limit is 0.
        Purpose: Ensure tools are unchanged when TOOL_DESCRIPTION_MAX_LENGTH=0.
        """
        print("Setup: Tool with long description and limit 0...")
        long_desc = "D" * 15000
        tools = [UnifiedTool(name="test_tool", description=long_desc, input_schema={})]
        
        print("Action: Processing tools with limit 0...")
        with patch('kiro.converters_core.TOOL_DESCRIPTION_MAX_LENGTH', 0):
            processed, doc = process_tools_with_long_descriptions(tools)
        
        print("Checking that description is unchanged...")
        assert processed[0].description == long_desc
        assert doc == ""
    
    def test_multiple_long_descriptions_all_moved(self):
        """
        What it does: Verifies moving of multiple long descriptions.
        Purpose: Ensure all long descriptions are moved.
        """
        print("Setup: Three tools with long descriptions...")
        tools = [
            UnifiedTool(name="tool1", description="F" * 15000, input_schema={}),
            UnifiedTool(name="tool2", description="G" * 15000, input_schema={}),
            UnifiedTool(name="tool3", description="H" * 15000, input_schema={})
        ]
        
        print("Action: Processing tools...")
        with patch('kiro.converters_core.TOOL_DESCRIPTION_MAX_LENGTH', 10000):
            processed, doc = process_tools_with_long_descriptions(tools)
        
        print("Checking all three tools...")
        assert len(processed) == 3
        for tool in processed:
            assert "[Full documentation in system prompt" in tool.description
        
        print("Checking documentation contains all three sections...")
        assert "## Tool: tool1" in doc
        assert "## Tool: tool2" in doc
        assert "## Tool: tool3" in doc
    
    def test_empty_description_unchanged(self):
        """
        What it does: Verifies handling of empty description.
        Purpose: Ensure empty description doesn't cause errors.
        """
        print("Setup: Tool with empty description...")
        tools = [UnifiedTool(name="empty_desc_tool", description="", input_schema={})]
        
        print("Action: Processing tools...")
        with patch('kiro.converters_core.TOOL_DESCRIPTION_MAX_LENGTH', 10000):
            processed, doc = process_tools_with_long_descriptions(tools)
        
        print("Checking that empty description remains empty...")
        assert processed[0].description == ""
        assert doc == ""
    
    def test_none_description_unchanged(self):
        """
        What it does: Verifies handling of None description.
        Purpose: Ensure None description doesn't cause errors.
        """
        print("Setup: Tool with None description...")
        tools = [UnifiedTool(name="none_desc_tool", description=None, input_schema={})]
        
        print("Action: Processing tools...")
        with patch('kiro.converters_core.TOOL_DESCRIPTION_MAX_LENGTH', 10000):
            processed, doc = process_tools_with_long_descriptions(tools)
        
        print("Checking that None description is handled correctly...")
        # None should remain None or become empty string
        assert processed[0].description is None or processed[0].description == ""
        assert doc == ""
    
    def test_preserves_tool_input_schema(self):
        """
        What it does: Verifies input_schema preservation when moving description.
        Purpose: Ensure input_schema is not lost.
        """
        print("Setup: Tool with input_schema and long description...")
        input_schema = {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name"},
                "units": {"type": "string", "enum": ["celsius", "fahrenheit"]}
            },
            "required": ["location"]
        }
        tools = [UnifiedTool(
            name="weather",
            description="C" * 15000,
            input_schema=input_schema
        )]
        
        print("Action: Processing tools...")
        with patch('kiro.converters_core.TOOL_DESCRIPTION_MAX_LENGTH', 10000):
            processed, doc = process_tools_with_long_descriptions(tools)
        
        print("Checking input_schema preservation...")
        assert processed[0].input_schema == input_schema


# ==================================================================================================
# Tests for convert_tools_to_kiro_format
# ==================================================================================================

class TestConvertToolsToKiroFormat:
    """Tests for convert_tools_to_kiro_format function."""
    
    def test_returns_empty_list_for_none(self):
        """
        What it does: Verifies handling of None.
        Purpose: Ensure None returns empty list.
        """
        print("Setup: None tools...")
        
        print("Action: Converting tools...")
        result = convert_tools_to_kiro_format(None)
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_returns_empty_list_for_empty_list(self):
        """
        What it does: Verifies handling of empty list.
        Purpose: Ensure empty list returns empty list.
        """
        print("Setup: Empty tools list...")
        
        print("Action: Converting tools...")
        result = convert_tools_to_kiro_format([])
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_converts_tool_to_kiro_format(self):
        """
        What it does: Verifies conversion of tool to Kiro format.
        Purpose: Ensure toolSpecification structure is correct.
        """
        print("Setup: Tool...")
        tools = [UnifiedTool(
            name="get_weather",
            description="Get weather for a location",
            input_schema={"type": "object", "properties": {"location": {"type": "string"}}}
        )]
        
        print("Action: Converting tools...")
        result = convert_tools_to_kiro_format(tools)
        
        print(f"Result: {result}")
        assert len(result) == 1
        assert "toolSpecification" in result[0]
        spec = result[0]["toolSpecification"]
        assert spec["name"] == "get_weather"
        assert spec["description"] == "Get weather for a location"
        assert "inputSchema" in spec
        assert "json" in spec["inputSchema"]
    
    def test_replaces_empty_description_with_placeholder(self):
        """
        What it does: Verifies replacement of empty description.
        Purpose: Ensure empty description is replaced with "Tool: {name}".
        """
        print("Setup: Tool with empty description...")
        tools = [UnifiedTool(name="focus_chain", description="", input_schema={})]
        
        print("Action: Converting tools...")
        result = convert_tools_to_kiro_format(tools)
        
        print(f"Result: {result}")
        spec = result[0]["toolSpecification"]
        assert spec["description"] == "Tool: focus_chain"
    
    def test_replaces_none_description_with_placeholder(self):
        """
        What it does: Verifies replacement of None description.
        Purpose: Ensure None description is replaced with "Tool: {name}".
        """
        print("Setup: Tool with None description...")
        tools = [UnifiedTool(name="test_tool", description=None, input_schema={})]
        
        print("Action: Converting tools...")
        result = convert_tools_to_kiro_format(tools)
        
        print(f"Result: {result}")
        spec = result[0]["toolSpecification"]
        assert spec["description"] == "Tool: test_tool"
    
    def test_sanitizes_input_schema(self):
        """
        What it does: Verifies sanitization of input schema.
        Purpose: Ensure problematic fields are removed from schema.
        """
        print("Setup: Tool with problematic schema...")
        tools = [UnifiedTool(
            name="test_tool",
            description="Test",
            input_schema={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False
            }
        )]
        
        print("Action: Converting tools...")
        result = convert_tools_to_kiro_format(tools)
        
        print(f"Result: {result}")
        schema = result[0]["toolSpecification"]["inputSchema"]["json"]
        assert "required" not in schema
        assert "additionalProperties" not in schema


# ==================================================================================================
# Tests for inject_thinking_tags
# ==================================================================================================

class TestInjectThinkingTags:
    """
    Tests for inject_thinking_tags function.
    
    This function injects thinking mode tags into content when FAKE_REASONING_ENABLED is True.
    """
    
    def test_returns_original_content_when_disabled(self):
        """
        What it does: Verifies that content is returned unchanged when fake reasoning is disabled.
        Purpose: Ensure no modification occurs when FAKE_REASONING_ENABLED=False.
        """
        print("Setup: Content with fake reasoning disabled...")
        content = "Hello, world!"
        
        print("Action: Inject thinking tags with FAKE_REASONING_ENABLED=False...")
        with patch('kiro.converters_core.FAKE_REASONING_ENABLED', False):
            result = inject_thinking_tags(content, ThinkingConfig())
        
        print(f"Comparing result: Expected 'Hello, world!', Got '{result}'")
        assert result == "Hello, world!"
    
    def test_injects_tags_when_enabled(self):
        """
        What it does: Verifies that thinking tags are injected when enabled.
        Purpose: Ensure tags are prepended to content when FAKE_REASONING_ENABLED=True.
        """
        print("Setup: Content with fake reasoning enabled...")
        content = "What is 2+2?"
        
        print("Action: Inject thinking tags with FAKE_REASONING_ENABLED=True...")
        with patch('kiro.converters_core.FAKE_REASONING_ENABLED', True):
            with patch('kiro.converters_core.FAKE_REASONING_MAX_TOKENS', 4000):
                result = inject_thinking_tags(content, ThinkingConfig())
        
        print(f"Result: {result[:200]}...")
        print("Checking that thinking_mode tag is present...")
        assert "<thinking_mode>enabled</thinking_mode>" in result
        
        print("Checking that max_thinking_length tag is present...")
        assert "<max_thinking_length>4000</max_thinking_length>" in result
        
        print("Checking that original content is preserved at the end...")
        assert result.endswith("What is 2+2?")
    
    def test_injects_thinking_instruction_tag(self):
        """
        What it does: Verifies that thinking_instruction tag is injected.
        Purpose: Ensure the quality improvement prompt is included.
        """
        print("Setup: Content with fake reasoning enabled...")
        content = "Analyze this code"
        
        print("Action: Inject thinking tags...")
        with patch('kiro.converters_core.FAKE_REASONING_ENABLED', True):
            with patch('kiro.converters_core.FAKE_REASONING_MAX_TOKENS', 8000):
                result = inject_thinking_tags(content, ThinkingConfig())
        
        print(f"Result length: {len(result)} chars")
        print("Checking that thinking_instruction tag is present...")
        assert "<thinking_instruction>" in result
        assert "</thinking_instruction>" in result
    
    def test_thinking_instruction_contains_english_directive(self):
        """
        What it does: Verifies that thinking instruction includes English language directive.
        Purpose: Ensure model is instructed to think in English for better reasoning quality.
        """
        print("Setup: Content with fake reasoning enabled...")
        content = "Test"
        
        print("Action: Inject thinking tags...")
        with patch('kiro.converters_core.FAKE_REASONING_ENABLED', True):
            with patch('kiro.converters_core.FAKE_REASONING_MAX_TOKENS', 4000):
                result = inject_thinking_tags(content, ThinkingConfig())
        
        print("Checking for English directive...")
        assert "Think in English" in result
    
    def test_uses_configured_max_tokens(self):
        """
        What it does: Verifies that FAKE_REASONING_MAX_TOKENS config value is used.
        Purpose: Ensure the configured max tokens value is injected into the tag.
        """
        print("Setup: Content with custom max tokens...")
        content = "Test"
        
        print("Action: Inject thinking tags with FAKE_REASONING_MAX_TOKENS=16000...")
        with patch('kiro.converters_core.FAKE_REASONING_ENABLED', True):
            with patch('kiro.converters_core.FAKE_REASONING_MAX_TOKENS', 16000):
                with patch('kiro.converters_core.FAKE_REASONING_BUDGET_CAP', 0):  # Disable cap
                    result = inject_thinking_tags(content, ThinkingConfig())
        
        print(f"Result: {result[:300]}...")
        print("Checking that max_thinking_length uses configured value...")
        assert "<max_thinking_length>16000</max_thinking_length>" in result
    
    def test_preserves_empty_content(self):
        """
        What it does: Verifies that empty content is handled correctly.
        Purpose: Ensure empty string doesn't cause issues.
        """
        print("Setup: Empty content with fake reasoning enabled...")
        content = ""
        
        print("Action: Inject thinking tags...")
        with patch('kiro.converters_core.FAKE_REASONING_ENABLED', True):
            with patch('kiro.converters_core.FAKE_REASONING_MAX_TOKENS', 4000):
                result = inject_thinking_tags(content, ThinkingConfig())
        
        print(f"Result length: {len(result)} chars")
        print("Checking that tags are present even with empty content...")
        assert "<thinking_mode>enabled</thinking_mode>" in result
        assert "<thinking_instruction>" in result
    
    def test_preserves_multiline_content(self):
        """
        What it does: Verifies that multiline content is preserved correctly.
        Purpose: Ensure newlines in original content are not corrupted.
        """
        print("Setup: Multiline content...")
        content = "Line 1\nLine 2\nLine 3"
        
        print("Action: Inject thinking tags...")
        with patch('kiro.converters_core.FAKE_REASONING_ENABLED', True):
            with patch('kiro.converters_core.FAKE_REASONING_MAX_TOKENS', 4000):
                result = inject_thinking_tags(content, ThinkingConfig())
        
        print("Checking that multiline content is preserved...")
        assert "Line 1\nLine 2\nLine 3" in result
    
    def test_preserves_special_characters(self):
        """
        What it does: Verifies that special characters in content are preserved.
        Purpose: Ensure XML-like content in user message doesn't break injection.
        """
        print("Setup: Content with special characters...")
        content = "Check this <code>example</code> and {json: 'value'}"
        
        print("Action: Inject thinking tags...")
        with patch('kiro.converters_core.FAKE_REASONING_ENABLED', True):
            with patch('kiro.converters_core.FAKE_REASONING_MAX_TOKENS', 4000):
                result = inject_thinking_tags(content, ThinkingConfig())
        
        print("Checking that special characters are preserved...")
        assert "<code>example</code>" in result
        assert "{json: 'value'}" in result
    
    def test_thinking_instruction_contains_systematic_approach(self):
        """
        What it does: Verifies that thinking instruction includes systematic approach guidance.
        Purpose: Ensure model is instructed to think systematically.
        """
        print("Setup: Content with fake reasoning enabled...")
        content = "Test"
        
        print("Action: Inject thinking tags...")
        with patch('kiro.converters_core.FAKE_REASONING_ENABLED', True):
            with patch('kiro.converters_core.FAKE_REASONING_MAX_TOKENS', 4000):
                result = inject_thinking_tags(content, ThinkingConfig())
        
        print("Checking for systematic approach keywords...")
        assert "thorough" in result.lower() or "systematic" in result.lower()
    
    def test_thinking_instruction_contains_understanding_step(self):
        """
        What it does: Verifies that thinking instruction includes understanding step.
        Purpose: Ensure model is instructed to understand the problem first.
        """
        print("Setup: Content with fake reasoning enabled...")
        content = "Test"
        
        print("Action: Inject thinking tags...")
        with patch('kiro.converters_core.FAKE_REASONING_ENABLED', True):
            with patch('kiro.converters_core.FAKE_REASONING_MAX_TOKENS', 4000):
                result = inject_thinking_tags(content, ThinkingConfig())
        
        print("Checking for understanding step...")
        assert "understand" in result.lower()
    
    def test_thinking_instruction_contains_verification_step(self):
        """
        What it does: Verifies that thinking instruction includes verification step.
        Purpose: Ensure model is instructed to verify reasoning before concluding.
        """
        print("Setup: Content with fake reasoning enabled...")
        content = "Test"
        
        print("Action: Inject thinking tags...")
        with patch('kiro.converters_core.FAKE_REASONING_ENABLED', True):
            with patch('kiro.converters_core.FAKE_REASONING_MAX_TOKENS', 4000):
                result = inject_thinking_tags(content, ThinkingConfig())
        
        print("Checking for verification step...")
        assert "verify" in result.lower()
    
    def test_thinking_instruction_contains_quality_emphasis(self):
        """
        What it does: Verifies that thinking instruction emphasizes quality over speed.
        Purpose: Ensure model is instructed to prioritize quality of thought.
        """
        print("Setup: Content with fake reasoning enabled...")
        content = "Test"
        
        print("Action: Inject thinking tags...")
        with patch('kiro.converters_core.FAKE_REASONING_ENABLED', True):
            with patch('kiro.converters_core.FAKE_REASONING_MAX_TOKENS', 4000):
                result = inject_thinking_tags(content, ThinkingConfig())
        
        print("Checking for quality emphasis...")
        assert "quality" in result.lower()
    
    def test_tag_order_is_correct(self):
        """
        What it does: Verifies that tags are in the correct order.
        Purpose: Ensure thinking_mode comes first, then max_thinking_length, then instruction, then content.
        """
        print("Setup: Content...")
        content = "USER_CONTENT_HERE"
        
        print("Action: Inject thinking tags...")
        with patch('kiro.converters_core.FAKE_REASONING_ENABLED', True):
            with patch('kiro.converters_core.FAKE_REASONING_MAX_TOKENS', 4000):
                result = inject_thinking_tags(content, ThinkingConfig())
        
        print("Checking tag order...")
        thinking_mode_pos = result.find("<thinking_mode>")
        max_length_pos = result.find("<max_thinking_length>")
        instruction_pos = result.find("<thinking_instruction>")
        content_pos = result.find("USER_CONTENT_HERE")
        
        print(f"Positions: thinking_mode={thinking_mode_pos}, max_length={max_length_pos}, instruction={instruction_pos}, content={content_pos}")
        
        assert thinking_mode_pos < max_length_pos, "thinking_mode should come before max_thinking_length"
        assert max_length_pos < instruction_pos, "max_thinking_length should come before thinking_instruction"
        assert instruction_pos < content_pos, "thinking_instruction should come before user content"


# ==================================================================================================
# Tests for build_kiro_history
# ==================================================================================================

class TestBuildKiroHistory:
    """Tests for build_kiro_history function using UnifiedMessage."""
    
    def test_builds_user_message(self):
        """
        What it does: Verifies building of user message.
        Purpose: Ensure user message is converted to userInputMessage.
        """
        print("Setup: User message...")
        messages = [UnifiedMessage(role="user", content="Hello")]
        
        print("Action: Building history...")
        result = build_kiro_history(messages, "claude-sonnet-4")
        
        print(f"Result: {result}")
        assert len(result) == 1
        assert "userInputMessage" in result[0]
        assert result[0]["userInputMessage"]["content"] == "Hello"
        assert result[0]["userInputMessage"]["modelId"] == "claude-sonnet-4"
    
    def test_builds_assistant_message(self):
        """
        What it does: Verifies building of assistant message.
        Purpose: Ensure assistant message is converted to assistantResponseMessage.
        """
        print("Setup: Assistant message...")
        messages = [UnifiedMessage(role="assistant", content="Hi there")]
        
        print("Action: Building history...")
        result = build_kiro_history(messages, "claude-sonnet-4")
        
        print(f"Result: {result}")
        assert len(result) == 1
        assert "assistantResponseMessage" in result[0]
        assert result[0]["assistantResponseMessage"]["content"] == "Hi there"
    
    def test_expects_normalized_roles_only(self):
        """
        What it does: Verifies build_kiro_history only handles user/assistant roles.
        Purpose: After normalize_message_roles(), build_kiro_history should never
                 see unknown roles. This test confirms it only processes normalized roles.
        """
        print("Setup: Messages with normalized roles (user/assistant only)...")
        messages = [
            UnifiedMessage(role="user", content="Normalized user"),
            UnifiedMessage(role="assistant", content="Assistant")
        ]
        
        print("Action: Building history...")
        result = build_kiro_history(messages, "claude-sonnet-4")
        
        print(f"Comparing length: Expected 2, Got {len(result)}")
        assert len(result) == 2
        print("Checking that user message is converted to userInputMessage...")
        assert "userInputMessage" in result[0]
        assert result[0]["userInputMessage"]["content"] == "Normalized user"
        print("Checking that assistant message is converted to assistantResponseMessage...")
        assert "assistantResponseMessage" in result[1]
        assert result[1]["assistantResponseMessage"]["content"] == "Assistant"
    
    def test_builds_conversation_history(self):
        """
        What it does: Verifies building of full conversation history.
        Purpose: Ensure user/assistant alternation is preserved.
        """
        print("Setup: Full conversation history...")
        messages = [
            UnifiedMessage(role="user", content="Hello"),
            UnifiedMessage(role="assistant", content="Hi"),
            UnifiedMessage(role="user", content="How are you?")
        ]
        
        print("Action: Building history...")
        result = build_kiro_history(messages, "claude-sonnet-4")
        
        print(f"Result: {result}")
        assert len(result) == 3
        assert "userInputMessage" in result[0]
        assert "assistantResponseMessage" in result[1]
        assert "userInputMessage" in result[2]
    
    def test_handles_empty_list(self):
        """
        What it does: Verifies empty list handling.
        Purpose: Ensure empty list returns empty history.
        """
        print("Setup: Empty list...")
        
        print("Action: Building history...")
        result = build_kiro_history([], "claude-sonnet-4")
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_builds_user_message_with_tool_results(self):
        """
        What it does: Verifies building of user message with tool_results.
        Purpose: Ensure tool_results are included in userInputMessageContext.
        """
        print("Setup: User message with tool_results...")
        messages = [
            UnifiedMessage(
                role="user",
                content="Here are the results",
                tool_results=[
                    {"type": "tool_result", "tool_use_id": "call_123", "content": "Result text"}
                ]
            )
        ]
        
        print("Action: Building history...")
        result = build_kiro_history(messages, "claude-sonnet-4")
        
        print(f"Result: {result}")
        assert len(result) == 1
        assert "userInputMessage" in result[0]
        user_msg = result[0]["userInputMessage"]
        assert "userInputMessageContext" in user_msg
        assert "toolResults" in user_msg["userInputMessageContext"]
    
    def test_builds_assistant_message_with_tool_calls(self):
        """
        What it does: Verifies building of assistant message with tool_calls.
        Purpose: Ensure tool_calls are converted to toolUses.
        """
        print("Setup: Assistant message with tool_calls...")
        messages = [
            UnifiedMessage(
                role="assistant",
                content="I'll call a tool",
                tool_calls=[{
                    "id": "call_123",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"location": "Moscow"}'
                    }
                }]
            )
        ]
        
        print("Action: Building history...")
        result = build_kiro_history(messages, "claude-sonnet-4")
        
        print(f"Result: {result}")
        assert len(result) == 1
        assert "assistantResponseMessage" in result[0]
        assistant_msg = result[0]["assistantResponseMessage"]
        assert "toolUses" in assistant_msg
    
    def test_adds_empty_placeholder_for_empty_user_content(self):
        """
        What it does: Verifies that "(empty)" placeholder is added for user messages with empty content.
        Purpose: Ensure Kiro API receives non-empty content in history.
        
        This is a fallback test for issue #20 - ensures any edge case with empty content
        is handled even if strip_all_tool_content didn't add a placeholder.
        """
        print("Setup: User message with empty content...")
        messages = [UnifiedMessage(role="user", content="")]
        
        print("Action: Building history...")
        result = build_kiro_history(messages, "claude-sonnet-4")
        
        print(f"Result: {result}")
        print(f"Content: '{result[0]['userInputMessage']['content']}'")
        print("Checking that '(empty)' placeholder is added...")
        assert result[0]["userInputMessage"]["content"] == "(empty)"
    
    def test_adds_empty_placeholder_for_empty_assistant_content(self):
        """
        What it does: Verifies that "(empty)" placeholder is added for assistant messages with empty content.
        Purpose: Ensure Kiro API receives non-empty content in history.
        
        This is a fallback test for issue #20 - ensures any edge case with empty content
        is handled even if strip_all_tool_content didn't add a placeholder.
        """
        print("Setup: Assistant message with empty content...")
        messages = [UnifiedMessage(role="assistant", content="")]
        
        print("Action: Building history...")
        result = build_kiro_history(messages, "claude-sonnet-4")
        
        print(f"Result: {result}")
        print(f"Content: '{result[0]['assistantResponseMessage']['content']}'")
        print("Checking that '(empty)' placeholder is added...")
        assert result[0]["assistantResponseMessage"]["content"] == "(empty)"
    
    def test_adds_empty_placeholder_for_none_user_content(self):
        """
        What it does: Verifies that "(empty)" placeholder is added for user messages with None content.
        Purpose: Ensure Kiro API receives non-empty content when content is None.
        """
        print("Setup: User message with None content...")
        messages = [UnifiedMessage(role="user", content=None)]
        
        print("Action: Building history...")
        result = build_kiro_history(messages, "claude-sonnet-4")
        
        print(f"Result: {result}")
        print(f"Content: '{result[0]['userInputMessage']['content']}'")
        print("Checking that '(empty)' placeholder is added...")
        assert result[0]["userInputMessage"]["content"] == "(empty)"
    
    def test_adds_empty_placeholder_for_none_assistant_content(self):
        """
        What it does: Verifies that "(empty)" placeholder is added for assistant messages with None content.
        Purpose: Ensure Kiro API receives non-empty content when content is None.
        """
        print("Setup: Assistant message with None content...")
        messages = [UnifiedMessage(role="assistant", content=None)]
        
        print("Action: Building history...")
        result = build_kiro_history(messages, "claude-sonnet-4")
        
        print(f"Result: {result}")
        print(f"Content: '{result[0]['assistantResponseMessage']['content']}'")
        print("Checking that '(empty)' placeholder is added...")
        assert result[0]["assistantResponseMessage"]["content"] == "(empty)"
    
    def test_preserves_non_empty_content_in_history(self):
        """
        What it does: Verifies that non-empty content is preserved (not replaced with placeholder).
        Purpose: Ensure placeholder is only added when content is actually empty.
        """
        print("Setup: Messages with actual content...")
        messages = [
            UnifiedMessage(role="user", content="Hello"),
            UnifiedMessage(role="assistant", content="Hi there")
        ]
        
        print("Action: Building history...")
        result = build_kiro_history(messages, "claude-sonnet-4")
        
        print(f"Result: {result}")
        print("Checking that original content is preserved...")
        assert result[0]["userInputMessage"]["content"] == "Hello"
        assert result[1]["assistantResponseMessage"]["content"] == "Hi there"
    
    def test_mixed_empty_and_non_empty_content_in_history(self):
        """
        What it does: Verifies correct handling of mixed empty and non-empty content.
        Purpose: Ensure only empty messages get placeholders.
        
        This simulates a conversation where some messages have content and some don't.
        """
        print("Setup: Mixed conversation with empty and non-empty content...")
        messages = [
            UnifiedMessage(role="user", content="Start"),
            UnifiedMessage(role="assistant", content=""),  # Empty - should get placeholder
            UnifiedMessage(role="user", content=""),  # Empty - should get placeholder
            UnifiedMessage(role="assistant", content="Response")
        ]
        
        print("Action: Building history...")
        result = build_kiro_history(messages, "claude-sonnet-4")
        
        print(f"Result: {result}")
        print("Checking each message...")
        
        print(f"Message 0 content: '{result[0]['userInputMessage']['content']}'")
        assert result[0]["userInputMessage"]["content"] == "Start"
        
        print(f"Message 1 content: '{result[1]['assistantResponseMessage']['content']}'")
        assert result[1]["assistantResponseMessage"]["content"] == "(empty)"
        
        print(f"Message 2 content: '{result[2]['userInputMessage']['content']}'")
        assert result[2]["userInputMessage"]["content"] == "(empty)"
        
        print(f"Message 3 content: '{result[3]['assistantResponseMessage']['content']}'")
        assert result[3]["assistantResponseMessage"]["content"] == "Response"
    
    def test_builds_user_message_with_images(self):
        """
        What it does: Verifies building of user message with images.
        Purpose: Ensure images are included directly in userInputMessage.images (Issue #32 fix).
        
        This is a critical test for Issue #30/#32 fix - images should be in Kiro format
        and placed directly in userInputMessage, NOT in userInputMessageContext.
        """
        print("Setup: User message with images...")
        messages = [
            UnifiedMessage(
                role="user",
                content="What's in this image?",
                images=[{"media_type": "image/jpeg", "data": TEST_IMAGE_BASE64}]
            )
        ]
        
        print("Action: Building history...")
        result = build_kiro_history(messages, "claude-sonnet-4")
        
        print(f"Result: {result}")
        assert len(result) == 1
        assert "userInputMessage" in result[0]
        
        user_msg = result[0]["userInputMessage"]
        print(f"User message: {user_msg}")
        
        print("Checking that images are directly in userInputMessage (Issue #32 fix)...")
        assert "images" in user_msg
        
        print("Checking image format (Kiro format)...")
        images = user_msg["images"]
        assert len(images) == 1
        assert images[0]["format"] == "jpeg"
        assert images[0]["source"]["bytes"] == TEST_IMAGE_BASE64
    
    def test_builds_user_message_with_multiple_images(self):
        """
        What it does: Verifies building of user message with multiple images.
        Purpose: Ensure all images are included directly in userInputMessage (Issue #32 fix).
        """
        print("Setup: User message with multiple images...")
        messages = [
            UnifiedMessage(
                role="user",
                content="Compare these images",
                images=[
                    {"media_type": "image/jpeg", "data": "image1_data"},
                    {"media_type": "image/png", "data": "image2_data"}
                ]
            )
        ]
        
        print("Action: Building history...")
        result = build_kiro_history(messages, "claude-sonnet-4")
        
        print(f"Result: {result}")
        user_msg = result[0]["userInputMessage"]
        images = user_msg["images"]
        
        print(f"Comparing image count: Expected 2, Got {len(images)}")
        assert len(images) == 2
        
        print("Checking first image...")
        assert images[0]["format"] == "jpeg"
        assert images[0]["source"]["bytes"] == "image1_data"
        
        print("Checking second image...")
        assert images[1]["format"] == "png"
        assert images[1]["source"]["bytes"] == "image2_data"
    
    def test_builds_user_message_with_images_and_tool_results(self):
        """
        What it does: Verifies building of user message with both images and tool_results.
        Purpose: Ensure images are in userInputMessage and toolResults are in userInputMessageContext (Issue #32 fix).
        """
        print("Setup: User message with images and tool_results...")
        messages = [
            UnifiedMessage(
                role="user",
                content="Here's the image and tool result",
                images=[{"media_type": "image/png", "data": "image_data"}],
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "call_123",
                    "content": "Tool output"
                }]
            )
        ]
        
        print("Action: Building history...")
        result = build_kiro_history(messages, "claude-sonnet-4")
        
        print(f"Result: {result}")
        user_msg = result[0]["userInputMessage"]
        context = user_msg.get("userInputMessageContext", {})
        
        print("Checking that images are directly in userInputMessage (Issue #32 fix)...")
        assert "images" in user_msg
        
        print("Checking that toolResults are in userInputMessageContext...")
        assert "toolResults" in context
        
        print("Checking images...")
        assert len(user_msg["images"]) == 1
        assert user_msg["images"][0]["format"] == "png"
        
        print("Checking toolResults...")
        assert len(context["toolResults"]) == 1
        assert context["toolResults"][0]["toolUseId"] == "call_123"
    
    def test_no_images_context_when_no_images(self):
        """
        What it does: Verifies that images key is not added when there are no images.
        Purpose: Ensure clean payload without empty images array.
        """
        print("Setup: User message without images...")
        messages = [
            UnifiedMessage(role="user", content="Hello, no images here")
        ]
        
        print("Action: Building history...")
        result = build_kiro_history(messages, "claude-sonnet-4")
        
        print(f"Result: {result}")
        user_msg = result[0]["userInputMessage"]
        
        print("Checking that images key is not present...")
        # Either no context at all, or context without images
        if "userInputMessageContext" in user_msg:
            context = user_msg["userInputMessageContext"]
            assert "images" not in context or context.get("images") == []
        else:
            print("No userInputMessageContext - OK")
    
    def test_builds_user_message_with_webp_image(self):
        """
        What it does: Verifies building of user message with WebP image.
        Purpose: Ensure WebP format is correctly converted to Kiro format in userInputMessage (Issue #32 fix).
        """
        print("Setup: User message with WebP image...")
        messages = [
            UnifiedMessage(
                role="user",
                content="Analyze this WebP image",
                images=[{"media_type": "image/webp", "data": "webp_image_data"}]
            )
        ]
        
        print("Action: Building history...")
        result = build_kiro_history(messages, "claude-sonnet-4")
        
        print(f"Result: {result}")
        user_msg = result[0]["userInputMessage"]
        images = user_msg["images"]
        
        print("Checking WebP format...")
        assert len(images) == 1
        assert images[0]["format"] == "webp"
        assert images[0]["source"]["bytes"] == "webp_image_data"
    
    def test_builds_user_message_with_gif_image(self):
        """
        What it does: Verifies building of user message with GIF image.
        Purpose: Ensure GIF format is correctly converted to Kiro format in userInputMessage (Issue #32 fix).
        """
        print("Setup: User message with GIF image...")
        messages = [
            UnifiedMessage(
                role="user",
                content="What's happening in this GIF?",
                images=[{"media_type": "image/gif", "data": "gif_image_data"}]
            )
        ]
        
        print("Action: Building history...")
        result = build_kiro_history(messages, "claude-sonnet-4")
        
        print(f"Result: {result}")
        user_msg = result[0]["userInputMessage"]
        images = user_msg["images"]
        
        print("Checking GIF format...")
        assert len(images) == 1
        assert images[0]["format"] == "gif"
        assert images[0]["source"]["bytes"] == "gif_image_data"
    
# ==================================================================================================
# Tests for strip_all_tool_content
# ==================================================================================================

class TestStripAllToolContent:
    """
    Tests for strip_all_tool_content function.
    
    This function strips ALL tool-related content (tool_calls and tool_results)
    from messages. It is used when no tools are defined in the request, because
    Kiro API rejects requests that have toolResults but no tools defined.
    
    This is a critical function for handling clients like Cline/Roo/Cursor that may
    send tool-related content even when tools are not available.
    """
    
    def test_returns_empty_list_for_empty_input(self):
        """
        What it does: Verifies empty list handling.
        Purpose: Ensure empty input returns empty output.
        """
        print("Setup: Empty list...")
        
        print("Action: Stripping tool content...")
        result, had_content = strip_all_tool_content([])
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
        assert had_content is False
    
    def test_preserves_messages_without_tool_content(self):
        """
        What it does: Verifies messages without tool content are unchanged.
        Purpose: Ensure regular messages pass through unmodified.
        """
        print("Setup: Messages without tool content...")
        messages = [
            UnifiedMessage(role="user", content="Hello"),
            UnifiedMessage(role="assistant", content="Hi there"),
            UnifiedMessage(role="user", content="How are you?")
        ]
        
        print("Action: Stripping tool content...")
        result, had_content = strip_all_tool_content(messages)
        
        print(f"Comparing length: Expected 3, Got {len(result)}")
        assert len(result) == 3
        assert result[0].content == "Hello"
        assert result[1].content == "Hi there"
        assert result[2].content == "How are you?"
        assert had_content is False
    
    def test_strips_tool_calls_from_assistant(self):
        """
        What it does: Verifies tool_calls are stripped and converted to text.
        Purpose: Ensure tool_calls are converted to text representation when no tools are defined.
        """
        print("Setup: Assistant message with tool_calls...")
        messages = [
            UnifiedMessage(
                role="assistant",
                content="I'll call a tool",
                tool_calls=[{
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"location": "Moscow"}'}
                }]
            )
        ]
        
        print("Action: Stripping tool content...")
        result, had_content = strip_all_tool_content(messages)
        
        print(f"Result: {result}")
        print("Checking that tool_calls are stripped and converted to text...")
        assert len(result) == 1
        assert result[0].tool_calls is None
        # Original content is preserved AND tool text is appended
        assert "I'll call a tool" in result[0].content
        assert "[Tool: get_weather" in result[0].content
        assert had_content is True
    
    def test_strips_tool_results_from_user(self):
        """
        What it does: Verifies tool_results are stripped and converted to text.
        Purpose: Ensure tool_results are converted to text representation when no tools are defined.
        """
        print("Setup: User message with tool_results...")
        messages = [
            UnifiedMessage(
                role="user",
                content="Here are the results",
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "call_123",
                    "content": "Weather is sunny"
                }]
            )
        ]
        
        print("Action: Stripping tool content...")
        result, had_content = strip_all_tool_content(messages)
        
        print(f"Result: {result}")
        print("Checking that tool_results are stripped and converted to text...")
        assert len(result) == 1
        assert result[0].tool_results is None
        # Original content is preserved AND tool result text is appended
        assert "Here are the results" in result[0].content
        assert "[Tool Result" in result[0].content
        assert "Weather is sunny" in result[0].content
        assert had_content is True
    
    def test_strips_both_tool_calls_and_tool_results(self):
        """
        What it does: Verifies both tool_calls and tool_results are stripped.
        Purpose: Ensure all tool content is removed in a conversation.
        """
        print("Setup: Conversation with tool_calls and tool_results...")
        messages = [
            UnifiedMessage(role="user", content="Call a tool"),
            UnifiedMessage(
                role="assistant",
                content="",
                tool_calls=[{
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": "{}"}
                }]
            ),
            UnifiedMessage(
                role="user",
                content="",
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "call_123",
                    "content": "Result"
                }]
            )
        ]
        
        print("Action: Stripping tool content...")
        result, had_content = strip_all_tool_content(messages)
        
        print(f"Result: {result}")
        print("Checking that all tool content is stripped...")
        assert len(result) == 3
        assert result[0].tool_calls is None
        assert result[0].tool_results is None
        assert result[1].tool_calls is None
        assert result[1].tool_results is None
        assert result[2].tool_calls is None
        assert result[2].tool_results is None
        assert had_content is True
    
    def test_strips_multiple_tool_calls(self):
        """
        What it does: Verifies multiple tool_calls are all stripped.
        Purpose: Ensure all tool_calls in a message are removed.
        """
        print("Setup: Assistant message with multiple tool_calls...")
        messages = [
            UnifiedMessage(
                role="assistant",
                content="",
                tool_calls=[
                    {"id": "call_1", "type": "function", "function": {"name": "tool1", "arguments": "{}"}},
                    {"id": "call_2", "type": "function", "function": {"name": "tool2", "arguments": "{}"}},
                    {"id": "call_3", "type": "function", "function": {"name": "tool3", "arguments": "{}"}}
                ]
            )
        ]
        
        print("Action: Stripping tool content...")
        result, had_content = strip_all_tool_content(messages)
        
        print(f"Result: {result}")
        print("Checking that all tool_calls are stripped...")
        assert result[0].tool_calls is None
        assert had_content is True
    
    def test_strips_multiple_tool_results(self):
        """
        What it does: Verifies multiple tool_results are all stripped.
        Purpose: Ensure all tool_results in a message are removed.
        """
        print("Setup: User message with multiple tool_results...")
        messages = [
            UnifiedMessage(
                role="user",
                content="",
                tool_results=[
                    {"type": "tool_result", "tool_use_id": "call_1", "content": "Result 1"},
                    {"type": "tool_result", "tool_use_id": "call_2", "content": "Result 2"},
                    {"type": "tool_result", "tool_use_id": "call_3", "content": "Result 3"}
                ]
            )
        ]
        
        print("Action: Stripping tool content...")
        result, had_content = strip_all_tool_content(messages)
        
        print(f"Result: {result}")
        print("Checking that all tool_results are stripped...")
        assert result[0].tool_results is None
        assert had_content is True
    
    def test_preserves_message_content_when_stripping(self):
        """
        What it does: Verifies message content is preserved and tool content is appended as text.
        Purpose: Ensure original content is kept and tool content is converted to text.
        """
        print("Setup: Messages with both content and tool content...")
        messages = [
            UnifiedMessage(
                role="assistant",
                content="Let me help you with that",
                tool_calls=[{
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "helper", "arguments": "{}"}
                }]
            ),
            UnifiedMessage(
                role="user",
                content="Thanks for the result",
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "call_123",
                    "content": "Done"
                }]
            )
        ]
        
        print("Action: Stripping tool content...")
        result, had_content = strip_all_tool_content(messages)
        
        print(f"Result: {result}")
        print("Checking that original content is preserved and tool text is appended...")
        assert "Let me help you with that" in result[0].content
        assert "[Tool: helper" in result[0].content
        assert "Thanks for the result" in result[1].content
        assert "[Tool Result" in result[1].content
        assert had_content is True
    
    def test_preserves_message_role_when_stripping(self):
        """
        What it does: Verifies message role is preserved when tool content is stripped.
        Purpose: Ensure role is not modified during stripping.
        """
        print("Setup: Messages with tool content...")
        messages = [
            UnifiedMessage(role="assistant", content="", tool_calls=[
                {"id": "call_1", "type": "function", "function": {"name": "tool", "arguments": "{}"}}
            ]),
            UnifiedMessage(role="user", content="", tool_results=[
                {"type": "tool_result", "tool_use_id": "call_1", "content": "Result"}
            ])
        ]
        
        print("Action: Stripping tool content...")
        result, had_content = strip_all_tool_content(messages)
        
        print(f"Result: {result}")
        print("Checking that roles are preserved...")
        assert result[0].role == "assistant"
        assert result[1].role == "user"
        assert had_content is True
    
    def test_mixed_messages_with_and_without_tool_content(self):
        """
        What it does: Verifies correct handling of mixed messages.
        Purpose: Ensure only messages with tool content are modified.
        """
        print("Setup: Mixed messages...")
        messages = [
            UnifiedMessage(role="user", content="Hello"),  # No tool content
            UnifiedMessage(
                role="assistant",
                content="",
                tool_calls=[{"id": "call_1", "type": "function", "function": {"name": "tool", "arguments": "{}"}}]
            ),  # Has tool content
            UnifiedMessage(role="user", content="Continue"),  # No tool content
        ]
        
        print("Action: Stripping tool content...")
        result, had_content = strip_all_tool_content(messages)
        
        print(f"Result: {result}")
        print("Checking mixed handling...")
        assert result[0].content == "Hello"
        assert result[0].tool_calls is None
        assert result[1].tool_calls is None  # Stripped
        assert result[2].content == "Continue"
        assert result[2].tool_calls is None
        assert had_content is True
    
    def test_returns_false_when_no_tool_content_stripped(self):
        """
        What it does: Verifies had_content flag is False when no tool content exists.
        Purpose: Ensure correct flag value for messages without tool content.
        """
        print("Setup: Messages without any tool content...")
        messages = [
            UnifiedMessage(role="user", content="Hello"),
            UnifiedMessage(role="assistant", content="Hi"),
            UnifiedMessage(role="user", content="Bye")
        ]
        
        print("Action: Stripping tool content...")
        result, had_content = strip_all_tool_content(messages)
        
        print(f"had_content: {had_content}")
        assert had_content is False
    
    def test_returns_true_when_tool_content_stripped(self):
        """
        What it does: Verifies had_content flag is True when tool content is stripped.
        Purpose: Ensure correct flag value for messages with tool content.
        """
        print("Setup: Message with tool content...")
        messages = [
            UnifiedMessage(
                role="assistant",
                content="",
                tool_calls=[{"id": "call_1", "type": "function", "function": {"name": "tool", "arguments": "{}"}}]
            )
        ]
        
        print("Action: Stripping tool content...")
        result, had_content = strip_all_tool_content(messages)
        
        print(f"had_content: {had_content}")
        assert had_content is True
    
    def test_handles_empty_tool_calls_list(self):
        """
        What it does: Verifies handling of empty tool_calls list.
        Purpose: Ensure empty list is treated as no tool content.
        """
        print("Setup: Message with empty tool_calls list...")
        messages = [
            UnifiedMessage(role="assistant", content="Hello", tool_calls=[])
        ]
        
        print("Action: Stripping tool content...")
        result, had_content = strip_all_tool_content(messages)
        
        print(f"Result: {result}")
        print(f"had_content: {had_content}")
        # Empty list is falsy, so should not be considered as having tool content
        assert had_content is False
    
    def test_handles_empty_tool_results_list(self):
        """
        What it does: Verifies handling of empty tool_results list.
        Purpose: Ensure empty list is treated as no tool content.
        """
        print("Setup: Message with empty tool_results list...")
        messages = [
            UnifiedMessage(role="user", content="Hello", tool_results=[])
        ]
        
        print("Action: Stripping tool content...")
        result, had_content = strip_all_tool_content(messages)
        
        print(f"Result: {result}")
        print(f"had_content: {had_content}")
        # Empty list is falsy, so should not be considered as having tool content
        assert had_content is False
    
    def test_adds_tool_text_for_empty_content_with_tool_calls(self):
        """
        What it does: Verifies that tool_calls are converted to text when content is empty.
        Purpose: Ensure Kiro API receives non-empty content for messages that only had tool_calls.
        
        This is a critical test for issue #20 - OpenCode compaction returns 400 error
        because messages with only tool_calls become empty after stripping.
        Now we convert tool_calls to text representation instead of simple placeholder.
        """
        print("Setup: Assistant message with only tool_calls (empty content)...")
        messages = [
            UnifiedMessage(
                role="assistant",
                content="",  # Empty content - only tool_calls
                tool_calls=[{
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "test.py"}'}
                }]
            )
        ]
        
        print("Action: Stripping tool content...")
        result, had_content = strip_all_tool_content(messages)
        
        print(f"Result: {result}")
        print(f"Content after stripping: '{result[0].content}'")
        print("Checking that tool_calls are converted to text representation...")
        assert "[Tool: read_file" in result[0].content
        assert "call_123" in result[0].content
        assert '{"path": "test.py"}' in result[0].content
        assert result[0].tool_calls is None
        assert had_content is True
    
    def test_adds_tool_text_for_empty_content_with_tool_results(self):
        """
        What it does: Verifies that tool_results are converted to text when content is empty.
        Purpose: Ensure Kiro API receives non-empty content for messages that only had tool_results.
        
        This is a critical test for issue #20 - OpenCode compaction returns 400 error
        because messages with only tool_results become empty after stripping.
        Now we convert tool_results to text representation instead of simple placeholder.
        """
        print("Setup: User message with only tool_results (empty content)...")
        messages = [
            UnifiedMessage(
                role="user",
                content="",  # Empty content - only tool_results
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "call_123",
                    "content": "File contents here"
                }]
            )
        ]
        
        print("Action: Stripping tool content...")
        result, had_content = strip_all_tool_content(messages)
        
        print(f"Result: {result}")
        print(f"Content after stripping: '{result[0].content}'")
        print("Checking that tool_results are converted to text representation...")
        assert "[Tool Result" in result[0].content
        assert "call_123" in result[0].content
        assert "File contents here" in result[0].content
        assert result[0].tool_results is None
        assert had_content is True
    
    def test_preserves_existing_content_when_stripping_tool_calls(self):
        """
        What it does: Verifies that existing content is preserved and tool text is appended.
        Purpose: Ensure original content is kept and tool_calls are converted to text.
        """
        print("Setup: Assistant message with both content and tool_calls...")
        messages = [
            UnifiedMessage(
                role="assistant",
                content="I'll read the file for you",
                tool_calls=[{
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"}
                }]
            )
        ]
        
        print("Action: Stripping tool content...")
        result, had_content = strip_all_tool_content(messages)
        
        print(f"Result: {result}")
        print(f"Content after stripping: '{result[0].content}'")
        print("Checking that original content is preserved and tool text is appended...")
        assert "I'll read the file for you" in result[0].content
        assert "[Tool: read_file" in result[0].content
        assert result[0].tool_calls is None
        assert had_content is True
    
    def test_preserves_existing_content_when_stripping_tool_results(self):
        """
        What it does: Verifies that existing content is preserved and tool result text is appended.
        Purpose: Ensure original content is kept and tool_results are converted to text.
        """
        print("Setup: User message with both content and tool_results...")
        messages = [
            UnifiedMessage(
                role="user",
                content="Here are the results you requested",
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "call_123",
                    "content": "Result data"
                }]
            )
        ]
        
        print("Action: Stripping tool content...")
        result, had_content = strip_all_tool_content(messages)
        
        print(f"Result: {result}")
        print(f"Content after stripping: '{result[0].content}'")
        print("Checking that original content is preserved and tool result text is appended...")
        assert "Here are the results you requested" in result[0].content
        assert "[Tool Result" in result[0].content
        assert "Result data" in result[0].content
        assert result[0].tool_results is None
        assert had_content is True
    
    def test_both_tool_calls_and_results_converted_to_text(self):
        """
        What it does: Verifies that both tool_calls and tool_results are converted to text.
        Purpose: Ensure all tool content is preserved when message has both types.
        
        Note: This is an edge case - normally assistant messages have tool_calls and user messages have tool_results.
        """
        print("Setup: Message with both tool_calls and tool_results (edge case)...")
        messages = [
            UnifiedMessage(
                role="assistant",
                content="",
                tool_calls=[{"id": "call_1", "type": "function", "function": {"name": "my_tool", "arguments": '{"x": 1}'}}],
                tool_results=[{"type": "tool_result", "tool_use_id": "call_0", "content": "Previous result"}]
            )
        ]
        
        print("Action: Stripping tool content...")
        result, had_content = strip_all_tool_content(messages)
        
        print(f"Result: {result}")
        print(f"Content after stripping: '{result[0].content}'")
        print("Checking that both tool_calls and tool_results are converted to text...")
        assert "[Tool: my_tool" in result[0].content
        assert "[Tool Result" in result[0].content
        assert "Previous result" in result[0].content
        assert had_content is True
    
    def test_multiple_messages_with_empty_content_get_text_representation(self):
        """
        What it does: Verifies correct text representation for multiple messages in a conversation.
        Purpose: Ensure each message gets the appropriate text representation based on its tool content type.
        
        This simulates the OpenCode compaction scenario from issue #20 where multiple
        tool-only messages are sent without text content.
        """
        print("Setup: Conversation with multiple tool-only messages...")
        messages = [
            UnifiedMessage(role="user", content="Read these files"),
            UnifiedMessage(
                role="assistant",
                content="",  # Only tool_calls
                tool_calls=[{"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "a.txt"}'}}]
            ),
            UnifiedMessage(
                role="user",
                content="",  # Only tool_results
                tool_results=[{"type": "tool_result", "tool_use_id": "call_1", "content": "File content ABC"}]
            ),
            UnifiedMessage(
                role="assistant",
                content="",  # Only tool_calls
                tool_calls=[{"id": "call_2", "type": "function", "function": {"name": "write_file", "arguments": '{"path": "b.txt"}'}}]
            ),
            UnifiedMessage(
                role="user",
                content="",  # Only tool_results
                tool_results=[{"type": "tool_result", "tool_use_id": "call_2", "content": "Write completed"}]
            )
        ]
        
        print("Action: Stripping tool content...")
        result, had_content = strip_all_tool_content(messages)
        
        print(f"Result: {result}")
        print("Checking text representation for each message...")
        
        print(f"Message 0 content: '{result[0].content}'")
        assert result[0].content == "Read these files"  # Original content preserved
        
        print(f"Message 1 content: '{result[1].content}'")
        assert "[Tool: read_file" in result[1].content  # Text representation for tool_calls
        assert "call_1" in result[1].content
        
        print(f"Message 2 content: '{result[2].content}'")
        assert "[Tool Result" in result[2].content  # Text representation for tool_results
        assert "File content ABC" in result[2].content
        
        print(f"Message 3 content: '{result[3].content}'")
        assert "[Tool: write_file" in result[3].content  # Text representation for tool_calls
        assert "call_2" in result[3].content
        
        print(f"Message 4 content: '{result[4].content}'")
        assert "[Tool Result" in result[4].content  # Text representation for tool_results
        assert "Write completed" in result[4].content
        
        assert had_content is True
    
    def test_converts_tool_calls_to_text_representation(self):
        """
        What it does: Verifies that tool_calls are converted to text representation.
        Purpose: Ensure tool context is preserved as readable text when stripping.
        
        This is a critical test for issue #20 - instead of losing tool context,
        we convert it to human-readable text.
        """
        print("Setup: Assistant message with tool_calls...")
        messages = [
            UnifiedMessage(
                role="assistant",
                content="",
                tool_calls=[{
                    "id": "call_abc123",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "test.py"}'}
                }]
            )
        ]
        
        print("Action: Stripping tool content...")
        result, had_content = strip_all_tool_content(messages)
        
        print(f"Result content: '{result[0].content}'")
        print("Checking that tool name is in text representation...")
        assert "[Tool: read_file" in result[0].content
        print("Checking that tool_id is in text representation...")
        assert "call_abc123" in result[0].content
        print("Checking that arguments are in text representation...")
        assert '{"path": "test.py"}' in result[0].content
        assert had_content is True
    
    def test_converts_tool_results_to_text_representation(self):
        """
        What it does: Verifies that tool_results are converted to text representation.
        Purpose: Ensure tool result context is preserved as readable text when stripping.
        
        This is a critical test for issue #20 - instead of losing tool context,
        we convert it to human-readable text.
        """
        print("Setup: User message with tool_results...")
        messages = [
            UnifiedMessage(
                role="user",
                content="",
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "call_xyz789",
                    "content": "File contents:\ndef hello():\n    print('world')"
                }]
            )
        ]
        
        print("Action: Stripping tool content...")
        result, had_content = strip_all_tool_content(messages)
        
        print(f"Result content: '{result[0].content}'")
        print("Checking that [Tool Result] marker is present...")
        assert "[Tool Result" in result[0].content
        print("Checking that tool_use_id is in text representation...")
        assert "call_xyz789" in result[0].content
        print("Checking that result content is preserved...")
        assert "def hello():" in result[0].content
        assert had_content is True


# ==================================================================================================
# Tests for strip_all_tool_content with images preservation (Issue #57 follow-up)
# ==================================================================================================

class TestStripAllToolContentPreservesImages:
    """Tests that strip_all_tool_content preserves images field (Issue #57 follow-up)."""
    
    def test_preserves_images_when_stripping_tool_results(self):
        """
        What it does: Verifies images are preserved when tool_results are stripped.
        Purpose: Ensure images from MCP tool messages aren't lost (critical bug fix).
        """
        print("Setup: Message with tool_results and images...")
        messages = [
            UnifiedMessage(
                role="user",
                content="Screenshot result",
                tool_results=[
                    {"type": "tool_result", "tool_use_id": "call_123", "content": "Done"}
                ],
                images=[
                    {"media_type": "image/png", "data": "screenshot_data"}
                ]
            )
        ]
        
        print("Action: Stripping tool content...")
        result, had_tools = strip_all_tool_content(messages)
        
        print(f"Result: {result}")
        print(f"Images preserved: {result[0].images}")
        
        assert had_tools is True
        assert result[0].tool_results is None  # Stripped
        assert result[0].images is not None  # PRESERVED
        assert len(result[0].images) == 1
        assert result[0].images[0]["data"] == "screenshot_data"
    
    def test_preserves_images_when_stripping_tool_calls(self):
        """
        What it does: Verifies images are preserved when tool_calls are stripped.
        Purpose: Ensure images aren't lost when assistant messages have tool_calls.
        """
        print("Setup: Message with tool_calls and images...")
        messages = [
            UnifiedMessage(
                role="assistant",
                content="Using tool",
                tool_calls=[
                    {"id": "call_456", "type": "function", "function": {"name": "test", "arguments": "{}"}}
                ],
                images=[
                    {"media_type": "image/jpeg", "data": "image_data"}
                ]
            )
        ]
        
        print("Action: Stripping tool content...")
        result, had_tools = strip_all_tool_content(messages)
        
        print(f"Result: {result}")
        print(f"Images preserved: {result[0].images}")
        
        assert had_tools is True
        assert result[0].tool_calls is None  # Stripped
        assert result[0].images is not None  # PRESERVED
        assert len(result[0].images) == 1
        assert result[0].images[0]["data"] == "image_data"
    
    def test_preserves_images_when_stripping_both_tool_calls_and_results(self):
        """
        What it does: Verifies images are preserved when both tool_calls and tool_results are stripped.
        Purpose: Ensure images survive complete tool content removal.
        """
        print("Setup: Message with both tool_calls, tool_results and images...")
        messages = [
            UnifiedMessage(
                role="user",
                content="Complex message",
                tool_calls=[
                    {"id": "call_1", "type": "function", "function": {"name": "tool1", "arguments": "{}"}}
                ],
                tool_results=[
                    {"type": "tool_result", "tool_use_id": "call_1", "content": "Result"}
                ],
                images=[
                    {"media_type": "image/png", "data": "complex_image"}
                ]
            )
        ]
        
        print("Action: Stripping tool content...")
        result, had_tools = strip_all_tool_content(messages)
        
        print(f"Result: {result}")
        print(f"Images preserved: {result[0].images}")
        
        assert had_tools is True
        assert result[0].tool_calls is None  # Stripped
        assert result[0].tool_results is None  # Stripped
        assert result[0].images is not None  # PRESERVED
        assert len(result[0].images) == 1
        assert result[0].images[0]["data"] == "complex_image"
    
    def test_preserves_none_images_when_stripping(self):
        """
        What it does: Verifies None images stay None when tool content is stripped.
        Purpose: Ensure we don't create spurious images field.
        """
        print("Setup: Message with tool_results but no images...")
        messages = [
            UnifiedMessage(
                role="user",
                content="Text only",
                tool_results=[
                    {"type": "tool_result", "tool_use_id": "call_789", "content": "Done"}
                ],
                images=None
            )
        ]
        
        print("Action: Stripping tool content...")
        result, had_tools = strip_all_tool_content(messages)
        
        print(f"Result: {result}")
        print(f"Images field: {result[0].images}")
        
        assert had_tools is True
        assert result[0].tool_results is None  # Stripped
        assert result[0].images is None  # Still None (not created)
    
    def test_preserves_multiple_images_when_stripping(self):
        """
        What it does: Verifies multiple images are all preserved when stripping.
        Purpose: Ensure all images survive, not just the first one.
        """
        print("Setup: Message with tool_results and multiple images...")
        messages = [
            UnifiedMessage(
                role="user",
                content="Multiple screenshots",
                tool_results=[
                    {"type": "tool_result", "tool_use_id": "call_multi", "content": "Done"}
                ],
                images=[
                    {"media_type": "image/png", "data": "image1"},
                    {"media_type": "image/jpeg", "data": "image2"},
                    {"media_type": "image/webp", "data": "image3"}
                ]
            )
        ]
        
        print("Action: Stripping tool content...")
        result, had_tools = strip_all_tool_content(messages)
        
        print(f"Result: {result}")
        print(f"Images count: {len(result[0].images)}")
        
        assert had_tools is True
        assert result[0].tool_results is None  # Stripped
        assert result[0].images is not None  # PRESERVED
        assert len(result[0].images) == 3
        assert result[0].images[0]["data"] == "image1"
        assert result[0].images[1]["data"] == "image2"
        assert result[0].images[2]["data"] == "image3"


# ==================================================================================================
# Tests for tool_calls_to_text
# ==================================================================================================

class TestToolCallsToText:
    """
    Tests for tool_calls_to_text function.
    
    This function converts tool_calls to human-readable text representation.
    Used when stripping tool content from messages (when no tools are defined).
    """
    
    def test_converts_single_tool_call_to_text(self):
        """
        What it does: Verifies conversion of a single tool call to text.
        Purpose: Ensure basic conversion works correctly.
        """
        print("Setup: Single tool call...")
        tool_calls = [{
            "id": "call_123",
            "type": "function",
            "function": {"name": "bash", "arguments": '{"command": "ls -la"}'}
        }]
        
        print("Action: Converting to text...")
        result = tool_calls_to_text(tool_calls)
        
        print(f"Result: '{result}'")
        print("Checking that tool name is present...")
        assert "[Tool: bash" in result
        print("Checking that arguments are present...")
        assert '{"command": "ls -la"}' in result
    
    def test_converts_multiple_tool_calls_to_text(self):
        """
        What it does: Verifies conversion of multiple tool calls to text.
        Purpose: Ensure all tool calls are converted and separated.
        """
        print("Setup: Multiple tool calls...")
        tool_calls = [
            {"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "a.txt"}'}},
            {"id": "call_2", "type": "function", "function": {"name": "write_file", "arguments": '{"path": "b.txt"}'}}
        ]
        
        print("Action: Converting to text...")
        result = tool_calls_to_text(tool_calls)
        
        print(f"Result: '{result}'")
        print("Checking that both tools are present...")
        assert "[Tool: read_file" in result
        assert "[Tool: write_file" in result
        assert '{"path": "a.txt"}' in result
        assert '{"path": "b.txt"}' in result
    
    def test_includes_tool_id_in_output(self):
        """
        What it does: Verifies that tool_id is included in output.
        Purpose: Ensure traceability between tool calls and results.
        """
        print("Setup: Tool call with id...")
        tool_calls = [{
            "id": "tooluse_abc123xyz",
            "type": "function",
            "function": {"name": "search", "arguments": "{}"}
        }]
        
        print("Action: Converting to text...")
        result = tool_calls_to_text(tool_calls)
        
        print(f"Result: '{result}'")
        print("Checking that tool_id is present...")
        assert "tooluse_abc123xyz" in result
    
    def test_handles_missing_tool_id(self):
        """
        What it does: Verifies handling of tool call without id.
        Purpose: Ensure function doesn't crash when id is missing.
        """
        print("Setup: Tool call without id...")
        tool_calls = [{
            "type": "function",
            "function": {"name": "test_tool", "arguments": "{}"}
        }]
        
        print("Action: Converting to text...")
        result = tool_calls_to_text(tool_calls)
        
        print(f"Result: '{result}'")
        print("Checking that tool name is still present...")
        assert "[Tool: test_tool]" in result
    
    def test_returns_empty_string_for_empty_list(self):
        """
        What it does: Verifies empty list handling.
        Purpose: Ensure empty input returns empty output.
        """
        print("Setup: Empty list...")
        
        print("Action: Converting to text...")
        result = tool_calls_to_text([])
        
        print(f"Comparing result: Expected '', Got '{result}'")
        assert result == ""
    
    def test_handles_missing_function_key(self):
        """
        What it does: Verifies handling of malformed tool call without function key.
        Purpose: Ensure function doesn't crash on malformed input.
        """
        print("Setup: Tool call without function key...")
        tool_calls = [{"id": "call_123", "type": "function"}]
        
        print("Action: Converting to text...")
        result = tool_calls_to_text(tool_calls)
        
        print(f"Result: '{result}'")
        print("Checking that 'unknown' is used as fallback...")
        assert "[Tool: unknown" in result
    
    def test_handles_complex_json_arguments(self):
        """
        What it does: Verifies handling of complex JSON arguments.
        Purpose: Ensure nested JSON is preserved correctly.
        """
        print("Setup: Tool call with complex arguments...")
        complex_args = '{"files": ["a.py", "b.py"], "options": {"recursive": true}}'
        tool_calls = [{
            "id": "call_123",
            "type": "function",
            "function": {"name": "process", "arguments": complex_args}
        }]
        
        print("Action: Converting to text...")
        result = tool_calls_to_text(tool_calls)
        
        print(f"Result: '{result}'")
        print("Checking that complex arguments are preserved...")
        assert complex_args in result


# ==================================================================================================
# Tests for tool_results_to_text
# ==================================================================================================

class TestToolResultsToText:
    """
    Tests for tool_results_to_text function.
    
    This function converts tool_results to human-readable text representation.
    Used when stripping tool content from messages (when no tools are defined).
    """
    
    def test_converts_single_tool_result_to_text(self):
        """
        What it does: Verifies conversion of a single tool result to text.
        Purpose: Ensure basic conversion works correctly.
        """
        print("Setup: Single tool result...")
        tool_results = [{
            "type": "tool_result",
            "tool_use_id": "call_123",
            "content": "Operation completed successfully"
        }]
        
        print("Action: Converting to text...")
        result = tool_results_to_text(tool_results)
        
        print(f"Result: '{result}'")
        print("Checking that [Tool Result] marker is present...")
        assert "[Tool Result" in result
        print("Checking that content is present...")
        assert "Operation completed successfully" in result
    
    def test_converts_multiple_tool_results_to_text(self):
        """
        What it does: Verifies conversion of multiple tool results to text.
        Purpose: Ensure all tool results are converted and separated.
        """
        print("Setup: Multiple tool results...")
        tool_results = [
            {"type": "tool_result", "tool_use_id": "call_1", "content": "Result 1"},
            {"type": "tool_result", "tool_use_id": "call_2", "content": "Result 2"}
        ]
        
        print("Action: Converting to text...")
        result = tool_results_to_text(tool_results)
        
        print(f"Result: '{result}'")
        print("Checking that both results are present...")
        assert "Result 1" in result
        assert "Result 2" in result
        assert "call_1" in result
        assert "call_2" in result
    
    def test_includes_tool_use_id_in_output(self):
        """
        What it does: Verifies that tool_use_id is included in output.
        Purpose: Ensure traceability between tool calls and results.
        """
        print("Setup: Tool result with tool_use_id...")
        tool_results = [{
            "type": "tool_result",
            "tool_use_id": "tooluse_xyz789abc",
            "content": "Done"
        }]
        
        print("Action: Converting to text...")
        result = tool_results_to_text(tool_results)
        
        print(f"Result: '{result}'")
        print("Checking that tool_use_id is present...")
        assert "tooluse_xyz789abc" in result
    
    def test_handles_missing_tool_use_id(self):
        """
        What it does: Verifies handling of tool result without tool_use_id.
        Purpose: Ensure function doesn't crash when tool_use_id is missing.
        """
        print("Setup: Tool result without tool_use_id...")
        tool_results = [{
            "type": "tool_result",
            "content": "Some result"
        }]
        
        print("Action: Converting to text...")
        result = tool_results_to_text(tool_results)
        
        print(f"Result: '{result}'")
        print("Checking that content is still present...")
        assert "Some result" in result
        assert "[Tool Result]" in result
    
    def test_handles_empty_content(self):
        """
        What it does: Verifies handling of empty content.
        Purpose: Ensure empty content is replaced with placeholder.
        """
        print("Setup: Tool result with empty content...")
        tool_results = [{
            "type": "tool_result",
            "tool_use_id": "call_123",
            "content": ""
        }]
        
        print("Action: Converting to text...")
        result = tool_results_to_text(tool_results)
        
        print(f"Result: '{result}'")
        print("Checking that placeholder is used...")
        assert "(empty result)" in result
    
    def test_returns_empty_string_for_empty_list(self):
        """
        What it does: Verifies empty list handling.
        Purpose: Ensure empty input returns empty output.
        """
        print("Setup: Empty list...")
        
        print("Action: Converting to text...")
        result = tool_results_to_text([])
        
        print(f"Comparing result: Expected '', Got '{result}'")
        assert result == ""
    
    def test_handles_multiline_content(self):
        """
        What it does: Verifies handling of multiline content.
        Purpose: Ensure newlines in content are preserved.
        """
        print("Setup: Tool result with multiline content...")
        multiline_content = "Line 1\nLine 2\nLine 3"
        tool_results = [{
            "type": "tool_result",
            "tool_use_id": "call_123",
            "content": multiline_content
        }]
        
        print("Action: Converting to text...")
        result = tool_results_to_text(tool_results)
        
        print(f"Result: '{result}'")
        print("Checking that multiline content is preserved...")
        assert "Line 1\nLine 2\nLine 3" in result
    
    def test_handles_list_content(self):
        """
        What it does: Verifies handling of list content (multimodal format).
        Purpose: Ensure list content is extracted correctly.
        """
        print("Setup: Tool result with list content...")
        tool_results = [{
            "type": "tool_result",
            "tool_use_id": "call_123",
            "content": [{"type": "text", "text": "Extracted text"}]
        }]
        
        print("Action: Converting to text...")
        result = tool_results_to_text(tool_results)
        
        print(f"Result: '{result}'")
        print("Checking that text is extracted from list...")
        assert "Extracted text" in result


# ==================================================================================================
# Tests for build_kiro_payload with Issue #20 Scenario
# ==================================================================================================

class TestBuildKiroPayloadIssue20:
    """
    Tests for build_kiro_payload function specifically for Issue #20 scenario.
    
    Issue #20: OpenCode compaction returns 400 "Improperly formed request"
    because it sends tool_calls/tool_results in history but WITHOUT tools definitions.
    
    Kiro API requires tools definitions if toolUses/toolResults are present.
    The fix converts tool content to text representation when no tools are defined.
    """
    
    def test_compaction_without_tools_converts_tool_content_to_text(self):
        """
        What it does: Simulates OpenCode compaction scenario - messages with tool content but no tools.
        Purpose: Ensure build_kiro_payload doesn't crash and converts tool content to text.
        
        This is THE critical test for issue #20. If this test passes but the fix is removed,
        the actual API call would fail with 400 error.
        """
        print("Setup: Simulating OpenCode compaction scenario...")
        messages = [
            UnifiedMessage(role="user", content="Read the file test.py"),
            UnifiedMessage(
                role="assistant",
                content="",
                tool_calls=[{
                    "id": "tooluse_abc123",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "test.py"}'}
                }]
            ),
            UnifiedMessage(
                role="user",
                content="",
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "tooluse_abc123",
                    "content": "def hello():\n    print('world')"
                }]
            ),
            UnifiedMessage(role="assistant", content="I see the file contains a hello function."),
            UnifiedMessage(role="user", content="Summarize what we did")
        ]
        
        print("Action: Building Kiro payload WITHOUT tools (compaction scenario)...")
        result = build_kiro_payload(
            messages=messages,
            system_prompt="You are a helpful assistant.",
            model_id="claude-sonnet-4",
            tools=None,  # NO TOOLS - this is the compaction scenario
            conversation_id="test-conv-123",
            profile_arn="arn:aws:codewhisperer:us-east-1:123456789:profile/test",
            thinking_config=ThinkingConfig(enabled=False)
        )
        
        print(f"Result payload keys: {result.payload.keys()}")
        print("Checking that payload was built successfully...")
        assert "conversationState" in result.payload
        assert "currentMessage" in result.payload["conversationState"]
        
        print("Checking that history exists...")
        history = result.payload["conversationState"].get("history", [])
        print(f"History length: {len(history)}")
        assert len(history) > 0
        
        print("Checking that NO toolUses in history (they should be converted to text)...")
        for i, msg in enumerate(history):
            if "assistantResponseMessage" in msg:
                assistant_msg = msg["assistantResponseMessage"]
                print(f"History[{i}] assistant content: '{assistant_msg.get('content', '')[:100]}...'")
                assert "toolUses" not in assistant_msg, f"toolUses should not be in history[{i}]"
        
        print("Checking that NO toolResults in history (they should be converted to text)...")
        for i, msg in enumerate(history):
            if "userInputMessage" in msg:
                user_msg = msg["userInputMessage"]
                context = user_msg.get("userInputMessageContext", {})
                print(f"History[{i}] user content: '{user_msg.get('content', '')[:100]}...'")
                assert "toolResults" not in context, f"toolResults should not be in history[{i}]"
        
        print("Checking that tool content was converted to text (preserved context)...")
        # Find the assistant message that had tool_calls
        found_tool_text = False
        for msg in history:
            if "assistantResponseMessage" in msg:
                content = msg["assistantResponseMessage"].get("content", "")
                if "[Tool: read_file" in content:
                    found_tool_text = True
                    print(f"Found tool text representation: '{content[:200]}...'")
                    break
        assert found_tool_text, "Tool calls should be converted to text representation"
    
    def test_compaction_preserves_tool_result_content_as_text(self):
        """
        What it does: Verifies that tool result content is preserved as text.
        Purpose: Ensure the actual tool output is not lost during compaction.
        """
        print("Setup: Message with tool result containing important data...")
        messages = [
            UnifiedMessage(
                role="user",
                content="",
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "call_123",
                    "content": "IMPORTANT_DATA_12345"
                }]
            ),
            UnifiedMessage(role="user", content="What was in that result?")
        ]
        
        print("Action: Building Kiro payload without tools...")
        result = build_kiro_payload(
            messages=messages,
            system_prompt="",
            model_id="claude-sonnet-4",
            tools=None,
            conversation_id="test-conv",
            profile_arn="arn:test",
            thinking_config=ThinkingConfig(enabled=False)
        )
        
        print("Checking that important data is preserved...")
        # The data could be in history OR in current message (after merging adjacent user messages)
        payload = result.payload
        
        found_data = False
        
        # Check history
        history = payload["conversationState"].get("history", [])
        for msg in history:
            if "userInputMessage" in msg:
                content = msg["userInputMessage"].get("content", "")
                if "IMPORTANT_DATA_12345" in content:
                    found_data = True
                    print(f"Found preserved data in history: '{content[:100]}...'")
                    break
        
        # Check current message (adjacent user messages are merged)
        if not found_data:
            current_content = payload["conversationState"]["currentMessage"]["userInputMessage"].get("content", "")
            if "IMPORTANT_DATA_12345" in current_content:
                found_data = True
                print(f"Found preserved data in current message: '{current_content[:100]}...'")
        
        assert found_data, "Tool result content should be preserved as text"
    
    def test_with_tools_defined_keeps_tool_structure(self):
        """
        What it does: Verifies that when tools ARE defined, tool structure is preserved.
        Purpose: Ensure the fix doesn't break normal tool usage.
        """
        print("Setup: Messages with tool content AND tools defined...")
        messages = [
            UnifiedMessage(role="user", content="Call a tool"),
            UnifiedMessage(
                role="assistant",
                content="",
                tool_calls=[{
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "test_tool", "arguments": "{}"}
                }]
            ),
            UnifiedMessage(
                role="user",
                content="",
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "call_123",
                    "content": "Tool executed"
                }]
            ),
            UnifiedMessage(role="user", content="Continue")
        ]
        
        tools = [UnifiedTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}}
        )]
        
        print("Action: Building Kiro payload WITH tools...")
        result = build_kiro_payload(
            messages=messages,
            system_prompt="",
            model_id="claude-sonnet-4",
            tools=tools,  # TOOLS DEFINED
            conversation_id="test-conv",
            profile_arn="arn:test",
            thinking_config=ThinkingConfig(enabled=False)
        )
        
        print("Checking that tools are in payload...")
        current_msg = result.payload["conversationState"]["currentMessage"]["userInputMessage"]
        context = current_msg.get("userInputMessageContext", {})
        assert "tools" in context, "Tools should be in payload when defined"
        
        print("Checking that toolUses are preserved in history...")
        history = result.payload["conversationState"].get("history", [])
        found_tool_uses = False
        for msg in history:
            if "assistantResponseMessage" in msg:
                if "toolUses" in msg["assistantResponseMessage"]:
                    found_tool_uses = True
                    break
        assert found_tool_uses, "toolUses should be preserved when tools are defined"
    
    def test_empty_tools_list_triggers_stripping(self):
        """
        What it does: Verifies that empty tools list (tools=[]) triggers tool content stripping.
        Purpose: Ensure edge case of empty tools list is handled correctly.
        """
        print("Setup: Messages with tool content and empty tools list...")
        messages = [
            UnifiedMessage(
                role="assistant",
                content="",
                tool_calls=[{
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "some_tool", "arguments": "{}"}
                }]
            ),
            UnifiedMessage(role="user", content="Continue")
        ]
        
        print("Action: Building Kiro payload with empty tools list...")
        result = build_kiro_payload(
            messages=messages,
            system_prompt="",
            model_id="claude-sonnet-4",
            tools=[],  # EMPTY TOOLS LIST
            conversation_id="test-conv",
            profile_arn="arn:test",
            thinking_config=ThinkingConfig(enabled=False)
        )
        
        print("Checking that NO tools in payload...")
        current_msg = result.payload["conversationState"]["currentMessage"]["userInputMessage"]
        context = current_msg.get("userInputMessageContext", {})
        assert "tools" not in context, "Empty tools list should result in no tools in payload"
        
        print("Checking that tool content was converted to text...")
        history = result.payload["conversationState"].get("history", [])
        for msg in history:
            if "assistantResponseMessage" in msg:
                assert "toolUses" not in msg["assistantResponseMessage"]


# ==================================================================================================
# Tests for build_kiro_payload with Images (Issue #30)
# ==================================================================================================

class TestBuildKiroPayloadImages:
    """
    Tests for build_kiro_payload function with image content.
    
    Issue #30: 422 Validation Error when sending image content blocks.
    The fix adds support for image content blocks in messages.
    
    These tests verify that images are correctly included in the Kiro payload.
    """
    
    def test_includes_images_in_current_message(self):
        """
        What it does: Verifies that images are included in the current message.
        Purpose: Ensure images from the last user message are directly in userInputMessage (Issue #32 fix).
        
        This is a critical test for Issue #30/#32 fix - images should be in userInputMessage, NOT in userInputMessageContext.
        """
        print("Setup: User message with image as current message...")
        messages = [
            UnifiedMessage(
                role="user",
                content="What's in this image?",
                images=[{"media_type": "image/jpeg", "data": TEST_IMAGE_BASE64}]
            )
        ]
        
        print("Action: Building Kiro payload...")
        result = build_kiro_payload(
            messages=messages,
            system_prompt="You are a helpful assistant.",
            model_id="claude-sonnet-4",
            tools=None,
            conversation_id="test-conv-123",
            profile_arn="arn:aws:codewhisperer:us-east-1:123456789:profile/test",
            thinking_config=ThinkingConfig(enabled=False)
        )
        
        print(f"Result payload keys: {result.payload.keys()}")
        print("Checking that payload was built successfully...")
        assert "conversationState" in result.payload
        
        current_msg = result.payload["conversationState"]["currentMessage"]["userInputMessage"]
        print(f"Current message: {current_msg}")
        
        print("Checking that images are directly in userInputMessage (Issue #32 fix)...")
        assert "images" in current_msg
        
        images = current_msg["images"]
        print(f"Images: {images}")
        assert len(images) == 1
        
        print("Checking image format (Kiro format)...")
        assert images[0]["format"] == "jpeg"
        assert images[0]["source"]["bytes"] == TEST_IMAGE_BASE64
    
    def test_includes_multiple_images_in_current_message(self):
        """
        What it does: Verifies that multiple images are included in the current message.
        Purpose: Ensure all images from the last user message are directly in userInputMessage (Issue #32 fix).
        """
        print("Setup: User message with multiple images...")
        messages = [
            UnifiedMessage(
                role="user",
                content="Compare these images",
                images=[
                    {"media_type": "image/jpeg", "data": "image1_data"},
                    {"media_type": "image/png", "data": "image2_data"},
                    {"media_type": "image/gif", "data": "image3_data"}
                ]
            )
        ]
        
        print("Action: Building Kiro payload...")
        result = build_kiro_payload(
            messages=messages,
            system_prompt="",
            model_id="claude-sonnet-4",
            tools=None,
            conversation_id="test-conv",
            profile_arn="arn:test",
            thinking_config=ThinkingConfig(enabled=False)
        )
        
        current_msg = result.payload["conversationState"]["currentMessage"]["userInputMessage"]
        images = current_msg["images"]
        
        print(f"Comparing image count: Expected 3, Got {len(images)}")
        assert len(images) == 3
        
        print("Checking image formats...")
        assert images[0]["format"] == "jpeg"
        assert images[1]["format"] == "png"
        assert images[2]["format"] == "gif"
    
    def test_includes_images_in_history(self):
        """
        What it does: Verifies that images are included in history messages.
        Purpose: Ensure images from previous user messages are directly in userInputMessage (Issue #32 fix).
        """
        print("Setup: Conversation with images in history...")
        messages = [
            UnifiedMessage(
                role="user",
                content="What's in this image?",
                images=[{"media_type": "image/jpeg", "data": "history_image_data"}]
            ),
            UnifiedMessage(role="assistant", content="I see a cat in the image."),
            UnifiedMessage(role="user", content="What color is the cat?")
        ]
        
        print("Action: Building Kiro payload...")
        result = build_kiro_payload(
            messages=messages,
            system_prompt="",
            model_id="claude-sonnet-4",
            tools=None,
            conversation_id="test-conv",
            profile_arn="arn:test",
            thinking_config=ThinkingConfig(enabled=False)
        )
        
        print("Checking history...")
        history = result.payload["conversationState"]["history"]
        print(f"History length: {len(history)}")
        assert len(history) >= 1
        
        print("Checking that first history message has images directly in userInputMessage (Issue #32 fix)...")
        first_msg = history[0]["userInputMessage"]
        assert "images" in first_msg
        
        images = first_msg["images"]
        print(f"History images: {images}")
        assert len(images) == 1
        assert images[0]["format"] == "jpeg"
        assert images[0]["source"]["bytes"] == "history_image_data"
    
    def test_images_with_tools(self):
        """
        What it does: Verifies that images work correctly with tools.
        Purpose: Ensure images are in userInputMessage and tools are in userInputMessageContext (Issue #32 fix).
        """
        print("Setup: User message with image and tools defined...")
        messages = [
            UnifiedMessage(
                role="user",
                content="Analyze this image and use tools if needed",
                images=[{"media_type": "image/png", "data": "image_with_tools_data"}]
            )
        ]
        
        tools = [UnifiedTool(
            name="analyze_image",
            description="Analyze an image",
            input_schema={"type": "object", "properties": {}}
        )]
        
        print("Action: Building Kiro payload with tools...")
        result = build_kiro_payload(
            messages=messages,
            system_prompt="",
            model_id="claude-sonnet-4",
            tools=tools,
            conversation_id="test-conv",
            profile_arn="arn:test",
            thinking_config=ThinkingConfig(enabled=False)
        )
        
        current_msg = result.payload["conversationState"]["currentMessage"]["userInputMessage"]
        context = current_msg.get("userInputMessageContext", {})
        
        print("Checking that images are directly in userInputMessage (Issue #32 fix)...")
        assert "images" in current_msg
        
        print("Checking that tools are in userInputMessageContext...")
        assert "tools" in context
        
        print("Checking images...")
        assert len(current_msg["images"]) == 1
        assert current_msg["images"][0]["format"] == "png"
        
        print("Checking tools...")
        assert len(context["tools"]) == 1
        assert context["tools"][0]["toolSpecification"]["name"] == "analyze_image"
    
    def test_images_with_tool_results(self):
        """
        What it does: Verifies that images work correctly with tool results.
        Purpose: Ensure images are in userInputMessage and tool_results are in userInputMessageContext (Issue #32 fix).
        """
        print("Setup: User message with image and tool_results...")
        messages = [
            UnifiedMessage(role="user", content="Call a tool"),
            UnifiedMessage(
                role="assistant",
                content="",
                tool_calls=[{
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "get_data", "arguments": "{}"}
                }]
            ),
            UnifiedMessage(
                role="user",
                content="Here's the result and an image",
                images=[{"media_type": "image/jpeg", "data": "image_with_result_data"}],
                tool_results=[{
                    "type": "tool_result",
                    "tool_use_id": "call_123",
                    "content": "Tool output"
                }]
            )
        ]
        
        tools = [UnifiedTool(
            name="get_data",
            description="Get data",
            input_schema={"type": "object", "properties": {}}
        )]
        
        print("Action: Building Kiro payload...")
        result = build_kiro_payload(
            messages=messages,
            system_prompt="",
            model_id="claude-sonnet-4",
            tools=tools,
            conversation_id="test-conv",
            profile_arn="arn:test",
            thinking_config=ThinkingConfig(enabled=False)
        )
        
        # The last user message becomes current message
        current_msg = result.payload["conversationState"]["currentMessage"]["userInputMessage"]
        context = current_msg.get("userInputMessageContext", {})
        
        print("Checking that images are directly in userInputMessage (Issue #32 fix)...")
        assert "images" in current_msg
        
        print("Checking that toolResults are in userInputMessageContext...")
        assert "toolResults" in context
        
        print("Checking images...")
        assert len(current_msg["images"]) == 1
        assert current_msg["images"][0]["format"] == "jpeg"
        
        print("Checking toolResults...")
        assert len(context["toolResults"]) == 1
    
    def test_no_images_when_none_provided(self):
        """
        What it does: Verifies that images key is not added when no images are provided.
        Purpose: Ensure clean payload without unnecessary empty arrays.
        """
        print("Setup: User message without images...")
        messages = [
            UnifiedMessage(role="user", content="Hello, no images here")
        ]
        
        print("Action: Building Kiro payload...")
        result = build_kiro_payload(
            messages=messages,
            system_prompt="",
            model_id="claude-sonnet-4",
            tools=None,
            conversation_id="test-conv",
            profile_arn="arn:test",
            thinking_config=ThinkingConfig(enabled=False)
        )
        
        context = result.payload["conversationState"]["currentMessage"]["userInputMessage"].get("userInputMessageContext", {})
        
        print("Checking that images key is not present or empty...")
        # Either no images key, or empty images array
        if "images" in context:
            assert context["images"] == [], "Images should be empty when none provided"
        else:
            print("No images key - OK")
    
    def test_large_image_data_preserved(self):
        """
        What it does: Verifies that large image data is preserved without truncation.
        Purpose: Ensure large images are not corrupted during conversion (Issue #32 fix).
        """
        print("Setup: User message with large image data...")
        large_image_data = "A" * 500000  # 500KB of data
        messages = [
            UnifiedMessage(
                role="user",
                content="Analyze this large image",
                images=[{"media_type": "image/png", "data": large_image_data}]
            )
        ]
        
        print("Action: Building Kiro payload...")
        result = build_kiro_payload(
            messages=messages,
            system_prompt="",
            model_id="claude-sonnet-4",
            tools=None,
            conversation_id="test-conv",
            profile_arn="arn:test",
            thinking_config=ThinkingConfig(enabled=False)
        )
        
        current_msg = result.payload["conversationState"]["currentMessage"]["userInputMessage"]
        images = current_msg["images"]
        
        print(f"Checking image data length: Expected 500000, Got {len(images[0]['source']['bytes'])}")
        assert len(images[0]["source"]["bytes"]) == 500000
        assert images[0]["source"]["bytes"] == large_image_data
    
    def test_images_with_thinking_injection(self):
        """
        What it does: Verifies that images work correctly with thinking injection.
        Purpose: Ensure images are preserved in userInputMessage when fake reasoning is enabled (Issue #32 fix).
        """
        print("Setup: User message with image and thinking injection...")
        messages = [
            UnifiedMessage(
                role="user",
                content="What's in this image?",
                images=[{"media_type": "image/jpeg", "data": "thinking_test_image"}]
            )
        ]
        
        print("Action: Building Kiro payload with thinking injection...")
        with patch('kiro.converters_core.FAKE_REASONING_ENABLED', True):
            with patch('kiro.converters_core.FAKE_REASONING_MAX_TOKENS', 4000):
                result = build_kiro_payload(
                    messages=messages,
                    system_prompt="",
                    model_id="claude-sonnet-4",
                    tools=None,
                    conversation_id="test-conv",
                    profile_arn="arn:test",
                    thinking_config=ThinkingConfig(enabled=True)
                )
        
        current_msg = result.payload["conversationState"]["currentMessage"]["userInputMessage"]
        
        print("Checking that images are directly in userInputMessage (Issue #32 fix)...")
        assert "images" in current_msg
        assert len(current_msg["images"]) == 1
        assert current_msg["images"][0]["source"]["bytes"] == "thinking_test_image"
        
        print("Checking that thinking tags were injected in content...")
        content = current_msg["content"]
        assert "<thinking_mode>" in content


# ==================================================================================================
# Tests for validate_tool_names (Issue #41 fix)
# ==================================================================================================

class TestValidateToolNames:
    """
    Tests for validate_tool_names function.
    
    This function validates tool names against Kiro API 64-character limit.
    Issue #41: 400 Improperly formed request with long tool names from MCP servers.
    """
    
    def test_accepts_short_tool_names(self):
        """
        What it does: Verifies that short tool names are accepted.
        Purpose: Ensure normal tool names pass validation.
        """
        print("Setup: Tool with short name...")
        tools = [UnifiedTool(name="get_weather", description="Get weather")]
        
        print("Action: Validating tool names...")
        try:
            from kiro.converters_core import validate_tool_names
            validate_tool_names(tools)
            print("Validation passed - OK")
        except ValueError as e:
            print(f"ERROR: Validation failed: {e}")
            raise AssertionError("Short tool names should be accepted")
    
    def test_accepts_exactly_64_character_name(self):
        """
        What it does: Verifies that exactly 64-character names are accepted (boundary).
        Purpose: Ensure boundary case is handled correctly.
        """
        print("Setup: Tool with exactly 64-character name...")
        name_64 = "a" * 64
        tools = [UnifiedTool(name=name_64, description="Test")]
        
        print(f"Tool name length: {len(name_64)}")
        print("Action: Validating tool names...")
        try:
            from kiro.converters_core import validate_tool_names
            validate_tool_names(tools)
            print("Validation passed - OK")
        except ValueError as e:
            print(f"ERROR: Validation failed: {e}")
            raise AssertionError("64-character names should be accepted")
    
    def test_rejects_65_character_name(self):
        """
        What it does: Verifies that 65-character names are rejected.
        Purpose: Ensure names exceeding limit are caught.
        """
        print("Setup: Tool with 65-character name...")
        name_65 = "a" * 65
        tools = [UnifiedTool(name=name_65, description="Test")]
        
        print(f"Tool name length: {len(name_65)}")
        print("Action: Validating tool names (should raise ValueError)...")
        try:
            from kiro.converters_core import validate_tool_names
            validate_tool_names(tools)
            print("ERROR: Validation passed but should have failed")
            raise AssertionError("65-character names should be rejected")
        except ValueError as e:
            print(f"Validation correctly rejected: {str(e)[:100]}...")
            assert "exceed Kiro API limit" in str(e)
            assert name_65 in str(e)
    
    def test_rejects_very_long_tool_names(self):
        """
        What it does: Verifies that very long tool names are rejected.
        Purpose: Ensure the validation works for extreme cases.
        """
        print("Setup: Tool with 100-character name...")
        name_100 = "mcp__GitHub__" + "a" * 87
        tools = [UnifiedTool(name=name_100, description="Test")]
        
        print(f"Tool name length: {len(name_100)}")
        print("Action: Validating tool names (should raise ValueError)...")
        try:
            from kiro.converters_core import validate_tool_names
            validate_tool_names(tools)
            raise AssertionError("Very long names should be rejected")
        except ValueError as e:
            print(f"Validation correctly rejected: {str(e)[:100]}...")
            assert "exceed Kiro API limit" in str(e)
            assert "100 characters" in str(e)
    
    def test_rejects_multiple_long_names(self):
        """
        What it does: Verifies that all long names are listed in error message.
        Purpose: Ensure user sees all problematic tools at once.
        """
        print("Setup: Multiple tools with long names...")
        tools = [
            UnifiedTool(name="a" * 65, description="Test 1"),
            UnifiedTool(name="short", description="Test 2"),
            UnifiedTool(name="b" * 70, description="Test 3")
        ]
        
        print("Action: Validating tool names (should raise ValueError)...")
        try:
            from kiro.converters_core import validate_tool_names
            validate_tool_names(tools)
            raise AssertionError("Should reject multiple long names")
        except ValueError as e:
            error_msg = str(e)
            print(f"Error message: {error_msg[:200]}...")
            
            print("Checking that both long names are listed...")
            assert "65 characters" in error_msg
            assert "70 characters" in error_msg
    
    def test_handles_none_tools(self):
        """
        What it does: Verifies that None tools list is handled gracefully.
        Purpose: Ensure function doesn't crash on None input.
        """
        print("Setup: None tools...")
        
        print("Action: Validating None...")
        try:
            from kiro.converters_core import validate_tool_names
            validate_tool_names(None)
            print("Validation passed - OK")
        except Exception as e:
            print(f"ERROR: Unexpected exception: {e}")
            raise AssertionError("None should be handled gracefully")
    
    def test_handles_empty_tools_list(self):
        """
        What it does: Verifies that empty tools list is handled gracefully.
        Purpose: Ensure function doesn't crash on empty list.
        """
        print("Setup: Empty tools list...")
        
        print("Action: Validating empty list...")
        try:
            from kiro.converters_core import validate_tool_names
            validate_tool_names([])
            print("Validation passed - OK")
        except Exception as e:
            print(f"ERROR: Unexpected exception: {e}")
            raise AssertionError("Empty list should be handled gracefully")
    
    def test_error_message_includes_solution(self):
        """
        What it does: Verifies that error message includes solution guidance.
        Purpose: Ensure user knows how to fix the problem.
        """
        print("Setup: Tool with long name...")
        tools = [UnifiedTool(name="mcp__GitHub__" + "a" * 60, description="Test")]
        
        print("Action: Validating tool names (should raise ValueError)...")
        try:
            from kiro.converters_core import validate_tool_names
            validate_tool_names(tools)
            raise AssertionError("Should reject long name")
        except ValueError as e:
            error_msg = str(e)
            print(f"Error message: {error_msg[:300]}...")
            
            print("Checking that error message includes solution...")
            assert "Solution:" in error_msg
            assert "64 characters" in error_msg
            assert "Example:" in error_msg
    
    def test_real_world_mcp_tool_names(self):
        """
        What it does: Verifies rejection of real MCP tool names from Issue #41.
        Purpose: Ensure the fix works for actual problematic tool names.
        """
        print("Setup: Real MCP tool names from Issue #41...")
        problematic_names = [
            "mcp__GitHub__check_if_a_person_is_followed_by_the_authenticated_user",
            "mcp__GitHub__check_if_a_repository_is_starred_by_the_authenticated_user",
            "mcp__GitHub__remove_interaction_restrictions_from_your_public_repositories",
        ]
        
        tools = [UnifiedTool(name=name, description="Test") for name in problematic_names]
        
        print("Action: Validating real MCP tool names (should raise ValueError)...")
        try:
            from kiro.converters_core import validate_tool_names
            validate_tool_names(tools)
            raise AssertionError("Should reject real MCP tool names")
        except ValueError as e:
            error_msg = str(e)
            print(f"Error message length: {len(error_msg)} chars")
            print(f"Error message: {error_msg[:400]}...")
            
            print("Checking that all problematic names are listed...")
            for name in problematic_names:
                assert name in error_msg, f"Tool name '{name}' should be in error message"
            
            print("Checking that character counts are shown...")
            assert "68 characters" in error_msg
            assert "71 characters" in error_msg
            assert "74 characters" in error_msg


# ==================================================================================================
# Tests for get_truncation_recovery_system_addition (Truncation Recovery System)
# ==================================================================================================

class TestGetTruncationRecoverySystemAddition:
    """
    Tests for get_truncation_recovery_system_addition function.
    
    This function generates system prompt addition for truncation recovery legitimization.
    Part of Truncation Recovery System (Issue #56).
    """
    
    def test_returns_text_when_enabled(self):
        """
        What it does: Verifies truncation recovery text is added to system prompt when enabled.
        Purpose: Ensure legitimization text is present when recovery is enabled.
        """
        print("Setup: TRUNCATION_RECOVERY=true...")
        
        print("Action: Getting truncation recovery system addition...")
        with patch.dict(os.environ, {"TRUNCATION_RECOVERY": "true"}):
            from importlib import reload
            from kiro import config
            reload(config)
            
            from kiro.converters_core import get_truncation_recovery_system_addition
            addition = get_truncation_recovery_system_addition()
            print(f"Addition length: {len(addition)} chars")
        
        print("Checking that non-empty string is returned...")
        assert len(addition) > 0
        
        print("Checking that [System Notice] marker is present...")
        assert "[System Notice]" in addition
        
        print("Checking that [API Limitation] marker is present...")
        assert "[API Limitation]" in addition
        
        print("Checking that 'legitimate' is used to legitimize messages...")
        assert "legitimate" in addition.lower()
        
        print("Checking that prompt injection is explicitly denied...")
        assert "not prompt injection" in addition.lower()
    
    def test_returns_empty_string_when_disabled(self):
        """
        What it does: Verifies empty string is returned when recovery is disabled.
        Purpose: Ensure no system prompt pollution when feature is off.
        """
        print("Setup: TRUNCATION_RECOVERY=false...")
        
        print("Action: Getting truncation recovery system addition...")
        with patch.dict(os.environ, {"TRUNCATION_RECOVERY": "false"}):
            from importlib import reload
            from kiro import config
            reload(config)
            
            from kiro.converters_core import get_truncation_recovery_system_addition
            addition = get_truncation_recovery_system_addition()
            print(f"Addition: '{addition}'")
        
        print(f"Comparing result: Expected '', Got '{addition}'")
        assert addition == ""
    
    def test_format_has_proper_structure(self):
        """
        What it does: Verifies the format of the system prompt addition.
        Purpose: Ensure proper markdown formatting and structure.
        """
        print("Setup: TRUNCATION_RECOVERY=true...")
        
        print("Action: Getting truncation recovery system addition...")
        with patch.dict(os.environ, {"TRUNCATION_RECOVERY": "true"}):
            from importlib import reload
            from kiro import config
            reload(config)
            
            from kiro.converters_core import get_truncation_recovery_system_addition
            addition = get_truncation_recovery_system_addition()
        
        print("Checking that addition starts with separator...")
        assert addition.startswith("\n\n---\n")
        
        print("Checking that clear heading is present...")
        assert "# Output Truncation Handling" in addition
        
        lines = addition.split("\n")
        print(f"Comparing line count: Expected >5, Got {len(lines)}")
        assert len(lines) > 5


# ==================================================================================================
# Tests for Client Thinking Budget Support (Issue #111)
# ==================================================================================================

class TestThinkingConfig:
    """Tests for ThinkingConfig dataclass."""
    
    def test_default_values(self):
        """
        What it does: Verifies ThinkingConfig() creates instance with enabled=True, budget_tokens=None
        Purpose: Ensure default configuration enables thinking with default budget
        """
        print("Creating ThinkingConfig with defaults...")
        config = ThinkingConfig()
        
        print(f"Comparing: enabled={config.enabled}, budget_tokens={config.budget_tokens}")
        assert config.enabled is True
        assert config.budget_tokens is None
    
    def test_custom_values(self):
        """
        What it does: Verifies ThinkingConfig(enabled=False, budget_tokens=8000) stores values correctly
        Purpose: Ensure custom configuration is preserved
        """
        print("Creating ThinkingConfig with custom values...")
        config = ThinkingConfig(enabled=False, budget_tokens=8000)
        
        print(f"Comparing: enabled={config.enabled}, budget_tokens={config.budget_tokens}")
        assert config.enabled is False
        assert config.budget_tokens == 8000
    
    def test_disabled_with_budget(self):
        """
        What it does: Verifies ThinkingConfig can be disabled even with budget specified
        Purpose: Ensure enabled flag takes precedence over budget presence
        """
        print("Creating ThinkingConfig with enabled=False but budget=5000...")
        config = ThinkingConfig(enabled=False, budget_tokens=5000)
        
        print(f"Comparing: enabled={config.enabled}, budget_tokens={config.budget_tokens}")
        assert config.enabled is False
        assert config.budget_tokens == 5000


class TestInjectThinkingTagsWithConfig:
    """Tests for inject_thinking_tags with ThinkingConfig parameter."""
    
    def test_disabled_by_global_flag(self, monkeypatch):
        """
        What it does: Verifies that tags are NOT injected when FAKE_REASONING_ENABLED=False
        Purpose: Ensure global disable flag works regardless of config
        """
        print("Setting FAKE_REASONING_ENABLED=False...")
        monkeypatch.setattr("kiro.converters_core.FAKE_REASONING_ENABLED", False)
        
        config = ThinkingConfig(enabled=True, budget_tokens=8000)
        content = "Hello, world!"
        
        print(f"Calling inject_thinking_tags with config={config}...")
        result = inject_thinking_tags(content, config)
        
        print(f"Comparing result: expected='{content}', got='{result}'")
        assert result == content
    
    def test_disabled_by_client_request(self, monkeypatch):
        """
        What it does: Verifies that tags are NOT injected when thinking_config.enabled=False
        Purpose: Ensure client can disable thinking per-request
        """
        print("Setting FAKE_REASONING_ENABLED=True...")
        monkeypatch.setattr("kiro.converters_core.FAKE_REASONING_ENABLED", True)
        
        config = ThinkingConfig(enabled=False, budget_tokens=None)
        content = "Hello, world!"
        
        print(f"Calling inject_thinking_tags with config={config}...")
        result = inject_thinking_tags(content, config)
        
        print(f"Comparing result: expected='{content}', got='{result}'")
        assert result == content
    
    def test_uses_default_budget(self, monkeypatch):
        """
        What it does: Verifies that FAKE_REASONING_MAX_TOKENS is used when budget_tokens=None
        Purpose: Ensure default budget fallback works
        """
        print("Setting FAKE_REASONING_ENABLED=True, FAKE_REASONING_MAX_TOKENS=4000...")
        monkeypatch.setattr("kiro.converters_core.FAKE_REASONING_ENABLED", True)
        monkeypatch.setattr("kiro.converters_core.FAKE_REASONING_MAX_TOKENS", 4000)
        monkeypatch.setattr("kiro.converters_core.FAKE_REASONING_BUDGET_CAP", 10000)
        
        config = ThinkingConfig(enabled=True, budget_tokens=None)
        content = "Test content"
        
        print(f"Calling inject_thinking_tags with config={config}...")
        result = inject_thinking_tags(content, config)
        
        print(f"Checking for <max_thinking_length>4000</max_thinking_length>...")
        assert "<max_thinking_length>4000</max_thinking_length>" in result
        assert "<thinking_mode>enabled</thinking_mode>" in result
        assert "Test content" in result
    
    def test_uses_custom_budget(self, monkeypatch):
        """
        What it does: Verifies that custom budget_tokens is used when specified
        Purpose: Ensure client-provided budget is respected
        """
        print("Setting FAKE_REASONING_ENABLED=True...")
        monkeypatch.setattr("kiro.converters_core.FAKE_REASONING_ENABLED", True)
        monkeypatch.setattr("kiro.converters_core.FAKE_REASONING_BUDGET_CAP", 10000)
        
        config = ThinkingConfig(enabled=True, budget_tokens=8000)
        content = "Test content"
        
        print(f"Calling inject_thinking_tags with config={config}...")
        result = inject_thinking_tags(content, config)
        
        print(f"Checking for <max_thinking_length>8000</max_thinking_length>...")
        assert "<max_thinking_length>8000</max_thinking_length>" in result
        assert "<thinking_mode>enabled</thinking_mode>" in result
        assert "Test content" in result
    
    def test_applies_cap_with_warning(self, monkeypatch):
        """
        What it does: Verifies that budget > cap is capped and WARNING is logged
        Purpose: Ensure cap prevents excessive thinking budget
        """
        from unittest.mock import patch, call
        
        print("Setting FAKE_REASONING_ENABLED=True, cap=10000...")
        monkeypatch.setattr("kiro.converters_core.FAKE_REASONING_ENABLED", True)
        monkeypatch.setattr("kiro.converters_core.FAKE_REASONING_BUDGET_CAP", 10000)
        
        config = ThinkingConfig(enabled=True, budget_tokens=50000)
        content = "Test content"
        
        print(f"Calling inject_thinking_tags with budget=50000 (exceeds cap)...")
        # Mock logger.warning to verify it's called
        with patch("kiro.converters_core.logger.warning") as mock_warning:
            result = inject_thinking_tags(content, config)
            
            print(f"Checking for capped value <max_thinking_length>10000</max_thinking_length>...")
            assert "<max_thinking_length>10000</max_thinking_length>" in result
            
            print(f"Checking that logger.warning was called...")
            assert mock_warning.called, "logger.warning should be called when budget exceeds cap"
            
            # Verify warning message content
            warning_call = mock_warning.call_args[0][0]
            print(f"Warning message: {warning_call}")
            assert "exceeds cap" in warning_call
            assert "50000" in warning_call
            assert "10000" in warning_call
    
    def test_uses_budget_when_below_cap(self, monkeypatch):
        """
        What it does: Verifies that budget < cap is used without modification
        Purpose: Ensure cap doesn't affect budgets below limit
        """
        print("Setting FAKE_REASONING_ENABLED=True, cap=10000...")
        monkeypatch.setattr("kiro.converters_core.FAKE_REASONING_ENABLED", True)
        monkeypatch.setattr("kiro.converters_core.FAKE_REASONING_BUDGET_CAP", 10000)
        
        config = ThinkingConfig(enabled=True, budget_tokens=5000)
        content = "Test content"
        
        print(f"Calling inject_thinking_tags with budget=5000 (below cap)...")
        result = inject_thinking_tags(content, config)
        
        print(f"Checking for <max_thinking_length>5000</max_thinking_length>...")
        assert "<max_thinking_length>5000</max_thinking_length>" in result
    
    def test_cap_disabled_when_zero(self, monkeypatch):
        """
        What it does: Verifies that cap is NOT applied when FAKE_REASONING_BUDGET_CAP=0
        Purpose: Ensure users can disable capping
        """
        print("Setting FAKE_REASONING_ENABLED=True, cap=0 (disabled)...")
        monkeypatch.setattr("kiro.converters_core.FAKE_REASONING_ENABLED", True)
        monkeypatch.setattr("kiro.converters_core.FAKE_REASONING_BUDGET_CAP", 0)
        
        config = ThinkingConfig(enabled=True, budget_tokens=50000)
        content = "Test content"
        
        print(f"Calling inject_thinking_tags with budget=50000 (cap disabled)...")
        result = inject_thinking_tags(content, config)
        
        print(f"Checking for <max_thinking_length>50000</max_thinking_length>...")
        assert "<max_thinking_length>50000</max_thinking_length>" in result


class TestBuildKiroPayloadWithThinkingConfig:
    """Tests for build_kiro_payload with thinking_config parameter."""
    
    def test_passes_thinking_config_to_inject(self, monkeypatch):
        """
        What it does: Verifies that build_kiro_payload passes thinking_config to inject_thinking_tags
        Purpose: Ensure thinking configuration flows through the pipeline
        """
        print("Setting up mocks...")
        monkeypatch.setattr("kiro.converters_core.FAKE_REASONING_ENABLED", True)
        monkeypatch.setattr("kiro.converters_core.FAKE_REASONING_BUDGET_CAP", 10000)
        
        messages = [UnifiedMessage(role="user", content="Test message")]
        thinking_config = ThinkingConfig(enabled=True, budget_tokens=7000)
        
        print(f"Calling build_kiro_payload with thinking_config={thinking_config}...")
        result = build_kiro_payload(
            messages=messages,
            system_prompt="",
            model_id="claude-sonnet-4.5",
            tools=None,
            conversation_id="test-conv-123",
            profile_arn="arn:aws:test",
            thinking_config=thinking_config
        )
        
        print("Extracting userInputMessage content...")
        user_input = result.payload["conversationState"]["currentMessage"]["userInputMessage"]
        content = user_input["content"]
        
        print(f"Checking for <max_thinking_length>7000</max_thinking_length> in content...")
        assert "<max_thinking_length>7000</max_thinking_length>" in content
        assert "<thinking_mode>enabled</thinking_mode>" in content