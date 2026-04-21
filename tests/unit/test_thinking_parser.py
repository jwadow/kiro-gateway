# -*- coding: utf-8 -*-

"""
Unit tests for ThinkingParser - FSM-based parser for thinking blocks in streaming responses.

Tests cover:
- Parser state transitions (PRE_CONTENT -> IN_THINKING -> STREAMING)
- Tag detection at response start
- "Cautious" buffering for split tags
- Different handling modes (as_reasoning_content, remove, pass, strip_tags)
- Edge cases and error handling
"""

import pytest
from unittest.mock import patch

from kiro.thinking_parser import (
    ThinkingParser,
    ThinkingParseResult,
    ParserState,
)


class TestParserStateEnum:
    """Tests for ParserState enum."""
    
    def test_pre_content_value(self):
        """
        What it does: Verifies PRE_CONTENT enum value.
        Purpose: Ensure PRE_CONTENT is 0 (initial state).
        """
        print("Checking PRE_CONTENT enum value...")
        assert ParserState.PRE_CONTENT == 0
    
    def test_in_thinking_value(self):
        """
        What it does: Verifies IN_THINKING enum value.
        Purpose: Ensure IN_THINKING is 1.
        """
        print("Checking IN_THINKING enum value...")
        assert ParserState.IN_THINKING == 1
    
    def test_streaming_value(self):
        """
        What it does: Verifies STREAMING enum value.
        Purpose: Ensure STREAMING is 2.
        """
        print("Checking STREAMING enum value...")
        assert ParserState.STREAMING == 2


class TestThinkingParseResult:
    """Tests for ThinkingParseResult dataclass."""
    
    def test_default_values(self):
        """
        What it does: Verifies default values of ThinkingParseResult.
        Purpose: Ensure all fields have correct defaults.
        """
        print("Creating ThinkingParseResult with defaults...")
        result = ThinkingParseResult()
        
        print(f"Comparing: Expected None, Got {result.thinking_content}")
        assert result.thinking_content is None
        assert result.regular_content is None
        assert result.is_first_thinking_chunk is False
        assert result.is_last_thinking_chunk is False
        assert result.state_changed is False
    
    def test_custom_values(self):
        """
        What it does: Verifies custom values in ThinkingParseResult.
        Purpose: Ensure all fields can be set.
        """
        print("Creating ThinkingParseResult with custom values...")
        result = ThinkingParseResult(
            thinking_content="thinking",
            regular_content="regular",
            is_first_thinking_chunk=True,
            is_last_thinking_chunk=True,
            state_changed=True
        )
        
        print(f"Comparing thinking_content: Expected 'thinking', Got '{result.thinking_content}'")
        assert result.thinking_content == "thinking"
        assert result.regular_content == "regular"
        assert result.is_first_thinking_chunk is True
        assert result.is_last_thinking_chunk is True
        assert result.state_changed is True


class TestThinkingParserInitialization:
    """Tests for ThinkingParser initialization."""
    
    def test_default_initialization(self):
        """
        What it does: Verifies default initialization of ThinkingParser.
        Purpose: Ensure parser starts in PRE_CONTENT state with empty buffers.
        """
        print("Creating ThinkingParser with defaults...")
        parser = ThinkingParser()
        
        print(f"Comparing state: Expected PRE_CONTENT, Got {parser.state}")
        assert parser.state == ParserState.PRE_CONTENT
        assert parser.initial_buffer == ""
        assert parser.thinking_buffer == ""
        assert parser.open_tag is None
        assert parser.close_tag is None
        assert parser.is_first_thinking_chunk is True
        assert parser._thinking_block_found is False
    
    def test_custom_handling_mode(self):
        """
        What it does: Verifies custom handling_mode parameter.
        Purpose: Ensure handling_mode can be overridden.
        """
        print("Creating ThinkingParser with custom handling_mode...")
        parser = ThinkingParser(handling_mode="remove")
        
        print(f"Comparing handling_mode: Expected 'remove', Got '{parser.handling_mode}'")
        assert parser.handling_mode == "remove"
    
    def test_custom_open_tags(self):
        """
        What it does: Verifies custom open_tags parameter.
        Purpose: Ensure open_tags can be overridden.
        """
        print("Creating ThinkingParser with custom open_tags...")
        custom_tags = ["<custom>", "<test>"]
        parser = ThinkingParser(open_tags=custom_tags)
        
        print(f"Comparing open_tags: Expected {custom_tags}, Got {parser.open_tags}")
        assert parser.open_tags == custom_tags
    
    def test_custom_initial_buffer_size(self):
        """
        What it does: Verifies custom initial_buffer_size parameter.
        Purpose: Ensure initial_buffer_size can be overridden.
        """
        print("Creating ThinkingParser with custom initial_buffer_size...")
        parser = ThinkingParser(initial_buffer_size=50)
        
        print(f"Comparing initial_buffer_size: Expected 50, Got {parser.initial_buffer_size}")
        assert parser.initial_buffer_size == 50
    
    def test_max_tag_length_calculated(self):
        """
        What it does: Verifies max_tag_length is calculated from open_tags.
        Purpose: Ensure cautious buffering uses correct buffer size.
        """
        print("Creating ThinkingParser and checking max_tag_length...")
        parser = ThinkingParser(open_tags=["<thinking>", "<think>"])
        
        # max_tag_length = max(len(tag) for tag in open_tags) * 2
        # len("<thinking>") = 10, so max_tag_length = 20
        expected = 20
        print(f"Comparing max_tag_length: Expected {expected}, Got {parser.max_tag_length}")
        assert parser.max_tag_length == expected


class TestThinkingParserFeedPreContent:
    """Tests for ThinkingParser.feed() in PRE_CONTENT state."""
    
    def test_empty_content_returns_empty_result(self):
        """
        What it does: Verifies empty content returns empty result.
        Purpose: Ensure empty string doesn't change state.
        """
        print("Feeding empty content...")
        parser = ThinkingParser()
        result = parser.feed("")
        
        print(f"Comparing result: Expected empty result")
        assert result.thinking_content is None
        assert result.regular_content is None
        assert result.state_changed is False
        assert parser.state == ParserState.PRE_CONTENT
    
    def test_detects_thinking_tag(self):
        """
        What it does: Verifies <thinking> tag detection.
        Purpose: Ensure parser transitions to IN_THINKING on tag detection.
        """
        print("Feeding content with <thinking> tag...")
        parser = ThinkingParser()
        result = parser.feed("<thinking>Hello")
        
        print(f"Comparing state: Expected IN_THINKING, Got {parser.state}")
        assert parser.state == ParserState.IN_THINKING
        assert parser.open_tag == "<thinking>"
        assert parser.close_tag == "</thinking>"
        assert result.state_changed is True
        assert parser._thinking_block_found is True
    
    def test_detects_think_tag(self):
        """
        What it does: Verifies <think> tag detection.
        Purpose: Ensure parser detects alternative tag format.
        """
        print("Feeding content with <think> tag...")
        parser = ThinkingParser()
        result = parser.feed("<think>Hello")
        
        print(f"Comparing open_tag: Expected '<think>', Got '{parser.open_tag}'")
        assert parser.state == ParserState.IN_THINKING
        assert parser.open_tag == "<think>"
        assert parser.close_tag == "</think>"
    
    def test_detects_reasoning_tag(self):
        """
        What it does: Verifies <reasoning> tag detection.
        Purpose: Ensure parser detects reasoning tag format.
        """
        print("Feeding content with <reasoning> tag...")
        parser = ThinkingParser()
        result = parser.feed("<reasoning>Hello")
        
        print(f"Comparing open_tag: Expected '<reasoning>', Got '{parser.open_tag}'")
        assert parser.state == ParserState.IN_THINKING
        assert parser.open_tag == "<reasoning>"
        assert parser.close_tag == "</reasoning>"
    
    def test_detects_thought_tag(self):
        """
        What it does: Verifies <thought> tag detection.
        Purpose: Ensure parser detects thought tag format.
        """
        print("Feeding content with <thought> tag...")
        parser = ThinkingParser()
        result = parser.feed("<thought>Hello")
        
        print(f"Comparing open_tag: Expected '<thought>', Got '{parser.open_tag}'")
        assert parser.state == ParserState.IN_THINKING
        assert parser.open_tag == "<thought>"
        assert parser.close_tag == "</thought>"
    
    def test_strips_leading_whitespace_for_tag_detection(self):
        """
        What it does: Verifies leading whitespace is stripped for tag detection.
        Purpose: Ensure tags with leading whitespace are detected.
        """
        print("Feeding content with leading whitespace...")
        parser = ThinkingParser()
        result = parser.feed("  \n\n<thinking>Hello")
        
        print(f"Comparing state: Expected IN_THINKING, Got {parser.state}")
        assert parser.state == ParserState.IN_THINKING
        assert parser.open_tag == "<thinking>"
    
    def test_buffers_partial_tag(self):
        """
        What it does: Verifies partial tag is buffered.
        Purpose: Ensure parser waits for complete tag.
        """
        print("Feeding partial tag...")
        parser = ThinkingParser()
        result = parser.feed("<think")
        
        print(f"Comparing state: Expected PRE_CONTENT, Got {parser.state}")
        assert parser.state == ParserState.PRE_CONTENT
        assert parser.initial_buffer == "<think"
        assert result.state_changed is False
    
    def test_completes_partial_tag(self):
        """
        What it does: Verifies partial tag is completed across chunks.
        Purpose: Ensure split tags are handled correctly.
        """
        print("Feeding partial tag in two chunks...")
        parser = ThinkingParser()
        
        result1 = parser.feed("<think")
        print(f"After first chunk: state={parser.state}, buffer='{parser.initial_buffer}'")
        assert parser.state == ParserState.PRE_CONTENT
        
        result2 = parser.feed("ing>Hello")
        print(f"After second chunk: state={parser.state}")
        assert parser.state == ParserState.IN_THINKING
        assert parser.open_tag == "<thinking>"
    
    def test_no_tag_transitions_to_streaming(self):
        """
        What it does: Verifies transition to STREAMING when no tag found.
        Purpose: Ensure regular content is passed through.
        """
        print("Feeding content without thinking tag...")
        parser = ThinkingParser()
        result = parser.feed("Hello, this is regular content without any thinking tags.")
        
        print(f"Comparing state: Expected STREAMING, Got {parser.state}")
        assert parser.state == ParserState.STREAMING
        assert result.state_changed is True
        assert result.regular_content == "Hello, this is regular content without any thinking tags."
    
    def test_buffer_exceeds_limit_transitions_to_streaming(self):
        """
        What it does: Verifies transition to STREAMING when buffer exceeds limit.
        Purpose: Ensure parser doesn't buffer indefinitely.
        """
        print("Feeding content that exceeds buffer limit...")
        parser = ThinkingParser(initial_buffer_size=10)
        result = parser.feed("This is a long content that exceeds the buffer limit")
        
        print(f"Comparing state: Expected STREAMING, Got {parser.state}")
        assert parser.state == ParserState.STREAMING
        assert result.state_changed is True


class TestThinkingParserFeedInThinking:
    """Tests for ThinkingParser.feed() in IN_THINKING state."""
    
    def test_accumulates_thinking_content(self):
        """
        What it does: Verifies thinking content is accumulated.
        Purpose: Ensure content inside thinking block is captured.
        """
        print("Feeding thinking content...")
        parser = ThinkingParser()
        parser.feed("<thinking>")
        
        # Feed more content
        result = parser.feed("This is thinking content")
        
        print(f"Comparing thinking_buffer: Got '{parser.thinking_buffer}'")
        # Content is in buffer due to cautious sending
        assert "This is thinking content" in parser.thinking_buffer or result.thinking_content
    
    def test_detects_closing_tag(self):
        """
        What it does: Verifies closing tag detection.
        Purpose: Ensure parser transitions to STREAMING on closing tag.
        """
        print("Feeding content with closing tag...")
        parser = ThinkingParser()
        parser.feed("<thinking>Hello")
        result = parser.feed("</thinking>World")
        
        print(f"Comparing state: Expected STREAMING, Got {parser.state}")
        assert parser.state == ParserState.STREAMING
        assert result.is_last_thinking_chunk is True
        assert result.state_changed is True
    
    def test_regular_content_after_closing_tag(self):
        """
        What it does: Verifies regular content after closing tag.
        Purpose: Ensure content after closing tag is returned as regular_content.
        """
        print("Feeding content with closing tag and regular content...")
        parser = ThinkingParser()
        parser.feed("<thinking>Thinking")
        result = parser.feed("</thinking>Regular content")
        
        print(f"Comparing regular_content: Got '{result.regular_content}'")
        assert result.regular_content == "Regular content"
    
    def test_strips_whitespace_after_closing_tag(self):
        """
        What it does: Verifies whitespace is stripped after closing tag.
        Purpose: Ensure leading newlines after closing tag are removed.
        """
        print("Feeding content with whitespace after closing tag...")
        parser = ThinkingParser()
        parser.feed("<thinking>Thinking")
        result = parser.feed("</thinking>\n\nRegular content")
        
        print(f"Comparing regular_content: Got '{result.regular_content}'")
        assert result.regular_content == "Regular content"
    
    def test_cautious_buffering(self):
        """
        What it does: Verifies cautious buffering keeps last max_tag_length chars.
        Purpose: Ensure closing tag is not split across chunks.
        """
        print("Testing cautious buffering...")
        parser = ThinkingParser(open_tags=["<t>"])  # Short tag for easier testing
        parser.feed("<t>")
        
        # Feed content longer than max_tag_length
        long_content = "A" * 50
        result = parser.feed(long_content)
        
        print(f"Comparing thinking_buffer length: Got {len(parser.thinking_buffer)}")
        # Buffer should keep last max_tag_length chars
        assert len(parser.thinking_buffer) <= parser.max_tag_length
    
    def test_split_closing_tag(self):
        """
        What it does: Verifies split closing tag is handled.
        Purpose: Ensure closing tag split across chunks is detected.
        """
        print("Feeding split closing tag...")
        parser = ThinkingParser()
        parser.feed("<thinking>Hello")
        parser.feed("</think")
        result = parser.feed("ing>World")
        
        print(f"Comparing state: Expected STREAMING, Got {parser.state}")
        assert parser.state == ParserState.STREAMING


class TestThinkingParserFeedStreaming:
    """Tests for ThinkingParser.feed() in STREAMING state."""
    
    def test_passes_content_through(self):
        """
        What it does: Verifies content is passed through in STREAMING state.
        Purpose: Ensure regular content is returned as-is.
        """
        print("Feeding content in STREAMING state...")
        parser = ThinkingParser()
        # Transition to STREAMING by feeding non-tag content
        parser.feed("Regular content")
        
        result = parser.feed("More content")
        
        print(f"Comparing regular_content: Expected 'More content', Got '{result.regular_content}'")
        assert result.regular_content == "More content"
        assert result.thinking_content is None
    
    def test_ignores_thinking_tags_in_streaming(self):
        """
        What it does: Verifies thinking tags are ignored in STREAMING state.
        Purpose: Ensure tags after initial detection are passed through.
        """
        print("Feeding thinking tag in STREAMING state...")
        parser = ThinkingParser()
        parser.feed("Regular content")  # Transition to STREAMING
        
        result = parser.feed("<thinking>This should be regular</thinking>")
        
        print(f"Comparing regular_content: Got '{result.regular_content}'")
        assert result.regular_content == "<thinking>This should be regular</thinking>"
        assert result.thinking_content is None


class TestThinkingParserFinalize:
    """Tests for ThinkingParser.finalize()."""
    
    def test_flushes_thinking_buffer(self):
        """
        What it does: Verifies thinking buffer is flushed on finalize.
        Purpose: Ensure remaining thinking content is returned.
        """
        print("Finalizing parser with thinking buffer...")
        parser = ThinkingParser()
        parser.feed("<thinking>Incomplete thinking")
        
        result = parser.finalize()
        
        print(f"Comparing thinking_content: Got '{result.thinking_content}'")
        assert result.thinking_content is not None
        assert result.is_last_thinking_chunk is True
    
    def test_flushes_initial_buffer(self):
        """
        What it does: Verifies initial buffer is flushed on finalize.
        Purpose: Ensure buffered content is returned when no tag found.
        """
        print("Finalizing parser with initial buffer...")
        parser = ThinkingParser()
        parser.feed("<thi")  # Partial tag, stays in initial_buffer
        
        result = parser.finalize()
        
        print(f"Comparing regular_content: Got '{result.regular_content}'")
        assert result.regular_content == "<thi"
    
    def test_clears_buffers_after_finalize(self):
        """
        What it does: Verifies buffers are cleared after finalize.
        Purpose: Ensure buffers are empty after finalize.
        """
        print("Checking buffers after finalize...")
        parser = ThinkingParser()
        parser.feed("<thinking>Content")
        parser.finalize()
        
        print(f"Comparing buffers: thinking_buffer='{parser.thinking_buffer}', initial_buffer='{parser.initial_buffer}'")
        assert parser.thinking_buffer == ""
        assert parser.initial_buffer == ""


class TestThinkingParserReset:
    """Tests for ThinkingParser.reset()."""
    
    def test_resets_to_initial_state(self):
        """
        What it does: Verifies reset returns parser to initial state.
        Purpose: Ensure parser can be reused.
        """
        print("Resetting parser after use...")
        parser = ThinkingParser()
        parser.feed("<thinking>Content</thinking>Regular")
        
        parser.reset()
        
        print(f"Comparing state: Expected PRE_CONTENT, Got {parser.state}")
        assert parser.state == ParserState.PRE_CONTENT
        assert parser.initial_buffer == ""
        assert parser.thinking_buffer == ""
        assert parser.open_tag is None
        assert parser.close_tag is None
        assert parser.is_first_thinking_chunk is True
        assert parser._thinking_block_found is False


class TestThinkingParserFoundThinkingBlock:
    """Tests for ThinkingParser.found_thinking_block property."""
    
    def test_false_initially(self):
        """
        What it does: Verifies found_thinking_block is False initially.
        Purpose: Ensure property starts as False.
        """
        print("Checking found_thinking_block initially...")
        parser = ThinkingParser()
        
        print(f"Comparing: Expected False, Got {parser.found_thinking_block}")
        assert parser.found_thinking_block is False
    
    def test_true_after_tag_detection(self):
        """
        What it does: Verifies found_thinking_block is True after tag detection.
        Purpose: Ensure property is set when thinking block is found.
        """
        print("Checking found_thinking_block after tag detection...")
        parser = ThinkingParser()
        parser.feed("<thinking>Content")
        
        print(f"Comparing: Expected True, Got {parser.found_thinking_block}")
        assert parser.found_thinking_block is True
    
    def test_false_when_no_tag(self):
        """
        What it does: Verifies found_thinking_block is False when no tag found.
        Purpose: Ensure property stays False for regular content.
        """
        print("Checking found_thinking_block with no tag...")
        parser = ThinkingParser()
        parser.feed("Regular content without thinking tags")
        
        print(f"Comparing: Expected False, Got {parser.found_thinking_block}")
        assert parser.found_thinking_block is False


class TestThinkingParserProcessForOutput:
    """Tests for ThinkingParser.process_for_output()."""
    
    def test_as_reasoning_content_mode(self):
        """
        What it does: Verifies as_reasoning_content mode returns content as-is.
        Purpose: Ensure content is returned unchanged for reasoning_content field.
        """
        print("Testing as_reasoning_content mode...")
        parser = ThinkingParser(handling_mode="as_reasoning_content")
        parser.open_tag = "<thinking>"
        parser.close_tag = "</thinking>"
        
        result = parser.process_for_output("Thinking content", is_first=True, is_last=True)
        
        print(f"Comparing: Expected 'Thinking content', Got '{result}'")
        assert result == "Thinking content"
    
    def test_remove_mode(self):
        """
        What it does: Verifies remove mode returns None.
        Purpose: Ensure thinking content is removed.
        """
        print("Testing remove mode...")
        parser = ThinkingParser(handling_mode="remove")
        
        result = parser.process_for_output("Thinking content", is_first=True, is_last=True)
        
        print(f"Comparing: Expected None, Got {result}")
        assert result is None
    
    def test_pass_mode_first_chunk(self):
        """
        What it does: Verifies pass mode adds opening tag to first chunk.
        Purpose: Ensure tags are preserved in pass mode.
        """
        print("Testing pass mode with first chunk...")
        parser = ThinkingParser(handling_mode="pass")
        parser.open_tag = "<thinking>"
        parser.close_tag = "</thinking>"
        
        result = parser.process_for_output("Content", is_first=True, is_last=False)
        
        print(f"Comparing: Expected '<thinking>Content', Got '{result}'")
        assert result == "<thinking>Content"
    
    def test_pass_mode_last_chunk(self):
        """
        What it does: Verifies pass mode adds closing tag to last chunk.
        Purpose: Ensure closing tag is added in pass mode.
        """
        print("Testing pass mode with last chunk...")
        parser = ThinkingParser(handling_mode="pass")
        parser.open_tag = "<thinking>"
        parser.close_tag = "</thinking>"
        
        result = parser.process_for_output("Content", is_first=False, is_last=True)
        
        print(f"Comparing: Expected 'Content</thinking>', Got '{result}'")
        assert result == "Content</thinking>"
    
    def test_pass_mode_first_and_last_chunk(self):
        """
        What it does: Verifies pass mode adds both tags when first and last.
        Purpose: Ensure both tags are added for single chunk.
        """
        print("Testing pass mode with first and last chunk...")
        parser = ThinkingParser(handling_mode="pass")
        parser.open_tag = "<thinking>"
        parser.close_tag = "</thinking>"
        
        result = parser.process_for_output("Content", is_first=True, is_last=True)
        
        print(f"Comparing: Expected '<thinking>Content</thinking>', Got '{result}'")
        assert result == "<thinking>Content</thinking>"
    
    def test_pass_mode_middle_chunk(self):
        """
        What it does: Verifies pass mode returns content as-is for middle chunk.
        Purpose: Ensure no tags are added for middle chunks.
        """
        print("Testing pass mode with middle chunk...")
        parser = ThinkingParser(handling_mode="pass")
        parser.open_tag = "<thinking>"
        parser.close_tag = "</thinking>"
        
        result = parser.process_for_output("Content", is_first=False, is_last=False)
        
        print(f"Comparing: Expected 'Content', Got '{result}'")
        assert result == "Content"
    
    def test_strip_tags_mode(self):
        """
        What it does: Verifies strip_tags mode returns content without tags.
        Purpose: Ensure content is returned without tags.
        """
        print("Testing strip_tags mode...")
        parser = ThinkingParser(handling_mode="strip_tags")
        
        result = parser.process_for_output("Thinking content", is_first=True, is_last=True)
        
        print(f"Comparing: Expected 'Thinking content', Got '{result}'")
        assert result == "Thinking content"
    
    def test_none_content_returns_none(self):
        """
        What it does: Verifies None content returns None.
        Purpose: Ensure None is handled correctly.
        """
        print("Testing None content...")
        parser = ThinkingParser()
        
        result = parser.process_for_output(None, is_first=True, is_last=True)
        
        print(f"Comparing: Expected None, Got {result}")
        assert result is None
    
    def test_empty_content_returns_none(self):
        """
        What it does: Verifies empty content returns None.
        Purpose: Ensure empty string is handled correctly.
        """
        print("Testing empty content...")
        parser = ThinkingParser()
        
        result = parser.process_for_output("", is_first=True, is_last=True)
        
        print(f"Comparing: Expected None, Got {result}")
        assert result is None


class TestThinkingParserFullFlow:
    """Integration tests for full parsing flow."""
    
    def test_complete_thinking_block(self):
        """
        What it does: Verifies complete thinking block parsing.
        Purpose: Ensure full flow works correctly.
        """
        print("Testing complete thinking block flow...")
        parser = ThinkingParser()
        
        # Feed complete thinking block
        result1 = parser.feed("<thinking>This is my reasoning process.</thinking>Here is the answer.")
        
        print(f"State: {parser.state}")
        print(f"Thinking content: {result1.thinking_content}")
        print(f"Regular content: {result1.regular_content}")
        
        assert parser.state == ParserState.STREAMING
        assert parser.found_thinking_block is True
        assert result1.regular_content == "Here is the answer."
    
    def test_multi_chunk_thinking_block(self):
        """
        What it does: Verifies thinking block split across multiple chunks.
        Purpose: Ensure chunked content is handled correctly.
        """
        print("Testing multi-chunk thinking block...")
        parser = ThinkingParser()
        
        # Feed in multiple chunks
        result1 = parser.feed("<think")
        print(f"After chunk 1: state={parser.state}")
        assert parser.state == ParserState.PRE_CONTENT
        
        result2 = parser.feed("ing>Let me think")
        print(f"After chunk 2: state={parser.state}")
        assert parser.state == ParserState.IN_THINKING
        
        result3 = parser.feed(" about this...</think")
        print(f"After chunk 3: state={parser.state}")
        assert parser.state == ParserState.IN_THINKING
        
        result4 = parser.feed("ing>The answer is 42.")
        print(f"After chunk 4: state={parser.state}")
        assert parser.state == ParserState.STREAMING
        assert result4.regular_content == "The answer is 42."
    
    def test_no_thinking_block(self):
        """
        What it does: Verifies handling of content without thinking block.
        Purpose: Ensure regular content passes through unchanged.
        """
        print("Testing content without thinking block...")
        parser = ThinkingParser()
        
        result = parser.feed("This is just regular content without any thinking tags.")
        
        print(f"State: {parser.state}")
        print(f"Regular content: {result.regular_content}")
        
        assert parser.state == ParserState.STREAMING
        assert parser.found_thinking_block is False
        assert result.regular_content == "This is just regular content without any thinking tags."
    
    def test_thinking_block_with_newlines(self):
        """
        What it does: Verifies thinking block with newlines after closing tag.
        Purpose: Ensure newlines are stripped from regular content.
        """
        print("Testing thinking block with newlines...")
        parser = ThinkingParser()
        
        result = parser.feed("<thinking>Reasoning</thinking>\n\n\nAnswer here")
        
        print(f"Regular content: '{result.regular_content}'")
        assert result.regular_content == "Answer here"
    
    def test_empty_thinking_block(self):
        """
        What it does: Verifies empty thinking block handling.
        Purpose: Ensure empty thinking block doesn't break parser.
        """
        print("Testing empty thinking block...")
        parser = ThinkingParser()
        
        result = parser.feed("<thinking></thinking>Answer")
        
        print(f"State: {parser.state}")
        print(f"Regular content: '{result.regular_content}'")
        assert parser.state == ParserState.STREAMING
        assert result.regular_content == "Answer"
    
    def test_thinking_block_only_whitespace_after(self):
        """
        What it does: Verifies thinking block with only whitespace after closing tag.
        Purpose: Ensure whitespace-only content after tag returns None.
        """
        print("Testing thinking block with only whitespace after...")
        parser = ThinkingParser()
        
        result = parser.feed("<thinking>Reasoning</thinking>   \n\n   ")
        
        print(f"Regular content: {result.regular_content}")
        # Whitespace-only content should be stripped to None
        assert result.regular_content is None or result.regular_content == ""


class TestThinkingParserEdgeCases:
    """Edge case tests for ThinkingParser."""
    
    def test_nested_tags_not_supported(self):
        """
        What it does: Verifies nested tags are not specially handled.
        Purpose: Ensure nested tags are treated as content.
        """
        print("Testing nested tags...")
        parser = ThinkingParser()
        
        result = parser.feed("<thinking>Outer<thinking>Inner</thinking>Still outer</thinking>Answer")
        
        print(f"State: {parser.state}")
        # First </thinking> closes the block
        assert parser.state == ParserState.STREAMING
    
    def test_tag_in_middle_of_content(self):
        """
        What it does: Verifies tag in middle of content is not detected.
        Purpose: Ensure tags are only detected at start.
        """
        print("Testing tag in middle of content...")
        parser = ThinkingParser()
        
        result = parser.feed("Some text <thinking>This is not a thinking block</thinking>")
        
        print(f"State: {parser.state}")
        print(f"Regular content: '{result.regular_content}'")
        assert parser.state == ParserState.STREAMING
        assert parser.found_thinking_block is False
        assert "<thinking>" in result.regular_content
    
    def test_malformed_closing_tag(self):
        """
        What it does: Verifies malformed closing tag is not detected.
        Purpose: Ensure only exact closing tag is matched.
        """
        print("Testing malformed closing tag...")
        parser = ThinkingParser()
        
        parser.feed("<thinking>Content")
        result = parser.feed("</THINKING>More content")  # Wrong case
        
        print(f"State: {parser.state}")
        # Should still be in thinking state
        assert parser.state == ParserState.IN_THINKING
    
    def test_unicode_content(self):
        """
        What it does: Verifies Unicode content is handled correctly.
        Purpose: Ensure non-ASCII characters work.
        """
        print("Testing Unicode content...")
        parser = ThinkingParser()
        
        result = parser.feed("<thinking>Думаю о проблеме 🤔</thinking>Ответ: 42")
        
        print(f"Regular content: '{result.regular_content}'")
        assert parser.state == ParserState.STREAMING
        assert result.regular_content == "Ответ: 42"
    
    def test_very_long_thinking_content(self):
        """
        What it does: Verifies very long thinking content is handled.
        Purpose: Ensure large content doesn't break parser.
        """
        print("Testing very long thinking content...")
        parser = ThinkingParser()
        
        long_content = "A" * 10000
        result = parser.feed(f"<thinking>{long_content}</thinking>Done")
        
        print(f"State: {parser.state}")
        assert parser.state == ParserState.STREAMING
        assert result.regular_content == "Done"
    
    def test_special_characters_in_content(self):
        """
        What it does: Verifies special characters are handled.
        Purpose: Ensure HTML-like content doesn't break parser.
        """
        print("Testing special characters...")
        parser = ThinkingParser()
        
        result = parser.feed("<thinking>Content with <b>bold</b> and &amp; entities</thinking>Answer")
        
        print(f"State: {parser.state}")
        assert parser.state == ParserState.STREAMING
        assert result.regular_content == "Answer"
    
    def test_multiple_feeds_after_streaming(self):
        """
        What it does: Verifies multiple feeds in STREAMING state.
        Purpose: Ensure parser continues to work after transition.
        """
        print("Testing multiple feeds in STREAMING state...")
        parser = ThinkingParser()
        
        parser.feed("<thinking>Thinking</thinking>First")
        result2 = parser.feed(" Second")
        result3 = parser.feed(" Third")
        
        print(f"Result 2: '{result2.regular_content}'")
        print(f"Result 3: '{result3.regular_content}'")
        assert result2.regular_content == " Second"
        assert result3.regular_content == " Third"


class TestThinkingParserConfigIntegration:
    """Tests for ThinkingParser integration with config."""
    
    def test_uses_config_handling_mode(self):
        """
        What it does: Verifies parser uses FAKE_REASONING_HANDLING from config.
        Purpose: Ensure config integration works.
        """
        print("Testing config handling mode...")
        with patch('kiro.thinking_parser.FAKE_REASONING_HANDLING', 'remove'):
            parser = ThinkingParser()
            
            print(f"Handling mode: {parser.handling_mode}")
            assert parser.handling_mode == "remove"
    
    def test_uses_config_open_tags(self):
        """
        What it does: Verifies parser uses FAKE_REASONING_OPEN_TAGS from config.
        Purpose: Ensure config integration works.
        """
        print("Testing config open tags...")
        custom_tags = ["<custom>"]
        with patch('kiro.thinking_parser.FAKE_REASONING_OPEN_TAGS', custom_tags):
            parser = ThinkingParser()
            
            print(f"Open tags: {parser.open_tags}")
            assert parser.open_tags == custom_tags
    
    def test_default_initial_buffer_size_from_config(self):
        """
        What it does: Verifies parser uses default initial_buffer_size from config.
        Purpose: Ensure config value is used when not overridden.
        
        Note: We can't easily patch the config value after import, so we just
        verify the default is used. Custom values are tested in
        TestThinkingParserInitialization.test_custom_initial_buffer_size.
        """
        print("Testing default initial buffer size from config...")
        from kiro.config import FAKE_REASONING_INITIAL_BUFFER_SIZE
        
        parser = ThinkingParser()
        
        print(f"Initial buffer size: {parser.initial_buffer_size}")
        print(f"Config value: {FAKE_REASONING_INITIAL_BUFFER_SIZE}")
        assert parser.initial_buffer_size == FAKE_REASONING_INITIAL_BUFFER_SIZE


class TestInjectThinkingTags:
    """Tests for inject_thinking_tags function in converters."""
    
    def test_injects_tags_when_enabled(self):
        """
        What it does: Verifies tags are injected when FAKE_REASONING_ENABLED is True.
        Purpose: Ensure tags are added to content.
        """
        print("Testing tag injection when enabled...")
        from kiro.converters_core import inject_thinking_tags, ThinkingConfig
        
        with patch('kiro.converters_core.FAKE_REASONING_ENABLED', True):
            with patch('kiro.converters_core.FAKE_REASONING_MAX_TOKENS', 4000):
                result = inject_thinking_tags("Hello", ThinkingConfig())
        
        print(f"Result: '{result}'")
        assert "<thinking_mode>enabled</thinking_mode>" in result
        assert "<max_thinking_length>4000</max_thinking_length>" in result
        assert "Hello" in result
    
    def test_no_injection_when_disabled(self):
        """
        What it does: Verifies tags are not injected when FAKE_REASONING_ENABLED is False.
        Purpose: Ensure tags are not added when disabled.
        """
        print("Testing no tag injection when disabled...")
        from kiro.converters_core import inject_thinking_tags, ThinkingConfig
        
        with patch('kiro.converters_core.FAKE_REASONING_ENABLED', False):
            result = inject_thinking_tags("Hello", ThinkingConfig())
        
        print(f"Result: '{result}'")
        assert result == "Hello"
        assert "<thinking_mode>" not in result
    
    def test_injection_preserves_content(self):
        """
        What it does: Verifies original content is preserved after injection.
        Purpose: Ensure content is not modified.
        """
        print("Testing content preservation...")
        from kiro.converters_core import inject_thinking_tags, ThinkingConfig
        
        original = "This is my original content with special chars: <>&"
        
        with patch('kiro.converters_core.FAKE_REASONING_ENABLED', True):
            with patch('kiro.converters_core.FAKE_REASONING_MAX_TOKENS', 4000):
                result = inject_thinking_tags(original, ThinkingConfig())
        
        print(f"Result ends with original: {result.endswith(original)}")
        assert result.endswith(original)
        
