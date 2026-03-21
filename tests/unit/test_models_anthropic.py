# -*- coding: utf-8 -*-

"""
Unit tests for Anthropic Pydantic models.

Comprehensive tests for all Anthropic API models:
- Content blocks (text, image, tool_use, tool_result, thinking)
- Image sources (base64, URL)
- Messages and requests
- Tools and tool choice
- Responses and streaming events
- Error models
"""

import pytest
from pydantic import ValidationError

from kiro.models_anthropic import (
    # Content blocks
    TextContentBlock,
    ThinkingContentBlock,
    ToolUseContentBlock,
    ToolResultContentBlock,
    # Image models
    Base64ImageSource,
    URLImageSource,
    ImageContentBlock,
    ContentBlock,
    # Message models
    AnthropicMessage,
    # Tool models
    AnthropicTool,
    ToolChoiceAuto,
    ToolChoiceAny,
    ToolChoiceTool,
    ToolChoice,
    # Request models
    SystemContentBlock,
    AnthropicMessagesRequest,
    # Response models
    AnthropicUsage,
    AnthropicMessagesResponse,
    # Streaming models
    MessageStartEvent,
    ContentBlockStartEvent,
    TextDelta,
    ThinkingDelta,
    InputJsonDelta,
    ContentBlockDeltaEvent,
    ContentBlockStopEvent,
    MessageDeltaUsage,
    MessageDeltaEvent,
    MessageStopEvent,
    PingEvent,
    ErrorEvent,
    # Error models
    AnthropicErrorDetail,
    AnthropicErrorResponse,
)


# Base64 1x1 pixel JPEG for testing
TEST_IMAGE_BASE64 = "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AVN//2Q=="


# ==================================================================================================
# Tests for Base64ImageSource
# ==================================================================================================

class TestBase64ImageSource:
    """Tests for Base64ImageSource Pydantic model."""
    
    def test_valid_base64_source(self):
        """
        What it does: Verifies creation of valid Base64ImageSource.
        Purpose: Ensure model accepts valid base64 image data.
        """
        print("Setup: Creating Base64ImageSource with valid data...")
        source = Base64ImageSource(
            type="base64",
            media_type="image/jpeg",
            data=TEST_IMAGE_BASE64
        )
        
        print(f"Result: {source}")
        print(f"Comparing type: Expected 'base64', Got '{source.type}'")
        assert source.type == "base64"
        
        print(f"Comparing media_type: Expected 'image/jpeg', Got '{source.media_type}'")
        assert source.media_type == "image/jpeg"
        
        print(f"Comparing data: Expected {TEST_IMAGE_BASE64[:20]}..., Got {source.data[:20]}...")
        assert source.data == TEST_IMAGE_BASE64
    
    def test_type_defaults_to_base64(self):
        """
        What it does: Verifies that type defaults to "base64".
        Purpose: Ensure default value is set correctly.
        """
        print("Setup: Creating Base64ImageSource without explicit type...")
        source = Base64ImageSource(
            media_type="image/png",
            data=TEST_IMAGE_BASE64
        )
        
        print(f"Comparing type: Expected 'base64', Got '{source.type}'")
        assert source.type == "base64"
    
    def test_requires_media_type(self):
        """
        What it does: Verifies that media_type is required.
        Purpose: Ensure validation fails without media_type.
        """
        print("Setup: Attempting to create Base64ImageSource without media_type...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            Base64ImageSource(data=TEST_IMAGE_BASE64)
        
        print(f"ValidationError raised: {exc_info.value}")
        assert "media_type" in str(exc_info.value)
    
    def test_requires_data(self):
        """
        What it does: Verifies that data is required.
        Purpose: Ensure validation fails without data.
        """
        print("Setup: Attempting to create Base64ImageSource without data...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            Base64ImageSource(media_type="image/jpeg")
        
        print(f"ValidationError raised: {exc_info.value}")
        assert "data" in str(exc_info.value)
    
    def test_accepts_various_media_types(self):
        """
        What it does: Verifies acceptance of various image media types.
        Purpose: Ensure all common image formats are supported.
        """
        print("Setup: Testing various media types...")
        media_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
        
        for media_type in media_types:
            print(f"Testing media_type: {media_type}")
            source = Base64ImageSource(media_type=media_type, data=TEST_IMAGE_BASE64)
            assert source.media_type == media_type
        
        print("All media types accepted successfully")


# ==================================================================================================
# Tests for URLImageSource
# ==================================================================================================

class TestURLImageSource:
    """Tests for URLImageSource Pydantic model."""
    
    def test_valid_url_source(self):
        """
        What it does: Verifies creation of valid URLImageSource.
        Purpose: Ensure model accepts valid URL.
        """
        print("Setup: Creating URLImageSource with valid URL...")
        source = URLImageSource(
            type="url",
            url="https://example.com/image.jpg"
        )
        
        print(f"Result: {source}")
        print(f"Comparing type: Expected 'url', Got '{source.type}'")
        assert source.type == "url"
        
        print(f"Comparing url: Expected 'https://example.com/image.jpg', Got '{source.url}'")
        assert source.url == "https://example.com/image.jpg"
    
    def test_type_defaults_to_url(self):
        """
        What it does: Verifies that type defaults to "url".
        Purpose: Ensure default value is set correctly.
        """
        print("Setup: Creating URLImageSource without explicit type...")
        source = URLImageSource(url="https://example.com/image.png")
        
        print(f"Comparing type: Expected 'url', Got '{source.type}'")
        assert source.type == "url"
    
    def test_requires_url(self):
        """
        What it does: Verifies that url is required.
        Purpose: Ensure validation fails without url.
        """
        print("Setup: Attempting to create URLImageSource without url...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            URLImageSource()
        
        print(f"ValidationError raised: {exc_info.value}")
        assert "url" in str(exc_info.value)


# ==================================================================================================
# Tests for ImageContentBlock
# ==================================================================================================

class TestImageContentBlock:
    """Tests for ImageContentBlock Pydantic model."""
    
    def test_with_base64_source(self):
        """
        What it does: Verifies creation of ImageContentBlock with base64 source.
        Purpose: Ensure model accepts Base64ImageSource.
        """
        print("Setup: Creating ImageContentBlock with base64 source...")
        block = ImageContentBlock(
            type="image",
            source=Base64ImageSource(
                media_type="image/jpeg",
                data=TEST_IMAGE_BASE64
            )
        )
        
        print(f"Result: {block}")
        print(f"Comparing type: Expected 'image', Got '{block.type}'")
        assert block.type == "image"
        
        print(f"Comparing source.type: Expected 'base64', Got '{block.source.type}'")
        assert block.source.type == "base64"
        assert block.source.media_type == "image/jpeg"
    
    def test_with_url_source(self):
        """
        What it does: Verifies creation of ImageContentBlock with URL source.
        Purpose: Ensure model accepts URLImageSource.
        """
        print("Setup: Creating ImageContentBlock with URL source...")
        block = ImageContentBlock(
            type="image",
            source=URLImageSource(url="https://example.com/image.jpg")
        )
        
        print(f"Result: {block}")
        print(f"Comparing type: Expected 'image', Got '{block.type}'")
        assert block.type == "image"
        
        print(f"Comparing source.type: Expected 'url', Got '{block.source.type}'")
        assert block.source.type == "url"
        assert block.source.url == "https://example.com/image.jpg"
    
    def test_with_dict_base64_source(self):
        """
        What it does: Verifies creation of ImageContentBlock with dict source.
        Purpose: Ensure model accepts dict that matches Base64ImageSource schema.
        """
        print("Setup: Creating ImageContentBlock with dict source...")
        block = ImageContentBlock(
            type="image",
            source={
                "type": "base64",
                "media_type": "image/png",
                "data": TEST_IMAGE_BASE64
            }
        )
        
        print(f"Result: {block}")
        print(f"Comparing source.type: Expected 'base64', Got '{block.source.type}'")
        assert block.source.type == "base64"
        assert block.source.media_type == "image/png"
    
    def test_with_dict_url_source(self):
        """
        What it does: Verifies creation of ImageContentBlock with dict URL source.
        Purpose: Ensure model accepts dict that matches URLImageSource schema.
        """
        print("Setup: Creating ImageContentBlock with dict URL source...")
        block = ImageContentBlock(
            type="image",
            source={
                "type": "url",
                "url": "https://example.com/test.gif"
            }
        )
        
        print(f"Result: {block}")
        print(f"Comparing source.type: Expected 'url', Got '{block.source.type}'")
        assert block.source.type == "url"
        assert block.source.url == "https://example.com/test.gif"
    
    def test_type_literal_is_image(self):
        """
        What it does: Verifies that type must be "image".
        Purpose: Ensure type literal validation works.
        """
        print("Setup: Creating ImageContentBlock with correct type...")
        block = ImageContentBlock(
            source=Base64ImageSource(media_type="image/jpeg", data=TEST_IMAGE_BASE64)
        )
        
        print(f"Comparing type: Expected 'image', Got '{block.type}'")
        assert block.type == "image"
    
    def test_requires_source(self):
        """
        What it does: Verifies that source is required.
        Purpose: Ensure validation fails without source.
        """
        print("Setup: Attempting to create ImageContentBlock without source...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            ImageContentBlock(type="image")
        
        print(f"ValidationError raised: {exc_info.value}")
        assert "source" in str(exc_info.value)


# ==================================================================================================
# Tests for ContentBlock Union
# ==================================================================================================

class TestContentBlockUnion:
    """Tests for ContentBlock union type accepting ImageContentBlock."""
    
    def test_accepts_text_content_block(self):
        """
        What it does: Verifies ContentBlock accepts TextContentBlock.
        Purpose: Ensure union includes text blocks.
        """
        print("Setup: Creating TextContentBlock...")
        block: ContentBlock = TextContentBlock(text="Hello, world!")
        
        print(f"Result: {block}")
        print(f"Comparing type: Expected 'text', Got '{block.type}'")
        assert block.type == "text"
        assert block.text == "Hello, world!"
    
    def test_accepts_image_content_block(self):
        """
        What it does: Verifies ContentBlock accepts ImageContentBlock.
        Purpose: Ensure union includes image blocks (Issue #30 fix).
        
        This is the key test that verifies the fix for Issue #30.
        Before the fix, ContentBlock union did not include ImageContentBlock,
        causing 422 Validation Error when image content was sent.
        """
        print("Setup: Creating ImageContentBlock...")
        block: ContentBlock = ImageContentBlock(
            source=Base64ImageSource(media_type="image/jpeg", data=TEST_IMAGE_BASE64)
        )
        
        print(f"Result: {block}")
        print(f"Comparing type: Expected 'image', Got '{block.type}'")
        assert block.type == "image"
        assert block.source.type == "base64"
    
    def test_accepts_tool_use_content_block(self):
        """
        What it does: Verifies ContentBlock accepts ToolUseContentBlock.
        Purpose: Ensure union includes tool_use blocks.
        """
        print("Setup: Creating ToolUseContentBlock...")
        block: ContentBlock = ToolUseContentBlock(
            id="call_123",
            name="get_weather",
            input={"location": "Moscow"}
        )
        
        print(f"Result: {block}")
        print(f"Comparing type: Expected 'tool_use', Got '{block.type}'")
        assert block.type == "tool_use"
    
    def test_accepts_tool_result_content_block(self):
        """
        What it does: Verifies ContentBlock accepts ToolResultContentBlock.
        Purpose: Ensure union includes tool_result blocks.
        """
        print("Setup: Creating ToolResultContentBlock...")
        block: ContentBlock = ToolResultContentBlock(
            tool_use_id="call_123",
            content="Weather: Sunny, 25°C"
        )
        
        print(f"Result: {block}")
        print(f"Comparing type: Expected 'tool_result', Got '{block.type}'")
        assert block.type == "tool_result"


# ==================================================================================================
# Tests for AnthropicMessage with Image Content (Issue #30 fix verification)
# ==================================================================================================

class TestAnthropicMessageWithImages:
    """
    Tests for AnthropicMessage with image content.
    
    These tests verify the fix for Issue #30 - 422 Validation Error
    when sending image content blocks in messages.
    """
    
    def test_message_with_image_content_validates(self):
        """
        What it does: Verifies AnthropicMessage accepts image content blocks.
        Purpose: This is the PRIMARY test for Issue #30 fix.
        
        Before the fix, this would raise a ValidationError because
        ContentBlock union did not include ImageContentBlock.
        """
        print("Setup: Creating AnthropicMessage with image content...")
        message = AnthropicMessage(
            role="user",
            content=[
                TextContentBlock(text="What's in this image?"),
                ImageContentBlock(
                    source=Base64ImageSource(
                        media_type="image/jpeg",
                        data=TEST_IMAGE_BASE64
                    )
                )
            ]
        )
        
        print(f"Result: {message}")
        print(f"Comparing role: Expected 'user', Got '{message.role}'")
        assert message.role == "user"
        
        print(f"Comparing content length: Expected 2, Got {len(message.content)}")
        assert len(message.content) == 2
        
        print(f"Comparing content[0].type: Expected 'text', Got '{message.content[0].type}'")
        assert message.content[0].type == "text"
        
        print(f"Comparing content[1].type: Expected 'image', Got '{message.content[1].type}'")
        assert message.content[1].type == "image"
    
    def test_message_with_dict_image_content_validates(self):
        """
        What it does: Verifies AnthropicMessage accepts dict image content.
        Purpose: Ensure raw dict format (as received from API) validates correctly.
        
        This is how the actual API request comes in - as raw dicts, not Pydantic models.
        """
        print("Setup: Creating AnthropicMessage with dict image content...")
        message = AnthropicMessage(
            role="user",
            content=[
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
        )
        
        print(f"Result: {message}")
        print(f"Comparing content length: Expected 2, Got {len(message.content)}")
        assert len(message.content) == 2
        
        print(f"Comparing content[1].type: Expected 'image', Got '{message.content[1].type}'")
        assert message.content[1].type == "image"
        assert message.content[1].source.type == "base64"
    
    def test_message_with_multiple_images_validates(self):
        """
        What it does: Verifies AnthropicMessage accepts multiple images.
        Purpose: Ensure multiple image blocks in one message work correctly.
        """
        print("Setup: Creating AnthropicMessage with multiple images...")
        message = AnthropicMessage(
            role="user",
            content=[
                {"type": "text", "text": "Compare these images"},
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": TEST_IMAGE_BASE64}
                },
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": TEST_IMAGE_BASE64}
                },
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/webp", "data": TEST_IMAGE_BASE64}
                }
            ]
        )
        
        print(f"Result content length: {len(message.content)}")
        assert len(message.content) == 4
        
        image_blocks = [b for b in message.content if b.type == "image"]
        print(f"Image blocks count: {len(image_blocks)}")
        assert len(image_blocks) == 3
    
    def test_message_with_url_image_validates(self):
        """
        What it does: Verifies AnthropicMessage accepts URL image source.
        Purpose: Ensure URL-based images are accepted (even if not fully supported).
        """
        print("Setup: Creating AnthropicMessage with URL image...")
        message = AnthropicMessage(
            role="user",
            content=[
                {"type": "text", "text": "What's in this image?"},
                {
                    "type": "image",
                    "source": {
                        "type": "url",
                        "url": "https://example.com/image.jpg"
                    }
                }
            ]
        )
        
        print(f"Result: {message}")
        print(f"Comparing content[1].source.type: Expected 'url', Got '{message.content[1].source.type}'")
        assert message.content[1].source.type == "url"
        assert message.content[1].source.url == "https://example.com/image.jpg"


# ==================================================================================================
# Tests for AnthropicMessagesRequest with Image Content
# ==================================================================================================

class TestAnthropicMessagesRequestWithImages:
    """Tests for full AnthropicMessagesRequest with image content."""
    
    def test_request_with_image_message_validates(self):
        """
        What it does: Verifies full request with image content validates.
        Purpose: End-to-end validation test for Issue #30 fix.
        
        This simulates the actual request that was failing with 422 error.
        """
        print("Setup: Creating full AnthropicMessagesRequest with image...")
        request = AnthropicMessagesRequest(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            messages=[
                AnthropicMessage(
                    role="user",
                    content=[
                        {"type": "text", "text": "What's in this image?"},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": TEST_IMAGE_BASE64
                            }
                        }
                    ]
                )
            ]
        )
        
        print(f"Result: {request}")
        print(f"Comparing model: Expected 'claude-sonnet-4-5', Got '{request.model}'")
        assert request.model == "claude-sonnet-4-5"
        
        print(f"Comparing messages count: Expected 1, Got {len(request.messages)}")
        assert len(request.messages) == 1
        
        print(f"Comparing content count: Expected 2, Got {len(request.messages[0].content)}")
        assert len(request.messages[0].content) == 2
        
        print("Request with image content validated successfully!")
    
    def test_request_with_conversation_including_images(self):
        """
        What it does: Verifies multi-turn conversation with images validates.
        Purpose: Ensure images work in conversation context.
        """
        print("Setup: Creating multi-turn conversation with images...")
        request = AnthropicMessagesRequest(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            messages=[
                AnthropicMessage(
                    role="user",
                    content=[
                        {"type": "text", "text": "What's in this image?"},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": TEST_IMAGE_BASE64
                            }
                        }
                    ]
                ),
                AnthropicMessage(
                    role="assistant",
                    content="I can see a small test image."
                ),
                AnthropicMessage(
                    role="user",
                    content="Can you describe it in more detail?"
                )
            ]
        )
        
        print(f"Result messages count: {len(request.messages)}")
        assert len(request.messages) == 3
        
        # First message has image
        assert request.messages[0].content[1].type == "image"
        
        # Second message is string (assistant)
        assert request.messages[1].content == "I can see a small test image."
        
        # Third message is string (user follow-up)
        assert request.messages[2].content == "Can you describe it in more detail?"
        
        print("Multi-turn conversation with images validated successfully!")


# ==================================================================================================
# Tests for TextContentBlock
# ==================================================================================================

class TestTextContentBlock:
    """Tests for TextContentBlock Pydantic model."""
    
    def test_valid_text_block(self):
        """
        What it does: Verifies creation of valid TextContentBlock.
        Purpose: Ensure model accepts valid text content.
        """
        print("Setup: Creating TextContentBlock with valid text...")
        block = TextContentBlock(text="Hello, world!")
        
        print(f"Result: {block}")
        print(f"Comparing type: Expected 'text', Got '{block.type}'")
        assert block.type == "text"
        
        print(f"Comparing text: Expected 'Hello, world!', Got '{block.text}'")
        assert block.text == "Hello, world!"
    
    def test_type_defaults_to_text(self):
        """
        What it does: Verifies that type defaults to "text".
        Purpose: Ensure default value is set correctly.
        """
        print("Setup: Creating TextContentBlock without explicit type...")
        block = TextContentBlock(text="Test")
        
        print(f"Comparing type: Expected 'text', Got '{block.type}'")
        assert block.type == "text"
    
    def test_requires_text(self):
        """
        What it does: Verifies that text is required.
        Purpose: Ensure validation fails without text.
        """
        print("Setup: Attempting to create TextContentBlock without text...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            TextContentBlock()
        
        print(f"ValidationError raised: {exc_info.value}")
        assert "text" in str(exc_info.value)
    
    def test_accepts_empty_string(self):
        """
        What it does: Verifies that empty string is accepted.
        Purpose: Ensure empty text is valid.
        """
        print("Setup: Creating TextContentBlock with empty string...")
        block = TextContentBlock(text="")
        
        print(f"Comparing text: Expected '', Got '{block.text}'")
        assert block.text == ""
    
    def test_accepts_multiline_text(self):
        """
        What it does: Verifies that multiline text is accepted.
        Purpose: Ensure newlines are preserved.
        """
        print("Setup: Creating TextContentBlock with multiline text...")
        multiline = "Line 1\nLine 2\nLine 3"
        block = TextContentBlock(text=multiline)
        
        print(f"Comparing text: Expected multiline, Got '{block.text}'")
        assert block.text == multiline
        assert "\n" in block.text


# ==================================================================================================
# Tests for ThinkingContentBlock
# ==================================================================================================

class TestThinkingContentBlock:
    """Tests for ThinkingContentBlock Pydantic model."""
    
    def test_valid_thinking_block(self):
        """
        What it does: Verifies creation of valid ThinkingContentBlock.
        Purpose: Ensure model accepts valid thinking content.
        """
        print("Setup: Creating ThinkingContentBlock with valid thinking...")
        block = ThinkingContentBlock(
            thinking="Let me analyze this step by step...",
            signature="abc123"
        )
        
        print(f"Result: {block}")
        print(f"Comparing type: Expected 'thinking', Got '{block.type}'")
        assert block.type == "thinking"
        
        print(f"Comparing thinking: Got '{block.thinking[:30]}...'")
        assert block.thinking == "Let me analyze this step by step..."
        
        print(f"Comparing signature: Expected 'abc123', Got '{block.signature}'")
        assert block.signature == "abc123"
    
    def test_type_defaults_to_thinking(self):
        """
        What it does: Verifies that type defaults to "thinking".
        Purpose: Ensure default value is set correctly.
        """
        print("Setup: Creating ThinkingContentBlock without explicit type...")
        block = ThinkingContentBlock(thinking="Test thinking")
        
        print(f"Comparing type: Expected 'thinking', Got '{block.type}'")
        assert block.type == "thinking"
    
    def test_signature_defaults_to_empty(self):
        """
        What it does: Verifies that signature defaults to empty string.
        Purpose: Ensure default value is set correctly.
        """
        print("Setup: Creating ThinkingContentBlock without signature...")
        block = ThinkingContentBlock(thinking="Test")
        
        print(f"Comparing signature: Expected '', Got '{block.signature}'")
        assert block.signature == ""
    
    def test_requires_thinking(self):
        """
        What it does: Verifies that thinking is required.
        Purpose: Ensure validation fails without thinking.
        """
        print("Setup: Attempting to create ThinkingContentBlock without thinking...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            ThinkingContentBlock()
        
        print(f"ValidationError raised: {exc_info.value}")
        assert "thinking" in str(exc_info.value)


# ==================================================================================================
# Tests for ToolUseContentBlock
# ==================================================================================================

class TestToolUseContentBlock:
    """Tests for ToolUseContentBlock Pydantic model."""
    
    def test_valid_tool_use_block(self):
        """
        What it does: Verifies creation of valid ToolUseContentBlock.
        Purpose: Ensure model accepts valid tool use data.
        """
        print("Setup: Creating ToolUseContentBlock with valid data...")
        block = ToolUseContentBlock(
            id="call_123",
            name="get_weather",
            input={"location": "Moscow", "units": "celsius"}
        )
        
        print(f"Result: {block}")
        print(f"Comparing type: Expected 'tool_use', Got '{block.type}'")
        assert block.type == "tool_use"
        
        print(f"Comparing id: Expected 'call_123', Got '{block.id}'")
        assert block.id == "call_123"
        
        print(f"Comparing name: Expected 'get_weather', Got '{block.name}'")
        assert block.name == "get_weather"
        
        print(f"Comparing input: Got {block.input}")
        assert block.input == {"location": "Moscow", "units": "celsius"}
    
    def test_type_defaults_to_tool_use(self):
        """
        What it does: Verifies that type defaults to "tool_use".
        Purpose: Ensure default value is set correctly.
        """
        print("Setup: Creating ToolUseContentBlock without explicit type...")
        block = ToolUseContentBlock(id="call_1", name="test", input={})
        
        print(f"Comparing type: Expected 'tool_use', Got '{block.type}'")
        assert block.type == "tool_use"
    
    def test_requires_id(self):
        """
        What it does: Verifies that id is required.
        Purpose: Ensure validation fails without id.
        """
        print("Setup: Attempting to create ToolUseContentBlock without id...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            ToolUseContentBlock(name="test", input={})
        
        print(f"ValidationError raised: {exc_info.value}")
        assert "id" in str(exc_info.value)
    
    def test_requires_name(self):
        """
        What it does: Verifies that name is required.
        Purpose: Ensure validation fails without name.
        """
        print("Setup: Attempting to create ToolUseContentBlock without name...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            ToolUseContentBlock(id="call_1", input={})
        
        print(f"ValidationError raised: {exc_info.value}")
        assert "name" in str(exc_info.value)
    
    def test_requires_input(self):
        """
        What it does: Verifies that input is required.
        Purpose: Ensure validation fails without input.
        """
        print("Setup: Attempting to create ToolUseContentBlock without input...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            ToolUseContentBlock(id="call_1", name="test")
        
        print(f"ValidationError raised: {exc_info.value}")
        assert "input" in str(exc_info.value)
    
    def test_accepts_empty_input(self):
        """
        What it does: Verifies that empty input dict is accepted.
        Purpose: Ensure tools without parameters work.
        """
        print("Setup: Creating ToolUseContentBlock with empty input...")
        block = ToolUseContentBlock(id="call_1", name="no_params_tool", input={})
        
        print(f"Comparing input: Expected {{}}, Got {block.input}")
        assert block.input == {}
    
    def test_accepts_complex_input(self):
        """
        What it does: Verifies that complex nested input is accepted.
        Purpose: Ensure nested structures work.
        """
        print("Setup: Creating ToolUseContentBlock with complex input...")
        complex_input = {
            "query": "test",
            "options": {"limit": 10, "offset": 0},
            "filters": ["active", "recent"]
        }
        block = ToolUseContentBlock(id="call_1", name="search", input=complex_input)
        
        print(f"Comparing input: Got {block.input}")
        assert block.input == complex_input


# ==================================================================================================
# Tests for ToolResultContentBlock
# ==================================================================================================

class TestToolResultContentBlock:
    """Tests for ToolResultContentBlock Pydantic model."""
    
    def test_valid_tool_result_block(self):
        """
        What it does: Verifies creation of valid ToolResultContentBlock.
        Purpose: Ensure model accepts valid tool result data.
        """
        print("Setup: Creating ToolResultContentBlock with valid data...")
        block = ToolResultContentBlock(
            tool_use_id="call_123",
            content="Weather in Moscow: Sunny, 25°C"
        )
        
        print(f"Result: {block}")
        print(f"Comparing type: Expected 'tool_result', Got '{block.type}'")
        assert block.type == "tool_result"
        
        print(f"Comparing tool_use_id: Expected 'call_123', Got '{block.tool_use_id}'")
        assert block.tool_use_id == "call_123"
        
        print(f"Comparing content: Got '{block.content}'")
        assert block.content == "Weather in Moscow: Sunny, 25°C"
    
    def test_type_defaults_to_tool_result(self):
        """
        What it does: Verifies that type defaults to "tool_result".
        Purpose: Ensure default value is set correctly.
        """
        print("Setup: Creating ToolResultContentBlock without explicit type...")
        block = ToolResultContentBlock(tool_use_id="call_1")
        
        print(f"Comparing type: Expected 'tool_result', Got '{block.type}'")
        assert block.type == "tool_result"
    
    def test_requires_tool_use_id(self):
        """
        What it does: Verifies that tool_use_id is required.
        Purpose: Ensure validation fails without tool_use_id.
        """
        print("Setup: Attempting to create ToolResultContentBlock without tool_use_id...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            ToolResultContentBlock(content="Result")
        
        print(f"ValidationError raised: {exc_info.value}")
        assert "tool_use_id" in str(exc_info.value)
    
    def test_content_is_optional(self):
        """
        What it does: Verifies that content is optional.
        Purpose: Ensure tool results without content work.
        """
        print("Setup: Creating ToolResultContentBlock without content...")
        block = ToolResultContentBlock(tool_use_id="call_1")
        
        print(f"Comparing content: Expected None, Got {block.content}")
        assert block.content is None
    
    def test_accepts_list_content(self):
        """
        What it does: Verifies that list content is accepted.
        Purpose: Ensure content can be list of TextContentBlock.
        """
        print("Setup: Creating ToolResultContentBlock with list content...")
        block = ToolResultContentBlock(
            tool_use_id="call_1",
            content=[TextContentBlock(text="Part 1"), TextContentBlock(text="Part 2")]
        )
        
        print(f"Comparing content type: Expected list, Got {type(block.content)}")
        assert isinstance(block.content, list)
        assert len(block.content) == 2
    
    def test_is_error_field(self):
        """
        What it does: Verifies that is_error field works.
        Purpose: Ensure error results can be marked.
        """
        print("Setup: Creating ToolResultContentBlock with is_error=True...")
        block = ToolResultContentBlock(
            tool_use_id="call_1",
            content="Error: File not found",
            is_error=True
        )
        
        print(f"Comparing is_error: Expected True, Got {block.is_error}")
        assert block.is_error is True
    
    def test_is_error_defaults_to_none(self):
        """
        What it does: Verifies that is_error defaults to None.
        Purpose: Ensure default value is correct.
        """
        print("Setup: Creating ToolResultContentBlock without is_error...")
        block = ToolResultContentBlock(tool_use_id="call_1", content="Success")
        
        print(f"Comparing is_error: Expected None, Got {block.is_error}")
        assert block.is_error is None


# ==================================================================================================
# Tests for AnthropicTool
# ==================================================================================================

class TestAnthropicTool:
    """Tests for AnthropicTool Pydantic model."""
    
    def test_valid_tool(self):
        """
        What it does: Verifies creation of valid AnthropicTool.
        Purpose: Ensure model accepts valid tool definition.
        """
        print("Setup: Creating AnthropicTool with valid data...")
        tool = AnthropicTool(
            name="get_weather",
            description="Get weather for a location",
            input_schema={
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"}
                },
                "required": ["location"]
            }
        )
        
        print(f"Result: {tool}")
        print(f"Comparing name: Expected 'get_weather', Got '{tool.name}'")
        assert tool.name == "get_weather"
        
        print(f"Comparing description: Got '{tool.description}'")
        assert tool.description == "Get weather for a location"
        
        print(f"Comparing input_schema: Got {tool.input_schema}")
        assert "properties" in tool.input_schema
    
    def test_name_is_optional_for_server_tools(self):
        """
        What it does: Verifies that name is optional (server tools use type instead).
        Purpose: Ensure server tools like web_search can be created without name.
        """
        print("Setup: Creating AnthropicTool without name (server tool)...")
        tool = AnthropicTool(type="web_search_20250305", input_schema=None)
        assert tool.name is None
        assert tool.type == "web_search_20250305"
    
    def test_input_schema_is_optional_for_server_tools(self):
        """
        What it does: Verifies that input_schema is optional (server tools don't have it).
        Purpose: Ensure server tools can be created without input_schema.
        """
        print("Setup: Creating AnthropicTool without input_schema (server tool)...")
        tool = AnthropicTool(type="code_execution_20250522", name="code_execution")
        assert tool.input_schema is None
    
    def test_description_is_optional(self):
        """
        What it does: Verifies that description is optional.
        Purpose: Ensure tools without description work.
        """
        print("Setup: Creating AnthropicTool without description...")
        tool = AnthropicTool(name="simple_tool", input_schema={})
        
        print(f"Comparing description: Expected None, Got {tool.description}")
        assert tool.description is None


# ==================================================================================================
# Tests for ToolChoice models
# ==================================================================================================

class TestToolChoiceModels:
    """Tests for ToolChoice Pydantic models."""
    
    def test_tool_choice_auto(self):
        """
        What it does: Verifies creation of ToolChoiceAuto.
        Purpose: Ensure auto tool choice works.
        """
        print("Setup: Creating ToolChoiceAuto...")
        choice = ToolChoiceAuto()
        
        print(f"Result: {choice}")
        print(f"Comparing type: Expected 'auto', Got '{choice.type}'")
        assert choice.type == "auto"
    
    def test_tool_choice_any(self):
        """
        What it does: Verifies creation of ToolChoiceAny.
        Purpose: Ensure any tool choice works.
        """
        print("Setup: Creating ToolChoiceAny...")
        choice = ToolChoiceAny()
        
        print(f"Result: {choice}")
        print(f"Comparing type: Expected 'any', Got '{choice.type}'")
        assert choice.type == "any"
    
    def test_tool_choice_tool(self):
        """
        What it does: Verifies creation of ToolChoiceTool.
        Purpose: Ensure specific tool choice works.
        """
        print("Setup: Creating ToolChoiceTool...")
        choice = ToolChoiceTool(name="get_weather")
        
        print(f"Result: {choice}")
        print(f"Comparing type: Expected 'tool', Got '{choice.type}'")
        assert choice.type == "tool"
        
        print(f"Comparing name: Expected 'get_weather', Got '{choice.name}'")
        assert choice.name == "get_weather"
    
    def test_tool_choice_tool_requires_name(self):
        """
        What it does: Verifies that ToolChoiceTool requires name.
        Purpose: Ensure validation fails without name.
        """
        print("Setup: Attempting to create ToolChoiceTool without name...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            ToolChoiceTool()
        
        print(f"ValidationError raised: {exc_info.value}")
        assert "name" in str(exc_info.value)


# ==================================================================================================
# Tests for SystemContentBlock
# ==================================================================================================

class TestSystemContentBlock:
    """Tests for SystemContentBlock Pydantic model."""
    
    def test_valid_system_block(self):
        """
        What it does: Verifies creation of valid SystemContentBlock.
        Purpose: Ensure model accepts valid system content.
        """
        print("Setup: Creating SystemContentBlock with valid data...")
        block = SystemContentBlock(text="You are a helpful assistant.")
        
        print(f"Result: {block}")
        print(f"Comparing type: Expected 'text', Got '{block.type}'")
        assert block.type == "text"
        
        print(f"Comparing text: Got '{block.text}'")
        assert block.text == "You are a helpful assistant."
    
    def test_with_cache_control(self):
        """
        What it does: Verifies SystemContentBlock with cache_control.
        Purpose: Ensure prompt caching format works.
        """
        print("Setup: Creating SystemContentBlock with cache_control...")
        block = SystemContentBlock(
            text="You are helpful.",
            cache_control={"type": "ephemeral"}
        )
        
        print(f"Result: {block}")
        print(f"Comparing cache_control: Got {block.cache_control}")
        assert block.cache_control == {"type": "ephemeral"}
    
    def test_cache_control_is_optional(self):
        """
        What it does: Verifies that cache_control is optional.
        Purpose: Ensure blocks without cache_control work.
        """
        print("Setup: Creating SystemContentBlock without cache_control...")
        block = SystemContentBlock(text="Test")
        
        print(f"Comparing cache_control: Expected None, Got {block.cache_control}")
        assert block.cache_control is None
    
    def test_requires_text(self):
        """
        What it does: Verifies that text is required.
        Purpose: Ensure validation fails without text.
        """
        print("Setup: Attempting to create SystemContentBlock without text...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            SystemContentBlock()
        
        print(f"ValidationError raised: {exc_info.value}")
        assert "text" in str(exc_info.value)


# ==================================================================================================
# Tests for AnthropicUsage
# ==================================================================================================

class TestAnthropicUsage:
    """Tests for AnthropicUsage Pydantic model."""
    
    def test_valid_usage(self):
        """
        What it does: Verifies creation of valid AnthropicUsage.
        Purpose: Ensure model accepts valid usage data.
        """
        print("Setup: Creating AnthropicUsage with valid data...")
        usage = AnthropicUsage(input_tokens=100, output_tokens=50)
        
        print(f"Result: {usage}")
        print(f"Comparing input_tokens: Expected 100, Got {usage.input_tokens}")
        assert usage.input_tokens == 100
        
        print(f"Comparing output_tokens: Expected 50, Got {usage.output_tokens}")
        assert usage.output_tokens == 50
    
    def test_requires_input_tokens(self):
        """
        What it does: Verifies that input_tokens is required.
        Purpose: Ensure validation fails without input_tokens.
        """
        print("Setup: Attempting to create AnthropicUsage without input_tokens...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            AnthropicUsage(output_tokens=50)
        
        print(f"ValidationError raised: {exc_info.value}")
        assert "input_tokens" in str(exc_info.value)
    
    def test_requires_output_tokens(self):
        """
        What it does: Verifies that output_tokens is required.
        Purpose: Ensure validation fails without output_tokens.
        """
        print("Setup: Attempting to create AnthropicUsage without output_tokens...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            AnthropicUsage(input_tokens=100)
        
        print(f"ValidationError raised: {exc_info.value}")
        assert "output_tokens" in str(exc_info.value)


# ==================================================================================================
# Tests for AnthropicMessagesResponse
# ==================================================================================================

class TestAnthropicMessagesResponse:
    """Tests for AnthropicMessagesResponse Pydantic model."""
    
    def test_valid_response(self):
        """
        What it does: Verifies creation of valid AnthropicMessagesResponse.
        Purpose: Ensure model accepts valid response data.
        """
        print("Setup: Creating AnthropicMessagesResponse with valid data...")
        response = AnthropicMessagesResponse(
            id="msg_123",
            model="claude-sonnet-4-5",
            content=[TextContentBlock(text="Hello!")],
            usage=AnthropicUsage(input_tokens=10, output_tokens=5)
        )
        
        print(f"Result: {response}")
        print(f"Comparing id: Expected 'msg_123', Got '{response.id}'")
        assert response.id == "msg_123"
        
        print(f"Comparing type: Expected 'message', Got '{response.type}'")
        assert response.type == "message"
        
        print(f"Comparing role: Expected 'assistant', Got '{response.role}'")
        assert response.role == "assistant"
        
        print(f"Comparing model: Expected 'claude-sonnet-4-5', Got '{response.model}'")
        assert response.model == "claude-sonnet-4-5"
    
    def test_stop_reason_values(self):
        """
        What it does: Verifies that stop_reason accepts valid values.
        Purpose: Ensure all stop reasons work.
        """
        print("Setup: Testing various stop_reason values...")
        stop_reasons = ["end_turn", "max_tokens", "stop_sequence", "tool_use"]
        
        for reason in stop_reasons:
            print(f"Testing stop_reason: {reason}")
            response = AnthropicMessagesResponse(
                id="msg_1",
                model="claude-sonnet-4-5",
                content=[TextContentBlock(text="Test")],
                usage=AnthropicUsage(input_tokens=1, output_tokens=1),
                stop_reason=reason
            )
            assert response.stop_reason == reason
        
        print("All stop_reason values accepted successfully")
    
    def test_stop_reason_is_optional(self):
        """
        What it does: Verifies that stop_reason is optional.
        Purpose: Ensure responses without stop_reason work.
        """
        print("Setup: Creating response without stop_reason...")
        response = AnthropicMessagesResponse(
            id="msg_1",
            model="claude-sonnet-4-5",
            content=[TextContentBlock(text="Test")],
            usage=AnthropicUsage(input_tokens=1, output_tokens=1)
        )
        
        print(f"Comparing stop_reason: Expected None, Got {response.stop_reason}")
        assert response.stop_reason is None


# ==================================================================================================
# Tests for Streaming Event Models
# ==================================================================================================

class TestStreamingEvents:
    """Tests for streaming event Pydantic models."""
    
    def test_message_start_event(self):
        """
        What it does: Verifies creation of MessageStartEvent.
        Purpose: Ensure message_start event works.
        """
        print("Setup: Creating MessageStartEvent...")
        event = MessageStartEvent(
            message={"id": "msg_1", "type": "message", "role": "assistant"}
        )
        
        print(f"Result: {event}")
        print(f"Comparing type: Expected 'message_start', Got '{event.type}'")
        assert event.type == "message_start"
        assert event.message["id"] == "msg_1"
    
    def test_content_block_start_event(self):
        """
        What it does: Verifies creation of ContentBlockStartEvent.
        Purpose: Ensure content_block_start event works.
        """
        print("Setup: Creating ContentBlockStartEvent...")
        event = ContentBlockStartEvent(
            index=0,
            content_block={"type": "text", "text": ""}
        )
        
        print(f"Result: {event}")
        print(f"Comparing type: Expected 'content_block_start', Got '{event.type}'")
        assert event.type == "content_block_start"
        assert event.index == 0
    
    def test_text_delta(self):
        """
        What it does: Verifies creation of TextDelta.
        Purpose: Ensure text_delta works.
        """
        print("Setup: Creating TextDelta...")
        delta = TextDelta(text="Hello")
        
        print(f"Result: {delta}")
        print(f"Comparing type: Expected 'text_delta', Got '{delta.type}'")
        assert delta.type == "text_delta"
        assert delta.text == "Hello"
    
    def test_thinking_delta(self):
        """
        What it does: Verifies creation of ThinkingDelta.
        Purpose: Ensure thinking_delta works.
        """
        print("Setup: Creating ThinkingDelta...")
        delta = ThinkingDelta(thinking="Let me think...")
        
        print(f"Result: {delta}")
        print(f"Comparing type: Expected 'thinking_delta', Got '{delta.type}'")
        assert delta.type == "thinking_delta"
        assert delta.thinking == "Let me think..."
    
    def test_input_json_delta(self):
        """
        What it does: Verifies creation of InputJsonDelta.
        Purpose: Ensure input_json_delta works.
        """
        print("Setup: Creating InputJsonDelta...")
        delta = InputJsonDelta(partial_json='{"loc')
        
        print(f"Result: {delta}")
        print(f"Comparing type: Expected 'input_json_delta', Got '{delta.type}'")
        assert delta.type == "input_json_delta"
        assert delta.partial_json == '{"loc'
    
    def test_content_block_delta_event(self):
        """
        What it does: Verifies creation of ContentBlockDeltaEvent.
        Purpose: Ensure content_block_delta event works.
        """
        print("Setup: Creating ContentBlockDeltaEvent...")
        event = ContentBlockDeltaEvent(
            index=0,
            delta=TextDelta(text="Hello")
        )
        
        print(f"Result: {event}")
        print(f"Comparing type: Expected 'content_block_delta', Got '{event.type}'")
        assert event.type == "content_block_delta"
        assert event.index == 0
    
    def test_content_block_stop_event(self):
        """
        What it does: Verifies creation of ContentBlockStopEvent.
        Purpose: Ensure content_block_stop event works.
        """
        print("Setup: Creating ContentBlockStopEvent...")
        event = ContentBlockStopEvent(index=0)
        
        print(f"Result: {event}")
        print(f"Comparing type: Expected 'content_block_stop', Got '{event.type}'")
        assert event.type == "content_block_stop"
        assert event.index == 0
    
    def test_message_delta_event(self):
        """
        What it does: Verifies creation of MessageDeltaEvent.
        Purpose: Ensure message_delta event works.
        """
        print("Setup: Creating MessageDeltaEvent...")
        event = MessageDeltaEvent(
            delta={"stop_reason": "end_turn"},
            usage=MessageDeltaUsage(output_tokens=10)
        )
        
        print(f"Result: {event}")
        print(f"Comparing type: Expected 'message_delta', Got '{event.type}'")
        assert event.type == "message_delta"
        assert event.delta["stop_reason"] == "end_turn"
    
    def test_message_stop_event(self):
        """
        What it does: Verifies creation of MessageStopEvent.
        Purpose: Ensure message_stop event works.
        """
        print("Setup: Creating MessageStopEvent...")
        event = MessageStopEvent()
        
        print(f"Result: {event}")
        print(f"Comparing type: Expected 'message_stop', Got '{event.type}'")
        assert event.type == "message_stop"
    
    def test_ping_event(self):
        """
        What it does: Verifies creation of PingEvent.
        Purpose: Ensure ping event works.
        """
        print("Setup: Creating PingEvent...")
        event = PingEvent()
        
        print(f"Result: {event}")
        print(f"Comparing type: Expected 'ping', Got '{event.type}'")
        assert event.type == "ping"
    
    def test_error_event(self):
        """
        What it does: Verifies creation of ErrorEvent.
        Purpose: Ensure error event works.
        """
        print("Setup: Creating ErrorEvent...")
        event = ErrorEvent(error={"type": "invalid_request", "message": "Bad request"})
        
        print(f"Result: {event}")
        print(f"Comparing type: Expected 'error', Got '{event.type}'")
        assert event.type == "error"
        assert event.error["type"] == "invalid_request"


# ==================================================================================================
# Tests for Error Models
# ==================================================================================================

class TestErrorModels:
    """Tests for error Pydantic models."""
    
    def test_anthropic_error_detail(self):
        """
        What it does: Verifies creation of AnthropicErrorDetail.
        Purpose: Ensure error detail model works.
        """
        print("Setup: Creating AnthropicErrorDetail...")
        detail = AnthropicErrorDetail(
            type="invalid_request_error",
            message="Invalid API key"
        )
        
        print(f"Result: {detail}")
        print(f"Comparing type: Expected 'invalid_request_error', Got '{detail.type}'")
        assert detail.type == "invalid_request_error"
        
        print(f"Comparing message: Got '{detail.message}'")
        assert detail.message == "Invalid API key"
    
    def test_anthropic_error_response(self):
        """
        What it does: Verifies creation of AnthropicErrorResponse.
        Purpose: Ensure error response model works.
        """
        print("Setup: Creating AnthropicErrorResponse...")
        response = AnthropicErrorResponse(
            error=AnthropicErrorDetail(
                type="authentication_error",
                message="Invalid API key provided"
            )
        )
        
        print(f"Result: {response}")
        print(f"Comparing type: Expected 'error', Got '{response.type}'")
        assert response.type == "error"
        
        print(f"Comparing error.type: Got '{response.error.type}'")
        assert response.error.type == "authentication_error"
