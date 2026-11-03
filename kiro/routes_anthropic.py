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
FastAPI routes for Anthropic Messages API.

Contains the /v1/messages endpoint compatible with Anthropic's Messages API.

Reference: https://docs.anthropic.com/en/api/messages
"""

import json
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Security, Header
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import APIKeyHeader
from loguru import logger

from kiro.config import PROXY_API_KEY, PROFILE_ARN
from kiro.models_anthropic import (
    AnthropicMessagesRequest,
    AnthropicCountTokensRequest,
    AnthropicMessagesResponse,
    AnthropicErrorResponse,
    AnthropicErrorDetail,
)
from kiro.auth import KiroAuthManager, AuthType
from kiro.cache import ModelInfoCache
from kiro.converters_anthropic import anthropic_to_kiro
from kiro.streaming_anthropic import (
    stream_kiro_to_anthropic,
    collect_anthropic_response,
    stream_with_first_token_retry_anthropic,
)
from kiro.http_client import KiroHttpClient
from kiro.utils import generate_conversation_id
from kiro.tokenizer import estimate_request_tokens
from kiro.config import WEB_SEARCH_ENABLED, FIRST_TOKEN_INNER_HTTP_RETRIES
from kiro.mcp_tools import handle_native_web_search
from kiro.exceptions import build_anthropic_error, retry_after_headers
from kiro.routes_openai import (
    CLIENT_CLOSED_REQUEST_STATUS,
    ClientDisconnectedError,
    close_upstream_response,
    run_until_disconnected,
    supported_kwargs,
)

# Import debug_logger
try:
    from kiro.debug_logger import debug_logger
except ImportError:
    debug_logger = None


# --- Security scheme ---
# Anthropic uses x-api-key header instead of Authorization: Bearer
anthropic_api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)
# Also support Authorization: Bearer for compatibility
auth_header = APIKeyHeader(name="Authorization", auto_error=False)


async def verify_anthropic_api_key(
    x_api_key: Optional[str] = Security(anthropic_api_key_header),
    authorization: Optional[str] = Security(auth_header)
) -> bool:
    """
    Verify API key for Anthropic API.
    
    Supports two authentication methods:
    1. x-api-key header (Anthropic native)
    2. Authorization: Bearer header (for compatibility)
    
    Args:
        x_api_key: Value from x-api-key header
        authorization: Value from Authorization header
    
    Returns:
        True if key is valid
    
    Raises:
        HTTPException: 401 if key is invalid or missing
    """
    # Check x-api-key first (Anthropic native)
    if x_api_key and x_api_key == PROXY_API_KEY:
        return True
    
    # Fall back to Authorization: Bearer
    if authorization and authorization == f"Bearer {PROXY_API_KEY}":
        return True
    
    logger.warning("Access attempt with invalid API key (Anthropic endpoint)")
    raise HTTPException(
        status_code=401,
        detail={
            "type": "error",
            "error": {
                "type": "authentication_error",
                "message": "Invalid or missing API key. Use x-api-key header or Authorization: Bearer."
            }
        }
    )


def anthropic_error_response(
    status_code: int,
    message: str,
    upstream_headers: Any = None,
    error_type: Optional[str] = None,
) -> JSONResponse:
    """
    Build an Anthropic-shaped error response.

    The error type follows the HTTP status (429 -> rate_limit_error, 503 -> overloaded_error, ...),
    and Retry-After is forwarded from the upstream on 429/503.

    Args:
        status_code: HTTP status
        message: User-facing error message
        upstream_headers: Upstream response headers (for Retry-After), if any
        error_type: Explicit error type (derived from status when omitted)

    Returns:
        JSONResponse with {"type": "error", "error": {"type", "message"}}
    """
    return JSONResponse(
        status_code=status_code,
        content=build_anthropic_error(message, status_code, error_type),
        headers=retry_after_headers(status_code, upstream_headers),
    )


def format_anthropic_stream_error(error: Exception) -> str:
    """
    Build an SSE error event for a mid-stream failure.

    Args:
        error: Exception that interrupted the stream

    Returns:
        "event: error" SSE frame in Anthropic error shape
    """
    payload = {"type": "error", "error": {"type": "api_error", "message": str(error)}}
    return f"event: error\ndata: {json.dumps(payload)}\n\n"


def apply_anthropic_truncation_recovery(request_data: AnthropicMessagesRequest) -> None:
    """
    Prepend truncation notices for tool calls/content truncated in earlier responses.

    Skipped entirely when recovery is disabled or nothing is pending, so the
    common case costs one dict-size check instead of a scan over all messages.

    Args:
        request_data: Request whose messages may be replaced in place
    """
    from kiro.truncation_state import get_tool_truncation, get_content_truncation, has_pending
    from kiro.truncation_recovery import (
        should_inject_recovery,
        generate_truncation_tool_result,
        generate_truncation_user_message,
    )
    from kiro.models_anthropic import AnthropicMessage

    if not should_inject_recovery() or not has_pending():
        return

    modified_messages = []
    tool_results_modified = 0
    content_notices_added = 0

    for msg in request_data.messages:
        # Check if this is a user message with tool_result blocks
        if msg.role == "user" and msg.content and isinstance(msg.content, list):
            modified_content_blocks = []
            has_modifications = False

            for block in msg.content:
                # Handle both dict and Pydantic objects (ToolResultContentBlock)
                if isinstance(block, dict):
                    block_type = block.get("type")
                    tool_use_id = block.get("tool_use_id")
                    original_content = block.get("content", "")
                elif hasattr(block, "type"):
                    block_type = block.type
                    tool_use_id = getattr(block, "tool_use_id", None)
                    original_content = getattr(block, "content", "")
                else:
                    modified_content_blocks.append(block)
                    continue

                if block_type == "tool_result" and tool_use_id:
                    truncation_info = get_tool_truncation(tool_use_id)
                    if truncation_info:
                        # Modify tool_result content to include truncation notice
                        synthetic = generate_truncation_tool_result(
                            tool_name=truncation_info.tool_name,
                            tool_use_id=tool_use_id,
                            truncation_info=truncation_info.truncation_info
                        )
                        # Prepend truncation notice to original content
                        modified_content = f"{synthetic['content']}\n\n---\n\nOriginal tool result:\n{original_content}"

                        # Create modified block (handle both dict and Pydantic)
                        if isinstance(block, dict):
                            modified_block = block.copy()
                            modified_block["content"] = modified_content
                        else:
                            modified_block = block.model_copy(update={"content": modified_content})

                        modified_content_blocks.append(modified_block)
                        tool_results_modified += 1
                        has_modifications = True
                        logger.debug(f"Modified tool_result for {tool_use_id} to include truncation notice")
                        continue

                modified_content_blocks.append(block)

            # Create NEW AnthropicMessage object if modifications were made (Pydantic immutability)
            if has_modifications:
                modified_messages.append(msg.model_copy(update={"content": modified_content_blocks}))
                continue

        # Check if this is an assistant message with truncated content
        if msg.role == "assistant" and msg.content:
            # Extract text content for hash check
            text_content = ""
            if isinstance(msg.content, str):
                text_content = msg.content
            elif isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_content += block.get("text", "")

            if text_content:
                truncation_info = get_content_truncation(text_content)
                if truncation_info:
                    # Add this message first, then a synthetic user message about truncation
                    modified_messages.append(msg)
                    modified_messages.append(AnthropicMessage(
                        role="user",
                        content=[{"type": "text", "text": generate_truncation_user_message()}]
                    ))
                    content_notices_added += 1
                    logger.debug(f"Added truncation notice after assistant message (hash: {truncation_info.message_hash})")
                    continue

        modified_messages.append(msg)

    if tool_results_modified > 0 or content_notices_added > 0:
        request_data.messages = modified_messages
        logger.info(f"Truncation recovery: modified {tool_results_modified} tool_result(s), added {content_notices_added} content notice(s)")


def log_kiro_payload(kiro_payload: Dict[str, Any]) -> None:
    """
    Serialize the Kiro payload into the debug log, only when debug logging is on.

    Args:
        kiro_payload: Payload sent to Kiro
    """
    if debug_logger is None or not debug_logger.enabled:
        return
    try:
        kiro_request_body = json.dumps(kiro_payload, ensure_ascii=False, indent=2).encode('utf-8')
        debug_logger.log_kiro_request_body(kiro_request_body)
    except (TypeError, ValueError) as e:
        logger.warning(f"Failed to log Kiro request: {e}")


def normalize_anthropic_stop_sequences(stop_sequences: Optional[List[str]]) -> Optional[List[str]]:
    """
    Drop empty/non-string entries from Anthropic stop_sequences.

    Args:
        stop_sequences: Raw stop_sequences from the request

    Returns:
        Cleaned list, or None if empty
    """
    cleaned = [s for s in (stop_sequences or []) if isinstance(s, str) and s]
    return cleaned or None


async def build_anthropic_success_response(
    request: Request,
    request_data: AnthropicMessagesRequest,
    http_client: KiroHttpClient,
    response: httpx.Response,
    url: str,
    kiro_payload: Dict[str, Any],
    model_cache: ModelInfoCache,
    auth_manager: KiroAuthManager,
    messages_for_tokenizer: List[Dict[str, Any]],
    tools_for_tokenizer: Optional[List[Dict[str, Any]]],
    system_for_tokenizer: Any,
) -> Response:
    """
    Turn an accepted (200) Kiro response into the client response.

    Shared by the account-system and legacy code paths so streaming and
    non-streaming behaviour stays identical in both.

    Args:
        request: Incoming request (used for disconnect detection)
        request_data: Parsed Anthropic request
        http_client: Kiro HTTP client (closed when done)
        response: Upstream 200 response
        url: Kiro endpoint (for first-token retries)
        kiro_payload: Payload sent to Kiro (for first-token retries)
        model_cache: Model metadata cache
        auth_manager: Account auth manager
        messages_for_tokenizer: Messages as dicts for fallback token counting
        tools_for_tokenizer: Tools as dicts for fallback token counting
        system_for_tokenizer: System prompt for fallback token counting

    Returns:
        StreamingResponse (stream=True) or JSONResponse
    """
    stop_sequences = normalize_anthropic_stop_sequences(request_data.stop_sequences)

    if request_data.stream:
        stream_fn = stream_with_first_token_retry_anthropic
        extra_kwargs = supported_kwargs(stream_fn, stop_sequences=stop_sequences)

        async def stream_wrapper():
            streaming_error = None
            client_disconnected = False
            try:
                async def make_retry_request():
                    return await http_client.request_with_retry(
                        "POST", url, kiro_payload, stream=True, max_retries=FIRST_TOKEN_INNER_HTTP_RETRIES
                    )

                async for chunk in stream_fn(
                    make_request=make_retry_request,
                    model=request_data.model,
                    model_cache=model_cache,
                    auth_manager=auth_manager,
                    initial_response=response,
                    request_messages=messages_for_tokenizer,
                    request_tools=tools_for_tokenizer,
                    request_system=system_for_tokenizer,
                    **extra_kwargs,
                ):
                    yield chunk
            except GeneratorExit:
                client_disconnected = True
                logger.debug("Client disconnected during streaming (GeneratorExit in routes)")
            except Exception as e:
                streaming_error = e
                # Send error event to client, then gracefully end the stream
                try:
                    yield format_anthropic_stream_error(e)
                except Exception:
                    pass
            finally:
                await http_client.close()
                if streaming_error:
                    error_type = type(streaming_error).__name__
                    error_msg = str(streaming_error) if str(streaming_error) else "(empty message)"
                    logger.error(f"HTTP 500 - POST /v1/messages (streaming) - [{error_type}] {error_msg[:100]}")
                elif client_disconnected:
                    logger.info("HTTP 200 - POST /v1/messages (streaming) - client disconnected")
                else:
                    logger.info("HTTP 200 - POST /v1/messages (streaming) - completed")

                if debug_logger:
                    if streaming_error:
                        debug_logger.flush_on_error(500, str(streaming_error))
                    else:
                        debug_logger.discard_buffers()

        return StreamingResponse(
            stream_wrapper(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )

    # Non-streaming mode - collect entire response, abandoning it if the client leaves
    collect_fn = collect_anthropic_response
    collect_kwargs = supported_kwargs(collect_fn, stop_sequences=stop_sequences)
    try:
        anthropic_response = await run_until_disconnected(
            request,
            collect_fn(
                response,
                request_data.model,
                model_cache,
                auth_manager,
                request_messages=messages_for_tokenizer,
                request_tools=tools_for_tokenizer,
                request_system=system_for_tokenizer,
                **collect_kwargs,
            ),
        )
    except ClientDisconnectedError:
        await close_upstream_response(response)
        await http_client.close()
        logger.info("HTTP 499 - POST /v1/messages (non-streaming) - client disconnected, upstream cancelled")
        if debug_logger:
            debug_logger.discard_buffers()
        return Response(status_code=CLIENT_CLOSED_REQUEST_STATUS)

    await http_client.close()
    logger.info("HTTP 200 - POST /v1/messages (non-streaming) - completed")

    if debug_logger:
        debug_logger.discard_buffers()

    return JSONResponse(content=anthropic_response)


# --- Router ---
router = APIRouter(tags=["Anthropic API"])


@router.post("/v1/messages", dependencies=[Depends(verify_anthropic_api_key)])
async def messages(
    request: Request,
    request_data: AnthropicMessagesRequest,
    anthropic_version: Optional[str] = Header(None, alias="anthropic-version")
):
    """
    Anthropic Messages API endpoint.
    
    Compatible with Anthropic's /v1/messages endpoint.
    Accepts requests in Anthropic format and translates them to Kiro API.
    
    Required headers:
    - x-api-key: Your API key (or Authorization: Bearer)
    - anthropic-version: API version (optional, for compatibility)
    - Content-Type: application/json
    
    Args:
        request: FastAPI Request for accessing app.state
        request_data: Request in Anthropic MessagesRequest format
        anthropic_version: Anthropic API version header (optional)
    
    Returns:
        StreamingResponse for streaming mode (SSE)
        JSONResponse for non-streaming mode
    
    Raises:
        HTTPException: On validation or API errors
    """
    logger.info(f"Request to /v1/messages (model={request_data.model}, stream={request_data.stream})")
    
    if anthropic_version:
        logger.debug(f"Anthropic-Version header: {anthropic_version}")
    
    # Note: prepare_new_request() and log_request_body() are now called by DebugLoggerMiddleware
    # This ensures debug logging works even for requests that fail Pydantic validation (422 errors)
    
    # Check for truncation recovery opportunities (no-op unless something is pending)
    apply_anthropic_truncation_recovery(request_data)

    # ==============================================================================
    # WebSearch Support - Path B: Auto-Injection (MCP Tool Emulation)
    # ==============================================================================
    
    # Auto-inject web_search tool if enabled (Path B - MCP emulation)
    if WEB_SEARCH_ENABLED:
        if request_data.tools is None:
            request_data.tools = []
        
        # Check if web_search already exists (by name)
        has_ws = any(
            getattr(tool, "name", "") == "web_search"
            for tool in request_data.tools
        )
        
        if not has_ws:
            from kiro.models_anthropic import AnthropicTool
            web_search_tool = AnthropicTool(
                name="web_search",
                description="Search the web for current information. Use when you need up-to-date data from the internet.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"}
                    },
                    "required": ["query"]
                }
            )
            request_data.tools.append(web_search_tool)
            logger.debug("Auto-injected web_search tool for MCP emulation (Path B)")
    
    # ==============================================================================
    # WebSearch Support - Path A: Native Anthropic (Early Return)
    # ==============================================================================
    
    # Check for native Anthropic server-side tool (Path A)
    # This works ALWAYS, regardless of WEB_SEARCH_ENABLED setting
    if request_data.tools:
        for tool in request_data.tools:
            tool_type = getattr(tool, "type", None)
            if tool_type and tool_type.startswith("web_search"):
                # Path A: Early return, direct MCP call
                # Get auth_manager from first available account (no failover needed for early return)
                account = request.app.state.account_manager.get_first_account()
                if not account.auth_manager:
                    logger.error("No initialized accounts available for native web_search")
                    return anthropic_error_response(503, "No initialized accounts available")
                auth_manager = account.auth_manager
                
                logger.info("Detected native Anthropic web_search (Path A), routing to MCP API")
                return await handle_native_web_search(request, request_data, auth_manager, api_format="anthropic")
    
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
        last_error_headers = None  # Retry-After from the last upstream 429/503, if any
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
                    return anthropic_error_response(
                        last_error_status or 503,
                        last_error_message or "Account unavailable",
                        last_error_headers,
                    )
                else:
                    # Multiple accounts - generic error with context
                    detail = "No available accounts for this model."
                    if last_error_message:
                        detail += f" Error from last account: {last_error_message}"
                    return anthropic_error_response(503, detail)
            
            # Mark account as tried in current failover loop
            tried_accounts.add(account.id)
            
            # Use objects from account
            auth_manager = account.auth_manager
            model_cache = account.model_cache
            model_resolver = account.model_resolver
            
            # Generate conversation ID
            conversation_id = generate_conversation_id()
            
            # Build payload for Kiro
            # profileArn is required by runtime.kiro.dev for all auth types
            profile_arn_for_payload = auth_manager.profile_arn or PROFILE_ARN or ""
            
            try:
                kiro_payload = anthropic_to_kiro(
                    request_data,
                    conversation_id,
                    profile_arn_for_payload
                )
            except ValueError as e:
                logger.error(f"Conversion error: {e}")
                return anthropic_error_response(400, str(e))
            
            # Log Kiro payload (serialized only when debug logging is enabled)
            log_kiro_payload(kiro_payload)
            
            # Create HTTP client
            url = f"{auth_manager.api_host}/generateAssistantResponse"
            logger.debug(f"Kiro API URL: {url} (account: {account.id})")
            
            if request_data.stream:
                http_client = KiroHttpClient(auth_manager, shared_client=None)
            else:
                shared_client = request.app.state.http_client
                http_client = KiroHttpClient(auth_manager, shared_client=shared_client)
            
            # Prepare data for token counting
            messages_for_tokenizer = [msg.model_dump() for msg in request_data.messages]
            tools_for_tokenizer = [tool.model_dump() for tool in request_data.tools] if request_data.tools else None
            if isinstance(request_data.system, list):
                system_for_tokenizer = [b.model_dump() if hasattr(b, "model_dump") else b for b in request_data.system]
            else:
                system_for_tokenizer = request_data.system
            
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
                    
                    return await build_anthropic_success_response(
                        request, request_data, http_client, response, url, kiro_payload,
                        model_cache, auth_manager,
                        messages_for_tokenizer, tools_for_tokenizer, system_for_tokenizer,
                    )
                
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
                    
                    last_error_headers = retry_after_headers(
                        response.status_code, getattr(response, "headers", None)
                    )

                    # Classify error
                    error_type = classify_error(response.status_code, error_reason)
                    
                    if error_type == ErrorType.FATAL:
                        # FATAL - return to client immediately
                        await account_manager.report_failure(
                            account.id, request_data.model, error_type,
                            response.status_code, error_reason
                        )
                        
                        logger.warning(f"HTTP {response.status_code} - POST /v1/messages - {last_error_message[:100]}")
                        
                        if debug_logger:
                            debug_logger.flush_on_error(response.status_code, last_error_message)
                        
                        return anthropic_error_response(
                            response.status_code, last_error_message, getattr(response, "headers", None)
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
                    last_error_headers = None
                    
                    # Single account - no point in failover, break immediately
                    if len(all_accounts) == 1:
                        break
                    
                    logger.warning(f"Network error on account {account.id}, trying next account")
                    continue  # Try next account
                
                # All other HTTPException (400, 500, etc.) = application errors
                # These come from build_kiro_payload() or other places → re-raise immediately
                logger.error(f"HTTP {e.status_code} - POST /v1/messages - {e.detail}")
                if debug_logger:
                    debug_logger.flush_on_error(e.status_code, str(e.detail))
                raise
            except Exception as e:
                await http_client.close()
                logger.error(f"Internal error: {e}", exc_info=True)
                logger.error(f"HTTP 500 - POST /v1/messages - {str(e)[:100]}")
                if debug_logger:
                    debug_logger.flush_on_error(500, str(e))
                
                return anthropic_error_response(500, f"Internal Server Error: {str(e)}")
        
        # All attempts exhausted
        if len(all_accounts) == 1:
            # Single account - return its original error
            # last_error_status and last_error_message are guaranteed to be set
            return anthropic_error_response(last_error_status, last_error_message, last_error_headers)
        else:
            # Multiple accounts - generic error with context
            detail = "All accounts failed after full circle."
            if last_error_message:
                detail += f" Error from last account: {last_error_message}"
            return anthropic_error_response(503, detail)
    
    else:
        # ==============================================================================
        # LEGACY MODE: Single Account (no failover)
        # ==============================================================================
        account = request.app.state.account_manager.get_first_account()
        if not account.auth_manager:
            logger.error("No initialized accounts available (legacy mode)")
            return anthropic_error_response(503, "No initialized accounts available")
        auth_manager = account.auth_manager
        model_cache = account.model_cache
        model_resolver = account.model_resolver
    
    # ==============================================================================
    # Normal Flow (Path B will be intercepted in streaming, or no web_search)
    # ==============================================================================
    
    # Generate conversation ID for Kiro API (random UUID, not used for tracking)
    conversation_id = generate_conversation_id()
    
    # Build payload for Kiro
    # profileArn is required by runtime.kiro.dev for all auth types
    profile_arn_for_payload = auth_manager.profile_arn or PROFILE_ARN or ""
    
    try:
        kiro_payload = anthropic_to_kiro(
            request_data,
            conversation_id,
            profile_arn_for_payload
        )
    except ValueError as e:
        logger.error(f"Conversion error: {e}")
        return anthropic_error_response(400, str(e))
    
    # Log Kiro payload (serialized only when debug logging is enabled)
    log_kiro_payload(kiro_payload)
    
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
    
    # Prepare data for token counting
    # Convert Pydantic models to dicts for tokenizer
    messages_for_tokenizer = [msg.model_dump() for msg in request_data.messages]
    tools_for_tokenizer = [tool.model_dump() for tool in request_data.tools] if request_data.tools else None
    # Serialize system prompt (may be a list of Pydantic objects)
    if isinstance(request_data.system, list):
        system_for_tokenizer = [b.model_dump() if hasattr(b, "model_dump") else b for b in request_data.system]
    else:
        system_for_tokenizer = request_data.system
    
    try:
        # Make request to Kiro API (for both streaming and non-streaming modes)
        # Important: we wait for Kiro response BEFORE returning StreamingResponse,
        # so that we can return proper HTTP error codes if Kiro fails
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
                f"HTTP {response.status_code} - POST /v1/messages - {error_message[:100]}"
            )
            
            # Flush debug logs on error
            if debug_logger:
                debug_logger.flush_on_error(response.status_code, error_message)
            
            # Return error in Anthropic format
            return anthropic_error_response(
                response.status_code, error_message, getattr(response, "headers", None)
            )
        
        return await build_anthropic_success_response(
            request, request_data, http_client, response, url, kiro_payload,
            model_cache, auth_manager,
            messages_for_tokenizer, tools_for_tokenizer, system_for_tokenizer,
        )
    
    except HTTPException as e:
        await http_client.close()
        
        # Network errors (502/504 from request_with_retry) = RECOVERABLE
        # In legacy mode, we still log them but re-raise (no failover available)
        if e.status_code in (502, 504):
            logger.warning(f"Network error (legacy mode, no failover available)")
        
        logger.error(f"HTTP {e.status_code} - POST /v1/messages - {e.detail}")
        if debug_logger:
            debug_logger.flush_on_error(e.status_code, str(e.detail))
        raise
    except Exception as e:
        await http_client.close()
        logger.error(f"Internal error: {e}", exc_info=True)
        logger.error(f"HTTP 500 - POST /v1/messages - {str(e)[:100]}")
        if debug_logger:
            debug_logger.flush_on_error(500, str(e))
        
        return anthropic_error_response(500, f"Internal Server Error: {str(e)}")


@router.post("/v1/messages/count_tokens", dependencies=[Depends(verify_anthropic_api_key)])
async def count_tokens_endpoint(
    request: Request,
    request_data: AnthropicCountTokensRequest,
):
    """
    Anthropic Count Tokens API endpoint.
    
    Returns estimated token count for the given request payload.
    Used by Claude Code to decide when to trigger conversation compaction.
    
    Uses the same fallback estimation as Anthropic streaming (message_start event),
    since Kiro API only provides accurate token counts after request completion.
    This endpoint is called BEFORE the actual request, so we cannot use Kiro's
    contextUsagePercentage (which is only available after generation completes).
    
    Args:
        request: FastAPI Request for accessing app.state
        request_data: Request in Anthropic MessagesRequest format
    
    Returns:
        JSONResponse with {"input_tokens": int}
    
    Raises:
        HTTPException: 401 if authentication fails (handled by dependency)
    """
    logger.info(f"Request to /v1/messages/count_tokens (model={request_data.model}, messages={len(request_data.messages)})")
    
    # Prepare data for tokenizer (same format as streaming message_start)
    messages_for_tokenizer = [msg.model_dump() for msg in request_data.messages]
    tools_for_tokenizer = [tool.model_dump() for tool in request_data.tools] if request_data.tools else None
    
    # Handle system prompt (can be string or list of content blocks)
    if isinstance(request_data.system, list):
        system_for_tokenizer = [b.model_dump() if hasattr(b, "model_dump") else b for b in request_data.system]
    else:
        system_for_tokenizer = request_data.system
    
    # Use the SAME estimation logic as Anthropic streaming message_start
    request_token_stats = estimate_request_tokens(
        messages=messages_for_tokenizer,
        tools=tools_for_tokenizer,
        system_prompt=system_for_tokenizer,
        apply_claude_correction=True  # CRITICAL: Enable correction for Claude models
    )
    
    input_tokens = request_token_stats["total_tokens"]
    
    logger.info(f"Token count estimate: {input_tokens} tokens")
    
    return JSONResponse(content={"input_tokens": input_tokens})
