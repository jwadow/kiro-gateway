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

import json
import re
from typing import Any, Dict, List, Optional

from loguru import logger

from kiro.utils import generate_tool_call_id


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
    if start_pos >= len(text) or text[start_pos] != '{':
        return -1
    
    brace_count = 0
    in_string = False
    escape_next = False
    
    for i in range(start_pos, len(text)):
        char = text[i]
        
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\' and in_string:
            escape_next = True
            continue
        
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        
        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return i
    
    return -1


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


# Anthropic/Claude models sometimes emit tool calls as XML inside the text
# channel instead of via the backend's structured tool events. The block looks
# like:
#
#   <function_calls>
#   <invoke name="tool_name">
#   <parameter name="arg">value</parameter>
#   <parameter name="obj">{"k": 1}</parameter>
#   </invoke>
#   </function_calls>
#
# When the backend forwards this verbatim (e.g. when text and a tool call share
# one turn), kg previously had no parser for it, so the raw XML leaked into the
# response content. The functions below recover those calls and strip the XML.
_XML_INVOKE_RE = re.compile(
    r'<invoke\s+name\s*=\s*"([^"]+)"\s*>(.*?)</invoke>',
    re.DOTALL,
)
_XML_PARAM_RE = re.compile(
    r'<parameter\s+name\s*=\s*"([^"]+)"\s*>(.*?)</parameter>',
    re.DOTALL,
)
# Matches a whole <function_calls>...</function_calls> wrapper, or a bare run of
# <invoke> blocks, so we can excise them from the visible content.
_XML_FUNCTION_CALLS_RE = re.compile(
    r'<function_calls>.*?</function_calls>',
    re.DOTALL,
)


def _coerce_xml_param_value(raw: str) -> Any:
    """Best-effort typing of an XML <parameter> body.

    Values arrive as text. If the body is valid JSON (object, array, number,
    bool, null, or quoted string) we decode it so structured args round-trip;
    otherwise we keep the trimmed string. This mirrors how Anthropic clients
    interpret parameter bodies.
    """
    stripped = raw.strip()
    if stripped == "":
        return ""
    # Only attempt JSON decode for values that look like JSON containers or
    # literals — avoids turning a plain word into a parse error path.
    first = stripped[0]
    if first in '{[' or stripped in ("true", "false", "null") or _looks_numeric(stripped):
        try:
            return json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            return stripped
    return stripped


def _looks_numeric(s: str) -> bool:
    """True if the string is a bare int/float literal."""
    if not s:
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


def parse_xml_tool_calls(response_text: str) -> List[Dict[str, Any]]:
    """Parses tool calls in the Anthropic ``<invoke name="...">`` XML format.

    Some models return tool calls as XML embedded in the text channel instead
    of via the backend's structured tool events. This extracts them into the
    OpenAI tool-call shape.

    Args:
        response_text: Model response text (may contain other prose too).

    Returns:
        List of tool calls in OpenAI format.

    Example:
        >>> text = '<invoke name="get_weather"><parameter name="city">London</parameter></invoke>'
        >>> calls = parse_xml_tool_calls(text)
        >>> calls[0]["function"]["name"]
        'get_weather'
    """
    if not response_text or "<invoke" not in response_text:
        return []

    tool_calls: List[Dict[str, Any]] = []
    for invoke_match in _XML_INVOKE_RE.finditer(response_text):
        func_name = invoke_match.group(1).strip()
        body = invoke_match.group(2)

        args: Dict[str, Any] = {}
        for param_match in _XML_PARAM_RE.finditer(body):
            param_name = param_match.group(1).strip()
            args[param_name] = _coerce_xml_param_value(param_match.group(2))

        tool_calls.append({
            "id": generate_tool_call_id(),
            "type": "function",
            "function": {
                "name": func_name,
                "arguments": json.dumps(args),
            },
        })

    return tool_calls


def strip_xml_tool_calls(response_text: str) -> str:
    """Removes ``<function_calls>``/``<invoke>`` XML blocks from content.

    Used after :func:`parse_xml_tool_calls` so the recovered XML does not leak
    into the visible assistant text. Strips the ``<function_calls>`` wrapper
    when present, then any stray bare ``<invoke>...</invoke>`` blocks, and
    tidies the surrounding whitespace.
    """
    if not response_text or "<invoke" not in response_text:
        return response_text
    cleaned = _XML_FUNCTION_CALLS_RE.sub("", response_text)
    cleaned = _XML_INVOKE_RE.sub("", cleaned)
    # Drop now-empty wrapper tags left dangling and collapse the blank gap.
    cleaned = cleaned.replace("<function_calls>", "").replace("</function_calls>", "")
    return cleaned.strip()


# Any of these substrings, appearing at the tail of the streamed-so-far content,
# means an XML tool-call block MIGHT be starting and we must stop emitting until
# we know for sure. Kept short so we only ever hold back a tiny suffix.
_XML_TOOL_MARKERS = ("<function_calls>", "<invoke")
# Longest prefix of a marker we might need to hold while waiting for more chunks.
_XML_MAX_MARKER_LEN = max(len(m) for m in _XML_TOOL_MARKERS)


def _tail_could_start_marker(buffer: str) -> bool:
    """True if ``buffer`` ends with a partial prefix of an XML tool marker.

    Lets the streaming gate hold back a short suffix like ``"<inv"`` that might
    grow into ``"<invoke"`` on the next chunk, without stalling on ordinary
    ``<`` characters in prose/code.
    """
    if not buffer:
        return False
    # Check the trailing window only.
    window = buffer[-_XML_MAX_MARKER_LEN:]
    for marker in _XML_TOOL_MARKERS:
        # Does any non-empty prefix of `marker` occur as a suffix of `window`?
        for plen in range(min(len(marker), len(window)), 0, -1):
            if window.endswith(marker[:plen]):
                return True
    return False


class StreamingXmlToolGate:
    """Incremental gate that keeps XML tool-call blocks out of streamed content.

    Anthropic models sometimes emit tool calls as ``<function_calls>``/
    ``<invoke>`` XML on the text channel. In a streaming response those chunks
    would otherwise reach the client verbatim before the post-hoc parser runs.

    Feed each content delta through :meth:`feed`; it returns the text that is
    safe to emit right now (everything up to a potential tool-call block),
    buffering any suspected XML. Call :meth:`flush` at end-of-stream to recover
    tool calls from the withheld buffer and get any remaining safe text.

    Usage:
        gate = StreamingXmlToolGate()
        safe = gate.feed(delta)            # emit `safe` if non-empty
        ...
        leftover, tool_calls = gate.flush()  # emit leftover, add tool_calls
    """

    def __init__(self) -> None:
        self._buffer = ""          # withheld text once a marker is seen
        self._holding = False      # currently buffering a suspected XML block
        self._pending = ""         # tiny tail that might be a partial marker

    def feed(self, chunk: str) -> str:
        """Consume a content delta, return text safe to emit immediately."""
        if not chunk:
            return ""

        if self._holding:
            # Already inside a suspected XML block — keep swallowing until the
            # block closes. If it closes and no more markers follow, whatever
            # trails the close is safe to emit.
            self._buffer += chunk
            return self._maybe_release_after_close()

        # Not holding yet. Combine any pending partial-marker tail with the new
        # chunk and look for a marker.
        combined = self._pending + chunk
        self._pending = ""

        idx = self._first_marker_index(combined)
        if idx is None:
            # No full marker. Hold back only a possible partial-marker suffix.
            if _tail_could_start_marker(combined):
                # Find how much to hold: the longest suffix that is a marker prefix.
                hold = self._partial_marker_suffix_len(combined)
                self._pending = combined[len(combined) - hold:]
                return combined[: len(combined) - hold]
            return combined

        # Found a marker — emit everything before it, start holding from there.
        safe = combined[:idx]
        self._buffer = combined[idx:]
        self._holding = True
        return safe + self._maybe_release_after_close()

    def _first_marker_index(self, text: str) -> Optional[int]:
        positions = [text.find(m) for m in _XML_TOOL_MARKERS]
        positions = [p for p in positions if p != -1]
        return min(positions) if positions else None

    def _partial_marker_suffix_len(self, text: str) -> int:
        window = text[-_XML_MAX_MARKER_LEN:]
        best = 0
        for marker in _XML_TOOL_MARKERS:
            for plen in range(min(len(marker), len(window)), 0, -1):
                if window.endswith(marker[:plen]):
                    best = max(best, plen)
                    break
        return best

    def _maybe_release_after_close(self) -> str:
        """If the buffered block contains a closed tool call with trailing
        non-XML text, we still keep holding (more calls may follow). We only
        release trailing text at flush(). This keeps the logic simple and
        correct: once holding, everything stays buffered until flush."""
        return ""

    def flush(self) -> tuple[str, List[Dict[str, Any]]]:
        """End of stream: parse tool calls from the buffer, return leftover text.

        Returns:
            (leftover_text, tool_calls) — leftover_text is any buffered content
            with XML blocks stripped (normally empty); tool_calls are recovered
            from the buffered XML.
        """
        buffered = self._buffer + self._pending
        self._buffer = ""
        self._pending = ""
        self._holding = False
        if not buffered:
            return "", []
        tool_calls = parse_xml_tool_calls(buffered)
        leftover = strip_xml_tool_calls(buffered) if tool_calls else buffered
        return leftover, tool_calls


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
        ('{"text":', 'reasoning'),            # reasoningContentEvent (native extended thinking)
        ('{"signature":', 'reasoning_sig'),   # reasoningContentEvent signature (metadata, ignored)
        ('{"name":', 'tool_start'),
        ('{"input":', 'tool_input'),
        ('{"stop":', 'tool_stop'),
        ('{"followupPrompt":', 'followup'),
        ('{"usage":', 'usage'),
        ('{"contextUsagePercentage":', 'context_usage'),
    ]
    
    def __init__(self):
        """Initializes the parser."""
        self.buffer = ""
        self.last_content: Optional[str] = None  # For deduplicating repeating content
        self.current_tool_call: Optional[Dict[str, Any]] = None
        self.tool_calls: List[Dict[str, Any]] = []
        self.native_thinking_started = False
    
    def feed(self, chunk: bytes) -> List[Dict[str, Any]]:
        """
        Adds chunk to buffer and returns parsed events.
        
        Args:
            chunk: Bytes of data from stream
        
        Returns:
            List of events in {"type": str, "data": Any} format
        """
        try:
            self.buffer += chunk.decode('utf-8', errors='ignore')
        except Exception:
            return []
        
        events = []
        
        while True:
            # Find nearest pattern
            earliest_pos = -1
            earliest_type = None
            
            for pattern, event_type in self.EVENT_PATTERNS:
                pos = self.buffer.find(pattern)
                if pos != -1 and (earliest_pos == -1 or pos < earliest_pos):
                    earliest_pos = pos
                    earliest_type = event_type
            
            if earliest_pos == -1:
                break
            
            # Find JSON end
            json_end = find_matching_brace(self.buffer, earliest_pos)
            if json_end == -1:
                # JSON not complete, wait for more data
                break
            
            json_str = self.buffer[earliest_pos:json_end + 1]
            self.buffer = self.buffer[json_end + 1:]
            
            try:
                data = json.loads(json_str)
                event = self._process_event(data, earliest_type)
                if event:
                    events.append(event)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse JSON: {json_str[:100]}")
        
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
        elif event_type == 'reasoning':
            return self._process_reasoning_event(data)
        elif event_type == 'reasoning_sig':
            # Signature is cryptographic metadata for native thinking blocks.
            # We don't surface it to clients; just swallow it.
            self.native_thinking_started = False
            return None
        elif event_type == 'thinking':
            is_first = not self.native_thinking_started
            self.native_thinking_started = True
            return {"type": "thinking", "data": data.get('text', ''), "is_first": is_first, "is_native": True}
        elif event_type == 'thinking_signature':
            self.native_thinking_started = False
            return {"type": "thinking_signature", "data": data.get('signature', '')}
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
    
    def _process_reasoning_event(self, data: dict) -> Optional[Dict[str, Any]]:
        """
        Processes a native reasoningContentEvent (extended thinking).

        The Kiro backend emits the model's native reasoning as a separate
        event channel (reasoningContentEvent) with incremental {"text": ...}
        deltas, followed by a {"signature": ...} metadata event. This is the
        real model thinking, distinct from kg's legacy fake-reasoning prompt
        injection. We surface it as a dedicated 'reasoning' event so the
        streaming layer can map it to reasoning_content (OpenAI) or a native
        thinking block (Anthropic).
        """
        text = data.get('text', '')
        if not text:
            return None
        is_first = not self.native_thinking_started
        self.native_thinking_started = True
        return {
            "type": "reasoning",
            "data": text,
            "is_first": is_first,
            "is_native": True,
        }
    
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
        
        logger.debug(f"Finalizing tool call '{tool_name}' with raw arguments: {repr(args)[:200]}")
        
        if isinstance(args, str):
            if args.strip():
                try:
                    parsed = json.loads(args)
                    # Ensure result is a JSON string
                    self.current_tool_call['function']['arguments'] = json.dumps(parsed)
                    logger.debug(f"Tool '{tool_name}' arguments parsed successfully: {list(parsed.keys()) if isinstance(parsed, dict) else type(parsed)}")
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
        self.native_thinking_started = False