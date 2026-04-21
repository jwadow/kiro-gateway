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
Module for fast token counting.

Uses tiktoken (OpenAI's Rust library) for approximate
token counting. The cl100k_base encoding is close to Claude tokenization.

Note: This is an approximate count, as the exact Claude tokenizer
is not public. Anthropic does not publish their tokenizer,
so tiktoken with a correction coefficient is used.

The correction coefficient CLAUDE_CORRECTION_FACTOR = 1.15 is based on
empirical observations: Claude tokenizes text approximately 15%
more than GPT-4 (cl100k_base). This is due to differences in BPE vocabularies.
"""

import json
from typing import List, Dict, Any, Optional
from loguru import logger

# Lazy loading of tiktoken to speed up import
_encoding = None

# Correction coefficient for Claude models
# Claude tokenizes text approximately 15% more than GPT-4 (cl100k_base)
# This is an empirical value based on comparison with context_usage from API
CLAUDE_CORRECTION_FACTOR = 1.15


def _get_encoding():
    """
    Lazy initialization of tokenizer.
    
    Uses cl100k_base - encoding for GPT-4/ChatGPT,
    which is close enough to Claude tokenization.
    
    Returns:
        tiktoken.Encoding or None if tiktoken is unavailable
    """
    global _encoding
    if _encoding is None:
        try:
            import tiktoken
            _encoding = tiktoken.get_encoding("cl100k_base")
            logger.debug("[Tokenizer] Initialized tiktoken with cl100k_base encoding")
        except ImportError:
            logger.warning(
                "[Tokenizer] tiktoken not installed. "
                "Token counting will use fallback estimation. "
                "Install with: pip install tiktoken"
            )
            _encoding = False  # Marker that import failed
        except Exception as e:
            logger.error(f"[Tokenizer] Failed to initialize tiktoken: {e}")
            _encoding = False
    return _encoding if _encoding else None


def count_tokens(text: str, apply_claude_correction: bool = True) -> int:
    """
    Counts the number of tokens in text.
    
    Args:
        text: Text to count tokens for
        apply_claude_correction: Apply correction coefficient for Claude (default True)
    
    Returns:
        Number of tokens (approximate, with Claude correction)
    """
    if not text:
        return 0
    
    encoding = _get_encoding()
    if encoding:
        try:
            base_tokens = len(encoding.encode(text))
            if apply_claude_correction:
                return int(base_tokens * CLAUDE_CORRECTION_FACTOR)
            return base_tokens
        except Exception as e:
            logger.warning(f"[Tokenizer] Error encoding text: {e}")
    
    # Fallback: rough estimate ~4 characters per token for English,
    # ~2-3 characters for other languages (taking average ~3.5)
    # For Claude we add correction
    base_estimate = len(text) // 4 + 1
    if apply_claude_correction:
        return int(base_estimate * CLAUDE_CORRECTION_FACTOR)
    return base_estimate


def count_message_tokens(messages: List[Dict[str, Any]], apply_claude_correction: bool = True) -> int:
    """
    Counts tokens in a list of chat messages.
    
    Accounts for OpenAI/Claude message structure:
    - role: ~1 token
    - content: text tokens
    - Service tokens between messages: ~3-4 tokens
    
    Args:
        messages: List of messages in OpenAI format
        apply_claude_correction: Apply correction coefficient for Claude
    
    Returns:
        Approximate number of tokens (with Claude correction)
    """
    if not messages:
        return 0
    
    total_tokens = 0
    
    for message in messages:
        # Base tokens per message (role, delimiters)
        total_tokens += 4  # ~4 tokens for service information
        
        # Role tokens (without correction, these are short strings)
        role = message.get("role", "")
        total_tokens += count_tokens(role, apply_claude_correction=False)
        
        # Content tokens
        content = message.get("content")
        if content:
            if isinstance(content, str):
                total_tokens += count_tokens(content, apply_claude_correction=False)
            elif isinstance(content, list):
                # Support OpenAI/Anthropic multi-type content blocks
                for item in content:
                    if isinstance(item, dict):
                        item_type = item.get("type")
                        if item_type == "text":
                            total_tokens += count_tokens(item.get("text", ""), apply_claude_correction=False)
                        elif item_type in {"image_url", "image"}:
                            # Estimate image as fixed cost to avoid significant undercount
                            total_tokens += 100
                        elif item_type == "tool_use":
                            total_tokens += count_tokens(item.get("id", ""), apply_claude_correction=False)
                            total_tokens += count_tokens(item.get("name", ""), apply_claude_correction=False)
                            tool_input_str = json.dumps(item.get("input", {}), ensure_ascii=False)
                            total_tokens += count_tokens(tool_input_str, apply_claude_correction=False)
                        elif item_type == "tool_result":
                            total_tokens += count_tokens(item.get("tool_use_id", ""), apply_claude_correction=False)
                            if item.get("is_error") is not None:
                                total_tokens += count_tokens(str(item.get("is_error")), apply_claude_correction=False)

                            tool_result_content = item.get("content")
                            if isinstance(tool_result_content, str):
                                total_tokens += count_tokens(tool_result_content, apply_claude_correction=False)
                            elif isinstance(tool_result_content, list):
                                for result_block in tool_result_content:
                                    if isinstance(result_block, dict):
                                        result_type = result_block.get("type")
                                        if result_type == "text":
                                            total_tokens += count_tokens(
                                                result_block.get("text", ""),
                                                apply_claude_correction=False
                                            )
                                        elif result_type in {"image_url", "image"}:
                                            total_tokens += 100
                                    else:
                                        total_tokens += count_tokens(str(result_block), apply_claude_correction=False)
                            elif tool_result_content is not None:
                                total_tokens += count_tokens(str(tool_result_content), apply_claude_correction=False)
                        else:
                            # Unknown block fallback: estimate via JSON to avoid undercount
                            total_tokens += count_tokens(
                                json.dumps(item, ensure_ascii=False),
                                apply_claude_correction=False
                            )
                    else:
                        total_tokens += count_tokens(str(item), apply_claude_correction=False)
        
        # tool_calls tokens (if present)
        tool_calls = message.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                total_tokens += 4  # Service tokens
                func = tc.get("function", {})
                total_tokens += count_tokens(func.get("name", ""), apply_claude_correction=False)
                total_tokens += count_tokens(func.get("arguments", ""), apply_claude_correction=False)
        
        # tool_call_id tokens (for tool responses)
        if message.get("tool_call_id"):
            total_tokens += count_tokens(message["tool_call_id"], apply_claude_correction=False)
    
    # Final service tokens
    total_tokens += 3
    
    # Apply correction to total count
    if apply_claude_correction:
        return int(total_tokens * CLAUDE_CORRECTION_FACTOR)
    return total_tokens


def count_tools_tokens(tools: Optional[List[Dict[str, Any]]], apply_claude_correction: bool = True) -> int:
    """
    Counts tokens in tool definitions.
    
    Args:
        tools: List of tools in OpenAI format
        apply_claude_correction: Apply correction coefficient for Claude
    
    Returns:
        Approximate number of tokens (with Claude correction)
    """
    if not tools:
        return 0
    
    total_tokens = 0
    
    for tool in tools:
        total_tokens += 4  # Service tokens

        # Support both OpenAI standard tools and Anthropic/OpenAI flat tools
        if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
            tool_payload = tool.get("function", {})
        else:
            tool_payload = tool

        # Name / description
        total_tokens += count_tokens(tool_payload.get("name", ""), apply_claude_correction=False)
        total_tokens += count_tokens(tool_payload.get("description", ""), apply_claude_correction=False)

        # JSON schema（Anthropic: input_schema, OpenAI: parameters）
        params = tool_payload.get("input_schema")
        if params is None:
            params = tool_payload.get("parameters")
        if params is not None:
            params_str = json.dumps(params, ensure_ascii=False)
            total_tokens += count_tokens(params_str, apply_claude_correction=False)
    
    # Apply correction to total count
    if apply_claude_correction:
        return int(total_tokens * CLAUDE_CORRECTION_FACTOR)
    return total_tokens


def count_system_tokens(system_prompt: Optional[Any], apply_claude_correction: bool = True) -> int:
    """
    Counts tokens in system prompt.

    Supports both plain string and Anthropic block list.

    Args:
        system_prompt: System prompt (str / list of blocks)
        apply_claude_correction: Apply correction coefficient for Claude

    Returns:
        Approximate number of tokens
    """
    if not system_prompt:
        return 0

    total_tokens = 0

    if isinstance(system_prompt, str):
        total_tokens += count_tokens(system_prompt, apply_claude_correction=False)
    elif isinstance(system_prompt, list):
        for block in system_prompt:
            if isinstance(block, dict):
                # Count text content, support prompt caching structure
                total_tokens += count_tokens(block.get("text", ""), apply_claude_correction=False)
                if block.get("cache_control") is not None:
                    total_tokens += count_tokens(
                        json.dumps(block.get("cache_control"), ensure_ascii=False),
                        apply_claude_correction=False
                    )
            else:
                total_tokens += count_tokens(str(block), apply_claude_correction=False)
    else:
        total_tokens += count_tokens(str(system_prompt), apply_claude_correction=False)

    if apply_claude_correction:
        return int(total_tokens * CLAUDE_CORRECTION_FACTOR)
    return total_tokens


def estimate_request_tokens(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    system_prompt: Optional[Any] = None,
    apply_claude_correction: bool = True
) -> Dict[str, int]:
    """
    Estimates total number of tokens in request.
    
    Args:
        messages: List of messages
        tools: List of tools (optional)
        system_prompt: System prompt (optional, string or Anthropic content blocks)
        apply_claude_correction: Apply correction coefficient for Claude
    
    Returns:
        Dictionary with token breakdown:
        - messages_tokens: message tokens
        - tools_tokens: tool tokens
        - system_tokens: system prompt tokens
        - total_tokens: total count
    """
    messages_tokens = count_message_tokens(messages, apply_claude_correction=apply_claude_correction)
    tools_tokens = count_tools_tokens(tools, apply_claude_correction=apply_claude_correction)
    system_tokens = count_system_tokens(system_prompt, apply_claude_correction=apply_claude_correction)
    
    return {
        "messages_tokens": messages_tokens,
        "tools_tokens": tools_tokens,
        "system_tokens": system_tokens,
        "total_tokens": messages_tokens + tools_tokens + system_tokens
    }
