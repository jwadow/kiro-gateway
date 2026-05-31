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
FastAPI routes for Kiro Gateway.

Contains all API endpoints:
- / and /health: Health check
- /v1/models: Models list
- /v1/chat/completions: Chat completions
"""

import json
import time
from datetime import datetime, timezone
from typing import Dict, Optional

# Consecutive-failure count at which an account's circuit is considered tripped.
# Mirrors the threshold used by the admin usage endpoint for a consistent view.
CIRCUIT_TRIP_THRESHOLD = 3

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Security
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import APIKeyHeader
from loguru import logger

from kiro.config import (
    PROXY_API_KEY,
    APP_VERSION,
    PROFILE_ARN,
)
from kiro.models_openai import (
    OpenAIModel,
    ModelList,
    ChatCompletionRequest,
    ResponsesRequest,
)
from kiro.auth import KiroAuthManager, AuthType
from kiro.cache import ModelInfoCache
from kiro.model_resolver import ModelResolver
from kiro.converters_openai import build_kiro_payload, convert_responses_request_to_chat
from kiro.streaming_openai import stream_kiro_to_openai, collect_stream_response, stream_with_first_token_retry
from kiro.streaming_responses import collect_responses_response, stream_kiro_to_responses
from kiro.http_client import KiroHttpClient
from kiro.utils import generate_conversation_id
from kiro.config import WEB_SEARCH_ENABLED
from kiro.mcp_tools import handle_native_web_search

# Import debug_logger
try:
    from kiro.debug_logger import debug_logger
except ImportError:
    debug_logger = None


# --- Security scheme ---
# Authorization: Bearer (OpenAI native)
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)
# x-api-key (Anthropic native) — for clients that auto-detect the auth header
# by api_mode and send x-api-key for /v1/models too (e.g. hermes-cli with
# api_mode: anthropic_messages). See #162, #188.
x_api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)


async def verify_api_key(
    auth_header: Optional[str] = Security(api_key_header),
    x_api_key: Optional[str] = Security(x_api_key_header),
) -> bool:
    """
    Verify API key for OpenAI-compatible endpoints.

    Supports two authentication methods:
    1. ``Authorization: Bearer {PROXY_API_KEY}`` (OpenAI native)
    2. ``x-api-key: {PROXY_API_KEY}`` (Anthropic native, for clients that
       send the same header for both /v1/models and /v1/messages)

    Args:
        auth_header: Authorization header value
        x_api_key: x-api-key header value

    Returns:
        True if key is valid

    Raises:
        HTTPException: 401 if neither header has a valid key
    """
    # Check Authorization: Bearer first (OpenAI native)
    if auth_header and auth_header == f"Bearer {PROXY_API_KEY}":
        return True

    # Fall back to x-api-key (Anthropic native)
    if x_api_key and x_api_key == PROXY_API_KEY:
        return True

    logger.warning("Access attempt with invalid API key.")
    raise HTTPException(status_code=401, detail="Invalid or missing API Key")


# --- Router ---
router = APIRouter()


@router.get("/")
async def root():
    """
    Health check endpoint.
    
    Returns:
        Status and application version
    """
    return {
        "status": "ok",
        "message": "Kiro Gateway is running",
        "version": APP_VERSION
    }


@router.get("/health")
async def health(request: Request):
    """
    Detailed health check with runtime and account-pool diagnostics.

    Reports liveness plus optional, best-effort operational signals so
    operators and uptime probes can see version, uptime, and account-pool
    health at a glance. All pool/runtime fields are computed defensively:
    if the account system is not ready they are simply omitted, and the
    endpoint always returns 200 with at least status/version/timestamp.

    Args:
        request: FastAPI Request for accessing app.state.

    Returns:
        A JSON-serializable dict with status, version, timestamp, uptime,
        and (when available) account-pool summary.
    """
    payload: Dict[str, object] = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": APP_VERSION,
    }

    # Uptime (best-effort; start_time is set in the lifespan startup).
    start_time = getattr(request.app.state, "start_time", None)
    if isinstance(start_time, (int, float)):
        payload["uptime_seconds"] = round(time.time() - start_time, 3)

    # Account-pool summary (best-effort; never fail the health check).
    account_system = getattr(request.app.state, "account_system", None)
    payload["account_system"] = bool(account_system)

    manager = getattr(request.app.state, "account_manager", None)
    if manager is not None:
        try:
            accounts = manager.get_all_accounts()
            initialized = sum(1 for a in accounts if a.auth_manager is not None)
            healthy = sum(
                1 for a in accounts
                if a.auth_manager is not None and a.failures < CIRCUIT_TRIP_THRESHOLD
            )
            pool = {
                "total": len(accounts),
                "initialized": initialized,
                "healthy": healthy,
            }
            try:
                pool["models_available"] = len(manager.get_all_available_models())
            except (AttributeError, RuntimeError) as exc:
                logger.debug(f"/health: could not collect available models: {exc}")
            payload["accounts"] = pool

            # Degraded (not unhealthy) when accounts exist but none are usable.
            if accounts and healthy == 0:
                payload["status"] = "degraded"
        except (AttributeError, RuntimeError) as exc:
            logger.debug(f"/health: account pool summary unavailable: {exc}")

    return payload

@router.get("/v1/models", response_model=ModelList, dependencies=[Depends(verify_api_key)])
async def get_models(request: Request):
    """
    Return list of available models.
    
    Models are loaded at startup (blocking) and cached.
    This endpoint returns the cached list.
    
    Args:
        request: FastAPI Request for accessing app.state
    
    Returns:
        ModelList with available models in consistent format (with dots)
    """
    logger.info("Request to /v1/models")
    
    # Get available models based on mode
    if request.app.state.account_system:
        # Account system: collect models from all initialized accounts
        available_model_ids = request.app.state.account_manager.get_all_available_models()
    else:
        # Legacy: use resolver from first account
        account = request.app.state.account_manager.get_first_account()
        available_model_ids = account.model_resolver.get_available_models()

    # Merge tokenLimits from every initialized account's model_cache so the
    # response exposes per-model ceilings (see OpenAIModel docstring). If the
    # same model appears across multiple accounts we keep the largest limits
    # observed (callers care about "what's possible", not the strictest tier).
    token_limits_by_model: Dict[str, Dict[str, int]] = {}
    try:
        for account in request.app.state.account_manager.iter_initialized_accounts():
            cache = getattr(account, "model_cache", None)
            if not cache:
                continue
            for mid in cache.get_all_model_ids():
                limits = cache.get_token_limits(mid)
                if not limits:
                    continue
                current = token_limits_by_model.setdefault(mid, {})
                for src, dst in (
                    ("maxInputTokens", "max_input_tokens"),
                    ("maxOutputTokens", "max_output_tokens"),
                ):
                    val = limits.get(src)
                    if isinstance(val, int) and val > current.get(dst, 0):
                        current[dst] = val
    except Exception as exc:  # pragma: no cover — defensive; never fail /v1/models
        logger.warning(f"Failed to merge tokenLimits for /v1/models: {exc}")

    # Build OpenAI-compatible model list
    openai_models = [
        OpenAIModel(
            id=model_id,
            owned_by="anthropic",
            description="Claude model via Kiro API",
            context_length=token_limits_by_model.get(model_id, {}).get("max_input_tokens"),
            max_input_tokens=token_limits_by_model.get(model_id, {}).get("max_input_tokens"),
            max_output_tokens=token_limits_by_model.get(model_id, {}).get("max_output_tokens"),
        )
        for model_id in available_model_ids
    ]
    
    return ModelList(data=openai_models)


@router.post("/v1/chat/completions", dependencies=[Depends(verify_api_key)])
async def chat_completions(request: Request, request_data: ChatCompletionRequest):
    """
    Chat completions endpoint - compatible with OpenAI API.
    
    Accepts requests in OpenAI format and translates them to Kiro API.
    Supports streaming and non-streaming modes.
    
    Args:
        request: FastAPI Request for accessing app.state
        request_data: Request in OpenAI ChatCompletionRequest format
    
    Returns:
        StreamingResponse for streaming mode
        JSONResponse for non-streaming mode
    
    Raises:
        HTTPException: On validation or API errors
    """
    logger.info(f"Request to /v1/chat/completions (model={request_data.model}, stream={request_data.stream})")
    
    # Note: prepare_new_request() and log_request_body() are now called by DebugLoggerMiddleware
    # This ensures debug logging works even for requests that fail Pydantic validation (422 errors)
    
    # Check for truncation recovery opportunities
    from kiro.truncation_state import get_tool_truncation, get_content_truncation
    from kiro.truncation_recovery import generate_truncation_tool_result, generate_truncation_user_message
    from kiro.models_openai import ChatMessage
    
    modified_messages = []
    tool_results_modified = 0
    content_notices_added = 0
    
    for msg in request_data.messages:
        # Check if this is a tool_result for a truncated tool call
        if msg.role == "tool" and msg.tool_call_id:
            truncation_info = get_tool_truncation(msg.tool_call_id)
            if truncation_info:
                # Modify tool_result content to include truncation notice
                synthetic = generate_truncation_tool_result(
                    tool_name=truncation_info.tool_name,
                    tool_use_id=msg.tool_call_id,
                    truncation_info=truncation_info.truncation_info
                )
                # Prepend truncation notice to original content
                modified_content = f"{synthetic['content']}\n\n---\n\nOriginal tool result:\n{msg.content}"
                
                # Create NEW ChatMessage object (Pydantic immutability)
                modified_msg = msg.model_copy(update={"content": modified_content})
                modified_messages.append(modified_msg)
                tool_results_modified += 1
                logger.debug(f"Modified tool_result for {msg.tool_call_id} to include truncation notice")
                continue  # Skip normal append since we already added modified version
        
        # Check if this is an assistant message with truncated content
        if msg.role == "assistant" and msg.content and isinstance(msg.content, str):
            truncation_info = get_content_truncation(msg.content)
            if truncation_info:
                # Add this message first
                modified_messages.append(msg)
                # Then add synthetic user message about truncation
                synthetic_user_msg = ChatMessage(
                    role="user",
                    content=generate_truncation_user_message()
                )
                modified_messages.append(synthetic_user_msg)
                content_notices_added += 1
                logger.debug(f"Added truncation notice after assistant message (hash: {truncation_info.message_hash})")
                continue  # Skip normal append since we already added it
        
        modified_messages.append(msg)
    
    if tool_results_modified > 0 or content_notices_added > 0:
        request_data.messages = modified_messages
        logger.info(f"Truncation recovery: modified {tool_results_modified} tool_result(s), added {content_notices_added} content notice(s)")
    
    # ==============================================================================
    # WebSearch Support - Path B: Auto-Injection (MCP Tool Emulation)
    # ==============================================================================
    
    # Auto-inject web_search tool if enabled (Path B - MCP emulation)
    if WEB_SEARCH_ENABLED:
        if request_data.tools is None:
            request_data.tools = []
        
        # Check if web_search already exists
        has_ws = any(
            getattr(tool, "type", None) == "function" and
            getattr(getattr(tool, "function", None), "name", None) == "web_search"
            for tool in request_data.tools
        )
        
        if not has_ws:
            from kiro.models_openai import Tool, ToolFunction
            web_search_tool = Tool(
                type="function",
                function=ToolFunction(
                    name="web_search",
                    description="Search the web for current information. Use when you need up-to-date data from the internet.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query"
                            }
                        },
                        "required": ["query"]
                    }
                )
            )
            request_data.tools.append(web_search_tool)
            logger.debug("Auto-injected web_search tool for MCP emulation (Path B)")
    
    # ==============================================================================
    # Account System: Account System Failover or Legacy Mode
    # ==============================================================================
    
    if request.app.state.account_system:
        # ==============================================================================
        # ACCOUNT SYSTEM ENABLED: Failover Loop
        # ==============================================================================
        from kiro.account_errors import classify_error, ErrorType
        
        account_manager = request.app.state.account_manager
        all_accounts = list(account_manager._accounts.keys())
        MAX_ATTEMPTS = len(all_accounts) * 2  # Full circle with margin
        
        last_error_message = None
        last_error_status = None
        tried_accounts = set()  # Track tried accounts in current failover loop
        
        for attempt in range(MAX_ATTEMPTS):
            # Get next available account (excluding already tried)
            account = await account_manager.get_next_account(
                request_data.model,
                exclude_accounts=tried_accounts
            )
            
            if account is None:
                # All accounts unavailable
                if len(all_accounts) == 1:
                    # Single account - return original error with original status code
                    raise HTTPException(
                        status_code=last_error_status or 503,
                        detail=last_error_message or "Account unavailable"
                    )
                else:
                    # Multiple accounts - generic error with context
                    detail = "No available accounts for this model."
                    if last_error_message:
                        detail += f" Error from last account: {last_error_message}"
                    raise HTTPException(status_code=503, detail=detail)
            
            # Mark account as tried in current failover loop
            tried_accounts.add(account.id)
            
            # Use objects from account
            auth_manager = account.auth_manager
            model_cache = account.model_cache
            model_resolver = account.model_resolver
            
            # Generate conversation ID
            conversation_id = generate_conversation_id()
            
            # Build payload for Kiro
            # profileArn handling by auth type (see #168, #150):
            # - Builder ID (AWS_SSO_OIDC) has no native profileArn; sending it
            #   causes a 403, so only an explicitly configured PROFILE_ARN is used.
            # - Kiro Desktop / Enterprise IDE: use native profileArn, fall back to env.
            if auth_manager.auth_type == AuthType.AWS_SSO_OIDC:
                profile_arn_for_payload = PROFILE_ARN or ""
            else:
                profile_arn_for_payload = auth_manager.profile_arn or PROFILE_ARN or ""
            
            try:
                kiro_payload = build_kiro_payload(
                    request_data,
                    conversation_id,
                    profile_arn_for_payload
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            
            # Log Kiro payload
            try:
                kiro_request_body = json.dumps(kiro_payload, ensure_ascii=False, indent=2).encode('utf-8')
                if debug_logger:
                    debug_logger.log_kiro_request_body(kiro_request_body)
            except Exception as e:
                logger.warning(f"Failed to log Kiro request: {e}")
            
            # Create HTTP client
            url = f"{auth_manager.api_host}/generateAssistantResponse"
            logger.debug(f"Kiro API URL: {url} (account: {account.id})")
            
            if request_data.stream:
                http_client = KiroHttpClient(auth_manager, shared_client=None)
            else:
                shared_client = request.app.state.http_client
                http_client = KiroHttpClient(auth_manager, shared_client=shared_client)
            
            try:
                # Make request to Kiro API
                response = await http_client.request_with_retry(
                    "POST",
                    url,
                    kiro_payload,
                    stream=True
                )
                
                if response.status_code == 200:
                    # SUCCESS - report and return
                    await account_manager.report_success(account.id, request_data.model)
                    
                    # Prepare data for token counting
                    messages_for_tokenizer = [msg.model_dump() for msg in request_data.messages]
                    tools_for_tokenizer = [tool.model_dump() for tool in request_data.tools] if request_data.tools else None
                    
                    if request_data.stream:
                        # Streaming mode
                        async def stream_wrapper():
                            streaming_error = None
                            client_disconnected = False
                            try:
                                async def make_retry_request():
                                    return await http_client.request_with_retry(
                                        "POST", url, kiro_payload, stream=True
                                    )
                                
                                async for chunk in stream_with_first_token_retry(
                                    make_request=make_retry_request,
                                    client=http_client.client,
                                    model=request_data.model,
                                    model_cache=model_cache,
                                    auth_manager=auth_manager,
                                    initial_response=response,
                                    request_messages=messages_for_tokenizer,
                                    request_tools=tools_for_tokenizer
                                ):
                                    yield chunk
                            except GeneratorExit:
                                client_disconnected = True
                                logger.debug("Client disconnected during streaming (GeneratorExit in routes)")
                            except Exception as e:
                                streaming_error = e
                                try:
                                    yield "data: [DONE]\n\n"
                                except Exception:
                                    pass
                                raise
                            finally:
                                await http_client.close()
                                if streaming_error:
                                    error_type = type(streaming_error).__name__
                                    error_msg = str(streaming_error) if str(streaming_error) else "(empty message)"
                                    logger.error(f"HTTP 500 - POST /v1/chat/completions (streaming) - [{error_type}] {error_msg[:100]}")
                                elif client_disconnected:
                                    logger.info(f"HTTP 200 - POST /v1/chat/completions (streaming) - client disconnected")
                                else:
                                    logger.info(f"HTTP 200 - POST /v1/chat/completions (streaming) - completed")
                                if debug_logger:
                                    if streaming_error:
                                        debug_logger.flush_on_error(500, str(streaming_error))
                                    else:
                                        debug_logger.discard_buffers()
                        
                        return StreamingResponse(stream_wrapper(), media_type="text/event-stream")
                    
                    else:
                        # Non-streaming mode
                        openai_response = await collect_stream_response(
                            http_client.client,
                            response,
                            request_data.model,
                            model_cache,
                            auth_manager,
                            request_messages=messages_for_tokenizer,
                            request_tools=tools_for_tokenizer
                        )
                        
                        await http_client.close()
                        logger.info(f"HTTP 200 - POST /v1/chat/completions (non-streaming) - completed")
                        
                        if debug_logger:
                            debug_logger.discard_buffers()
                        
                        return JSONResponse(content=openai_response)
                
                else:
                    # ERROR - classify and decide
                    try:
                        error_content = await response.aread()
                    except Exception:
                        error_content = b"Unknown error"
                    
                    await http_client.close()
                    error_text = error_content.decode('utf-8', errors='replace')
                    
                    # Extract error reason and save for final return
                    error_reason = None
                    try:
                        error_json = json.loads(error_text)
                        from kiro.kiro_errors import enhance_kiro_error
                        error_info = enhance_kiro_error(error_json)
                        error_reason = error_info.reason
                        last_error_message = error_info.user_message
                        last_error_status = response.status_code
                        logger.debug(f"Original Kiro error: {error_info.original_message} (reason: {error_info.reason})")
                    except (json.JSONDecodeError, KeyError):
                        last_error_message = error_text
                        last_error_status = response.status_code
                    
                    # Classify error
                    error_type = classify_error(response.status_code, error_reason)
                    
                    if error_type == ErrorType.FATAL:
                        # FATAL - return to client immediately
                        await account_manager.report_failure(
                            account.id, request_data.model, error_type,
                            response.status_code, error_reason
                        )
                        
                        logger.warning(f"HTTP {response.status_code} - POST /v1/chat/completions - {last_error_message[:100]}")
                        
                        if debug_logger:
                            debug_logger.flush_on_error(response.status_code, last_error_message)
                        
                        return JSONResponse(
                            status_code=response.status_code,
                            content={
                                "error": {
                                    "message": last_error_message,
                                    "type": "kiro_api_error",
                                    "code": response.status_code
                                }
                            }
                        )
                    
                    else:  # ErrorType.RECOVERABLE
                        # RECOVERABLE - try next account
                        await account_manager.report_failure(
                            account.id, request_data.model, error_type,
                            response.status_code, error_reason
                        )
                        
                        # Single account - no point in failover, break immediately
                        if len(all_accounts) == 1:
                            break
                        
                        continue  # Next iteration
            
            except HTTPException as e:
                await http_client.close()
                
                # Network errors (502/504 from request_with_retry) = RECOVERABLE
                # These are thrown ONLY for network-level issues (timeouts, connection errors)
                # NOT for HTTP-level errors (which are returned as response objects)
                if e.status_code in (502, 504):
                    # Network error → try next account
                    await account_manager.report_failure(
                        account.id, request_data.model, ErrorType.RECOVERABLE,
                        e.status_code, None
                    )
                    
                    last_error_message = str(e.detail)
                    last_error_status = e.status_code
                    
                    # Single account - no point in failover, break immediately
                    if len(all_accounts) == 1:
                        break
                    
                    logger.warning(f"Network error on account {account.id}, trying next account")
                    continue  # Try next account
                
                # All other HTTPException (400, 500, etc.) = application errors
                # These come from build_kiro_payload() or other places → re-raise immediately
                logger.error(f"HTTP {e.status_code} - POST /v1/chat/completions - {e.detail}")
                if debug_logger:
                    debug_logger.flush_on_error(e.status_code, str(e.detail))
                raise
            except Exception as e:
                await http_client.close()
                logger.error(f"Internal error: {e}", exc_info=True)
                logger.error(f"HTTP 500 - POST /v1/chat/completions - {str(e)[:100]}")
                if debug_logger:
                    debug_logger.flush_on_error(500, str(e))
                raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
        
        # All attempts exhausted
        if len(all_accounts) == 1:
            # Single account - return its original error
            # last_error_status and last_error_message are guaranteed to be set
            raise HTTPException(
                status_code=last_error_status,
                detail=last_error_message
            )
        else:
            # Multiple accounts - generic error with context
            detail = "All accounts failed after full circle."
            if last_error_message:
                detail += f" Error from last account: {last_error_message}"
            raise HTTPException(status_code=503, detail=detail)
    
    else:
        # ==============================================================================
        # LEGACY MODE: Single Account (no failover)
        # ==============================================================================
        account = request.app.state.account_manager.get_first_account()
        if not account.auth_manager:
            logger.error("No initialized accounts available (legacy mode)")
            raise HTTPException(503, "No initialized accounts available")
        auth_manager = account.auth_manager
        model_cache = account.model_cache
        model_resolver = account.model_resolver
    
    # Generate conversation ID for Kiro API (random UUID, not used for tracking)
    conversation_id = generate_conversation_id()
    
    # Build payload for Kiro
    # profileArn handling by auth type (see #168, #150):
    # - Builder ID (AWS_SSO_OIDC) has no native profileArn; sending it
    #   causes a 403, so only an explicitly configured PROFILE_ARN is used.
    # - Kiro Desktop / Enterprise IDE: use native profileArn, fall back to env.
    if auth_manager.auth_type == AuthType.AWS_SSO_OIDC:
        profile_arn_for_payload = PROFILE_ARN or ""
    else:
        profile_arn_for_payload = auth_manager.profile_arn or PROFILE_ARN or ""
    
    try:
        kiro_payload = build_kiro_payload(
            request_data,
            conversation_id,
            profile_arn_for_payload
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Log Kiro payload
    try:
        kiro_request_body = json.dumps(kiro_payload, ensure_ascii=False, indent=2).encode('utf-8')
        if debug_logger:
            debug_logger.log_kiro_request_body(kiro_request_body)
    except Exception as e:
        logger.warning(f"Failed to log Kiro request: {e}")
    
    # Create HTTP client with retry logic
    # For streaming: use per-request client to avoid CLOSE_WAIT leak on VPN disconnect (issue #54)
    # For non-streaming: use shared client for connection pooling
    url = f"{auth_manager.api_host}/generateAssistantResponse"
    logger.debug(f"Kiro API URL: {url}")
    
    if request_data.stream:
        # Streaming mode: per-request client prevents orphaned connections
        # when network interface changes (VPN disconnect/reconnect)
        http_client = KiroHttpClient(auth_manager, shared_client=None)
    else:
        # Non-streaming mode: shared client for efficient connection reuse
        shared_client = request.app.state.http_client
        http_client = KiroHttpClient(auth_manager, shared_client=shared_client)
    try:
        # Make request to Kiro API (for both streaming and non-streaming modes)
        # Important: we wait for Kiro response BEFORE returning StreamingResponse,
        # so that 200 OK means Kiro accepted the request and started responding
        response = await http_client.request_with_retry(
            "POST",
            url,
            kiro_payload,
            stream=True
        )
        
        if response.status_code != 200:
            try:
                error_content = await response.aread()
            except Exception:
                error_content = b"Unknown error"
            
            await http_client.close()
            error_text = error_content.decode('utf-8', errors='replace')
            
            # Try to parse JSON response from Kiro to extract error message
            error_message = error_text
            try:
                error_json = json.loads(error_text)
                # Enhance Kiro API errors with user-friendly messages
                from kiro.kiro_errors import enhance_kiro_error
                error_info = enhance_kiro_error(error_json)
                error_message = error_info.user_message
                # Log original error for debugging
                logger.debug(f"Original Kiro error: {error_info.original_message} (reason: {error_info.reason})")
            except (json.JSONDecodeError, KeyError):
                pass
            
            # Log access log for error (before flush, so it gets into app_logs)
            logger.warning(
                f"HTTP {response.status_code} - POST /v1/chat/completions - {error_message[:100]}"
            )
            
            # Flush debug logs on error ("errors" mode)
            if debug_logger:
                debug_logger.flush_on_error(response.status_code, error_message)
            
            # Return error in OpenAI API format
            return JSONResponse(
                status_code=response.status_code,
                content={
                    "error": {
                        "message": error_message,
                        "type": "kiro_api_error",
                        "code": response.status_code
                    }
                }
            )
        
        # Prepare data for fallback token counting
        # Convert Pydantic models to dicts for tokenizer
        messages_for_tokenizer = [msg.model_dump() for msg in request_data.messages]
        tools_for_tokenizer = [tool.model_dump() for tool in request_data.tools] if request_data.tools else None
        
        if request_data.stream:
            # Streaming mode with first token retry
            async def stream_wrapper():
                streaming_error = None
                client_disconnected = False
                try:
                    # Create retry request function for retries
                    async def make_retry_request():
                        return await http_client.request_with_retry(
                            "POST", url, kiro_payload, stream=True
                        )
                    
                    # Use retry wrapper with initial response
                    async for chunk in stream_with_first_token_retry(
                        make_request=make_retry_request,
                        client=http_client.client,
                        model=request_data.model,
                        model_cache=model_cache,
                        auth_manager=auth_manager,
                        initial_response=response,
                        request_messages=messages_for_tokenizer,
                        request_tools=tools_for_tokenizer
                    ):
                        yield chunk
                except GeneratorExit:
                    # Client disconnected - this is normal
                    client_disconnected = True
                    logger.debug("Client disconnected during streaming (GeneratorExit in routes)")
                except Exception as e:
                    streaming_error = e
                    # Try to send [DONE] to client before finishing
                    # so client doesn't "hang" waiting for data
                    try:
                        yield "data: [DONE]\n\n"
                    except Exception:
                        pass  # Client already disconnected
                    raise
                finally:
                    await http_client.close()
                    # Log access log for streaming (success or error)
                    if streaming_error:
                        error_type = type(streaming_error).__name__
                        error_msg = str(streaming_error) if str(streaming_error) else "(empty message)"
                        logger.error(f"HTTP 500 - POST /v1/chat/completions (streaming) - [{error_type}] {error_msg[:100]}")
                    elif client_disconnected:
                        logger.info(f"HTTP 200 - POST /v1/chat/completions (streaming) - client disconnected")
                    else:
                        logger.info(f"HTTP 200 - POST /v1/chat/completions (streaming) - completed")
                    # Write debug logs AFTER streaming completes
                    if debug_logger:
                        if streaming_error:
                            debug_logger.flush_on_error(500, str(streaming_error))
                        else:
                            debug_logger.discard_buffers()
            
            return StreamingResponse(stream_wrapper(), media_type="text/event-stream")
        
        else:
            
            # Non-streaming mode - collect entire response
            openai_response = await collect_stream_response(
                http_client.client,
                response,
                request_data.model,
                model_cache,
                auth_manager,
                request_messages=messages_for_tokenizer,
                request_tools=tools_for_tokenizer
            )
            
            await http_client.close()
            
            # Log access log for non-streaming success
            logger.info(f"HTTP 200 - POST /v1/chat/completions (non-streaming) - completed")
            
            # Write debug logs after non-streaming request completes
            if debug_logger:
                debug_logger.discard_buffers()
            
            return JSONResponse(content=openai_response)
    
    except HTTPException as e:
        await http_client.close()
        
        # Network errors (502/504 from request_with_retry) = RECOVERABLE
        # In legacy mode, we still log them but re-raise (no failover available)
        if e.status_code in (502, 504):
            logger.warning(f"Network error (legacy mode, no failover available)")
        
        # Log access log for HTTP error
        logger.error(f"HTTP {e.status_code} - POST /v1/chat/completions - {e.detail}")
        # Flush debug logs on HTTP error ("errors" mode)
        if debug_logger:
            debug_logger.flush_on_error(e.status_code, str(e.detail))
        raise
    except Exception as e:
        await http_client.close()
        logger.error(f"Internal error: {e}", exc_info=True)
        # Log access log for internal error
        logger.error(f"HTTP 500 - POST /v1/chat/completions - {str(e)[:100]}")
        # Flush debug logs on internal error ("errors" mode)
        if debug_logger:
            debug_logger.flush_on_error(500, str(e))
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


def _profile_arn_for_auth(auth_manager: KiroAuthManager) -> str:
    """
    Resolve the profileArn to send for the given auth type.

    Builder ID (AWS_SSO_OIDC) accounts have no native profileArn; sending one
    causes a 403 (see #168), so only an explicitly configured PROFILE_ARN is
    used. Other auth types use the native profileArn with an env fallback.

    Args:
        auth_manager: The selected account's auth manager.

    Returns:
        The profileArn string to embed in the Kiro payload (may be empty).
    """
    if auth_manager.auth_type == AuthType.AWS_SSO_OIDC:
        return PROFILE_ARN or ""
    return auth_manager.profile_arn or PROFILE_ARN or ""


@router.post("/v1/responses", dependencies=[Depends(verify_api_key)])
async def responses(request: Request, request_data: ResponsesRequest):
    """
    Responses endpoint - compatible with OpenAI Responses API.

    Accepts Responses API input items and translates them to Kiro API through
    the existing Chat Completions conversion path. Supports streaming semantic
    Responses API SSE events and non-streaming response objects.

    Args:
        request: FastAPI Request for accessing app.state.
        request_data: Request in OpenAI Responses API format.

    Returns:
        StreamingResponse for streaming mode.
        JSONResponse for non-streaming mode.

    Raises:
        HTTPException: On validation or API errors.
    """
    logger.info(f"Request to /v1/responses (model={request_data.model}, stream={request_data.stream})")

    try:
        chat_request = convert_responses_request_to_chat(request_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    async def send_with_account(auth_manager, model_cache, account_id=None):
        """Send a Responses request through a selected account."""
        conversation_id = generate_conversation_id()
        profile_arn_for_payload = _profile_arn_for_auth(auth_manager)

        try:
            kiro_payload = build_kiro_payload(
                chat_request,
                conversation_id,
                profile_arn_for_payload
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        try:
            kiro_request_body = json.dumps(kiro_payload, ensure_ascii=False, indent=2).encode('utf-8')
            if debug_logger:
                debug_logger.log_kiro_request_body(kiro_request_body)
        except Exception as e:
            logger.warning(f"Failed to log Kiro request: {e}")

        url = f"{auth_manager.api_host}/generateAssistantResponse"
        if account_id:
            logger.debug(f"Kiro API URL: {url} (account: {account_id})")
        else:
            logger.debug(f"Kiro API URL: {url}")

        if request_data.stream:
            http_client = KiroHttpClient(auth_manager, shared_client=None)
        else:
            shared_client = request.app.state.http_client
            http_client = KiroHttpClient(auth_manager, shared_client=shared_client)

        try:
            response = await http_client.request_with_retry(
                "POST",
                url,
                kiro_payload,
                stream=True
            )
        except HTTPException:
            await http_client.close()
            raise
        except Exception:
            await http_client.close()
            raise

        messages_for_tokenizer = [msg.model_dump() for msg in chat_request.messages]
        tools_for_tokenizer = [tool.model_dump() for tool in chat_request.tools] if chat_request.tools else None

        if response.status_code == 200:
            if request_data.stream:
                async def stream_wrapper():
                    streaming_error = None
                    client_disconnected = False
                    try:
                        async for chunk in stream_kiro_to_responses(
                            http_client.client,
                            response,
                            request_data.model,
                            model_cache,
                            auth_manager,
                            request_messages=messages_for_tokenizer,
                            request_tools=tools_for_tokenizer
                        ):
                            yield chunk
                    except GeneratorExit:
                        client_disconnected = True
                        logger.debug("Client disconnected during Responses streaming")
                    except Exception as e:
                        streaming_error = e
                        try:
                            yield "data: [DONE]\n\n"
                        except Exception:
                            pass
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

            responses_response = await collect_responses_response(
                http_client.client,
                response,
                request_data.model,
                model_cache,
                auth_manager,
                request_messages=messages_for_tokenizer,
                request_tools=tools_for_tokenizer
            )

            await http_client.close()
            logger.info("HTTP 200 - POST /v1/responses (non-streaming) - completed")

            if debug_logger:
                debug_logger.discard_buffers()

            return JSONResponse(content=responses_response)

        try:
            error_content = await response.aread()
        except Exception:
            error_content = b"Unknown error"

        await http_client.close()
        error_text = error_content.decode('utf-8', errors='replace')
        error_reason = None
        error_message = error_text

        try:
            error_json = json.loads(error_text)
            from kiro.kiro_errors import enhance_kiro_error
            error_info = enhance_kiro_error(error_json)
            error_reason = error_info.reason
            error_message = error_info.user_message
            logger.debug(f"Original Kiro error: {error_info.original_message} (reason: {error_info.reason})")
        except (json.JSONDecodeError, KeyError):
            pass

        return {
            "status_code": response.status_code,
            "message": error_message,
            "reason": error_reason,
        }

    if request.app.state.account_system:
        from kiro.account_errors import classify_error, ErrorType

        account_manager = request.app.state.account_manager
        all_accounts = list(account_manager._accounts.keys())
        max_attempts = len(all_accounts) * 2
        tried_accounts = set()
        last_error_message = None
        last_error_status = None

        for _ in range(max_attempts):
            account = await account_manager.get_next_account(
                request_data.model,
                exclude_accounts=tried_accounts
            )

            if account is None:
                if len(all_accounts) == 1:
                    raise HTTPException(
                        status_code=last_error_status or 503,
                        detail=last_error_message or "Account unavailable"
                    )

                detail = "No available accounts for this model."
                if last_error_message:
                    detail += f" Error from last account: {last_error_message}"
                raise HTTPException(status_code=503, detail=detail)

            tried_accounts.add(account.id)

            try:
                result = await send_with_account(account.auth_manager, account.model_cache, account.id)

                if isinstance(result, (JSONResponse, StreamingResponse)):
                    await account_manager.report_success(account.id, request_data.model)
                    return result

                last_error_status = result["status_code"]
                last_error_message = result["message"]
                error_type = classify_error(last_error_status, result["reason"])

                await account_manager.report_failure(
                    account.id,
                    request_data.model,
                    error_type,
                    last_error_status,
                    result["reason"]
                )

                if error_type == ErrorType.FATAL:
                    logger.warning(f"HTTP {last_error_status} - POST /v1/responses - {last_error_message[:100]}")
                    if debug_logger:
                        debug_logger.flush_on_error(last_error_status, last_error_message)
                    return JSONResponse(
                        status_code=last_error_status,
                        content={
                            "error": {
                                "message": last_error_message,
                                "type": "kiro_api_error",
                                "code": last_error_status,
                            }
                        }
                    )

                if len(all_accounts) == 1:
                    break

            except HTTPException as e:
                if e.status_code in (502, 504):
                    await account_manager.report_failure(
                        account.id,
                        request_data.model,
                        ErrorType.RECOVERABLE,
                        e.status_code,
                        None
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

        if len(all_accounts) == 1:
            raise HTTPException(
                status_code=last_error_status,
                detail=last_error_message
            )

        detail = "All accounts failed after full circle."
        if last_error_message:
            detail += f" Error from last account: {last_error_message}"
        raise HTTPException(status_code=503, detail=detail)

    account = request.app.state.account_manager.get_first_account()
    if not account.auth_manager:
        logger.error("No initialized accounts available (legacy mode)")
        raise HTTPException(503, "No initialized accounts available")

    try:
        result = await send_with_account(account.auth_manager, account.model_cache)
        if isinstance(result, (JSONResponse, StreamingResponse)):
            return result

        logger.warning(f"HTTP {result['status_code']} - POST /v1/responses - {result['message'][:100]}")
        if debug_logger:
            debug_logger.flush_on_error(result["status_code"], result["message"])
        return JSONResponse(
            status_code=result["status_code"],
            content={
                "error": {
                    "message": result["message"],
                    "type": "kiro_api_error",
                    "code": result["status_code"],
                }
            }
        )

    except HTTPException as e:
        if e.status_code in (502, 504):
            logger.warning("Network error (legacy mode, no failover available)")
        logger.error(f"HTTP {e.status_code} - POST /v1/responses - {e.detail}")
        if debug_logger:
            debug_logger.flush_on_error(e.status_code, str(e.detail))
        raise
    except Exception as e:
        logger.error(f"Internal error: {e}", exc_info=True)
        logger.error(f"HTTP 500 - POST /v1/responses - {str(e)[:100]}")
        if debug_logger:
            debug_logger.flush_on_error(500, str(e))
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")