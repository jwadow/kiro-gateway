# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Parsers for AWS Event Stream format.

Contains classes and functions for:
- Parsing binary AWS SSE stream
- Extracting JSON events
- Processing tool calls
- Content deduplication
"""

import codecs
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from kiro.utils import generate_tool_call_id


# Characters that matter to the brace scanner outside / inside JSON string literals.
# Jumping between them with a compiled regex keeps scanning in C instead of a
# per-character Python loop.
_STRUCTURAL_CHARS_RE = re.compile(r'[{}"]')
_STRING_SPECIAL_CHARS_RE = re.compile(r'["\\]')


class _BraceScanState:
    """
    Resumable state of a brace-matching scan over a growing text buffer.

    Lets the scanner continue from where it stopped when more data arrives,
    instead of rescanning the whole pending JSON object on every chunk.

    Attributes:
        pos: Next position in the text to examine
        depth: Current brace nesting depth
        in_string: True if the scanner is inside a JSON string literal
        escape_next: True if the next character is escaped (follows a backslash)
    """

    __slots__ = ("pos", "depth", "in_string", "escape_next")

    def __init__(self, pos: int) -> None:
        """
        Initializes a fresh scan state.

        Args:
            pos: Position of the opening brace where the scan starts
        """
        self.pos = pos
        self.depth = 0
        self.in_string = False
        self.escape_next = False

    def shift(self, offset: int) -> None:
        """
        Rebases the scan position after the buffer prefix was dropped.

        Args:
            offset: Number of characters removed from the start of the buffer
        """
        self.pos -= offset


def _scan_for_matching_brace(text: str, state: _BraceScanState) -> int:
    """
    Advances a brace scan over text, resuming from the saved state.

    Semantics match the classic character loop: braces count only outside
    strings, a backslash inside a string escapes the next character, and a
    quote toggles string mode.

    Args:
        text: Text to scan (may have grown since the previous call)
        state: Scan state, updated in place when the closing brace is not found

    Returns:
        Position of the closing brace, or -1 if the text ends before it
    """
    pos = state.pos
    depth = state.depth
    in_string = state.in_string
    escape_next = state.escape_next
    length = len(text)

    while pos < length:
        if escape_next:
            escape_next = False
            pos += 1
            continue

        if in_string:
            match = _STRING_SPECIAL_CHARS_RE.search(text, pos)
            if match is None:
                pos = length
                break
            pos = match.start()
            if text[pos] == '\\':
                escape_next = True
            else:
                in_string = False
            pos += 1
            continue

        match = _STRUCTURAL_CHARS_RE.search(text, pos)
        if match is None:
            pos = length
            break
        pos = match.start()
        char = text[pos]
        if char == '"':
            in_string = True
        elif char == '{':
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return pos
        pos += 1

    state.pos = pos
    state.depth = depth
    state.in_string = in_string
    state.escape_next = escape_next
    return -1


# Maximum number of characters shown when logging raw tool arguments
_LOG_PREVIEW_CHARS = 200


def _preview_repr(value: Any, limit: int = _LOG_PREVIEW_CHARS) -> str:
    """
    Builds a short repr() preview of a possibly huge value for logging.
    
    Strings are truncated before repr() so the cost does not depend on the
    full value size.
    
    Args:
        value: Value to preview
        limit: Maximum length of the returned preview
    
    Returns:
        repr() of the value, at most limit characters long
    """
    if isinstance(value, str):
        return repr(value[:limit])[:limit]
    return repr(value)[:limit]


def find_matching_brace(text: str, start_pos: int) -> int:
    """
    Finds the position of the closing brace considering nesting and strings.
    
    Uses bracket counting for correct parsing of nested JSON.
    Accounts for quoted strings and escape sequences.
    
    Args:
        text: Text to search
        start_pos: Position of opening brace '{'
    
    Returns:
        Position of closing brace or -1 if not found
    
    Example:
        >>> find_matching_brace('{"a": {"b": 1}}', 0)
        14
        >>> find_matching_brace('{"a": "{}"}', 0)
        10
    """
    if start_pos < 0 or start_pos >= len(text) or text[start_pos] != '{':
        return -1
    
    return _scan_for_matching_brace(text, _BraceScanState(start_pos))


def parse_bracket_tool_calls(response_text: str) -> List[Dict[str, Any]]:
    """
    Parses tool calls in [Called func_name with args: {...}] format.
    
    Some models return tool calls in text format instead of
    structured JSON. This function extracts them.
    
    Args:
        response_text: Model response text
    
    Returns:
        List of tool calls in OpenAI format
    
    Example:
        >>> text = "[Called get_weather with args: {\"city\": \"London\"}]"
        >>> calls = parse_bracket_tool_calls(text)
        >>> calls[0]["function"]["name"]
        'get_weather'
    """
    if not response_text or "[Called" not in response_text:
        return []
    
    tool_calls = []
    pattern = r'\[Called\s+(\w+)\s+with\s+args:\s*'
    
    for match in re.finditer(pattern, response_text, re.IGNORECASE):
        func_name = match.group(1)
        args_start = match.end()
        
        # Find JSON start
        json_start = response_text.find('{', args_start)
        if json_start == -1:
            continue
        
        # Find JSON end considering nesting
        json_end = find_matching_brace(response_text, json_start)
        if json_end == -1:
            continue
        
        json_str = response_text[json_start:json_end + 1]
        
        try:
            args = json.loads(json_str)
            tool_call_id = generate_tool_call_id()
            # index will be added later when forming the final response
            tool_calls.append({
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": func_name,
                    "arguments": json.dumps(args)
                }
            })
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse tool call arguments: {json_str[:100]}")
    
    return tool_calls


def deduplicate_tool_calls(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Removes duplicate tool calls.
    
    Deduplication occurs by two criteria:
    1. By id - if there are multiple tool calls with the same id, keep the one with
       more arguments (not empty "{}")
    2. By name+arguments - remove complete duplicates
    
    Args:
        tool_calls: List of tool calls
    
    Returns:
        List of unique tool calls
    """
    # First deduplicate by id - keep tool call with non-empty arguments
    by_id: Dict[str, Dict[str, Any]] = {}
    for tc in tool_calls:
        tc_id = tc.get("id", "")
        if not tc_id:
            # Without id - add as is (will be deduplicated by name+args)
            continue
        
        existing = by_id.get(tc_id)
        if existing is None:
            by_id[tc_id] = tc
        else:
            # Duplicate by id exists - keep the one with more arguments
            existing_args = existing.get("function", {}).get("arguments", "{}")
            current_args = tc.get("function", {}).get("arguments", "{}")
            
            # Prefer non-empty arguments
            if current_args != "{}" and (existing_args == "{}" or len(current_args) > len(existing_args)):
                logger.debug(f"Replacing tool call {tc_id} with better arguments: {len(existing_args)} -> {len(current_args)}")
                by_id[tc_id] = tc
    
    # Collect tool calls: first those with id, then without id
    result_with_id = list(by_id.values())
    result_without_id = [tc for tc in tool_calls if not tc.get("id")]
    
    # Now deduplicate by name+arguments for all
    seen = set()
    unique = []
    
    for tc in result_with_id + result_without_id:
        # Protection against None in function
        func = tc.get("function") or {}
        func_name = func.get("name") or ""
        func_args = func.get("arguments") or "{}"
        key = f"{func_name}-{func_args}"
        if key not in seen:
            seen.add(key)
            unique.append(tc)
    
    if len(tool_calls) != len(unique):
        logger.debug(f"Deduplicated tool calls: {len(tool_calls)} -> {len(unique)}")
    
    return unique


class AwsEventStreamParser:
    """
    Parser for AWS Event Stream format.
    
    AWS returns events in binary format with :message-type...event delimiters.
    This class extracts JSON events from the stream and converts them to a convenient format.
    
    Supported event types:
    - content: Text content of response
    - tool_start: Start of tool call (name, toolUseId)
    - tool_input: Continuation of input for tool call
    - tool_stop: End of tool call
    - usage: Credit consumption information
    - context_usage: Context usage percentage
    
    Attributes:
        buffer: Buffer for accumulating data
        last_content: Last processed content (for deduplication)
        current_tool_call: Current incomplete tool call
        tool_calls: List of completed tool calls
    
    Example:
        >>> parser = AwsEventStreamParser()
        >>> events = parser.feed(chunk)
        >>> for event in events:
        ...     if event["type"] == "content":
        ...         print(event["data"])
    """
    
    # Patterns for finding JSON events
    EVENT_PATTERNS = [
        ('{"content":', 'content'),
        ('{"name":', 'tool_start'),
        ('{"input":', 'tool_input'),
        ('{"stop":', 'tool_stop'),
        ('{"followupPrompt":', 'followup'),
        ('{"usage":', 'usage'),
        ('{"contextUsagePercentage":', 'context_usage'),
    ]
    
    # Longest event prefix: a prefix that straddles the end of already-searched
    # text can start at most this many characters minus one before the end.
    _MAX_PATTERN_LENGTH = max(len(pattern) for pattern, _ in EVENT_PATTERNS)
    
    def __init__(self) -> None:
        """Initializes the parser."""
        self.buffer = ""
        self.last_content: Optional[str] = None  # For deduplicating repeating content
        self.current_tool_call: Optional[Dict[str, Any]] = None
        self.tool_calls: List[Dict[str, Any]] = []
        self._reset_stream_state()
    
    def _reset_stream_state(self) -> None:
        """
        Resets decoding and incremental scanning state.
        
        The incremental UTF-8 decoder keeps incomplete multibyte sequences
        between chunks, so characters split across network chunks are not lost.
        The scan state lets feed() resume where it stopped instead of rescanning
        the whole buffer on every chunk.
        """
        self._decoder = codecs.getincrementaldecoder('utf-8')(errors='ignore')
        # Buffer offset before which no event prefix can start
        self._search_from = 0
        # Start position and type of the earliest event whose JSON is incomplete
        self._pending_start = -1
        self._pending_type: Optional[str] = None
        self._scan_state: Optional[_BraceScanState] = None
        # Buffer length the incremental state was computed for
        self._tracked_length = 0
    
    def _find_earliest_pattern(self, start: int) -> Tuple[int, Optional[str]]:
        """
        Finds the earliest event prefix in the buffer at or after start.
        
        Args:
            start: Buffer offset to start searching from
        
        Returns:
            Tuple of (position, event type), or (-1, None) if no prefix found
        """
        earliest_pos = -1
        earliest_type = None
        
        for pattern, event_type in self.EVENT_PATTERNS:
            pos = self.buffer.find(pattern, start)
            if pos != -1 and (earliest_pos == -1 or pos < earliest_pos):
                earliest_pos = pos
                earliest_type = event_type
        
        return earliest_pos, earliest_type
    
    def feed(self, chunk: bytes) -> List[Dict[str, Any]]:
        """
        Adds chunk to buffer and returns parsed events.
        
        Decoding is incremental (multibyte UTF-8 characters split across chunks
        are preserved) and JSON scanning resumes from the previous position, so
        a large event delivered in many small chunks is processed in linear time.
        
        Args:
            chunk: Bytes of data from stream
        
        Returns:
            List of events in {"type": str, "data": Any} format
        """
        try:
            decoded = self._decoder.decode(chunk)
        except (TypeError, AttributeError, UnicodeDecodeError) as e:
            logger.warning(f"Failed to decode stream chunk ({type(chunk).__name__}): {e}")
            return []
        
        if len(self.buffer) != self._tracked_length:
            # Buffer was modified outside feed(); incremental state is stale
            self._search_from = 0
            self._pending_start = -1
            self._pending_type = None
            self._scan_state = None
        
        if decoded:
            self.buffer += decoded
        
        events = []
        buffer = self.buffer
        consumed = 0  # Offset of the first unconsumed character in buffer
        
        while True:
            if self._pending_start != -1:
                # Earliest prefix is already known; new data cannot introduce an earlier one
                earliest_pos = self._pending_start
                earliest_type = self._pending_type
                state = self._scan_state
            else:
                earliest_pos, earliest_type = self._find_earliest_pattern(
                    max(consumed, self._search_from)
                )
                if earliest_pos == -1:
                    # Only a prefix straddling the current end can match after more data
                    self._search_from = max(
                        consumed, len(buffer) - (self._MAX_PATTERN_LENGTH - 1)
                    )
                    break
                state = _BraceScanState(earliest_pos)
            
            # Find JSON end, resuming the scan where the previous chunk stopped
            json_end = _scan_for_matching_brace(buffer, state)
            if json_end == -1:
                # JSON not complete, wait for more data
                self._pending_start = earliest_pos
                self._pending_type = earliest_type
                self._scan_state = state
                break
            
            json_str = buffer[earliest_pos:json_end + 1]
            consumed = json_end + 1
            self._search_from = consumed
            self._pending_start = -1
            self._pending_type = None
            self._scan_state = None
            
            try:
                data = json.loads(json_str)
                event = self._process_event(data, earliest_type)
                if event:
                    events.append(event)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse JSON: {json_str[:100]}")
        
        if consumed:
            # Drop consumed text once and rebase stored offsets
            self.buffer = buffer[consumed:]
            self._search_from = max(0, self._search_from - consumed)
            if self._pending_start != -1:
                self._pending_start -= consumed
                self._scan_state.shift(consumed)
        
        self._tracked_length = len(self.buffer)
        return events
    
    def _process_event(self, data: dict, event_type: str) -> Optional[Dict[str, Any]]:
        """
        Processes a parsed event.
        
        Args:
            data: Parsed JSON
            event_type: Event type
        
        Returns:
            Processed event or None
        """
        if event_type == 'content':
            return self._process_content_event(data)
        elif event_type == 'tool_start':
            return self._process_tool_start_event(data)
        elif event_type == 'tool_input':
            return self._process_tool_input_event(data)
        elif event_type == 'tool_stop':
            return self._process_tool_stop_event(data)
        elif event_type == 'usage':
            return {"type": "usage", "data": data.get('usage', 0)}
        elif event_type == 'context_usage':
            return {"type": "context_usage", "data": data.get('contextUsagePercentage', 0)}
        
        return None
    
    def _process_content_event(self, data: dict) -> Optional[Dict[str, Any]]:
        """Processes content event."""
        content = data.get('content', '')
        
        # Skip followupPrompt
        if data.get('followupPrompt'):
            return None
        
        # Deduplicate repeating content
        if content == self.last_content:
            return None
        
        self.last_content = content
        
        return {"type": "content", "data": content}
    
    def _process_tool_start_event(self, data: dict) -> Optional[Dict[str, Any]]:
        """Processes tool call start."""
        # Finalize previous tool call if exists
        if self.current_tool_call:
            self._finalize_tool_call()
        
        # input can be string or object
        input_data = data.get('input', '')
        if isinstance(input_data, dict):
            if input_data:
                # Non-empty dict: serialize it
                input_str = json.dumps(input_data)
            else:
                # Empty dict {}: fragments will follow, use empty string
                input_str = ''
        else:
            input_str = str(input_data) if input_data else ''
        
        self.current_tool_call = {
            "id": data.get('toolUseId', generate_tool_call_id()),
            "type": "function",
            "function": {
                "name": data.get('name', ''),
                "arguments": input_str
            }
        }
        
        if data.get('stop'):
            self._finalize_tool_call()
        
        return None
    
    def _process_tool_input_event(self, data: dict) -> Optional[Dict[str, Any]]:
        """Processes input continuation for tool call."""
        if self.current_tool_call:
            # input can be string or object
            input_data = data.get('input', '')
            if isinstance(input_data, dict):
                if input_data:
                    input_str = json.dumps(input_data)
                else:
                    input_str = ''
            else:
                input_str = str(input_data) if input_data else ''
            self.current_tool_call['function']['arguments'] += input_str
        return None
    
    def _process_tool_stop_event(self, data: dict) -> Optional[Dict[str, Any]]:
        """Processes tool call end."""
        if self.current_tool_call and data.get('stop'):
            self._finalize_tool_call()
        return None
    
    def _finalize_tool_call(self) -> None:
        """Finalizes current tool call and adds to list."""
        if not self.current_tool_call:
            return
        
        # Try to parse and normalize arguments as JSON
        args = self.current_tool_call['function']['arguments']
        tool_name = self.current_tool_call['function'].get('name', 'unknown')
        
        # Lazy logging: tool arguments can be hundreds of KB, so never build
        # their repr unless DEBUG is enabled, and truncate before repr().
        logger.opt(lazy=True).debug(
            "Finalizing tool call '{}' with raw arguments: {}",
            lambda: tool_name,
            lambda: _preview_repr(args),
        )
        
        if isinstance(args, str):
            if args.strip():
                try:
                    parsed = json.loads(args)
                    # Ensure result is a JSON string
                    self.current_tool_call['function']['arguments'] = json.dumps(parsed)
                    logger.opt(lazy=True).debug(
                        "Tool '{}' arguments parsed successfully: {}",
                        lambda: tool_name,
                        lambda: list(parsed.keys()) if isinstance(parsed, dict) else type(parsed),
                    )
                except json.JSONDecodeError as e:
                    # Analyze the failure to provide better diagnostics
                    truncation_info = self._diagnose_json_truncation(args)
                    
                    if truncation_info["is_truncated"]:
                        # Mark for recovery system
                        self.current_tool_call['_truncation_detected'] = True
                        self.current_tool_call['_truncation_info'] = truncation_info
                        
                        # Check if recovery is enabled
                        from kiro.config import TRUNCATION_RECOVERY
                        tool_id = self.current_tool_call.get('id', 'unknown')
                        
                        # Clear error message: this is Kiro API's fault, not ours
                        logger.error(
                            f"Tool call truncated by Kiro API: "
                            f"tool='{tool_name}', id={tool_id}, size={truncation_info['size_bytes']} bytes, "
                            f"reason={truncation_info['reason']}. "
                            f"This is a Kiro API limitation. "
                            f"{'Model will be notified automatically about truncation.' if TRUNCATION_RECOVERY else 'Set TRUNCATION_RECOVERY=true in .env to auto-notify model about truncation.'}"
                        )
                    else:
                        # Regular JSON parse error
                        logger.warning(f"Failed to parse tool '{tool_name}' arguments: {e}. Raw: {args[:200]}")
                    
                    self.current_tool_call['function']['arguments'] = "{}"
            else:
                # Empty string - use empty object
                # This is normal behavior for duplicate tool calls from Kiro
                logger.debug(f"Tool '{tool_name}' has empty arguments string (will be deduplicated)")
                self.current_tool_call['function']['arguments'] = "{}"
        elif isinstance(args, dict):
            # If already an object - serialize to string
            self.current_tool_call['function']['arguments'] = json.dumps(args)
            logger.debug(f"Tool '{tool_name}' arguments already dict with keys: {list(args.keys())}")
        else:
            # Unknown type - empty object
            logger.warning(f"Tool '{tool_name}' has unexpected arguments type: {type(args)}")
            self.current_tool_call['function']['arguments'] = "{}"
        
        self.tool_calls.append(self.current_tool_call)
        self.current_tool_call = None
    
    def _diagnose_json_truncation(self, json_str: str) -> Dict[str, Any]:
        """
        Analyzes a malformed JSON string to determine if it was truncated.
        
        This helps distinguish between upstream issues (Kiro API cutting off
        large tool call arguments) and actual malformed JSON from the model.
        
        Args:
            json_str: The raw JSON string that failed to parse
        
        Returns:
            Dictionary with diagnostic information:
            - is_truncated: True if the JSON appears to be cut off
            - reason: Human-readable explanation of why it's truncated
            - size_bytes: Size of the received data
        """
        size_bytes = len(json_str.encode('utf-8'))
        stripped = json_str.strip()
        
        # Check for obvious truncation signs
        if not stripped:
            return {"is_truncated": False, "reason": "empty string", "size_bytes": size_bytes}
        
        # Count braces and brackets (simplified, doesn't account for strings perfectly)
        open_braces = stripped.count('{')
        close_braces = stripped.count('}')
        open_brackets = stripped.count('[')
        close_brackets = stripped.count(']')
        
        # Check if JSON starts with { but doesn't end with }
        if stripped.startswith('{') and not stripped.endswith('}'):
            missing = open_braces - close_braces
            return {
                "is_truncated": True,
                "reason": f"missing {missing} closing brace(s)",
                "size_bytes": size_bytes
            }
        
        # Check if JSON starts with [ but doesn't end with ]
        if stripped.startswith('[') and not stripped.endswith(']'):
            missing = open_brackets - close_brackets
            return {
                "is_truncated": True,
                "reason": f"missing {missing} closing bracket(s)",
                "size_bytes": size_bytes
            }
        
        # Check for unbalanced braces/brackets
        if open_braces != close_braces:
            diff = open_braces - close_braces
            return {
                "is_truncated": True,
                "reason": f"unbalanced braces ({open_braces} open, {close_braces} close)",
                "size_bytes": size_bytes
            }
        
        if open_brackets != close_brackets:
            diff = open_brackets - close_brackets
            return {
                "is_truncated": True,
                "reason": f"unbalanced brackets ({open_brackets} open, {close_brackets} close)",
                "size_bytes": size_bytes
            }
        
        # Check for unclosed string (ends with backslash or inside quotes)
        # This is a heuristic - count unescaped quotes
        quote_count = 0
        i = 0
        while i < len(stripped):
            if stripped[i] == '\\' and i + 1 < len(stripped):
                i += 2  # Skip escaped character
                continue
            if stripped[i] == '"':
                quote_count += 1
            i += 1
        
        if quote_count % 2 != 0:
            return {
                "is_truncated": True,
                "reason": "unclosed string literal",
                "size_bytes": size_bytes
            }
        
        # Doesn't look truncated, probably just malformed
        return {"is_truncated": False, "reason": "malformed JSON", "size_bytes": size_bytes}
    
    def get_tool_calls(self) -> List[Dict[str, Any]]:
        """
        Returns all collected tool calls.
        
        Finalizes current tool call if not finished.
        Removes duplicates.
        
        Returns:
            List of unique tool calls
        """
        if self.current_tool_call:
            self._finalize_tool_call()
        return deduplicate_tool_calls(self.tool_calls)
    
    def reset(self) -> None:
        """Resets parser state."""
        self.buffer = ""
        self.last_content = None
        self.current_tool_call = None
        self.tool_calls = []
        self._reset_stream_state()