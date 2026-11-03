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
FastAPI route for the OpenAI Responses API (POST /v1/responses).

The endpoint is an adapter over /v1/chat/completions: the request is translated
to a ChatCompletionRequest and handed to the same chat_completions handler, so
account failover, truncation recovery, web search emulation, retries and
streaming behave identically. The chat result is then translated back into the
Responses format (JSON object or Responses SSE events).
"""

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger

from kiro.converters_responses import (
    ResponsesConversionError,
    chat_completion_to_response,
    responses_request_to_chat,
    stream_chat_to_responses,
)
from kiro.models_responses import ResponsesRequest
from kiro.routes_openai import chat_completions, verify_api_key


# OpenAI error "type" values by HTTP status
ERROR_TYPES: Dict[int, str] = {
    400: "invalid_request_error",
    401: "authentication_error",
    403: "permission_error",
    404: "not_found_error",
    429: "rate_limit_error",
}


router = APIRouter()


def openai_error_response(
    status_code: int,
    message: str,
    param: Optional[str] = None,
    code: Optional[Any] = None,
    error_type: Optional[str] = None,
) -> JSONResponse:
    """
    Build an error response in OpenAI shape.

    Args:
        status_code: HTTP status
        message: User-facing error message
        param: Offending request parameter
        code: Error code
        error_type: OpenAI error type (derived from status when omitted)

    Returns:
        JSONResponse {"error": {"message", "type", "param", "code"}}
    """
    if error_type is None:
        error_type = ERROR_TYPES.get(status_code, "api_error" if status_code >= 500 else "invalid_request_error")
    return JSONResponse(
        status_code=status_code,
        content={"error": {"message": message, "type": error_type, "param": param, "code": code}},
    )


def _normalize_chat_error(response: JSONResponse) -> JSONResponse:
    """
    Ensure an error JSONResponse from chat_completions has the full OpenAI error shape.

    Args:
        response: Non-200 JSONResponse from the chat pipeline

    Returns:
        JSONResponse with "message", "type", "param" and "code"
    """
    try:
        body = json.loads(response.body)
        error = body.get("error") if isinstance(body, dict) else None
    except (json.JSONDecodeError, TypeError, AttributeError):
        error = None
    if not isinstance(error, dict):
        return openai_error_response(response.status_code, "Upstream request failed.")
    return openai_error_response(
        response.status_code,
        str(error.get("message") or "Upstream request failed."),
        param=error.get("param"),
        code=error.get("code"),
        error_type=error.get("type"),
    )


@router.post("/v1/responses", dependencies=[Depends(verify_api_key)])
async def create_response(request: Request, request_data: ResponsesRequest):
    """
    Responses endpoint - compatible with the OpenAI Responses API.

    Stateless: previous_response_id and conversation are rejected with 400.

    Args:
        request: FastAPI Request (app.state is used by the chat pipeline)
        request_data: Responses API request

    Returns:
        JSONResponse with a response object, Responses SSE StreamingResponse,
        or an OpenAI-shaped error JSONResponse
    """
    logger.info(f"Request to /v1/responses (model={request_data.model}, stream={request_data.stream})")

    try:
        chat_request = responses_request_to_chat(request_data)
    except ResponsesConversionError as e:
        logger.warning(f"HTTP 400 - POST /v1/responses - {e.message}")
        return openai_error_response(400, e.message, param=e.param)

    try:
        chat_result = await chat_completions(request, chat_request)
    except HTTPException as e:
        logger.warning(f"HTTP {e.status_code} - POST /v1/responses - {str(e.detail)[:100]}")
        return openai_error_response(e.status_code, str(e.detail))

    if isinstance(chat_result, StreamingResponse):
        return StreamingResponse(
            stream_chat_to_responses(chat_result.body_iterator, request_data),
            media_type="text/event-stream",
        )

    if chat_result.status_code != 200:
        return _normalize_chat_error(chat_result)

    try:
        chat_body = json.loads(chat_result.body)
    except (json.JSONDecodeError, TypeError) as e:
        logger.error(f"Chat pipeline returned unparseable body: {e}")
        return openai_error_response(500, "Internal Server Error: invalid upstream response.")

    response_object = chat_completion_to_response(chat_body, request_data)
    logger.info(f"HTTP 200 - POST /v1/responses (non-streaming) - {response_object['status']}")
    return JSONResponse(content=response_object)
