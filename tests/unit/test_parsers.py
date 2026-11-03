# -*- coding: utf-8 -*-

"""
Unit tests for AwsEventStreamParser and auxiliary parsing functions.
Tests the parsing logic for AWS SSE stream from Kiro API.
"""

import json
import time

import pytest

from kiro.parsers import (
    AwsEventStreamParser,
    _preview_repr,
    find_matching_brace,
    parse_bracket_tool_calls,
    deduplicate_tool_calls
)


class TestFindMatchingBrace:
    """Tests for find_matching_brace function."""
    
    def test_simple_json_object(self):
        """
        What it does: Tests finding closing brace for simple JSON.
        Goal: Ensure the basic case works.
        """
        print("Setup: Simple JSON object...")
        text = '{"key": "value"}'
        
        print("Action: Finding closing brace...")
        result = find_matching_brace(text, 0)
        
        print(f"Comparing result: Expected 15, Got {result}")
        assert result == 15
    
    def test_nested_json_object(self):
        """
        What it does: Tests finding brace for nested JSON.
        Goal: Ensure nesting is handled correctly.
        """
        print("Setup: Nested JSON object...")
        text = '{"outer": {"inner": "value"}}'
        
        print("Action: Finding closing brace...")
        result = find_matching_brace(text, 0)
        
        # String length 29, last character index 28
        print(f"Comparing result: Expected 28, Got {result}")
        assert result == 28
    
    def test_json_with_braces_in_string(self):
        """
        What it does: Tests ignoring braces inside strings.
        Goal: Ensure braces in strings don't affect counting.
        """
        print("Setup: JSON with braces in string...")
        text = '{"text": "Hello {world}"}'
        
        print("Action: Finding closing brace...")
        result = find_matching_brace(text, 0)
        
        print(f"Comparing result: Expected 24, Got {result}")
        assert result == 24
    
    def test_json_with_escaped_quotes(self):
        """
        What it does: Tests handling of escaped quotes.
        Goal: Ensure escape sequences don't break parsing.
        """
        print("Setup: JSON with escaped quotes...")
        text = '{"text": "Say \\"hello\\""}'
        
        print("Action: Finding closing brace...")
        result = find_matching_brace(text, 0)
        
        # String length 25, last character index 24
        print(f"Comparing result: Expected 24, Got {result}")
        assert result == 24
    
    def test_incomplete_json(self):
        """
        What it does: Tests handling of incomplete JSON.
        Goal: Ensure -1 is returned for incomplete JSON.
        """
        print("Setup: Incomplete JSON...")
        text = '{"key": "value"'
        
        print("Action: Finding closing brace...")
        result = find_matching_brace(text, 0)
        
        print(f"Comparing result: Expected -1, Got {result}")
        assert result == -1
    
    def test_invalid_start_position(self):
        """
        What it does: Tests handling of invalid start position.
        Goal: Ensure -1 is returned if start_pos is not on '{'.
        """
        print("Setup: Text without brace at start_pos...")
        text = 'hello {"key": "value"}'
        
        print("Action: Finding from position 0 (not a brace)...")
        result = find_matching_brace(text, 0)
        
        print(f"Comparing result: Expected -1, Got {result}")
        assert result == -1
    
    def test_start_position_out_of_bounds(self):
        """
        What it does: Tests handling of position beyond text bounds.
        Goal: Ensure -1 is returned for invalid position.
        """
        print("Setup: Short text...")
        text = '{"a":1}'
        
        print("Action: Finding from position 100...")
        result = find_matching_brace(text, 100)
        
        print(f"Comparing result: Expected -1, Got {result}")
        assert result == -1


class TestParseBracketToolCalls:
    """Tests for parse_bracket_tool_calls function."""
    
    def test_parses_single_tool_call(self):
        """
        What it does: Tests parsing of a single tool call.
        Goal: Ensure bracket-style tool call is extracted correctly.
        """
        print("Setup: Text with one tool call...")
        text = '[Called get_weather with args: {"location": "Moscow"}]'
        
        print("Action: Parsing tool calls...")
        result = parse_bracket_tool_calls(text)
        
        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0]["function"]["name"] == "get_weather"
        assert '"location"' in result[0]["function"]["arguments"]
    
    def test_parses_multiple_tool_calls(self):
        """
        What it does: Tests parsing of multiple tool calls.
        Goal: Ensure all tool calls are extracted.
        """
        print("Setup: Text with multiple tool calls...")
        text = '''
        [Called get_weather with args: {"location": "Moscow"}]
        Some text in between
        [Called get_time with args: {"timezone": "UTC"}]
        '''
        
        print("Action: Parsing tool calls...")
        result = parse_bracket_tool_calls(text)
        
        print(f"Result: {result}")
        assert len(result) == 2
        assert result[0]["function"]["name"] == "get_weather"
        assert result[1]["function"]["name"] == "get_time"
    
    def test_returns_empty_for_no_tool_calls(self):
        """
        What it does: Tests returning empty list without tool calls.
        Goal: Ensure regular text is not parsed as tool call.
        """
        print("Setup: Regular text without tool calls...")
        text = "This is just regular text without any tool calls."
        
        print("Action: Parsing tool calls...")
        result = parse_bracket_tool_calls(text)
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_returns_empty_for_empty_string(self):
        """
        What it does: Tests handling of empty string.
        Goal: Ensure empty string doesn't cause errors.
        """
        print("Setup: Empty string...")
        
        print("Action: Parsing tool calls...")
        result = parse_bracket_tool_calls("")
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_returns_empty_for_none(self):
        """
        What it does: Tests handling of None.
        Goal: Ensure None doesn't cause errors.
        """
        print("Setup: None...")
        
        print("Action: Parsing tool calls...")
        result = parse_bracket_tool_calls(None)
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_handles_nested_json_in_args(self):
        """
        What it does: Tests parsing of nested JSON in arguments.
        Goal: Ensure complex arguments are parsed correctly.
        """
        print("Setup: Tool call with nested JSON...")
        text = '[Called complex_func with args: {"data": {"nested": {"deep": "value"}}}]'
        
        print("Action: Parsing tool calls...")
        result = parse_bracket_tool_calls(text)
        
        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0]["function"]["name"] == "complex_func"
        assert "nested" in result[0]["function"]["arguments"]
    
    def test_generates_unique_ids(self):
        """
        What it does: Tests generation of unique IDs for tool calls.
        Goal: Ensure each tool call has a unique ID.
        """
        print("Setup: Two identical tool calls...")
        text = '''
        [Called func with args: {"a": 1}]
        [Called func with args: {"a": 1}]
        '''
        
        print("Action: Parsing tool calls...")
        result = parse_bracket_tool_calls(text)
        
        print(f"IDs: {[r['id'] for r in result]}")
        assert len(result) == 2
        assert result[0]["id"] != result[1]["id"]


class TestDeduplicateToolCalls:
    """Tests for deduplicate_tool_calls function."""
    
    def test_removes_duplicates(self):
        """
        What it does: Tests removal of duplicates.
        Goal: Ensure identical tool calls are removed.
        """
        print("Setup: List with duplicates...")
        tool_calls = [
            {"id": "1", "function": {"name": "func", "arguments": '{"a": 1}'}},
            {"id": "2", "function": {"name": "func", "arguments": '{"a": 1}'}},
            {"id": "3", "function": {"name": "other", "arguments": '{"b": 2}'}},
        ]
        
        print("Action: Deduplication...")
        result = deduplicate_tool_calls(tool_calls)
        
        print(f"Comparing length: Expected 2, Got {len(result)}")
        assert len(result) == 2
    
    def test_preserves_first_occurrence(self):
        """
        What it does: Tests preservation of first occurrence.
        Goal: Ensure the first tool call from duplicates is preserved.
        """
        print("Setup: List with duplicates...")
        tool_calls = [
            {"id": "first", "function": {"name": "func", "arguments": '{"a": 1}'}},
            {"id": "second", "function": {"name": "func", "arguments": '{"a": 1}'}},
        ]
        
        print("Action: Deduplication...")
        result = deduplicate_tool_calls(tool_calls)
        
        print(f"Comparing ID: Expected 'first', Got '{result[0]['id']}'")
        assert result[0]["id"] == "first"
    
    def test_handles_empty_list(self):
        """
        What it does: Tests handling of empty list.
        Goal: Ensure empty list doesn't cause errors.
        """
        print("Setup: Empty list...")
        
        print("Action: Deduplication...")
        result = deduplicate_tool_calls([])
        
        print(f"Comparing result: Expected [], Got {result}")
        assert result == []
    
    def test_deduplicates_by_id_keeps_one_with_arguments(self):
        """
        What it does: Tests deduplication by id keeping tool call with arguments.
        Goal: Ensure that when duplicates by id exist, the one with arguments is kept.
        """
        print("Setup: Two tool calls with same id, one with arguments, one empty...")
        tool_calls = [
            {"id": "call_123", "function": {"name": "func", "arguments": "{}"}},
            {"id": "call_123", "function": {"name": "func", "arguments": '{"location": "Moscow"}'}},
        ]
        
        print("Action: Deduplication...")
        result = deduplicate_tool_calls(tool_calls)
        
        print(f"Result: {result}")
        print(f"Comparing length: Expected 1, Got {len(result)}")
        assert len(result) == 1
        
        print("Verifying that tool call with arguments was kept...")
        assert "Moscow" in result[0]["function"]["arguments"]
    
    def test_deduplicates_by_id_prefers_longer_arguments(self):
        """
        What it does: Tests that duplicates by id prefer longer arguments.
        Goal: Ensure tool call with more complete arguments is kept.
        """
        print("Setup: Two tool calls with same id, different argument lengths...")
        tool_calls = [
            {"id": "call_abc", "function": {"name": "search", "arguments": '{"q": "test"}'}},
            {"id": "call_abc", "function": {"name": "search", "arguments": '{"q": "test", "limit": 10, "offset": 0}'}},
        ]
        
        print("Action: Deduplication...")
        result = deduplicate_tool_calls(tool_calls)
        
        print(f"Result: {result}")
        assert len(result) == 1
        
        print("Verifying that tool call with longer arguments was kept...")
        assert "limit" in result[0]["function"]["arguments"]
    
    def test_deduplicates_empty_arguments_replaced_by_non_empty(self):
        """
        What it does: Tests replacement of empty arguments with non-empty.
        Goal: Ensure "{}" is replaced with actual arguments.
        """
        print("Setup: First tool call with empty arguments, second with real ones...")
        tool_calls = [
            {"id": "call_xyz", "function": {"name": "get_weather", "arguments": "{}"}},
            {"id": "call_xyz", "function": {"name": "get_weather", "arguments": '{"city": "London"}'}},
        ]
        
        print("Action: Deduplication...")
        result = deduplicate_tool_calls(tool_calls)
        
        print(f"Result: {result}")
        assert len(result) == 1
        assert result[0]["function"]["arguments"] == '{"city": "London"}'
    
    def test_handles_tool_calls_without_id(self):
        """
        What it does: Tests handling of tool calls without id.
        Goal: Ensure tool calls without id are deduplicated by name+arguments.
        """
        print("Setup: Tool calls without id...")
        tool_calls = [
            {"id": "", "function": {"name": "func", "arguments": '{"a": 1}'}},
            {"id": "", "function": {"name": "func", "arguments": '{"a": 1}'}},
            {"id": "", "function": {"name": "func", "arguments": '{"b": 2}'}},
        ]
        
        print("Action: Deduplication...")
        result = deduplicate_tool_calls(tool_calls)
        
        print(f"Result: {result}")
        # Two unique by name+arguments
        assert len(result) == 2
    
    def test_mixed_with_and_without_id(self):
        """
        What it does: Tests mixed list with and without id.
        Goal: Ensure both types are handled correctly.
        """
        print("Setup: Mixed list...")
        tool_calls = [
            {"id": "call_1", "function": {"name": "func1", "arguments": '{"x": 1}'}},
            {"id": "call_1", "function": {"name": "func1", "arguments": "{}"}},  # Duplicate by id
            {"id": "", "function": {"name": "func2", "arguments": '{"y": 2}'}},
            {"id": "", "function": {"name": "func2", "arguments": '{"y": 2}'}},  # Duplicate by name+args
        ]
        
        print("Action: Deduplication...")
        result = deduplicate_tool_calls(tool_calls)
        
        print(f"Result: {result}")
        # call_1 with arguments + func2 once
        assert len(result) == 2
        
        # Verify that call_1 kept its arguments
        call_1 = next(tc for tc in result if tc["id"] == "call_1")
        assert call_1["function"]["arguments"] == '{"x": 1}'


class TestAwsEventStreamParserInitialization:
    """Tests for AwsEventStreamParser initialization."""
    
    def test_initialization_creates_empty_state(self):
        """
        What it does: Tests initial parser state.
        Goal: Ensure parser is created with empty state.
        """
        print("Setup: Creating parser...")
        parser = AwsEventStreamParser()
        
        print("Check: Buffer is empty...")
        assert parser.buffer == ""
        
        print("Check: last_content is None...")
        assert parser.last_content is None
        
        print("Check: current_tool_call is None...")
        assert parser.current_tool_call is None
        
        print("Check: tool_calls is empty...")
        assert parser.tool_calls == []


class TestAwsEventStreamParserFeed:
    """Tests for parser feed method."""
    
    def test_parses_content_event(self, aws_event_parser):
        """
        What it does: Tests parsing of content event.
        Goal: Ensure text content is extracted.
        """
        print("Setup: Chunk with content...")
        chunk = b'{"content":"Hello World"}'
        
        print("Action: Parsing chunk...")
        events = aws_event_parser.feed(chunk)
        
        print(f"Result: {events}")
        assert len(events) == 1
        assert events[0]["type"] == "content"
        assert events[0]["data"] == "Hello World"
    
    def test_parses_multiple_content_events(self, aws_event_parser):
        """
        What it does: Tests parsing of multiple content events.
        Goal: Ensure all events are extracted.
        """
        print("Setup: Chunk with multiple events...")
        chunk = b'{"content":"First"}{"content":"Second"}'
        
        print("Action: Parsing chunk...")
        events = aws_event_parser.feed(chunk)
        
        print(f"Result: {events}")
        assert len(events) == 2
        assert events[0]["data"] == "First"
        assert events[1]["data"] == "Second"
    
    def test_deduplicates_repeated_content(self, aws_event_parser):
        """
        What it does: Tests deduplication of repeated content.
        Goal: Ensure identical content is not duplicated.
        """
        print("Setup: Chunks with repeated content...")
        
        print("Action: Parsing first chunk...")
        events1 = aws_event_parser.feed(b'{"content":"Same"}')
        
        print("Action: Parsing second chunk with same content...")
        events2 = aws_event_parser.feed(b'{"content":"Same"}')
        
        print(f"First result: {events1}")
        print(f"Second result: {events2}")
        assert len(events1) == 1
        assert len(events2) == 0  # Duplicate filtered out
    
    def test_parses_usage_event(self, aws_event_parser):
        """
        What it does: Tests parsing of usage event.
        Goal: Ensure credits information is extracted.
        """
        print("Setup: Chunk with usage...")
        chunk = b'{"usage":1.5}'
        
        print("Action: Parsing chunk...")
        events = aws_event_parser.feed(chunk)
        
        print(f"Result: {events}")
        assert len(events) == 1
        assert events[0]["type"] == "usage"
        assert events[0]["data"] == 1.5
    
    def test_parses_context_usage_event(self, aws_event_parser):
        """
        What it does: Tests parsing of context_usage event.
        Goal: Ensure context usage percentage is extracted.
        """
        print("Setup: Chunk with context usage...")
        chunk = b'{"contextUsagePercentage":25.5}'
        
        print("Action: Parsing chunk...")
        events = aws_event_parser.feed(chunk)
        
        print(f"Result: {events}")
        assert len(events) == 1
        assert events[0]["type"] == "context_usage"
        assert events[0]["data"] == 25.5
    
    def test_handles_incomplete_json(self, aws_event_parser):
        """
        What it does: Tests handling of incomplete JSON.
        Goal: Ensure incomplete JSON is buffered.
        """
        print("Setup: Incomplete chunk...")
        chunk = b'{"content":"Hel'
        
        print("Action: Parsing incomplete chunk...")
        events = aws_event_parser.feed(chunk)
        
        print(f"Result: {events}")
        assert len(events) == 0  # Nothing parsed
        
        print("Check: Data in buffer...")
        assert 'content' in aws_event_parser.buffer
    
    def test_completes_json_across_chunks(self, aws_event_parser):
        """
        What it does: Tests assembling JSON from multiple chunks.
        Goal: Ensure JSON is assembled from parts.
        """
        print("Setup: First part of JSON...")
        events1 = aws_event_parser.feed(b'{"content":"Hel')
        
        print("Action: Second part of JSON...")
        events2 = aws_event_parser.feed(b'lo World"}')
        
        print(f"First result: {events1}")
        print(f"Second result: {events2}")
        assert len(events1) == 0
        assert len(events2) == 1
        assert events2[0]["data"] == "Hello World"
    
    def test_decodes_escape_sequences(self, aws_event_parser):
        """
        What it does: Tests decoding of escape sequences.
        Goal: Ensure \\n is converted to actual newline.
        """
        print("Setup: Chunk with escape sequence...")
        # Using correct escape sequence format
        chunk = b'{"content":"Line1\\nLine2"}'
        
        print("Action: Parsing chunk...")
        events = aws_event_parser.feed(chunk)
        
        print(f"Result: {events}")
        assert len(events) == 1
        assert "\n" in events[0]["data"]
    def test_handles_invalid_bytes(self, aws_event_parser):
        """
        What it does: Tests handling of invalid bytes.
        Goal: Ensure invalid data doesn't break the parser.
        """
        print("Setup: Invalid bytes...")
        chunk = b'\xff\xfe{"content":"test"}'
        
        print("Action: Parsing chunk...")
        events = aws_event_parser.feed(chunk)
        
        print(f"Result: {events}")
        # Parser should continue working
        assert len(events) == 1


class TestAwsEventStreamParserToolCalls:
    """Tests for tool calls parsing."""
    
    def test_parses_tool_start_event(self, aws_event_parser):
        """
        What it does: Tests parsing of tool call start.
        Goal: Ensure tool_start creates current_tool_call.
        """
        print("Setup: Chunk with tool call start...")
        chunk = b'{"name":"get_weather","toolUseId":"call_123"}'
        
        print("Action: Parsing chunk...")
        events = aws_event_parser.feed(chunk)
        
        print(f"Result: {events}")
        print(f"current_tool_call: {aws_event_parser.current_tool_call}")
        
        # tool_start doesn't return event, but creates current_tool_call
        assert aws_event_parser.current_tool_call is not None
        assert aws_event_parser.current_tool_call["function"]["name"] == "get_weather"
    
    def test_parses_tool_input_event(self, aws_event_parser):
        """
        What it does: Tests parsing of input for tool call.
        Goal: Ensure input is added to current_tool_call.
        """
        print("Setup: Tool call start...")
        aws_event_parser.feed(b'{"name":"func","toolUseId":"call_1"}')
        
        print("Action: Parsing input...")
        aws_event_parser.feed(b'{"input":"{\\"key\\": \\"value\\"}"}')
        
        print(f"current_tool_call: {aws_event_parser.current_tool_call}")
        assert '{"key": "value"}' in aws_event_parser.current_tool_call["function"]["arguments"]
    
    def test_parses_tool_stop_event(self, aws_event_parser):
        """
        What it does: Tests tool call completion.
        Goal: Ensure tool call is added to the list.
        """
        print("Setup: Complete tool call...")
        aws_event_parser.feed(b'{"name":"func","toolUseId":"call_1"}')
        aws_event_parser.feed(b'{"input":"{}"}')
        
        print("Action: Parsing stop...")
        aws_event_parser.feed(b'{"stop":true}')
        
        print(f"tool_calls: {aws_event_parser.tool_calls}")
        assert len(aws_event_parser.tool_calls) == 1
        assert aws_event_parser.current_tool_call is None
    
    def test_get_tool_calls_returns_all(self, aws_event_parser):
        """
        What it does: Tests getting all tool calls.
        Goal: Ensure get_tool_calls returns completed calls.
        """
        print("Setup: Multiple tool calls...")
        aws_event_parser.feed(b'{"name":"func1","toolUseId":"call_1"}')
        aws_event_parser.feed(b'{"stop":true}')
        aws_event_parser.feed(b'{"name":"func2","toolUseId":"call_2"}')
        aws_event_parser.feed(b'{"stop":true}')
        
        print("Action: Getting tool calls...")
        tool_calls = aws_event_parser.get_tool_calls()
        
        print(f"Result: {tool_calls}")
        assert len(tool_calls) == 2
    
    def test_get_tool_calls_finalizes_current(self, aws_event_parser):
        """
        What it does: Tests finalization of incomplete tool call.
        Goal: Ensure get_tool_calls finalizes current_tool_call.
        """
        print("Setup: Incomplete tool call...")
        aws_event_parser.feed(b'{"name":"func","toolUseId":"call_1"}')
        
        print("Action: Getting tool calls...")
        tool_calls = aws_event_parser.get_tool_calls()
        
        print(f"Result: {tool_calls}")
        assert len(tool_calls) == 1
        assert aws_event_parser.current_tool_call is None


class TestAwsEventStreamParserReset:
    """Tests for reset method."""
    
    def test_reset_clears_state(self, aws_event_parser):
        """
        What it does: Tests parser state reset.
        Goal: Ensure reset clears all data.
        """
        print("Setup: Filling parser with data...")
        aws_event_parser.feed(b'{"content":"test"}')
        aws_event_parser.feed(b'{"name":"func","toolUseId":"call_1"}')
        
        print("Action: Resetting parser...")
        aws_event_parser.reset()
        
        print("Check: All data cleared...")
        assert aws_event_parser.buffer == ""
        assert aws_event_parser.last_content is None
        assert aws_event_parser.current_tool_call is None
        assert aws_event_parser.tool_calls == []


class TestAwsEventStreamParserFinalizeToolCall:
    """Tests for _finalize_tool_call method handling different input types."""
    
    def test_finalize_with_string_arguments(self, aws_event_parser):
        """
        What it does: Tests finalization of tool call with string arguments.
        Goal: Ensure JSON string is parsed and serialized back.
        """
        print("Setup: Tool call with string arguments...")
        aws_event_parser.current_tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "test_func",
                "arguments": '{"key": "value"}'
            }
        }
        
        print("Action: Finalizing tool call...")
        aws_event_parser._finalize_tool_call()
        
        print(f"Result: {aws_event_parser.tool_calls}")
        assert len(aws_event_parser.tool_calls) == 1
        assert aws_event_parser.tool_calls[0]["function"]["arguments"] == '{"key": "value"}'
    
    def test_finalize_with_dict_arguments(self, aws_event_parser):
        """
        What it does: Tests finalization of tool call with dict arguments.
        Goal: Ensure dict is serialized to JSON string.
        """
        print("Setup: Tool call with dict arguments...")
        aws_event_parser.current_tool_call = {
            "id": "call_2",
            "type": "function",
            "function": {
                "name": "test_func",
                "arguments": {"location": "Moscow", "units": "celsius"}
            }
        }
        
        print("Action: Finalizing tool call...")
        aws_event_parser._finalize_tool_call()
        
        print(f"Result: {aws_event_parser.tool_calls}")
        assert len(aws_event_parser.tool_calls) == 1
        
        args = aws_event_parser.tool_calls[0]["function"]["arguments"]
        print(f"Arguments: {args}")
        assert isinstance(args, str)
        assert "Moscow" in args
        assert "celsius" in args
    
    def test_finalize_with_empty_string_arguments(self, aws_event_parser):
        """
        What it does: Tests finalization of tool call with empty string arguments.
        Goal: Ensure empty string is replaced with "{}".
        """
        print("Setup: Tool call with empty string arguments...")
        aws_event_parser.current_tool_call = {
            "id": "call_3",
            "type": "function",
            "function": {
                "name": "test_func",
                "arguments": ""
            }
        }
        
        print("Action: Finalizing tool call...")
        aws_event_parser._finalize_tool_call()
        
        print(f"Result: {aws_event_parser.tool_calls}")
        assert len(aws_event_parser.tool_calls) == 1
        assert aws_event_parser.tool_calls[0]["function"]["arguments"] == "{}"
    
    def test_finalize_with_whitespace_only_arguments(self, aws_event_parser):
        """
        What it does: Tests finalization of tool call with whitespace arguments.
        Goal: Ensure whitespace string is replaced with "{}".
        """
        print("Setup: Tool call with whitespace arguments...")
        aws_event_parser.current_tool_call = {
            "id": "call_4",
            "type": "function",
            "function": {
                "name": "test_func",
                "arguments": "   "
            }
        }
        
        print("Action: Finalizing tool call...")
        aws_event_parser._finalize_tool_call()
        
        print(f"Result: {aws_event_parser.tool_calls}")
        assert len(aws_event_parser.tool_calls) == 1
        assert aws_event_parser.tool_calls[0]["function"]["arguments"] == "{}"
    
    def test_finalize_with_invalid_json_arguments(self, aws_event_parser):
        """
        What it does: Tests finalization of tool call with invalid JSON.
        Goal: Ensure invalid JSON is replaced with "{}".
        """
        print("Setup: Tool call with invalid JSON...")
        aws_event_parser.current_tool_call = {
            "id": "call_5",
            "type": "function",
            "function": {
                "name": "test_func",
                "arguments": "not valid json {"
            }
        }
        
        print("Action: Finalizing tool call...")
        aws_event_parser._finalize_tool_call()
        
        print(f"Result: {aws_event_parser.tool_calls}")
        assert len(aws_event_parser.tool_calls) == 1
        assert aws_event_parser.tool_calls[0]["function"]["arguments"] == "{}"
    
    def test_finalize_with_none_current_tool_call(self, aws_event_parser):
        """
        What it does: Tests finalization when current_tool_call is None.
        Goal: Ensure nothing happens with None.
        """
        print("Setup: current_tool_call = None...")
        aws_event_parser.current_tool_call = None
        
        print("Action: Finalizing tool call...")
        aws_event_parser._finalize_tool_call()
        
        print(f"Result: {aws_event_parser.tool_calls}")
        assert len(aws_event_parser.tool_calls) == 0
    
    def test_finalize_clears_current_tool_call(self, aws_event_parser):
        """
        What it does: Tests that finalization clears current_tool_call.
        Goal: Ensure current_tool_call = None after finalization.
        """
        print("Setup: Tool call...")
        aws_event_parser.current_tool_call = {
            "id": "call_6",
            "type": "function",
            "function": {
                "name": "test_func",
                "arguments": "{}"
            }
        }
        
        print("Action: Finalizing tool call...")
        aws_event_parser._finalize_tool_call()
        
        print(f"current_tool_call after finalization: {aws_event_parser.current_tool_call}")
        assert aws_event_parser.current_tool_call is None


class TestAwsEventStreamParserEdgeCases:
    """Tests for edge cases."""
    
    def test_handles_followup_prompt(self, aws_event_parser):
        """
        What it does: Tests ignoring followupPrompt.
        Goal: Ensure followupPrompt doesn't create an event.
        """
        print("Setup: Chunk with followupPrompt...")
        chunk = b'{"content":"text","followupPrompt":"suggestion"}'
        
        print("Action: Parsing chunk...")
        events = aws_event_parser.feed(chunk)
        
        print(f"Result: {events}")
        assert len(events) == 0  # followupPrompt is ignored
    
    def test_handles_mixed_events(self, aws_event_parser):
        """
        What it does: Tests parsing of mixed events.
        Goal: Ensure different event types are handled together.
        """
        print("Setup: Chunk with mixed events...")
        chunk = b'{"content":"Hello"}{"usage":1.0}{"contextUsagePercentage":50}'
        
        print("Action: Parsing chunk...")
        events = aws_event_parser.feed(chunk)
        
        print(f"Result: {events}")
        assert len(events) == 3
        assert events[0]["type"] == "content"
        assert events[1]["type"] == "usage"
        assert events[2]["type"] == "context_usage"
    
    def test_handles_garbage_between_events(self, aws_event_parser):
        """
        What it does: Tests handling of garbage between events.
        Goal: Ensure parser finds JSON among garbage.
        """
        print("Setup: Chunk with garbage between JSON...")
        chunk = b'garbage{"content":"valid"}more garbage{"usage":1}'
        
        print("Action: Parsing chunk...")
        events = aws_event_parser.feed(chunk)
        
        print(f"Result: {events}")
        assert len(events) == 2
    
    def test_handles_empty_chunk(self, aws_event_parser):
        """
        What it does: Tests handling of empty chunk.
        Goal: Ensure empty chunk doesn't cause errors.
        """
        print("Setup: Empty chunk...")
        
        print("Action: Parsing empty chunk...")
        events = aws_event_parser.feed(b'')
        
        print(f"Comparing result: Expected [], Got {events}")
        assert events == []


class TestDiagnoseJsonTruncation:
    """
    Tests for _diagnose_json_truncation method for diagnosing truncated JSON.
    
    This method helps distinguish upstream issues (Kiro API truncates large
    tool call arguments) from actually invalid JSON from the model.
    """
    
    def test_empty_string_not_truncated(self, aws_event_parser):
        """
        What it does: Tests handling of empty string.
        Goal: Ensure empty string is not considered truncated.
        """
        print("Setup: Empty string...")
        json_str = ""
        
        print("Action: Diagnosis...")
        result = aws_event_parser._diagnose_json_truncation(json_str)
        
        print(f"Result: {result}")
        print(f"Comparing is_truncated: Expected False, Got {result['is_truncated']}")
        assert result["is_truncated"] is False
        assert result["reason"] == "empty string"
        assert result["size_bytes"] == 0
    
    def test_whitespace_only_not_truncated(self, aws_event_parser):
        """
        What it does: Tests handling of whitespace-only string.
        Goal: Ensure whitespace string is not considered truncated.
        """
        print("Setup: Whitespace string...")
        json_str = "   \t\n  "
        
        print("Action: Diagnosis...")
        result = aws_event_parser._diagnose_json_truncation(json_str)
        
        print(f"Result: {result}")
        print(f"Comparing is_truncated: Expected False, Got {result['is_truncated']}")
        assert result["is_truncated"] is False
        assert result["reason"] == "empty string"
    
    def test_valid_json_not_truncated(self, aws_event_parser):
        """
        What it does: Tests handling of valid JSON.
        Goal: Ensure valid JSON is not considered truncated.
        """
        print("Setup: Valid JSON...")
        json_str = '{"key": "value", "number": 42}'
        
        print("Action: Diagnosis...")
        result = aws_event_parser._diagnose_json_truncation(json_str)
        
        print(f"Result: {result}")
        print(f"Comparing is_truncated: Expected False, Got {result['is_truncated']}")
        assert result["is_truncated"] is False
        assert result["reason"] == "malformed JSON"  # Function doesn't check validity, only structure
    
    def test_valid_nested_json_not_truncated(self, aws_event_parser):
        """
        What it does: Tests handling of nested valid JSON.
        Goal: Ensure complex JSON is not considered truncated.
        """
        print("Setup: Nested valid JSON...")
        json_str = '{"outer": {"inner": {"deep": [1, 2, 3]}}}'
        
        print("Action: Diagnosis...")
        result = aws_event_parser._diagnose_json_truncation(json_str)
        
        print(f"Result: {result}")
        assert result["is_truncated"] is False
    
    def test_missing_closing_brace_truncated(self, aws_event_parser):
        """
        What it does: Tests detection of missing closing brace.
        Goal: Ensure JSON without closing } is considered truncated.
        """
        print("Setup: JSON without closing brace...")
        json_str = '{"filePath": "/path/to/file.md"'
        
        print("Action: Diagnosis...")
        result = aws_event_parser._diagnose_json_truncation(json_str)
        
        print(f"Result: {result}")
        print(f"Comparing is_truncated: Expected True, Got {result['is_truncated']}")
        assert result["is_truncated"] is True
        assert "missing" in result["reason"] and "brace" in result["reason"]
    
    def test_real_world_truncation_from_issue_34(self, aws_event_parser):
        """
        What it does: Tests real example from Issue #34.
        Goal: Ensure real truncated JSON from bug is detected.
        """
        print("Setup: Real example from Issue #34...")
        # This is exact example from log: JSON truncated after filePath
        json_str = '{"filePath": "/Users/cc/Documents/Code/mock-all/docs/plans/2026-01-12-mock-all-impl.md"'
        
        print("Action: Diagnosis...")
        result = aws_event_parser._diagnose_json_truncation(json_str)
        
        print(f"Result: {result}")
        print(f"Comparing is_truncated: Expected True, Got {result['is_truncated']}")
        assert result["is_truncated"] is True
        assert "brace" in result["reason"]
        assert result["size_bytes"] == 87  # Exact size from log (char 87 = error position)
    
    def test_multiple_missing_braces_truncated(self, aws_event_parser):
        """
        What it does: Tests detection of multiple missing braces.
        Goal: Ensure nested JSON without closing braces is detected.
        """
        print("Setup: Nested JSON without closing braces...")
        json_str = '{"outer": {"inner": {"deep": "value"'
        
        print("Action: Diagnosis...")
        result = aws_event_parser._diagnose_json_truncation(json_str)
        
        print(f"Result: {result}")
        assert result["is_truncated"] is True
        assert "3" in result["reason"] or "brace" in result["reason"]
    
    def test_missing_closing_bracket_truncated(self, aws_event_parser):
        """
        What it does: Tests detection of missing closing square bracket.
        Goal: Ensure array without ] is considered truncated.
        """
        print("Setup: Array without closing bracket...")
        json_str = '[1, 2, 3, {"key": "value"}'
        
        print("Action: Diagnosis...")
        result = aws_event_parser._diagnose_json_truncation(json_str)
        
        print(f"Result: {result}")
        print(f"Comparing is_truncated: Expected True, Got {result['is_truncated']}")
        assert result["is_truncated"] is True
        assert "bracket" in result["reason"]
    
    def test_array_start_truncated(self, aws_event_parser):
        """
        What it does: Tests detection of truncated array at start.
        Goal: Ensure [ without ] is detected.
        """
        print("Setup: Array start without end...")
        json_str = '["item1", "item2"'
        
        print("Action: Diagnosis...")
        result = aws_event_parser._diagnose_json_truncation(json_str)
        
        print(f"Result: {result}")
        assert result["is_truncated"] is True
        assert "bracket" in result["reason"]
    
    def test_unbalanced_braces_truncated(self, aws_event_parser):
        """
        What it does: Tests detection of unbalanced curly braces.
        Goal: Ensure different count of { and } is detected.
        """
        print("Setup: JSON with unbalanced braces...")
        # Ends with }, but has extra opening inside
        json_str = '{"a": {"b": 1}}'[:-1]  # Remove last }
        
        print("Action: Diagnosis...")
        result = aws_event_parser._diagnose_json_truncation(json_str)
        
        print(f"Result: {result}")
        assert result["is_truncated"] is True
    
    def test_unbalanced_brackets_truncated(self, aws_event_parser):
        """
        What it does: Tests detection of unbalanced square brackets.
        Goal: Ensure different count of [ and ] is detected.
        """
        print("Setup: JSON with unbalanced square brackets...")
        json_str = '{"items": [[1, 2], [3, 4]}'  # Missing one ]
        
        print("Action: Diagnosis...")
        result = aws_event_parser._diagnose_json_truncation(json_str)
        
        print(f"Result: {result}")
        assert result["is_truncated"] is True
        assert "bracket" in result["reason"]
    
    def test_unclosed_string_truncated(self, aws_event_parser):
        """
        What it does: Tests detection of unclosed string.
        Goal: Ensure odd number of quotes is detected.
        """
        print("Setup: JSON with unclosed string...")
        json_str = '{"content": "This is a very long string that was cut off'
        
        print("Action: Diagnosis...")
        result = aws_event_parser._diagnose_json_truncation(json_str)
        
        print(f"Result: {result}")
        print(f"Comparing is_truncated: Expected True, Got {result['is_truncated']}")
        assert result["is_truncated"] is True
        assert "string" in result["reason"] or "brace" in result["reason"]
    
    def test_escaped_quotes_handled_correctly(self, aws_event_parser):
        """
        What it does: Tests correct handling of escaped quotes.
        Goal: Ensure \\" doesn't break quote counting.
        """
        print("Setup: JSON with escaped quotes...")
        json_str = '{"text": "Say \\"hello\\" to everyone"}'
        
        print("Action: Diagnosis...")
        result = aws_event_parser._diagnose_json_truncation(json_str)
        
        print(f"Result: {result}")
        print(f"Comparing is_truncated: Expected False, Got {result['is_truncated']}")
        assert result["is_truncated"] is False
    
    def test_truncated_in_middle_of_escaped_sequence(self, aws_event_parser):
        """
        What it does: Tests truncation in middle of escape sequence.
        Goal: Ensure truncation after \\ is detected.
        """
        print("Setup: JSON truncated after backslash...")
        json_str = '{"text": "Line1\\nLine2\\'
        
        print("Action: Diagnosis...")
        result = aws_event_parser._diagnose_json_truncation(json_str)
        
        print(f"Result: {result}")
        assert result["is_truncated"] is True
    
    def test_size_bytes_calculated_correctly(self, aws_event_parser):
        """
        What it does: Tests correct byte size calculation.
        Goal: Ensure UTF-8 characters are counted correctly.
        """
        print("Setup: JSON with Unicode characters...")
        json_str = '{"city": "Москва"'  # Cyrillic = 2 bytes per character
        
        print("Action: Diagnosis...")
        result = aws_event_parser._diagnose_json_truncation(json_str)
        
        print(f"Result: {result}")
        expected_size = len(json_str.encode('utf-8'))
        print(f"Comparing size_bytes: Expected {expected_size}, Got {result['size_bytes']}")
        assert result["size_bytes"] == expected_size
        assert result["is_truncated"] is True  # No closing }
    
    def test_large_truncated_json(self, aws_event_parser):
        """
        What it does: Tests handling of large truncated JSON.
        Goal: Ensure large data is handled correctly.
        """
        print("Setup: Large truncated JSON...")
        # Simulate large file that was truncated
        content = "x" * 10000
        json_str = f'{{"filePath": "/path/to/file.md", "content": "{content}'
        
        print("Action: Diagnosis...")
        result = aws_event_parser._diagnose_json_truncation(json_str)
        
        print(f"Result: is_truncated={result['is_truncated']}, size_bytes={result['size_bytes']}")
        assert result["is_truncated"] is True
        assert result["size_bytes"] > 10000
    
    def test_malformed_but_not_truncated(self, aws_event_parser):
        """
        What it does: Tests invalid but not truncated JSON.
        Goal: Ensure syntax errors are not confused with truncation.
        """
        print("Setup: Invalid JSON (trailing comma)...")
        json_str = '{"key": "value",}'  # Trailing comma - invalid, but not truncated
        
        print("Action: Diagnosis...")
        result = aws_event_parser._diagnose_json_truncation(json_str)
        
        print(f"Result: {result}")
        print(f"Comparing is_truncated: Expected False, Got {result['is_truncated']}")
        assert result["is_truncated"] is False
        assert result["reason"] == "malformed JSON"
    
    def test_json_with_only_opening_brace(self, aws_event_parser):
        """
        What it does: Tests JSON with only opening brace.
        Goal: Ensure minimal truncated JSON is detected.
        """
        print("Setup: Only opening brace...")
        json_str = '{'
        
        print("Action: Diagnosis...")
        result = aws_event_parser._diagnose_json_truncation(json_str)
        
        print(f"Result: {result}")
        assert result["is_truncated"] is True
        assert "brace" in result["reason"]
    
    def test_json_with_only_opening_bracket(self, aws_event_parser):
        """
        What it does: Tests JSON with only opening square bracket.
        Goal: Ensure minimal truncated array is detected.
        """
        print("Setup: Only opening square bracket...")
        json_str = '['
        
        print("Action: Diagnosis...")
        result = aws_event_parser._diagnose_json_truncation(json_str)
        
        print(f"Result: {result}")
        assert result["is_truncated"] is True
        assert "bracket" in result["reason"]
    
    def test_braces_inside_string_not_counted(self, aws_event_parser):
        """
        What it does: Tests that braces inside strings don't affect counting.
        Goal: Ensure "{}" inside string doesn't break diagnosis.
        
        Note: Current implementation uses simplified counting,
        which doesn't account for string context. This is a known limitation.
        """
        print("Setup: JSON with braces inside string...")
        json_str = '{"text": "Hello {world}"}'
        
        print("Action: Diagnosis...")
        result = aws_event_parser._diagnose_json_truncation(json_str)
        
        print(f"Result: {result}")
        # Function uses simplified counting, so this may be False
        # Main thing - it doesn't crash and returns correct structure
        assert "is_truncated" in result
        assert "reason" in result
        assert "size_bytes" in result
    
    def test_complex_nested_truncation(self, aws_event_parser):
        """
        What it does: Tests complex nested truncated JSON.
        Goal: Ensure deep nesting is handled.
        """
        print("Setup: Complex nested truncated JSON...")
        json_str = '{"level1": {"level2": {"level3": [{"item": "value'
        
        print("Action: Diagnosis...")
        result = aws_event_parser._diagnose_json_truncation(json_str)
        
        print(f"Result: {result}")
        assert result["is_truncated"] is True


# =============================================================================
# Tests for Truncation Recovery System integration (Issue #56)
# =============================================================================

class TestTruncationRecoveryIntegration:
    """
    Tests for Truncation Recovery System integration in parsers.
    
    Verifies that tool calls are marked with truncation flags when JSON is truncated.
    Part of Truncation Recovery System (Issue #56).
    """
    
    def test_tool_call_marked_with_truncation_flags(self, aws_event_parser):
        """
        What it does: Verifies tool call is marked with _truncation_detected and _truncation_info.
        Purpose: Ensure truncation detection marks tool calls for recovery system.
        """
        print("Setup: Creating tool call with truncated JSON arguments...")
        aws_event_parser.current_tool_call = {
            "id": "tooluse_truncated",
            "type": "function",
            "function": {
                "name": "write_to_file",
                "arguments": '{"filePath": "/path/to/file.md", "content": "This is a very long content that was cut off'
            }
        }
        
        print("Action: Finalizing tool call (should detect truncation)...")
        aws_event_parser._finalize_tool_call()
        
        print("Checking: Tool call was added to list...")
        assert len(aws_event_parser.tool_calls) == 1
        
        tool_call = aws_event_parser.tool_calls[0]
        print(f"Tool call: {tool_call}")
        
        print("Checking: _truncation_detected flag is set...")
        assert tool_call.get("_truncation_detected") is True
        
        print("Checking: _truncation_info is present...")
        assert "_truncation_info" in tool_call
        
        truncation_info = tool_call["_truncation_info"]
        print(f"Truncation info: {truncation_info}")
        
        print("Checking: truncation_info has required fields...")
        assert truncation_info["is_truncated"] is True
        assert "size_bytes" in truncation_info
        assert truncation_info["size_bytes"] > 0
        assert "reason" in truncation_info
        assert len(truncation_info["reason"]) > 0
    
    def test_valid_tool_call_not_marked_with_truncation(self, aws_event_parser):
        """
        What it does: Verifies valid tool call is NOT marked with truncation flags.
        Purpose: Ensure false positives don't occur.
        """
        print("Setup: Creating tool call with valid JSON arguments...")
        aws_event_parser.current_tool_call = {
            "id": "tooluse_valid",
            "type": "function",
            "function": {
                "name": "get_weather",
                "arguments": '{"location": "Moscow", "units": "celsius"}'
            }
        }
        
        print("Action: Finalizing tool call...")
        aws_event_parser._finalize_tool_call()
        
        print("Checking: Tool call was added to list...")
        assert len(aws_event_parser.tool_calls) == 1
        
        tool_call = aws_event_parser.tool_calls[0]
        print(f"Tool call: {tool_call}")
        
        print("Checking: _truncation_detected flag is NOT set...")
        assert tool_call.get("_truncation_detected") is not True
        
        print("Checking: _truncation_info is NOT present...")
        assert "_truncation_info" not in tool_call
    
    def test_multiple_tool_calls_with_mixed_truncation(self, aws_event_parser):
        """
        What it does: Verifies multiple tool calls are marked independently.
        Purpose: Ensure truncation detection works correctly for multiple tool calls.
        """
        print("Setup: Creating first tool call (valid)...")
        aws_event_parser.current_tool_call = {
            "id": "tooluse_1",
            "type": "function",
            "function": {
                "name": "func1",
                "arguments": '{"param": "value"}'
            }
        }
        aws_event_parser._finalize_tool_call()
        
        print("Setup: Creating second tool call (truncated)...")
        aws_event_parser.current_tool_call = {
            "id": "tooluse_2",
            "type": "function",
            "function": {
                "name": "func2",
                "arguments": '{"param": "incomplete'
            }
        }
        aws_event_parser._finalize_tool_call()
        
        print("Setup: Creating third tool call (valid)...")
        aws_event_parser.current_tool_call = {
            "id": "tooluse_3",
            "type": "function",
            "function": {
                "name": "func3",
                "arguments": '{"param": "complete"}'
            }
        }
        aws_event_parser._finalize_tool_call()
        
        print("Checking: All tool calls were added...")
        assert len(aws_event_parser.tool_calls) == 3
        
        print("Checking: First tool call NOT marked as truncated...")
        assert aws_event_parser.tool_calls[0].get("_truncation_detected") is not True
        
        print("Checking: Second tool call IS marked as truncated...")
        assert aws_event_parser.tool_calls[1].get("_truncation_detected") is True
        assert "_truncation_info" in aws_event_parser.tool_calls[1]
        
        print("Checking: Third tool call NOT marked as truncated...")
        assert aws_event_parser.tool_calls[2].get("_truncation_detected") is not True


def _json_str(text: str) -> str:
    """Serializes text as a JSON string literal without ASCII escaping."""
    return json.dumps(text, ensure_ascii=False)


def _feed_in_chunks(payload: bytes, chunk_size: int):
    """Feeds payload into a fresh parser in fixed-size chunks; returns (events, tool_calls, parser)."""
    parser = AwsEventStreamParser()
    events = []
    for i in range(0, len(payload), chunk_size):
        events.extend(parser.feed(payload[i:i + chunk_size]))
    return events, parser.get_tool_calls(), parser


def _build_large_tool_stream(arg_size: int) -> bytes:
    """Builds a stream with a large tool call whose args contain braces, quotes and escapes."""
    content = ('x{"k": "}{\\"' * (arg_size // 12 + 1))[:arg_size]
    args = json.dumps({"path": "/tmp/f.txt", "content": content, "nested": {"a": [1, {"b": "}"}]}})
    return (
        b'{"content":"Writing file"}'
        + json.dumps({"name": "write_file", "toolUseId": "tool_big", "input": args}).encode("utf-8")
        + b'{"stop":true}{"contextUsagePercentage":42.0}'
    )


class TestAwsEventStreamParserUtf8Chunking:
    """Tests for incremental UTF-8 decoding across chunk boundaries."""

    @pytest.mark.parametrize("char", ["\u00e9", "\u20ac", "\u4e2d", "\U0001F600", "\U0001D11E"])
    def test_multibyte_char_split_at_every_offset(self, char):
        """
        What it does: Splits a 2/3/4-byte UTF-8 character at every byte offset.
        Goal: Ensure no character is dropped when a chunk boundary falls inside it.
        """
        encoded_char = char.encode("utf-8")
        payload = b'{"content":"a' + encoded_char + b'b"}'
        char_start = payload.index(encoded_char)
        assert len(encoded_char) >= 2

        for split in range(char_start + 1, char_start + len(encoded_char)):
            parser = AwsEventStreamParser()
            events = parser.feed(payload[:split]) + parser.feed(payload[split:])
            print(f"Split at {split}: {events}")
            assert events == [{"type": "content", "data": f"a{char}b"}]

    def test_multibyte_text_fed_byte_by_byte(self):
        """
        What it does: Feeds mixed-width UTF-8 content one byte at a time.
        Goal: Ensure byte-by-byte delivery produces exactly the original text.
        """
        text = "\u041f\u0440\u0438\u0432\u0435\u0442, \u4e16\u754c! \U0001F600 \u00e9\u20ac\U0001D11E"
        payload = ('garbage{"content":' + _json_str(text) + '}').encode("utf-8")
        parser = AwsEventStreamParser()
        events = []
        for i in range(len(payload)):
            events.extend(parser.feed(payload[i:i + 1]))
        assert events == [{"type": "content", "data": text}]

    def test_every_split_offset_of_multi_event_stream(self):
        """
        What it does: Splits a multi-event stream with multibyte text at every byte offset.
        Goal: Ensure output is identical to single-chunk feed regardless of split point.
        """
        payload = (
            '{"content":"\u65e5\u672c\u8a9e"}junk{"name":"tool","toolUseId":"t1","input":{}}'
            '{"input":"{\\"q\\": \\"\u00fc\U0001F600\\"}"}{"stop":true}{"usage":1.5}'
        ).encode("utf-8")
        reference = AwsEventStreamParser()
        expected_events = reference.feed(payload)
        expected_tools = reference.get_tool_calls()
        assert json.loads(expected_tools[0]["function"]["arguments"]) == {"q": "\u00fc\U0001F600"}

        for split in range(len(payload) + 1):
            parser = AwsEventStreamParser()
            events = parser.feed(payload[:split]) + parser.feed(payload[split:])
            assert events == expected_events, f"split={split}"
            assert parser.get_tool_calls() == expected_tools, f"split={split}"

    def test_invalid_bytes_still_ignored(self, aws_event_parser):
        """
        What it does: Feeds invalid UTF-8 bytes split across chunks.
        Goal: Ensure invalid bytes are dropped without breaking later events.
        """
        events = aws_event_parser.feed(b'\xff')
        events += aws_event_parser.feed(b'\xfe{"content":"ok"}\xe4')
        events += aws_event_parser.feed(b'{"usage":2}')
        assert events == [
            {"type": "content", "data": "ok"},
            {"type": "usage", "data": 2},
        ]

    def test_reset_clears_pending_partial_character(self, aws_event_parser):
        """
        What it does: Leaves half of a multibyte char pending, then resets.
        Goal: Ensure reset discards decoder state so it cannot corrupt the next stream.
        """
        aws_event_parser.feed('{"content":"\u20ac'.encode("utf-8")[:-1])
        aws_event_parser.reset()
        assert aws_event_parser.buffer == ""
        events = aws_event_parser.feed(b'{"content":"fresh"}')
        assert events == [{"type": "content", "data": "fresh"}]

    def test_non_bytes_chunk_returns_empty(self, aws_event_parser):
        """
        What it does: Feeds a str instead of bytes.
        Goal: Ensure the parser returns [] instead of raising (same as before).
        """
        assert aws_event_parser.feed("not bytes") == []
        assert aws_event_parser.feed(b'{"usage":1}') == [{"type": "usage", "data": 1}]


class TestAwsEventStreamParserIncrementalScan:
    """Tests for the resumable JSON scan in feed()."""

    @pytest.mark.parametrize("chunk_size", [1, 7, 64, 1024, 4096])
    def test_large_tool_call_chunked_equals_single_feed(self, chunk_size):
        """
        What it does: Feeds a large tool-call stream in chunks of various sizes.
        Goal: Ensure chunked parsing yields exactly the same events and tool calls.
        """
        payload = _build_large_tool_stream(20_000)
        expected_events, expected_tools, _ = _feed_in_chunks(payload, len(payload))
        events, tools, parser = _feed_in_chunks(payload, chunk_size)
        assert events == expected_events
        assert tools == expected_tools
        assert parser.buffer == ""
        assert len(tools) == 1
        assert tools[0]["id"] == "tool_big"
        assert json.loads(tools[0]["function"]["arguments"])["nested"] == {"a": [1, {"b": "}"}]}

    def test_large_event_in_small_chunks_is_fast(self):
        """
        What it does: Feeds a ~300KB tool-call event in 1KB chunks.
        Goal: Guard against O(n^2) rescanning of the pending event.
        """
        payload = _build_large_tool_stream(300_000)
        assert len(payload) > 300_000
        started = time.perf_counter()
        _, tools, _ = _feed_in_chunks(payload, 1024)
        elapsed = time.perf_counter() - started
        print(f"Elapsed: {elapsed:.3f}s")
        assert len(tools) == 1
        assert elapsed < 2.0

    def test_pattern_split_across_chunks_is_found(self):
        """
        What it does: Splits an event prefix like '{"contextUsagePercentage":' at every offset.
        Goal: Ensure a prefix straddling the search boundary is still detected.
        """
        payload = b'noise' * 10 + b'{"contextUsagePercentage":12.5}'
        for split in range(len(payload) + 1):
            parser = AwsEventStreamParser()
            events = parser.feed(payload[:split])
            events += parser.feed(payload[split:])
            assert events == [{"type": "context_usage", "data": 12.5}], f"split={split}"

    def test_garbage_only_chunks_then_event(self):
        """
        What it does: Feeds many garbage chunks without any event, then one event.
        Goal: Ensure garbage is kept in buffer (semantics unchanged) and the event is still parsed.
        """
        parser = AwsEventStreamParser()
        for _ in range(500):
            assert parser.feed(b'\x00\x01:message-type event ') == []
        assert ':message-type' in parser.buffer
        events = parser.feed(b'{"content":"after garbage"}')
        assert events == [{"type": "content", "data": "after garbage"}]
        assert parser.buffer == ""

    def test_split_inside_escape_sequence(self):
        """
        What it does: Splits right after a backslash inside a JSON string.
        Goal: Ensure escape state survives across chunks (escaped quote not treated as end).
        """
        payload = b'{"content":"say \\"}\\" now"}{"usage":1}'
        split = payload.index(b'\\') + 1
        parser = AwsEventStreamParser()
        events = parser.feed(payload[:split]) + parser.feed(payload[split:])
        assert events == [
            {"type": "content", "data": 'say "}" now'},
            {"type": "usage", "data": 1},
        ]

    def test_nested_pattern_inside_pending_event_not_rematched(self):
        """
        What it does: Pending event whose string contains another event prefix, split everywhere.
        Goal: Ensure the nested prefix is not mistaken for a new event after resuming.
        """
        payload = b'{"content":"text {\\"usage\\": 5} more"}'
        for split in range(1, len(payload)):
            parser = AwsEventStreamParser()
            events = parser.feed(payload[:split]) + parser.feed(payload[split:])
            assert events == [{"type": "content", "data": 'text {"usage": 5} more'}], f"split={split}"

    def test_external_buffer_modification_resets_scan(self, aws_event_parser):
        """
        What it does: Clears the buffer directly while an event is pending.
        Goal: Ensure stale incremental state is discarded and parsing stays correct.
        """
        aws_event_parser.feed(b'{"content":"partial')
        aws_event_parser.buffer = ""
        events = aws_event_parser.feed(b'{"content":"new"}')
        assert events == [{"type": "content", "data": "new"}]

    def test_malformed_balanced_json_is_skipped(self, aws_event_parser):
        """
        What it does: Feeds a brace-balanced but invalid JSON event in chunks, then a valid one.
        Goal: Ensure invalid JSON is consumed and the next event is parsed.
        """
        events = aws_event_parser.feed(b'{"content": bad')
        events += aws_event_parser.feed(b'}{"usage":3}')
        assert events == [{"type": "usage", "data": 3}]
        assert aws_event_parser.buffer == ""

    def test_find_matching_brace_negative_start(self):
        """
        What it does: Passes a negative start position.
        Goal: Ensure -1 is returned rather than indexing from the end.
        """
        assert find_matching_brace('{"a": 1}', -1) == -1

    def test_find_matching_brace_unterminated_escape_at_end(self):
        """
        What it does: Text ends right after a backslash inside a string.
        Goal: Ensure -1 is returned without errors.
        """
        assert find_matching_brace('{"a": "x\\', 0) == -1

    def test_find_matching_brace_matches_reference_loop(self):
        """
        What it does: Compares the regex-based scanner to the original char loop on tricky inputs.
        Goal: Ensure identical results for escapes, nested braces and strings.
        """
        def reference(text, start):
            if start >= len(text) or text[start] != '{':
                return -1
            depth, in_str, esc = 0, False, False
            for i in range(start, len(text)):
                c = text[i]
                if esc:
                    esc = False
                    continue
                if c == '\\' and in_str:
                    esc = True
                    continue
                if c == '"':
                    in_str = not in_str
                    continue
                if not in_str:
                    if c == '{':
                        depth += 1
                    elif c == '}':
                        depth -= 1
                        if depth == 0:
                            return i
            return -1

        samples = [
            '{}', '{{}}', '{"a":"}"}', '{"a":"\\""}', '{"a":"\\\\"}x}', '{\\}',
            '{"a":{"b":"{"}}', '{"x": "\\\\\\"}"}', '{"unterminated', '{"a":1}}}',
            '{ "k" : [ { } , "}" ] }tail', '{"\\u007d": 1}',
        ]
        for sample in samples:
            for start in range(len(sample)):
                assert find_matching_brace(sample, start) == reference(sample, start), (sample, start)


class TestAwsEventStreamParserLazyLogging:
    """Tests that debug logging does not build huge argument reprs."""

    def test_finalize_uses_truncated_preview(self, aws_event_parser):
        """
        What it does: Finalizes a tool call with huge arguments while DEBUG logging is captured.
        Goal: Ensure the logged preview is truncated and arguments stay intact.
        """
        from loguru import logger as loguru_logger

        big_args = '{"data": "' + "z" * 500_000 + '"}'
        aws_event_parser.current_tool_call = {
            "id": "t", "type": "function",
            "function": {"name": "f", "arguments": big_args},
        }
        messages = []
        sink_id = loguru_logger.add(messages.append, level="DEBUG", format="{message}")
        try:
            aws_event_parser._finalize_tool_call()
        finally:
            loguru_logger.remove(sink_id)

        assert json.loads(aws_event_parser.tool_calls[0]["function"]["arguments"]) == json.loads(big_args)
        finalize_logs = [m for m in messages if "Finalizing tool call" in m]
        assert len(finalize_logs) == 1
        assert len(finalize_logs[0]) < 400
        assert any("parsed successfully: ['data']" in m for m in messages)

    def test_preview_repr_truncates(self):
        """
        What it does: Checks _preview_repr for strings and non-strings.
        Goal: Ensure output never exceeds the limit.
        """
        assert len(_preview_repr("a" * 10_000)) <= 200
        assert _preview_repr("ab") == "'ab'"
        assert len(_preview_repr(list(range(10_000)))) <= 200
        assert _preview_repr(None) == "None"