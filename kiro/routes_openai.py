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

import asyncio
import inspect
import json
import time
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Awaitable, Callable, Dict, FrozenSet, List, Optional, Tuple, Union

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Security
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import APIKeyHeader
from loguru import logger

from kiro.config import (
    PROXY_API_KEY,
    APP_VERSION,
    PROFILE_ARN,
    ACCOUNT_RECOVERY_TIMEOUT,
    ACCOUNT_MAX_BACKOFF_MULTIPLIER,
)
from kiro.models_openai import (
    OpenAIModel,
    ModelList,
    ChatCompletionRequest,
    PROCESS_START_TIME,
)
from kiro.exceptions import build_openai_error, retry_after_headers
from kiro.auth import KiroAuthManager, AuthType
from kiro.cache import ModelInfoCache
from kiro.model_resolver import ModelResolver, normalize_model_name
from kiro.converters_openai import build_kiro_payload
from kiro.streaming_openai import stream_kiro_to_openai, collect_stream_response, stream_with_first_token_retry
from kiro.http_client import KiroHttpClient
from kiro.utils import generate_conversation_id
from kiro.config import WEB_SEARCH_ENABLED, FIRST_TOKEN_INNER_HTTP_RETRIES
from kiro.mcp_tools import handle_native_web_search

# Import debug_logger
try:
    from kiro.debug_logger import debug_logger
except ImportError:
    debug_logger = None


# --- Security scheme ---
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)
# Anthropic SDKs list models with x-api-key instead of Authorization: Bearer
x_api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

# Interval between client-disconnect checks while collecting a non-streaming response
DISCONNECT_POLL_INTERVAL_SECONDS: float = 1.0

# Status logged when the client goes away before a non-streaming response is ready
# (nginx convention "client closed request"; never actually delivered)
CLIENT_CLOSED_REQUEST_STATUS: int = 499


class ClientDisconnectedError(Exception):
    """Raised when the client disconnects while a non-streaming response is being collected."""


async def run_until_disconnected(
    request: Request,
    awaitable: Awaitable[Any],
    poll_interval: float = DISCONNECT_POLL_INTERVAL_SECONDS,
) -> Any:
    """
    Await a coroutine, cancelling it if the HTTP client disconnects meanwhile.

    Non-streaming requests otherwise keep consuming the upstream Kiro stream
    (and the account's quota) after the client has gone away.

    Args:
        request: Incoming request, polled via request.is_disconnected()
        awaitable: Work to run (e.g. collecting the upstream stream)
        poll_interval: Seconds between disconnect checks

    Returns:
        The awaitable's result

    Raises:
        ClientDisconnectedError: If the client disconnected first (the work is cancelled)
    """
    task = asyncio.ensure_future(awaitable)
    is_disconnected = getattr(request, "is_disconnected", None)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=poll_interval)
            if task in done:
                return task.result()
            if is_disconnected is None:
                continue
            try:
                disconnected = await is_disconnected()
            except TypeError:
                # Not an awaitable check (non-Starlette request object): stop polling
                is_disconnected = None
                continue
            if disconnected is True:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise ClientDisconnectedError()
    except asyncio.CancelledError:
        task.cancel()
        raise


async def close_upstream_response(response: Any) -> None:
    """
    Close an upstream httpx response, tolerating mocks and already-closed streams.

    Args:
        response: Upstream response (httpx.Response or test double)
    """
    aclose = getattr(response, "aclose", None)
    if not callable(aclose):
        return
    try:
        result = aclose()
        if inspect.isawaitable(result):
            await result
    except (httpx.HTTPError, OSError, RuntimeError) as e:
        logger.debug(f"Error closing upstream response after client disconnect: {e}")


@lru_cache(maxsize=64)
def _accepted_kwargs(fn: Callable[..., Any]) -> Optional[FrozenSet[str]]:
    """
    Return the keyword names a callable accepts (None = accepts any via **kwargs).

    Cached per function object; used to pass optional streaming options only
    to functions that support them.

    Args:
        fn: Target callable

    Returns:
        Frozen set of parameter names, or None if the callable takes **kwargs
        or its signature cannot be inspected
    """
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return None
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return None
    return frozenset(params)


def supported_kwargs(fn: Callable[..., Any], **candidates: Any) -> Dict[str, Any]:
    """
    Filter optional keyword arguments down to those `fn` accepts.

    Candidates set to None/False/empty are dropped so callers stay identical to
    the previous call shape when the option is not used.

    Args:
        fn: Target callable
        **candidates: Optional keyword arguments

    Returns:
        Keyword arguments safe to pass to fn
    """
    accepted = _accepted_kwargs(fn)
    return {
        name: value
        for name, value in candidates.items()
        if value and (accepted is None or name in accepted)
    }


def normalize_stop_sequences(stop: Union[str, List[str], None]) -> Optional[List[str]]:
    """
    Normalize an OpenAI `stop` value to a list of non-empty strings.

    Args:
        stop: String, list of strings, or None

    Returns:
        List of stop sequences, or None if there are none
    """
    if stop is None:
        return None
    items = [stop] if isinstance(stop, str) else list(stop)
    sequences = [s for s in items if isinstance(s, str) and s]
    return sequences or None


def wants_stream_usage(stream_options: Any) -> bool:
    """
    Read stream_options.include_usage from an OpenAI request.

    Args:
        stream_options: Raw stream_options value (dict or None)

    Returns:
        True if the client asked for a usage chunk
    """
    return isinstance(stream_options, dict) and stream_options.get("include_usage") is True


def format_openai_stream_error(error: Exception) -> str:
    """
    Build an SSE data frame reporting a mid-stream failure in OpenAI error shape.

    Args:
        error: Exception that interrupted the stream

    Returns:
        SSE frame "data: {"error": {...}}\\n\\n"
    """
    message = str(getattr(error, "detail", None) or error) or type(error).__name__
    payload = {"error": {"message": message, "type": "api_error", "param": None, "code": None}}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def apply_openai_truncation_recovery(request_data: ChatCompletionRequest) -> None:
    """
    Prepend truncation notices for tool calls/content truncated in earlier responses.

    Skipped entirely when recovery is disabled or nothing is pending, so the
    common case costs one dict-size check instead of a scan over all messages.

    Args:
        request_data: Request whose messages may be replaced in place
    """
    from kiro.truncation_recovery import (
        should_inject_recovery,
        generate_truncation_tool_result,
        generate_truncation_user_message,
    )
    from kiro.truncation_state import get_tool_truncation, get_content_truncation, has_pending
    from kiro.models_openai import ChatMessage

    if not should_inject_recovery() or not has_pending():
        return

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
                modified_messages.append(msg.model_copy(update={"content": modified_content}))
                tool_results_modified += 1
                logger.debug(f"Modified tool_result for {msg.tool_call_id} to include truncation notice")
                continue

        # Check if this is an assistant message with truncated content
        if msg.role == "assistant" and msg.content and isinstance(msg.content, str):
            truncation_info = get_content_truncation(msg.content)
            if truncation_info:
                # Add this message first, then a synthetic user message about truncation
                modified_messages.append(msg)
                modified_messages.append(ChatMessage(role="user", content=generate_truncation_user_message()))
                content_notices_added += 1
                logger.debug(f"Added truncation notice after assistant message (hash: {truncation_info.message_hash})")
                continue

        modified_messages.append(msg)

    if tool_results_modified > 0 or content_notices_added > 0:
        request_data.messages = modified_messages
        logger.info(f"Truncation recovery: modified {tool_results_modified} tool_result(s), added {content_notices_added} content notice(s)")


def openai_upstream_error_response(status_code: int, message: str, upstream_headers: Any) -> JSONResponse:
    """
    Build the OpenAI-shaped response for a non-200 Kiro reply.

    Keeps the historical "kiro_api_error" type and numeric code (clients may
    match on them), adds "param", and forwards Retry-After on 429/503.

    Args:
        status_code: Upstream HTTP status
        message: User-facing error message
        upstream_headers: Upstream response headers

    Returns:
        JSONResponse with {"error": {"message", "type", "param", "code"}}
    """
    return JSONResponse(
        status_code=status_code,
        content=build_openai_error(message, status_code, error_type="kiro_api_error", code=status_code),
        headers=retry_after_headers(status_code, upstream_headers),
    )


async def build_openai_success_response(
    request: Request,
    request_data: ChatCompletionRequest,
    http_client: KiroHttpClient,
    response: httpx.Response,
    url: str,
    kiro_payload: Dict[str, Any],
    model_cache: ModelInfoCache,
    auth_manager: KiroAuthManager,
    stop_sequences: Optional[List[str]],
    include_usage: bool,
) -> Response:
    """
    Turn an accepted (200) Kiro response into the client response.

    Shared by the account-system and legacy code paths so streaming and
    non-streaming behaviour stays identical in both.

    Args:
        request: Incoming request (used for disconnect detection)
        request_data: Parsed OpenAI request
        http_client: Kiro HTTP client (closed when done)
        response: Upstream 200 response
        url: Kiro endpoint (for first-token retries)
        kiro_payload: Payload sent to Kiro (for first-token retries)
        model_cache: Model metadata cache
        auth_manager: Account auth manager
        stop_sequences: Normalized stop sequences, if any
        include_usage: stream_options.include_usage

    Returns:
        StreamingResponse (stream=True) or JSONResponse
    """
    # Prepare data for fallback token counting
    messages_for_tokenizer = [msg.model_dump() for msg in request_data.messages]
    tools_for_tokenizer = [tool.model_dump() for tool in request_data.tools] if request_data.tools else None

    if request_data.stream:
        stream_fn = stream_with_first_token_retry
        extra_kwargs = supported_kwargs(stream_fn, include_usage=include_usage, stop_sequences=stop_sequences)

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
                    client=http_client.client,
                    model=request_data.model,
                    model_cache=model_cache,
                    auth_manager=auth_manager,
                    initial_response=response,
                    request_messages=messages_for_tokenizer,
                    request_tools=tools_for_tokenizer,
                    **extra_kwargs,
                ):
                    yield chunk
            except GeneratorExit:
                # Client disconnected - this is normal
                client_disconnected = True
                logger.debug("Client disconnected during streaming (GeneratorExit in routes)")
            except Exception as e:
                streaming_error = e
                # Report the failure in-band so clients don't mistake it for a clean
                # finish, then send [DONE] so they don't hang waiting for data
                try:
                    yield format_openai_stream_error(e)
                    yield "data: [DONE]\n\n"
                except Exception:
                    pass  # Client already disconnected
                raise
            finally:
                await http_client.close()
                if streaming_error:
                    error_type = type(streaming_error).__name__
                    error_msg = str(streaming_error) if str(streaming_error) else "(empty message)"
                    logger.error(f"HTTP 500 - POST /v1/chat/completions (streaming) - [{error_type}] {error_msg[:100]}")
                elif client_disconnected:
                    logger.info("HTTP 200 - POST /v1/chat/completions (streaming) - client disconnected")
                else:
                    logger.info("HTTP 200 - POST /v1/chat/completions (streaming) - completed")
                # Write debug logs AFTER streaming completes
                if debug_logger:
                    if streaming_error:
                        debug_logger.flush_on_error(500, str(streaming_error))
                    else:
                        debug_logger.discard_buffers()

        return StreamingResponse(stream_wrapper(), media_type="text/event-stream")

    # Non-streaming mode - collect entire response, abandoning it if the client leaves
    collect_fn = collect_stream_response
    collect_kwargs = supported_kwargs(collect_fn, stop_sequences=stop_sequences)
    try:
        openai_response = await run_until_disconnected(
            request,
            collect_fn(
                http_client.client,
                response,
                request_data.model,
                model_cache,
                auth_manager,
                request_messages=messages_for_tokenizer,
                request_tools=tools_for_tokenizer,
                **collect_kwargs,
            ),
        )
    except ClientDisconnectedError:
        await close_upstream_response(response)
        await http_client.close()
        logger.info("HTTP 499 - POST /v1/chat/completions (non-streaming) - client disconnected, upstream cancelled")
        if debug_logger:
            debug_logger.discard_buffers()
        return Response(status_code=CLIENT_CLOSED_REQUEST_STATUS)

    await http_client.close()
    logger.info("HTTP 200 - POST /v1/chat/completions (non-streaming) - completed")

    # Write debug logs after non-streaming request completes
    if debug_logger:
        debug_logger.discard_buffers()

    return JSONResponse(content=openai_response)


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


async def verify_api_key(auth_header: str = Security(api_key_header)) -> bool:
    """
    Verify API key in Authorization header.
    
    Expects format: "Bearer {PROXY_API_KEY}"
    
    Args:
        auth_header: Authorization header value
    
    Returns:
        True if key is valid
    
    Raises:
        HTTPException: 401 if key is invalid or missing
    """
    if not auth_header or auth_header != f"Bearer {PROXY_API_KEY}":
        logger.warning("Access attempt with invalid API key.")
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    return True


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


async def verify_models_api_key(
    auth_header: Optional[str] = Security(api_key_header),
    x_api_key: Optional[str] = Security(x_api_key_header),
) -> bool:
    """
    Verify API key for the models endpoints, accepting both client conventions.

    OpenAI SDKs send "Authorization: Bearer {key}", Anthropic SDKs send "x-api-key: {key}".

    Args:
        auth_header: Authorization header value
        x_api_key: x-api-key header value

    Returns:
        True if either header carries the valid key

    Raises:
        HTTPException: 401 if neither header is valid
    """
    if x_api_key and x_api_key == PROXY_API_KEY:
        return True
    if auth_header and auth_header == f"Bearer {PROXY_API_KEY}":
        return True
    logger.warning("Access attempt with invalid API key (models endpoint).")
    raise HTTPException(status_code=401, detail="Invalid or missing API Key")


def _is_account_usable(account: Any, single_account: bool, now: float) -> bool:
    """
    Decide whether an account can currently serve requests (Circuit Breaker view).

    Mirrors AccountManager.get_next_account(): a single account is always tried;
    otherwise an account in its failure backoff window is not usable.

    Args:
        account: Account object (failures, last_failure_time)
        single_account: True if it is the only configured account
        now: Current Unix time

    Returns:
        True if the account is usable
    """
    if single_account:
        return True
    failures = getattr(account, "failures", 0)
    if not isinstance(failures, int) or failures <= 0:
        return True
    last_failure = getattr(account, "last_failure_time", 0.0)
    if not isinstance(last_failure, (int, float)):
        return True
    backoff = ACCOUNT_RECOVERY_TIMEOUT * min(2 ** (failures - 1), ACCOUNT_MAX_BACKOFF_MULTIPLIER)
    return now - last_failure >= backoff


def count_usable_accounts(account_manager: Any) -> Optional[Tuple[int, int]]:
    """
    Count configured and currently usable accounts.

    Args:
        account_manager: AccountManager from app.state (or None)

    Returns:
        (total, usable), or None if no account manager / accounts mapping exists
    """
    accounts = getattr(account_manager, "_accounts", None) if account_manager is not None else None
    if not isinstance(accounts, dict):
        return None
    now = time.time()
    single = len(accounts) == 1
    usable = sum(1 for account in accounts.values() if _is_account_usable(account, single, now))
    return len(accounts), usable


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    """
    Detailed health check.

    Includes account counts when the account manager is running. Returns 503
    with status "unhealthy" only when accounts exist and none is usable.

    Args:
        request: FastAPI Request for accessing app.state

    Returns:
        Status, timestamp, version and (when available) account counts
    """
    body: Dict[str, Any] = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": APP_VERSION
    }
    counts = count_usable_accounts(getattr(request.app.state, "account_manager", None))
    if counts is None:
        return JSONResponse(content=body)
    total, usable = counts
    body["accounts_total"] = total
    body["accounts_usable"] = usable
    if usable == 0:
        body["status"] = "unhealthy"
        logger.warning(f"Health check: 0 of {total} accounts usable")
        return JSONResponse(status_code=503, content=body)
    return JSONResponse(content=body)

# Memoized /v1/models body: (model ids it was built from, serialized JSON bytes).
# Rebuilt only when the set/order of available model ids changes.
_models_response_cache: Optional[Tuple[Tuple[str, ...], bytes]] = None


def _build_models_body(model_ids: Tuple[str, ...]) -> bytes:
    """
    Serialize the OpenAI-format model list for the given ids, reusing a memoized body.

    Args:
        model_ids: Ordered tuple of available model ids

    Returns:
        JSON bytes of ModelList (object/data[id, object, created, owned_by, description])
    """
    global _models_response_cache
    cached = _models_response_cache
    if cached is not None and cached[0] == model_ids:
        return cached[1]

    body = ModelList(
        data=[
            OpenAIModel(
                id=model_id,
                owned_by="anthropic",
                description="Claude model via Kiro API"
            )
            for model_id in model_ids
        ]
    ).model_dump_json().encode("utf-8")
    _models_response_cache = (model_ids, body)
    logger.debug(f"[Models] Rebuilt /v1/models response ({len(model_ids)} models)")
    return body


def _available_model_ids(request: Request) -> Tuple[str, ...]:
    """
    Collect available model ids for the current mode.

    Args:
        request: FastAPI Request for accessing app.state

    Returns:
        Ordered tuple of model ids
    """
    if request.app.state.account_system:
        # Account system: collect models from all initialized accounts
        return tuple(request.app.state.account_manager.get_all_available_models())
    # Legacy: use resolver from first account
    account = request.app.state.account_manager.get_first_account()
    return tuple(account.model_resolver.get_available_models())


def _anthropic_model_object(model_id: str) -> Dict[str, Any]:
    """
    Build a model object in Anthropic Models API shape.

    Args:
        model_id: Model id

    Returns:
        {"type": "model", "id", "display_name", "created_at"}
    """
    return {
        "type": "model",
        "id": model_id,
        "display_name": model_id,
        "created_at": datetime.fromtimestamp(PROCESS_START_TIME, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _openai_model_object(model_id: str) -> Dict[str, Any]:
    """
    Build a model object in OpenAI shape (same fields as the /v1/models list entries).

    Args:
        model_id: Model id

    Returns:
        OpenAIModel as a dict
    """
    return OpenAIModel(
        id=model_id,
        owned_by="anthropic",
        description="Claude model via Kiro API"
    ).model_dump()


def _wants_anthropic_models(request: Request) -> bool:
    """
    Check whether the client asked for the Anthropic Models API shape.

    Args:
        request: Incoming request

    Returns:
        True if a non-empty anthropic-version header is present
    """
    headers = getattr(request, "headers", None)
    getter = getattr(headers, "get", None)
    value = getter("anthropic-version") if callable(getter) else None
    return isinstance(value, str) and bool(value)


def _find_model_id(model_id: str, available: Tuple[str, ...]) -> Optional[str]:
    """
    Find a requested model id among available ids, accepting client name formats.

    Args:
        model_id: Requested id (e.g. "claude-sonnet-4-5" or "claude-sonnet-4.5")
        available: Available ids

    Returns:
        Matching available id, or None
    """
    if model_id in available:
        return model_id
    normalized = normalize_model_name(model_id)
    if normalized in available:
        return normalized
    return None


@router.get(
    "/v1/models",
    dependencies=[Depends(verify_models_api_key)],
    responses={200: {"model": ModelList}},
)
async def get_models(request: Request) -> Response:
    """
    Return list of available models.

    Models are loaded at startup (blocking) and cached.
    The serialized OpenAI response is memoized per set of available model ids.
    Requests carrying an anthropic-version header get the Anthropic list shape.

    Args:
        request: FastAPI Request for accessing app.state

    Returns:
        JSON response with ModelList schema (models in consistent format, with dots),
        or the Anthropic {data, has_more, first_id, last_id} shape
    """
    logger.debug("Request to /v1/models")

    available_model_ids = _available_model_ids(request)

    if _wants_anthropic_models(request):
        data = [_anthropic_model_object(model_id) for model_id in available_model_ids]
        return JSONResponse(content={
            "data": data,
            "has_more": False,
            "first_id": data[0]["id"] if data else None,
            "last_id": data[-1]["id"] if data else None,
        })

    body = _build_models_body(available_model_ids)
    return Response(content=body, media_type="application/json")


@router.get("/v1/models/{model_id:path}", dependencies=[Depends(verify_models_api_key)])
async def get_model(request: Request, model_id: str) -> JSONResponse:
    """
    Return a single model object (OpenAI shape, or Anthropic with anthropic-version).

    Args:
        request: FastAPI Request for accessing app.state
        model_id: Requested model id

    Returns:
        JSON model object

    Raises:
        HTTPException: 404 if the model is not available
    """
    logger.debug(f"Request to /v1/models/{model_id}")
    found = _find_model_id(model_id, _available_model_ids(request))
    if found is None:
        raise HTTPException(status_code=404, detail=f"The model '{model_id}' does not exist or is not available.")
    if _wants_anthropic_models(request):
        return JSONResponse(content=_anthropic_model_object(found))
    return JSONResponse(content=_openai_model_object(found))


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
    
    # OpenAI "n" (number of choices): Kiro returns a single completion
    if request_data.n is not None and request_data.n != 1:
        logger.warning(f"HTTP 400 - POST /v1/chat/completions - unsupported n={request_data.n}")
        return JSONResponse(
            status_code=400,
            content=build_openai_error(
                "n>1 is not supported: Kiro API returns a single completion per request. Send n=1 or omit it.",
                400,
                param="n",
            ),
        )
    
    # Check for truncation recovery opportunities (no-op unless something is pending)
    apply_openai_truncation_recovery(request_data)
    
    # Optional streaming options, forwarded only to stream functions that accept them
    stop_sequences = normalize_stop_sequences(request_data.stop)
    include_usage = wants_stream_usage(request_data.stream_options)
    
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
                    raise HTTPException(
                        status_code=last_error_status or 503,
                        detail=last_error_message or "Account unavailable",
                        headers=last_error_headers,
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
            # profileArn is required by runtime.kiro.dev for all auth types
            profile_arn_for_payload = auth_manager.profile_arn or PROFILE_ARN or ""
            
            try:
                kiro_payload = build_kiro_payload(
                    request_data,
                    conversation_id,
                    profile_arn_for_payload
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            
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
                    
                    return await build_openai_success_response(
                        request, request_data, http_client, response, url, kiro_payload,
                        model_cache, auth_manager, stop_sequences, include_usage,
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
                        
                        logger.warning(f"HTTP {response.status_code} - POST /v1/chat/completions - {last_error_message[:100]}")
                        
                        if debug_logger:
                            debug_logger.flush_on_error(response.status_code, last_error_message)
                        
                        return openai_upstream_error_response(
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
                detail=last_error_message,
                headers=last_error_headers,
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
    # profileArn is required by runtime.kiro.dev for all auth types
    profile_arn_for_payload = auth_manager.profile_arn or PROFILE_ARN or ""
    
    try:
        kiro_payload = build_kiro_payload(
            request_data,
            conversation_id,
            profile_arn_for_payload
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
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
            return openai_upstream_error_response(
                response.status_code, error_message, getattr(response, "headers", None)
            )
        
        return await build_openai_success_response(
            request, request_data, http_client, response, url, kiro_payload,
            model_cache, auth_manager, stop_sequences, include_usage,
        )
    
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