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
Pydantic models for OpenAI Responses API (/v1/responses).

The Responses API is the protocol used by OpenAI Codex CLI. It differs from
Chat Completions in several ways:
- Uses `input` (string or list of typed items) instead of `messages`
- Uses `instructions` instead of a system message
- Tool calls / tool outputs are TOP-LEVEL items, not nested inside a message
- Tools use a flat structure (no nested `function` object)
- Reasoning is configured via a `reasoning` object

Validation is intentionally lenient (extra="allow") because Codex CLI sends
many fields we do not need, and the `input` items are polymorphic. The
polymorphic items are processed as plain dicts in converters_responses.py.
"""

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


# ==================================================================================================
# Reasoning configuration
# ==================================================================================================

class ReasoningConfig(BaseModel):
    """
    Reasoning configuration for the Responses API.

    Attributes:
        effort: Reasoning effort level (minimal, low, medium, high, ...)
        summary: Reasoning summary mode ("auto", "concise", "detailed", None)
    """
    effort: Optional[str] = None
    summary: Optional[str] = None

    model_config = {"extra": "allow"}


# ==================================================================================================
# Tools
# ==================================================================================================

class ResponsesTool(BaseModel):
    """
    Tool definition in Responses API format.

    Unlike Chat Completions, the function fields are FLAT (not nested under a
    `function` key):
        {"type": "function", "name": "shell", "description": "...",
         "parameters": {...}, "strict": false}

    Non-function tool types (web_search, file_search, etc.) are accepted but
    ignored by the converter since Kiro only supports custom function tools.

    Attributes:
        type: Tool type (usually "function")
        name: Function name (flat format)
        description: Function description
        parameters: JSON Schema for function parameters
    """
    type: str = "function"
    name: Optional[str] = None
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None

    model_config = {"extra": "allow"}


# ==================================================================================================
# Request
# ==================================================================================================

class ResponsesRequest(BaseModel):
    """
    Request body for POST /v1/responses.

    Attributes:
        model: Model ID for generation
        input: User input - either a plain string or a list of typed items
               (message / function_call / function_call_output / reasoning / ...)
        instructions: System prompt equivalent
        stream: Use streaming (default False)
        tools: List of available tools (flat format)
        tool_choice: Tool selection strategy
        parallel_tool_calls: Whether parallel tool calls are allowed
        reasoning: Reasoning configuration (effort / summary)
        max_output_tokens: Maximum number of output tokens
        temperature / top_p: Generation parameters
        store: Whether the response is persisted server-side (Codex sends false)
        previous_response_id: Prior response ID (stateful mode - we ignore it)
        include: Extra fields to include (e.g. reasoning.encrypted_content)
    """
    model: str
    input: Union[str, List[Any]]

    instructions: Optional[str] = None
    stream: bool = False

    # Tools
    tools: Optional[List[ResponsesTool]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    parallel_tool_calls: Optional[bool] = None

    # Reasoning
    reasoning: Optional[ReasoningConfig] = None

    # Generation parameters
    max_output_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None

    # Stateless/compat fields (accepted, mostly ignored)
    store: Optional[bool] = None
    previous_response_id: Optional[str] = None
    include: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    user: Optional[str] = None

    model_config = {"extra": "allow"}
