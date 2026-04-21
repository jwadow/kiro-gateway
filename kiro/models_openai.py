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
Pydantic models for OpenAI-compatible API.

Defines data schemas for requests and responses,
providing validation and serialization.
"""

import time
from typing import Any, Dict, List, Literal, Optional, Union
from typing_extensions import Annotated
from pydantic import BaseModel, Field


# ==================================================================================================
# Models for /v1/models endpoint
# ==================================================================================================

class OpenAIModel(BaseModel):
    """
    Data model for describing an AI model in OpenAI format.
    
    Used in the /v1/models endpoint response.
    """
    id: str
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "anthropic"
    description: Optional[str] = None


class ModelList(BaseModel):
    """
    List of models in OpenAI format.
    
    Response of GET /v1/models endpoint.
    """
    object: str = "list"
    data: List[OpenAIModel]


# ==================================================================================================
# Models for /v1/chat/completions endpoint
# ==================================================================================================

class ChatMessage(BaseModel):
    """
    Chat message in OpenAI format.
    
    Supports various roles (user, assistant, system, tool)
    and various content formats (string, list, object).
    
    Attributes:
        role: Sender role (user, assistant, system, tool)
        content: Message content (can be string, list, or None)
        name: Optional sender name
        tool_calls: List of tool calls (for assistant)
        tool_call_id: Tool call ID (for tool)
    """
    role: str
    content: Optional[Union[str, List[Any], Any]] = None
    name: Optional[str] = None
    tool_calls: Optional[List[Any]] = None
    tool_call_id: Optional[str] = None
    
    model_config = {"extra": "allow"}


class ToolFunction(BaseModel):
    """
    Tool function description.
    
    Attributes:
        name: Function name
        description: Function description
        parameters: JSON Schema of function parameters
    """
    name: str
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class Tool(BaseModel):
    """
    Tool in OpenAI format.
    
    Supports two formats:
    1. Standard OpenAI format: {"type": "function", "function": {...}}
    2. Flat format (Cursor-style): {"name": "...", "description": "...", "input_schema": {...}}
    
    Attributes:
        type: Tool type (usually "function")
        function: Function description (standard format)
        name: Function name (flat format)
        description: Function description (flat format)
        input_schema: Function parameters (flat format)
    """
    # Standard OpenAI format fields
    type: str = "function"
    function: Optional[ToolFunction] = None
    
    # Flat format fields (Cursor-style)
    name: Optional[str] = None
    description: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    
    model_config = {"extra": "allow"}


class ChatCompletionRequest(BaseModel):
    """
    Request for response generation in OpenAI Chat Completions API format.
    
    Supports all standard OpenAI API fields, including:
    - Basic parameters (model, messages, stream)
    - Generation parameters (temperature, top_p, max_tokens)
    - Tools (function calling)
    - Additional parameters (ignored but accepted for compatibility)
    
    Attributes:
        model: Model ID for generation
        messages: List of chat messages
        stream: Use streaming (default False)
        temperature: Generation temperature (0-2)
        top_p: Top-p sampling
        n: Number of response variants
        max_tokens: Maximum number of tokens in response
        max_completion_tokens: Alternative field for max_tokens
        stop: Stop sequences
        presence_penalty: Penalty for topic repetition
        frequency_penalty: Penalty for word repetition
        tools: List of available tools
        tool_choice: Tool selection strategy
    """
    model: str
    messages: Annotated[List[ChatMessage], Field(min_length=1)]
    stream: bool = False
    
    # Generation parameters
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    n: Optional[int] = 1
    max_tokens: Optional[int] = None
    max_completion_tokens: Optional[int] = None
    stop: Optional[Union[str, List[str]]] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    
    # Reasoning (OpenAI reasoning models)
    # Supports all official reasoning_effort levels from OpenAI API
    reasoning_effort: Optional[Literal["none", "minimal", "low", "medium", "high", "xhigh"]] = None
    
    # Tools (function calling)
    tools: Optional[List[Tool]] = None
    tool_choice: Optional[Union[str, Dict]] = None
    
    # Compatibility fields (ignored)
    stream_options: Optional[Dict[str, Any]] = None
    logit_bias: Optional[Dict[str, float]] = None
    logprobs: Optional[bool] = None
    top_logprobs: Optional[int] = None
    user: Optional[str] = None
    seed: Optional[int] = None
    parallel_tool_calls: Optional[bool] = None
    
    model_config = {"extra": "allow"}


# ==================================================================================================
# Models for responses
# ==================================================================================================

class ChatCompletionChoice(BaseModel):
    """
    Single response variant in Chat Completion.
    
    Attributes:
        index: Variant index
        message: Response message
        finish_reason: Completion reason (stop, tool_calls, length)
    """
    index: int = 0
    message: Dict[str, Any]
    finish_reason: Optional[str] = None


class ChatCompletionUsage(BaseModel):
    """
    Token usage information.
    
    Attributes:
        prompt_tokens: Number of tokens in request
        completion_tokens: Number of tokens in response
        total_tokens: Total number of tokens
        credits_used: Credits used (Kiro-specific)
    """
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    credits_used: Optional[float] = None


class ChatCompletionResponse(BaseModel):
    """
    Full Chat Completion response (non-streaming).
    
    Attributes:
        id: Unique response ID
        object: Object type ("chat.completion")
        created: Creation timestamp
        model: Model used
        choices: List of response variants
        usage: Token usage information
    """
    id: str
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionChoice]
    usage: ChatCompletionUsage


class ChatCompletionChunkDelta(BaseModel):
    """
    Delta of changes in streaming chunk.
    
    Attributes:
        role: Role (only in first chunk)
        content: New content
        tool_calls: New tool calls
    """
    role: Optional[str] = None
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class ChatCompletionChunkChoice(BaseModel):
    """
    Single variant in streaming chunk.
    
    Attributes:
        index: Variant index
        delta: Delta of changes
        finish_reason: Completion reason (only in last chunk)
    """
    index: int = 0
    delta: ChatCompletionChunkDelta
    finish_reason: Optional[str] = None


class ChatCompletionChunk(BaseModel):
    """
    Streaming chunk in OpenAI format.
    
    Attributes:
        id: Unique response ID
        object: Object type ("chat.completion.chunk")
        created: Creation timestamp
        model: Model used
        choices: List of variants
        usage: Usage information (only in last chunk)
    """
    id: str
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionChunkChoice]
    usage: Optional[ChatCompletionUsage] = None