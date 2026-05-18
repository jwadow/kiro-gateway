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
Utility functions for Kiro Gateway.

Contains functions for fingerprint generation, header formatting,
and other common utilities.
"""

import hashlib
import json
import uuid
from typing import TYPE_CHECKING, List, Dict, Any

from loguru import logger

if TYPE_CHECKING:
    from kiro.auth import KiroAuthManager


def get_machine_fingerprint() -> str:
    """
    Generates a unique machine fingerprint based on hostname and username.
    
    Used for User-Agent formation to identify a specific gateway installation.
    
    Returns:
        SHA256 hash of the string "{hostname}-{username}-kiro-gateway"
    """
    try:
        import socket
        import getpass
        
        hostname = socket.gethostname()
        username = getpass.getuser()
        unique_string = f"{hostname}-{username}-kiro-gateway"
        
        return hashlib.sha256(unique_string.encode()).hexdigest()
    except Exception as e:
        logger.warning(f"Failed to get machine fingerprint: {e}")
        return hashlib.sha256(b"default-kiro-gateway").hexdigest()


def get_kiro_headers(auth_manager: "KiroAuthManager", token: str) -> dict:
    """
    Builds headers for Kiro API requests.
    
    Includes all necessary headers for authentication and identification:
    - Authorization with Bearer token
    - User-Agent with fingerprint
    - AWS CodeWhisperer specific headers
    
    Args:
        auth_manager: Authentication manager for obtaining fingerprint
        token: Access token for authorization
    
    Returns:
        Dictionary with headers for HTTP request
    """
    fingerprint = auth_manager.fingerprint
    
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/x-amz-json-1.0",
        "x-amz-target": "AmazonCodeWhispererStreamingService.GenerateAssistantResponse",
        "User-Agent": f"aws-sdk-js/1.0.27 ua/2.1 os/win32#10.0.19044 lang/js md/nodejs#22.21.1 api/codewhispererstreaming#1.0.27 m/E KiroIDE-0.7.45-{fingerprint}",
        "x-amz-user-agent": f"aws-sdk-js/1.0.27 KiroIDE-0.7.45-{fingerprint}",
        "x-amzn-codewhisperer-optout": "true",
        "x-amzn-kiro-agent-mode": "vibe",
        "amz-sdk-invocation-id": str(uuid.uuid4()),
        "amz-sdk-request": "attempt=1; max=3",
    }


def generate_completion_id() -> str:
    """
    Generates a unique ID for chat completion.
    
    Returns:
        ID in format "chatcmpl-{uuid_hex}"
    """
    return f"chatcmpl-{uuid.uuid4().hex}"


def generate_conversation_id(messages: List[Dict[str, Any]] = None) -> str:
    """
    Generates a stable conversation ID based on message history.
    
    For truncation recovery, we need a stable ID that persists across requests
    in the same conversation. This is generated from a hash of key messages.
    
    If no messages provided, falls back to random UUID (for backward compatibility).
    
    Args:
        messages: List of messages in the conversation (optional)
    
    Returns:
        Stable conversation ID (16-char hex) or random UUID
    
    Example:
        >>> messages = [
        ...     {"role": "user", "content": "Hello"},
        ...     {"role": "assistant", "content": "Hi there!"}
        ... ]
        >>> conv_id = generate_conversation_id(messages)
        >>> # Same messages will always produce same ID
    """
    if not messages:
        # Fallback to random UUID for backward compatibility
        return str(uuid.uuid4())
    
    # Use first 3 messages + last message for stability
    # This ensures the ID stays the same as conversation grows,
    # but changes if the conversation history is different
    if len(messages) <= 3:
        key_messages = messages
    else:
        key_messages = messages[:3] + [messages[-1]]
    
    # Extract role and first 100 chars of content for hashing
    # This makes the hash stable even if content has minor formatting differences
    simplified_messages = []
    for msg in key_messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        
        # Handle different content formats (string, list, dict)
        if isinstance(content, str):
            content_str = content[:100]
        elif isinstance(content, list):
            # For Anthropic-style content blocks
            content_str = json.dumps(content, sort_keys=True)[:100]
        else:
            content_str = str(content)[:100]
        
        simplified_messages.append({
            "role": role,
            "content": content_str
        })
    
    # Generate stable hash
    content_json = json.dumps(simplified_messages, sort_keys=True)
    hash_digest = hashlib.sha256(content_json.encode()).hexdigest()
    
    # Return first 16 chars for readability (still 64 bits of entropy)
    return hash_digest[:16]


def generate_tool_call_id() -> str:
    """
    Generates a unique ID for tool call.
    
    Returns:
        ID in format "call_{uuid_hex[:8]}"
    """
    return f"call_{uuid.uuid4().hex[:8]}"