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
Pydantic models for the OpenAI Responses API (POST /v1/responses).

Only the request is modelled strictly. Input items, tools and the response
object are plain dicts: the Responses API has many item/tool variants, and the
translation layer (converters_responses.py) validates the ones we support and
returns actionable 400 errors for the rest.
"""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel


class ResponsesRequest(BaseModel):
    """
    Request body of the OpenAI Responses API.

    Attributes:
        model: Model ID for generation
        input: Plain string (one user message) or list of input items
        instructions: System/developer instructions prepended as a system message
        stream: Use SSE streaming (default False)
        tools: Tool definitions (only type "function" is supported)
        tool_choice: Tool selection strategy ("auto", "none", "required" or object)
        parallel_tool_calls: Allow parallel tool calls
        max_output_tokens: Maximum tokens in the response
        temperature: Sampling temperature
        top_p: Nucleus sampling
        reasoning: Reasoning config, e.g. {"effort": "high"}
        previous_response_id: Server-side conversation state (not supported)
        conversation: Server-side conversation state (not supported)
        store: Whether to store the response (ignored, nothing is stored)
        metadata: Arbitrary metadata echoed back in the response
        text: Output text format config (echoed back, not enforced)
        user: End-user identifier (ignored)
    """
    model: str
    input: Union[str, List[Any]]
    instructions: Optional[str] = None
    stream: bool = False

    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    parallel_tool_calls: Optional[bool] = None

    max_output_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    reasoning: Optional[Dict[str, Any]] = None

    previous_response_id: Optional[str] = None
    conversation: Optional[Union[str, Dict[str, Any]]] = None
    store: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None
    text: Optional[Dict[str, Any]] = None
    user: Optional[str] = None

    model_config = {"extra": "allow"}
