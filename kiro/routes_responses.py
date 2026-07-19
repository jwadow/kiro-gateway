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
FastAPI route for the OpenAI Responses API (/v1/responses).

This is the endpoint used by OpenAI Codex CLI. It mirrors the account-system
failover / legacy-mode logic of routes_openai.py but produces Responses API
output (a `response` object for non-streaming, or the Responses SSE event
sequence for streaming).
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger

from kiro.profile_arn import profile_arn_for_payload
from kiro.models_responses import ResponsesRequest
from kiro.converters_responses import (
    build_kiro_payload,
    convert_responses_input_to_unified,
    convert_responses_tools_to_unified,
)
from kiro.converters_core import extract_text_content
from kiro.streaming_responses import (
    stream_responses_with_first_token_retry,
    collect_responses_response,
)
from kiro.http_client import KiroHttpClient
from kiro.utils import generate_conversation_id

# Reuse the OpenAI endpoint's API-key verification (same Bearer scheme)
from kiro.routes_openai import verify_api_key

try:
    from kiro.debug_logger import debug_logger
except ImportError:
    debug_logger = None


router = APIRouter()


def _build_tokenizer_inputs(request_data: ResponsesRequest):
    """
    Build simple message/tool dicts for fallback (tiktoken) token counting.

    Kiro's context_usage percentage is the primary token source; this is only
    used when Kiro returns no usage data.
    """
    _, unified_messages = convert_responses_input_to_unified(request_data)
    messages_for_tokenizer = [
        {"role": m.role, "content": extract_text_content(m.content)}
        for m in unified_messages
    ]

    tools_for_tokenizer = None
    unified_tools = convert_responses_tools_to_unified(request_data.tools)
    if unified_tools:
        tools_for_tokenizer = [
            {"name": t.name, "description": t.description or "", "parameters": t.input_schema or {}}
            for t in unified_tools
        ]

    return messages_for_tokenizer, tools_for_tokenizer


def _error_response(status_code: int, message: str) -> JSONResponse:
    """Build a Responses-style error JSON response."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"message": message, "type": "kiro_api_error", "code": status_code}},
    )


@router.post("/v1/responses", dependencies=[Depends(verify_api_key)])
async def responses(request: Request, request_data: ResponsesRequest):
    """
    Responses API endpoint - compatible with OpenAI Codex CLI.

    Accepts requests in Responses API format, translates them to Kiro, and
    returns either a `response` object (non-streaming) or the Responses SSE
    event sequence (streaming).
    """
    logger.info(f"Request to /v1/responses (model={request_data.model}, stream={request_data.stream})")

    messages_for_tokenizer, tools_for_tokenizer = _build_tokenizer_inputs(request_data)

    # ==============================================================================
    # ACCOUNT SYSTEM ENABLED: Failover Loop
    # ==============================================================================
    if request.app.state.account_system:
        from kiro.account_errors import classify_error, ErrorType

        account_manager = request.app.state.account_manager
        all_accounts = list(account_manager._accounts.keys())
        MAX_ATTEMPTS = len(all_accounts) * 2

        last_error_message = None
        last_error_status = None
        tried_accounts = set()

        for attempt in range(MAX_ATTEMPTS):
            account = await account_manager.get_next_account(
                request_data.model, exclude_accounts=tried_accounts
            )

            if account is None:
                if len(all_accounts) == 1:
                    raise HTTPException(
                        status_code=last_error_status or 503,
                        detail=last_error_message or "Account unavailable",
                    )
                detail = "No available accounts for this model."
                if last_error_message:
                    detail += f" Error from last account: {last_error_message}"
                raise HTTPException(status_code=503, detail=detail)

            tried_accounts.add(account.id)

            auth_manager = account.auth_manager
            model_cache = account.model_cache

            conversation_id = generate_conversation_id()
            profile_arn = profile_arn_for_payload(auth_manager)

            try:
                kiro_payload = build_kiro_payload(
                    request_data, conversation_id, profile_arn
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            try:
                kiro_request_body = json.dumps(kiro_payload, ensure_ascii=False, indent=2).encode("utf-8")
                if debug_logger:
                    debug_logger.log_kiro_request_body(kiro_request_body)
            except Exception as e:
                logger.warning(f"Failed to log Kiro request: {e}")

            url = f"{auth_manager.api_host}/generateAssistantResponse"
            logger.debug(f"Kiro API URL: {url} (account: {account.id})")

            if request_data.stream:
                http_client = KiroHttpClient(auth_manager, shared_client=None)
            else:
                shared_client = request.app.state.http_client
                http_client = KiroHttpClient(auth_manager, shared_client=shared_client)

            try:
                response = await http_client.request_with_retry("POST", url, kiro_payload, stream=True)

                if response.status_code == 200:
                    await account_manager.report_success(account.id, request_data.model)

                    if request_data.stream:
                        return _make_streaming_response(
                            http_client, url, kiro_payload, request_data,
                            model_cache, auth_manager, response,
                            messages_for_tokenizer, tools_for_tokenizer,
                        )

                    responses_obj = await collect_responses_response(
                        http_client.client, response, request_data.model,
                        model_cache, auth_manager,
                        request_messages=messages_for_tokenizer,
                        request_tools=tools_for_tokenizer,
                    )
                    await http_client.close()
                    logger.info("HTTP 200 - POST /v1/responses (non-streaming) - completed")
                    if debug_logger:
                        debug_logger.discard_buffers()
                    return JSONResponse(content=responses_obj)

                # --- error path ---
                try:
                    error_content = await response.aread()
                except Exception:
                    error_content = b"Unknown error"
                await http_client.close()
                error_text = error_content.decode("utf-8", errors="replace")

                error_reason = None
                try:
                    error_json = json.loads(error_text)
                    from kiro.kiro_errors import enhance_kiro_error
                    error_info = enhance_kiro_error(error_json)
                    error_reason = error_info.reason
                    last_error_message = error_info.user_message
                    last_error_status = response.status_code
                except (json.JSONDecodeError, KeyError):
                    last_error_message = error_text
                    last_error_status = response.status_code

                error_type = classify_error(response.status_code, error_reason)

                if error_type == ErrorType.FATAL:
                    await account_manager.report_failure(
                        account.id, request_data.model, error_type,
                        response.status_code, error_reason,
                    )
                    logger.warning(f"HTTP {response.status_code} - POST /v1/responses - {last_error_message[:100]}")
                    if debug_logger:
                        debug_logger.flush_on_error(response.status_code, last_error_message)
                    return _error_response(response.status_code, last_error_message)

                # RECOVERABLE - try next account
                await account_manager.report_failure(
                    account.id, request_data.model, error_type,
                    response.status_code, error_reason,
                )
                if len(all_accounts) == 1:
                    break
                continue

            except HTTPException as e:
                await http_client.close()
                if e.status_code in (502, 504):
                    await account_manager.report_failure(
                        account.id, request_data.model, ErrorType.RECOVERABLE, e.status_code, None
                    )
                    last_error_message = str(e.detail)
                    last_error_status = e.status_code
                    if len(all_accounts) == 1:
                        break
                    logger.warning(f"Network error on account {account.id}, trying next account")
                    continue
                logger.error(f"HTTP {e.status_code} - POST /v1/responses - {e.detail}")
                if debug_logger:
                    debug_logger.flush_on_error(e.status_code, str(e.detail))
                raise
            except Exception as e:
                await http_client.close()
                logger.error(f"Internal error: {e}", exc_info=True)
                logger.error(f"HTTP 500 - POST /v1/responses - {str(e)[:100]}")
                if debug_logger:
                    debug_logger.flush_on_error(500, str(e))
                raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

        # All attempts exhausted
        if len(all_accounts) == 1:
            raise HTTPException(status_code=last_error_status, detail=last_error_message)
        detail = "All accounts failed after full circle."
        if last_error_message:
            detail += f" Error from last account: {last_error_message}"
        raise HTTPException(status_code=503, detail=detail)

    # ==============================================================================
    # LEGACY MODE: Single Account (no failover)
    # ==============================================================================
    account = request.app.state.account_manager.get_first_account()
    if not account.auth_manager:
        logger.error("No initialized accounts available (legacy mode)")
        raise HTTPException(503, "No initialized accounts available")
    auth_manager = account.auth_manager
    model_cache = account.model_cache

    conversation_id = generate_conversation_id()
    profile_arn = profile_arn_for_payload(auth_manager)

    try:
        kiro_payload = build_kiro_payload(request_data, conversation_id, profile_arn)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        kiro_request_body = json.dumps(kiro_payload, ensure_ascii=False, indent=2).encode("utf-8")
        if debug_logger:
            debug_logger.log_kiro_request_body(kiro_request_body)
    except Exception as e:
        logger.warning(f"Failed to log Kiro request: {e}")

    url = f"{auth_manager.api_host}/generateAssistantResponse"
    logger.debug(f"Kiro API URL: {url}")

    if request_data.stream:
        http_client = KiroHttpClient(auth_manager, shared_client=None)
    else:
        shared_client = request.app.state.http_client
        http_client = KiroHttpClient(auth_manager, shared_client=shared_client)

    try:
        response = await http_client.request_with_retry("POST", url, kiro_payload, stream=True)

        if response.status_code != 200:
            try:
                error_content = await response.aread()
            except Exception:
                error_content = b"Unknown error"
            await http_client.close()
            error_text = error_content.decode("utf-8", errors="replace")

            error_message = error_text
            try:
                error_json = json.loads(error_text)
                from kiro.kiro_errors import enhance_kiro_error
                error_info = enhance_kiro_error(error_json)
                error_message = error_info.user_message
            except (json.JSONDecodeError, KeyError):
                pass

            logger.warning(f"HTTP {response.status_code} - POST /v1/responses - {error_message[:100]}")
            if debug_logger:
                debug_logger.flush_on_error(response.status_code, error_message)
            return _error_response(response.status_code, error_message)

        if request_data.stream:
            return _make_streaming_response(
                http_client, url, kiro_payload, request_data,
                model_cache, auth_manager, response,
                messages_for_tokenizer, tools_for_tokenizer,
            )

        responses_obj = await collect_responses_response(
            http_client.client, response, request_data.model,
            model_cache, auth_manager,
            request_messages=messages_for_tokenizer,
            request_tools=tools_for_tokenizer,
        )
        await http_client.close()
        logger.info("HTTP 200 - POST /v1/responses (non-streaming) - completed")
        if debug_logger:
            debug_logger.discard_buffers()
        return JSONResponse(content=responses_obj)

    except HTTPException as e:
        await http_client.close()
        if e.status_code in (502, 504):
            logger.warning("Network error (legacy mode, no failover available)")
        logger.error(f"HTTP {e.status_code} - POST /v1/responses - {e.detail}")
        if debug_logger:
            debug_logger.flush_on_error(e.status_code, str(e.detail))
        raise
    except Exception as e:
        await http_client.close()
        logger.error(f"Internal error: {e}", exc_info=True)
        logger.error(f"HTTP 500 - POST /v1/responses - {str(e)[:100]}")
        if debug_logger:
            debug_logger.flush_on_error(500, str(e))
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


def _make_streaming_response(
    http_client, url, kiro_payload, request_data,
    model_cache, auth_manager, initial_response,
    messages_for_tokenizer, tools_for_tokenizer,
) -> StreamingResponse:
    """Build the StreamingResponse wrapper for Responses SSE output."""

    async def stream_wrapper():
        streaming_error = None
        client_disconnected = False
        try:
            async def make_retry_request():
                return await http_client.request_with_retry("POST", url, kiro_payload, stream=True)

            async for chunk in stream_responses_with_first_token_retry(
                make_request=make_retry_request,
                client=http_client.client,
                model=request_data.model,
                model_cache=model_cache,
                auth_manager=auth_manager,
                initial_response=initial_response,
                request_messages=messages_for_tokenizer,
                request_tools=tools_for_tokenizer,
            ):
                yield chunk
        except GeneratorExit:
            client_disconnected = True
            logger.debug("Client disconnected during streaming (GeneratorExit in routes)")
        except Exception as e:
            streaming_error = e
            raise
        finally:
            await http_client.close()
            if streaming_error:
                error_type = type(streaming_error).__name__
                error_msg = str(streaming_error) if str(streaming_error) else "(empty message)"
                logger.error(f"HTTP 500 - POST /v1/responses (streaming) - [{error_type}] {error_msg[:100]}")
            elif client_disconnected:
                logger.info("HTTP 200 - POST /v1/responses (streaming) - client disconnected")
            else:
                logger.info("HTTP 200 - POST /v1/responses (streaming) - completed")
            if debug_logger:
                if streaming_error:
                    debug_logger.flush_on_error(500, str(streaming_error))
                else:
                    debug_logger.discard_buffers()

    return StreamingResponse(stream_wrapper(), media_type="text/event-stream")
