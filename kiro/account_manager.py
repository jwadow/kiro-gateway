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
Unified Account System for Kiro Gateway.

Manages multiple Kiro accounts with intelligent failover, sticky behavior,
and circuit breaker pattern for reliability.

Key features:
- Lazy initialization (only first working account at startup)
- Sticky behavior (prefer successful account)
- Circuit breaker with exponential backoff
- Probabilistic retry for "dead" accounts
- TTL-based model cache refresh (only when using account)
- Atomic state persistence
"""

import asyncio
import hashlib
import json
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import httpx
from loguru import logger

from kiro.auth import KiroAuthManager, AuthType
from kiro.cache import ModelInfoCache
from kiro.model_resolver import ModelResolver, normalize_model_name
from kiro.config import (
    HIDDEN_MODELS,
    MODEL_ALIASES,
    HIDDEN_FROM_LIST,
    ACCOUNT_RECOVERY_TIMEOUT,
    ACCOUNT_MAX_BACKOFF_MULTIPLIER,
    ACCOUNT_PROBABILISTIC_RETRY_CHANCE,
    ACCOUNT_CACHE_TTL,
    STATE_SAVE_INTERVAL_SECONDS,
    FALLBACK_MODELS,
    CANDIDATE_MODELS,
    ACCOUNT_CACHE_RETRY_INTERVAL,
    MODEL_PROBING_ENABLED,
    MODEL_DISCOVERY_TIMEOUT,
)
from kiro.utils import get_kiro_headers
from kiro.account_errors import ErrorType


def _is_runtime_endpoint(auth_manager: KiroAuthManager) -> bool:
    """
    Check if auth manager uses runtime endpoint that doesn't provide /ListAvailableModels.
    
    Runtime endpoint pattern: https://runtime.{region}.kiro.dev
    Old endpoint pattern: https://q.{region}.amazonaws.com
    
    Runtime endpoint does not provide /ListAvailableModels API (AWS limitation).
    
    Args:
        auth_manager: KiroAuthManager instance
    
    Returns:
        True if using runtime endpoint, False otherwise
    
    Examples:
        >>> auth_manager.api_host = "https://runtime.us-east-1.kiro.dev"
        >>> _is_runtime_endpoint(auth_manager)
        True
        >>> auth_manager.api_host = "https://runtime.eu-central-1.kiro.dev"
        >>> _is_runtime_endpoint(auth_manager)
        True
        >>> auth_manager.api_host = "https://q.us-east-1.amazonaws.com"
        >>> _is_runtime_endpoint(auth_manager)
        False
    """
    return "://runtime." in auth_manager.api_host


# Shared timeouts for model discovery requests (seconds). One short attempt, no retries.
_DISCOVERY_HTTP_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)

# Maximum number of concurrent model probes across ALL accounts of one manager.
# Every probe is a real inference request, so an unbounded burst at startup
# (all accounts x all candidates) would look like abuse and trigger rate limits.
MODEL_PROBE_CONCURRENCY = 4

# Substrings (lowercase) of credential entry keys whose values must never be logged.
_SENSITIVE_KEY_FRAGMENTS = ("token", "secret", "password", "key")

# Placeholder that replaces sensitive values in logs.
_REDACTED = "***REDACTED***"


def _redact_entry(entry: object) -> object:
    """
    Return a copy of a credentials.json entry that is safe to log.

    Values of keys containing 'token', 'secret', 'password' or 'key'
    (case-insensitive) are replaced with a placeholder. Nested dicts are
    redacted recursively. Non-dict entries are reduced to their type name,
    because their content is unknown and may itself be a secret.

    Args:
        entry: Raw credential entry from credentials.json

    Returns:
        Redacted copy of the entry (the original is not modified).

    Examples:
        >>> _redact_entry({"type": "refresh_token", "refresh_token": "abc"})
        {'type': 'refresh_token', 'refresh_token': '***REDACTED***'}
    """
    if not isinstance(entry, dict):
        return f"<{type(entry).__name__}>"
    redacted: Dict[str, object] = {}
    for key, value in entry.items():
        if any(fragment in str(key).lower() for fragment in _SENSITIVE_KEY_FRAGMENTS):
            redacted[key] = _REDACTED
        elif isinstance(value, dict):
            redacted[key] = _redact_entry(value)
        else:
            redacted[key] = value
    return redacted

# Lowercase body fragments that mean "this model id is not known to Kiro".
_MODEL_NOT_FOUND_INDICATORS = (
    "not found",
    "not available",
    "invalid model",
    "invalid_model_id",
    "invalidmodelid",
    "unknown model",
    "does not exist",
    "not supported",
)


def _classify_probe_response(status_code: int, body: str) -> Optional[bool]:
    """
    Classify a probe response into available / unavailable / unknown.

    The status code is checked BEFORE the body, so rate limits, auth problems and
    server errors can never be mistaken for "model not found".

    Args:
        status_code: HTTP status code of the probe response
        body: Lowercased response body (only consulted for ambiguous 4xx codes)

    Returns:
        True if the model is available, False if it definitely does not exist,
        None if the result is inconclusive (caller keeps its previous knowledge).
    """
    if status_code == 200:
        return True
    if status_code in (401, 403, 408, 429) or status_code >= 500:
        return None
    if status_code == 404:
        return False
    if 400 <= status_code < 500 and any(i in body for i in _MODEL_NOT_FOUND_INDICATORS):
        return False
    return None


async def _probe_model(
    client: httpx.AsyncClient,
    auth_manager: KiroAuthManager,
    token: str,
    model_id: str,
    profile_arn: str,
) -> Optional[bool]:
    """
    Probe a single model with a minimal generateAssistantResponse request.

    NOTE: every successful probe is a real (billed) inference request, which is why
    probing is opt-in (MODEL_PROBING_ENABLED). The response is streamed and closed as
    soon as the status line is known, so the generation is not read to completion.

    Args:
        client: Shared httpx client (one client for all probes)
        auth_manager: Authenticated KiroAuthManager (host and header fingerprint)
        token: Valid access token
        model_id: Model ID to probe (e.g., "claude-sonnet-5")
        profile_arn: Profile ARN for the request (may be empty)

    Returns:
        True if available, False if the model does not exist, None if unknown
        (timeout, network error, 401/403/429/5xx, ambiguous 4xx).
    """
    payload = {
        "conversationState": {
            "chatTriggerType": "MANUAL",
            "conversationId": str(uuid.uuid4()),
            "currentMessage": {
                "userInputMessage": {
                    "content": "hi",
                    "modelId": model_id,
                    "origin": "AI_EDITOR",
                }
            },
        }
    }
    if profile_arn:
        payload["profileArn"] = profile_arn

    url = f"{auth_manager.api_host}/generateAssistantResponse"
    headers = get_kiro_headers(auth_manager, token)

    try:
        async with client.stream(
            "POST", url, content=json.dumps(payload).encode(), headers=headers
        ) as response:
            status = response.status_code
            if status == 200:
                return True
            body = (await response.aread()).decode("utf-8", errors="replace").lower()
    except httpx.TimeoutException as e:
        logger.debug(f"Probe {model_id}: {type(e).__name__} (inconclusive)")
        return None
    except httpx.HTTPError as e:
        logger.debug(f"Probe {model_id}: {type(e).__name__}: {e} (inconclusive)")
        return None

    result = _classify_probe_response(status, body)
    if result is None:
        logger.debug(f"Probe {model_id}: HTTP {status} (inconclusive)")
    return result


async def _probe_candidate_models(
    client: httpx.AsyncClient,
    auth_manager: KiroAuthManager,
    candidates: List[str],
    profile_arn: str,
    known: Iterable[str] = (),
    semaphore: Optional[asyncio.Semaphore] = None,
) -> List[Dict[str, str]]:
    """
    Probe candidate models concurrently to discover which are available.

    Concurrency is bounded by ``semaphore``. AccountManager passes one shared
    semaphore so the limit applies across all accounts probing at once.

    Inconclusive probes (timeout, 403, 429, 5xx, network errors) never ADD a model;
    they keep previous knowledge instead: such a model is retained only if it is in
    ``known`` (the account's current cache).

    Args:
        client: Shared httpx client reused by all probes
        auth_manager: Authenticated KiroAuthManager
        candidates: Model IDs to probe
        profile_arn: Profile ARN for the requests
        known: Model IDs the account currently has (kept on inconclusive probes)
        semaphore: Shared concurrency limiter; if None, a private one with
            MODEL_PROBE_CONCURRENCY slots is created for this call

    Returns:
        List of model dicts ({"modelId": "..."}); always includes "auto".

    Raises:
        ValueError: If the access token cannot be obtained
        httpx.HTTPError: If the token refresh fails at the network level
    """
    token = await auth_manager.get_access_token()
    known_set = set(known)
    if semaphore is None:
        semaphore = asyncio.Semaphore(MODEL_PROBE_CONCURRENCY)

    async def probe(model_id: str) -> Optional[bool]:
        async with semaphore:
            return await _probe_model(client, auth_manager, token, model_id, profile_arn)

    logger.info(f"Probing {len(candidates)} candidate models for availability...")
    results = await asyncio.gather(*(probe(m) for m in candidates), return_exceptions=True)

    available: List[Dict[str, str]] = [{"modelId": "auto"}]
    available_names: List[str] = []
    missing_names: List[str] = []
    unknown_names: List[str] = []

    for model_id, result in zip(candidates, results):
        if isinstance(result, asyncio.CancelledError):
            raise result
        if isinstance(result, BaseException):
            logger.warning(f"Probe {model_id} raised {type(result).__name__}: {result}")
            result = None
        if result is True or (result is None and model_id in known_set):
            available.append({"modelId": model_id})
            available_names.append(model_id)
        elif result is None:
            unknown_names.append(model_id)
        else:
            missing_names.append(model_id)

    logger.info(
        f"Model probing complete: {len(available_names)} available, "
        f"{len(missing_names)} unavailable, {len(unknown_names)} inconclusive"
    )
    if available_names:
        logger.info(f"Available models: {', '.join(sorted(available_names))}")
    return available


async def _fetch_listed_models(
    client: httpx.AsyncClient, auth_manager: KiroAuthManager
) -> Optional[List[Dict]]:
    """
    Tier 1 discovery: single short GET to /ListAvailableModels (no retries).

    Args:
        client: Shared discovery client (short timeouts)
        auth_manager: Authenticated KiroAuthManager

    Returns:
        List of model dicts, or None if the API is unavailable or returned nothing.
    """
    params = {"origin": "AI_EDITOR"}
    if auth_manager.auth_type == AuthType.KIRO_DESKTOP and auth_manager.profile_arn:
        params["profileArn"] = auth_manager.profile_arn
    url = f"{auth_manager.q_host}/ListAvailableModels"

    try:
        token = await auth_manager.get_access_token()
        response = await client.get(
            url, headers=get_kiro_headers(auth_manager, token), params=params
        )
    except (httpx.HTTPError, ValueError) as e:
        logger.warning(f"/ListAvailableModels request failed ({type(e).__name__}: {e})")
        return None

    if response.status_code != 200:
        logger.warning(f"/ListAvailableModels returned HTTP {response.status_code}")
        return None
    try:
        models = response.json().get("models", [])
    except (ValueError, AttributeError) as e:
        logger.warning(f"/ListAvailableModels returned an unparsable body ({type(e).__name__}: {e})")
        return None
    return models or None



def _format_duration(seconds: float) -> str:
    """
    Format duration in human-readable format.
    
    Args:
        seconds: Duration in seconds
    
    Returns:
        Formatted string (e.g., "30s", "5m", "2h", "1d")
    
    Examples:
        >>> _format_duration(30)
        '30s'
        >>> _format_duration(300)
        '5m'
        >>> _format_duration(7200)
        '2h'
        >>> _format_duration(86400)
        '1d'
    """
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds / 60)}m"
    elif seconds < 86400:
        return f"{int(seconds / 3600)}h"
    else:
        return f"{int(seconds / 86400)}d"


@dataclass
class AccountStats:
    """
    Statistics for account usage.
    
    Tracks request counts for monitoring and future web UI.
    """
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0


@dataclass
class Account:
    """
    Complete account entity with all dependencies.
    
    Represents a single Kiro account with its authentication,
    model cache, resolver, and runtime state.
    
    Attributes:
        id: Unique identifier (path to credentials file)
        auth_manager: Authentication manager (lazy initialized)
        model_cache: Model metadata cache (lazy initialized)
        model_resolver: Model resolver (lazy initialized)
        failures: Consecutive failure count (for Circuit Breaker)
        last_failure_time: Timestamp of last failure
        models_cached_at: Timestamp of last model cache update
        refreshing: Whether a background model discovery is in flight
        stats: Usage statistics
    """
    id: str
    auth_manager: Optional[KiroAuthManager] = None
    model_cache: Optional[ModelInfoCache] = None
    model_resolver: Optional[ModelResolver] = None
    failures: int = 0
    last_failure_time: float = 0.0
    models_cached_at: float = 0.0
    stats: AccountStats = field(default_factory=AccountStats)
    refreshing: bool = False  # True while a background model discovery task runs


@dataclass
class ModelAccountList:
    """
    List of accounts for a specific model.
    
    Attributes:
        accounts: List of account IDs that have this model
    
    Note: next_index removed - now using global _current_account_index
    """
    accounts: List[str] = field(default_factory=list)


class AccountManager:
    """
    Manages multiple Kiro accounts with intelligent failover.
    
    Responsibilities:
    - Load credentials from credentials.json
    - Lazy initialization of accounts
    - Select next available account (Circuit Breaker + Sticky)
    - Track statistics and failures
    - Persist state to state.json
    
    Example:
        >>> manager = AccountManager("credentials.json", "state.json")
        >>> await manager.load_credentials()
        >>> await manager.load_state()
        >>> account = await manager.get_next_account("claude-opus-4.5")
        >>> await manager.report_success(account.id, "claude-opus-4.5")
    """
    
    def __init__(self, credentials_file: str, state_file: str):
        """
        Initialize AccountManager.
        
        Args:
            credentials_file: Path to credentials.json
            state_file: Path to state.json
        """
        self._credentials_file = credentials_file
        self._state_file = state_file
        self._accounts: Dict[str, Account] = {}
        self._model_to_accounts: Dict[str, ModelAccountList] = {}
        self._lock = asyncio.Lock()
        self._dirty = False
        self._credentials_config: List[Dict] = []
        self._current_account_index: int = 0  # GLOBAL sticky index for all models
        self._tasks: set = set()  # strong refs to background tasks (discovery, init)
        self._discovery_client: Optional[httpx.AsyncClient] = None
        # Single-flight account initialization: one in-flight task per account,
        # shared by startup, background init and lazy init on the request path.
        self._init_tasks: Dict[str, "asyncio.Task[bool]"] = {}
        # Shared limit for model probes across all accounts
        self._probe_semaphore = asyncio.Semaphore(MODEL_PROBE_CONCURRENCY)
        # Serializes state file writes (periodic saver vs. startup/shutdown saves)
        self._save_lock = asyncio.Lock()
    
    async def load_credentials(self) -> None:
        """
        Load credentials from credentials.json.
        
        Validates each entry and creates Account objects.
        Invalid entries are skipped with warnings.
        Folders are scanned for credential files.
        """
        creds_path = Path(self._credentials_file).expanduser()
        
        if not creds_path.exists():
            logger.warning(f"Credentials file not found: {self._credentials_file}")
            return
        
        try:
            with open(creds_path, 'r', encoding='utf-8') as f:
                self._credentials_config = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load credentials: {e}")
            return
        
        # Process each credential entry
        for entry in self._credentials_config:
            cred_type = entry.get("type")
            path = entry.get("path")
            enabled = entry.get("enabled", True)
            
            if not enabled:
                continue
            
            # Validate required fields based on type
            if not cred_type:
                logger.warning(f"Invalid credential entry (missing type): {_redact_entry(entry)}")
                continue
            
            # For json/sqlite types, path is required
            if cred_type in ("json", "sqlite") and not path:
                logger.warning(
                    f"Invalid credential entry (type={cred_type} requires path): {_redact_entry(entry)}"
                )
                continue
            
            # For refresh_token type, refresh_token field is required
            if cred_type == "refresh_token" and not entry.get("refresh_token"):
                logger.warning(
                    "Invalid credential entry (type=refresh_token requires refresh_token field): "
                    f"{_redact_entry(entry)}"
                )
                continue
            
            # Handle refresh_token type (no path processing needed)
            if cred_type == "refresh_token":
                # Use deterministic hash for refresh_token (hash() is not deterministic between process restarts)
                token = entry.get('refresh_token', '')
                token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
                account_id = f"refresh_token_{token_hash}"
                self._accounts[account_id] = Account(id=account_id)
                logger.debug(f"Added account: {account_id}")
                continue  # Skip path processing for refresh_token
            
            # Handle folder scanning for json/sqlite types
            expanded_path = Path(path).expanduser()
            if expanded_path.is_dir():
                logger.info(f"Scanning folder for credentials: {path}")
                for file_path in expanded_path.iterdir():
                    if not file_path.is_file():
                        continue
                    
                    # Validate file before adding as account
                    account_id = str(file_path.resolve())
                    is_valid = False
                    
                    # Try JSON validation
                    if cred_type == "json":
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                # Valid if has refreshToken or clientId
                                if 'refreshToken' in data or 'clientId' in data:
                                    is_valid = True
                        except Exception as e:
                            logger.warning(f"Invalid JSON credentials file {file_path.name}: {e}")
                    
                    # Try SQLite validation
                    elif cred_type == "sqlite":
                        try:
                            import sqlite3
                            conn = sqlite3.connect(str(file_path))
                            cursor = conn.cursor()
                            # Check if auth_kv table exists
                            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='auth_kv'")
                            if cursor.fetchone():
                                is_valid = True
                            conn.close()
                        except Exception as e:
                            logger.warning(f"Invalid SQLite database file {file_path.name}: {e}")
                    
                    if is_valid:
                        self._accounts[account_id] = Account(id=account_id)
                        logger.debug(f"Added account from folder: {account_id}")
                    else:
                        logger.warning(f"Skipping invalid credentials file: {file_path.name}")
            elif expanded_path.is_file() or cred_type == "refresh_token":
                # Single file or refresh_token type
                if cred_type == "refresh_token":
                    # Use deterministic hash for refresh_token (hash() is not deterministic between process restarts)
                    token = entry.get('refresh_token', '')
                    token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
                    account_id = f"refresh_token_{token_hash}"
                else:
                    account_id = str(expanded_path.resolve())
                self._accounts[account_id] = Account(id=account_id)
                logger.debug(f"Added account: {account_id}")
            else:
                logger.warning(f"Credential path not found: {path}")
        
        logger.info(f"Loaded {len(self._accounts)} account(s) from credentials")
    
    async def load_state(self) -> None:
        """
        Load runtime state from state.json.
        
        Restores model_to_accounts mapping and account runtime state.
        Creates empty state if file doesn't exist.
        """
        state_path = Path(self._state_file)
        
        if not state_path.exists():
            logger.debug("State file not found, starting with empty state")
            return
        
        try:
            with open(state_path, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            # Restore global current_account_index
            self._current_account_index = state_data.get("current_account_index", 0)
            
            # Restore model_to_accounts mapping (without next_index)
            for model, data in state_data.get("model_to_accounts", {}).items():
                self._model_to_accounts[model] = ModelAccountList(
                    accounts=data.get("accounts", [])
                )
            
            # Restore account runtime state
            for account_id, data in state_data.get("accounts", {}).items():
                if account_id in self._accounts:
                    account = self._accounts[account_id]
                    account.failures = data.get("failures", 0)
                    account.last_failure_time = data.get("last_failure_time", 0.0)
                    account.models_cached_at = data.get("models_cached_at", 0.0)
                    
                    stats_data = data.get("stats", {})
                    account.stats = AccountStats(
                        total_requests=stats_data.get("total_requests", 0),
                        successful_requests=stats_data.get("successful_requests", 0),
                        failed_requests=stats_data.get("failed_requests", 0)
                    )
            
            logger.info(f"Loaded state: {len(self._model_to_accounts)} model mappings, {len(self._accounts)} accounts")
        
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
    
    def _snapshot_state(self) -> Dict:
        """
        Build a self-contained copy of the runtime state for persistence.

        Synchronous on purpose: with no ``await`` it is atomic with respect to
        other coroutines, so the snapshot is consistent. Lists are copied so the
        worker thread that writes the file never iterates live, mutable state.

        Returns:
            JSON-serializable state dict
        """
        return {
            "current_account_index": self._current_account_index,
            "accounts": {
                account_id: {
                    "failures": account.failures,
                    "last_failure_time": account.last_failure_time,
                    "models_cached_at": account.models_cached_at,
                    "stats": {
                        "total_requests": account.stats.total_requests,
                        "successful_requests": account.stats.successful_requests,
                        "failed_requests": account.stats.failed_requests
                    }
                }
                for account_id, account in self._accounts.items()
            },
            "model_to_accounts": {
                model: {
                    "accounts": list(mal.accounts)
                }
                for model, mal in self._model_to_accounts.items()
            }
        }

    def _write_state_file(self, state_data: Dict) -> bool:
        """
        Write a state snapshot to state.json atomically (blocking file I/O).

        Uses tmp file + rename for atomic write. Runs in a worker thread.

        Args:
            state_data: Snapshot produced by ``_snapshot_state``

        Returns:
            True if the file was written, False on failure (logged).
        """
        state_path = Path(self._state_file)
        tmp_path = state_path.with_suffix('.json.tmp')

        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, indent=2, ensure_ascii=False)

            # Atomic rename
            tmp_path.replace(state_path)
            logger.debug("State saved successfully")
            return True

        except (OSError, TypeError, ValueError) as e:
            logger.error(f"Failed to save state to {self._state_file}: {type(e).__name__}: {e}")
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError as cleanup_error:
                logger.debug(f"Could not remove temporary state file {tmp_path}: {cleanup_error}")
            return False

    async def _save_state(self) -> bool:
        """
        Save runtime state to state.json atomically without blocking the event loop.

        The snapshot is taken synchronously (consistent, no lock needed), then
        the file is written in a worker thread. ``self._lock`` is never held
        during the write, so account selection and reporting are not blocked
        by disk I/O. ``self._save_lock`` keeps concurrent writers from racing
        on the temporary file.

        Returns:
            True if the state was written, False on failure.
        """
        state_data = self._snapshot_state()
        async with self._save_lock:
            return await asyncio.to_thread(self._write_state_file, state_data)

    async def save_state_periodically(self) -> None:
        """
        Background task for periodic state saving.

        Saves state every STATE_SAVE_INTERVAL_SECONDS if dirty flag is set.
        The dirty flag is cleared before writing so changes made during the
        write are picked up by the next cycle, and restored if the write fails.
        """
        while True:
            await asyncio.sleep(STATE_SAVE_INTERVAL_SECONDS)

            if self._dirty:
                self._dirty = False
                if not await self._save_state():
                    self._dirty = True
    
    async def _initialize_account(self, account_id: str) -> bool:
        """
        Initialize account once, sharing a single in-flight attempt (single-flight).

        Startup, background init and lazy init on the request path may all ask
        for the same account at the same time. Only the first caller starts the
        real work (``_do_initialize_account``); every other caller awaits the
        same task, so the same credentials are never refreshed twice in
        parallel. The task is shielded: a caller that is cancelled (e.g. the
        client disconnected) does not cancel the shared initialization.

        Must never be awaited while holding ``self._lock``: initialization does
        network I/O (token refresh) that can take many seconds.

        Args:
            account_id: Account ID to initialize

        Returns:
            True if the account is (now) initialized, False otherwise
        """
        account = self._accounts.get(account_id)
        if not account:
            return False
        if account.auth_manager is not None:
            return True

        task = self._init_tasks.get(account_id)
        if task is None:
            task = asyncio.create_task(
                self._do_initialize_account(account_id), name=f"account-init-flight:{account_id}"
            )
            self._init_tasks[account_id] = task

            def _forget(t: "asyncio.Task[bool]", aid: str = account_id) -> None:
                if self._init_tasks.get(aid) is t:
                    del self._init_tasks[aid]

            task.add_done_callback(_forget)
            self._track_task(task)
        else:
            logger.debug(f"Joining in-flight initialization for account: {account_id}")

        return await asyncio.shield(task)

    async def _do_initialize_account(self, account_id: str) -> bool:
        """
        Initialize account (fast path: credentials + token + static model list).

        Creates auth_manager, verifies the token and installs FALLBACK_MODELS +
        HIDDEN_MODELS so the account can serve requests immediately. Real model
        discovery is NOT done here; it runs in the background via
        ``_schedule_refresh`` so neither startup nor requests wait for it.

        Only called through ``_initialize_account`` (single-flight wrapper).

        Args:
            account_id: Account ID to initialize

        Returns:
            True if successful, False otherwise
        """
        account = self._accounts.get(account_id)
        if not account:
            return False
        if account.auth_manager is not None:
            return True

        try:
            # Find credentials config for this account
            creds_config = None
            for entry in self._credentials_config:
                path = entry.get("path", "")
                expanded_path = Path(path).expanduser()

                if entry.get("type") == "refresh_token":
                    # Match by deterministic hash for refresh_token type
                    token = entry.get('refresh_token', '')
                    token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
                    if account_id == f"refresh_token_{token_hash}":
                        creds_config = entry
                        break
                elif str(expanded_path.resolve()) == account_id or (expanded_path.is_dir() and account_id.startswith(str(expanded_path.resolve()) + os.sep)):
                    creds_config = entry
                    break

            if not creds_config:
                logger.error(f"No credentials config found for account: {account_id}")
                return False

            # Create KiroAuthManager based on type
            cred_type = creds_config.get("type")
            if cred_type == "json":
                auth_manager = KiroAuthManager(
                    creds_file=account_id,
                    profile_arn=creds_config.get("profile_arn"),
                    region=creds_config.get("region", "us-east-1"),
                    api_region=creds_config.get("api_region")
                )
            elif cred_type == "sqlite":
                auth_manager = KiroAuthManager(
                    sqlite_db=account_id,
                    profile_arn=creds_config.get("profile_arn"),
                    region=creds_config.get("region", "us-east-1"),
                    api_region=creds_config.get("api_region")
                )
            elif cred_type == "refresh_token":
                auth_manager = KiroAuthManager(
                    refresh_token=creds_config.get("refresh_token"),
                    profile_arn=creds_config.get("profile_arn"),
                    region=creds_config.get("region", "us-east-1"),
                    api_region=creds_config.get("api_region")
                )
            else:
                logger.error(f"Unknown credential type: {cred_type}")
                return False

            # Get token to verify credentials
            await auth_manager.get_access_token()

            # Background init and lazy init may race: first one to finish wins
            if account.auth_manager is not None:
                return True

            # Serve immediately with the static list; discovery refines it in background
            model_cache = ModelInfoCache()
            await model_cache.update(FALLBACK_MODELS)
            for display_name, internal_id in HIDDEN_MODELS.items():
                model_cache.add_hidden_model(display_name, internal_id)

            if account.auth_manager is not None:
                return True
            account.auth_manager = auth_manager
            account.model_cache = model_cache
            account.model_resolver = ModelResolver(
                cache=model_cache,
                hidden_models=HIDDEN_MODELS,
                aliases=MODEL_ALIASES,
                hidden_from_list=HIDDEN_FROM_LIST
            )
            account.models_cached_at = time.time()
            self._register_account_models(account)

            logger.info(
                f"Initialized account: {account_id} "
                f"({len(FALLBACK_MODELS)} fallback models, discovery runs in background)"
            )
            return True

        except Exception as e:  # noqa: BLE001 - last-resort guard: one bad account must not crash startup
            logger.error(f"Failed to initialize account {account_id}: {type(e).__name__}: {e}")
            return False

    def _register_account_models(self, account: Account) -> None:
        """
        Add the account to ``_model_to_accounts`` for every model it exposes.

        Synchronous on purpose: it contains no ``await``, so it is atomic with respect
        to other coroutines (``_save_state`` and get_next_account never observe a
        half-applied update) and can be called from background tasks and from
        initialization without taking ``self._lock``. No network I/O ever
        happens inside it.

        Args:
            account: Initialized account
        """
        if not account.model_resolver:
            return
        for model in account.model_resolver.get_available_models():
            mal = self._model_to_accounts.setdefault(model, ModelAccountList())
            if account.id not in mal.accounts:
                mal.accounts.append(account.id)
        self._dirty = True

    def _get_discovery_client(self) -> httpx.AsyncClient:
        """Return the shared short-timeout client used by all discovery requests."""
        if self._discovery_client is None:
            self._discovery_client = httpx.AsyncClient(timeout=_DISCOVERY_HTTP_TIMEOUT)
        return self._discovery_client

    def _track_task(self, task: "asyncio.Task", account: Optional[Account] = None) -> None:
        """
        Keep a strong reference to a background task until it finishes.

        Args:
            task: Task to track
            account: If given, its ``refreshing`` flag is cleared when the task ends
        """
        self._tasks.add(task)

        def _on_done(t: "asyncio.Task") -> None:
            self._tasks.discard(t)
            if account is not None:
                account.refreshing = False
            if not t.cancelled() and t.exception() is not None:
                exc = t.exception()
                logger.error(f"Background task {t.get_name()} failed: {type(exc).__name__}: {exc}")

        task.add_done_callback(_on_done)

    def _schedule_refresh(self, account_id: str) -> bool:
        """
        Start background model discovery for an account (non-blocking).

        Guarded by a per-account ``refreshing`` flag so at most one discovery runs
        per account at a time. Must be called from a running event loop.

        Args:
            account_id: Account ID

        Returns:
            True if a new task was started, False if skipped.
        """
        account = self._accounts.get(account_id)
        if account is None or account.auth_manager is None or account.refreshing:
            return False
        account.refreshing = True
        task = asyncio.create_task(
            self._refresh_account_models(account_id), name=f"model-discovery:{account_id}"
        )
        self._track_task(task, account)
        return True

    def _schedule_refresh_if_stale(self, account: Account) -> None:
        """Schedule a background refresh when the account's model cache is older than the TTL."""
        if account.models_cached_at > 0 and time.time() - account.models_cached_at > ACCOUNT_CACHE_TTL:
            self._schedule_refresh(account.id)

    def start_background_init(self) -> None:
        """
        Start background work after the first account is ready (non-blocking).

        - Model discovery for already initialized accounts.
        - Concurrent initialization (then discovery) of all remaining accounts, so
          they are not initialized lazily on the request path.
        """
        for account_id, account in self._accounts.items():
            if account.auth_manager is not None:
                self._schedule_refresh(account_id)
            else:
                task = asyncio.create_task(
                    self._init_and_discover(account_id), name=f"account-init:{account_id}"
                )
                self._track_task(task)

    async def _init_and_discover(self, account_id: str) -> None:
        """Initialize one account in the background, then start its model discovery."""
        if await self._initialize_account(account_id):
            self._schedule_refresh(account_id)
        else:
            logger.warning(f"Background initialization failed for account: {account_id}")

    async def shutdown(self) -> None:
        """Cancel all background tasks, wait for them and close the discovery client."""
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self._discovery_client is not None:
            await self._discovery_client.aclose()
            self._discovery_client = None

    def _defer_next_refresh(self, account: Account) -> None:
        """
        Reset the TTL clock after a failed/empty discovery.

        The next attempt happens after ACCOUNT_CACHE_RETRY_INTERVAL seconds instead
        of on every request.
        """
        retry = min(ACCOUNT_CACHE_RETRY_INTERVAL, ACCOUNT_CACHE_TTL)
        account.models_cached_at = time.time() - ACCOUNT_CACHE_TTL + retry

    async def _discover_models(self, account: Account) -> Optional[List[Dict]]:
        """
        Run model discovery for an account (network I/O, never called under the lock).

        1. /ListAvailableModels (skipped for runtime endpoints, which lack it)
        2. Probing candidate models (only if MODEL_PROBING_ENABLED)

        Args:
            account: Initialized account

        Returns:
            Model dicts, or None when nothing could be discovered.
        """
        auth_manager = account.auth_manager
        client = self._get_discovery_client()

        if not _is_runtime_endpoint(auth_manager):
            listed = await _fetch_listed_models(client, auth_manager)
            if listed:
                logger.info(f"Account {account.id}: fetched {len(listed)} models from /ListAvailableModels")
                return listed

        if MODEL_PROBING_ENABLED:
            known = account.model_cache.get_all_model_ids() if account.model_cache else ()
            probed = await _probe_candidate_models(
                client,
                auth_manager,
                CANDIDATE_MODELS,
                auth_manager.profile_arn or "",
                known,
                semaphore=self._probe_semaphore,
            )
            if len(probed) > 1:  # More than just "auto"
                logger.info(f"Account {account.id}: discovered {len(probed)} models via probing")
                return probed
        return None

    async def _refresh_account_models(self, account_id: str) -> None:
        """
        Discover models for an account and update its cache (initial + TTL refresh).

        Never raises for expected network problems. On failure the current cache is
        kept and the TTL clock is reset (see ``_defer_next_refresh``) so discovery
        is not retried on every request.

        Args:
            account_id: Account ID to refresh
        """
        account = self._accounts.get(account_id)
        if not account or not account.auth_manager or not account.model_cache:
            return

        if _is_runtime_endpoint(account.auth_manager) and not MODEL_PROBING_ENABLED:
            # Nothing to discover: runtime endpoints have no list API and probing is off.
            logger.debug(f"Account {account_id}: runtime endpoint, probing disabled; keeping static model list")
            account.models_cached_at = time.time()
            return

        applied = False
        try:
            models_list = await asyncio.wait_for(
                self._discover_models(account), timeout=MODEL_DISCOVERY_TIMEOUT
            )
            if models_list:
                await account.model_cache.update(models_list)
                for display_name, internal_id in HIDDEN_MODELS.items():
                    account.model_cache.add_hidden_model(display_name, internal_id)
                account.models_cached_at = time.time()
                self._register_account_models(account)
                applied = True
        except asyncio.TimeoutError:
            logger.warning(f"Account {account_id}: model discovery timed out after {MODEL_DISCOVERY_TIMEOUT}s")
        except (httpx.HTTPError, ValueError) as e:
            logger.warning(f"Account {account_id}: model discovery failed ({type(e).__name__}: {e})")
        finally:
            if not applied:
                self._defer_next_refresh(account)
                logger.warning(f"Account {account_id}: could not discover models, keeping current cache")
    
    async def get_next_account(self, model: str, exclude_accounts: Optional[set] = None) -> Optional[Account]:
        """
        Get next available account for model (Circuit Breaker + Sticky).
        
        Implements:
        - Sticky behavior (prefer successful account)
        - Circuit Breaker with exponential backoff
        - Probabilistic retry for "dead" accounts (10%)
        - TTL-based model cache refresh
        - Exclusion of already-tried accounts in current failover loop
        
        Args:
            model: Model name (will be normalized)
            exclude_accounts: Set of account IDs to exclude (already tried in current failover loop)
        
        Returns:
            Account object or None if no accounts available
        """
        # Accounts whose lazy init failed during THIS call. Kept local so the
        # caller's exclude set is never mutated.
        skipped: set = set(exclude_accounts) if exclude_accounts else set()
        single_account = len(self._accounts) == 1

        while True:
            # Selection is synchronous and fast: the global lock is held only for it,
            # never across network I/O.
            async with self._lock:
                account = self._select_account(skipped)
            if account is None:
                return None

            if account.auth_manager is not None:
                return account

            # Lazy initialization OUTSIDE the global lock (token refresh can take
            # seconds). Single-flight: joins any in-flight background init.
            if await self._initialize_account(account.id):
                self._schedule_refresh(account.id)
                return account

            if single_account:
                # Single account: no circuit breaker, nothing to fail over to
                return None

            async with self._lock:
                account.failures += 1
                account.last_failure_time = time.time()  # starts the cooldown window
                self._dirty = True
            logger.warning(
                f"Lazy initialization failed for account {account.id} "
                f"(failure #{account.failures}), trying next account"
            )
            skipped.add(account.id)

    def _select_account(self, excluded: set) -> Optional[Account]:
        """
        Pick the next account to use (Circuit Breaker + global sticky). No I/O.

        Must be called with ``self._lock`` held. Contains no ``await``, so the
        decision and the half-open bookkeeping are atomic.

        Half-open single probe: when an account's cooldown has expired, the
        first request to see it gets it as a trial and the cooldown clock
        (``last_failure_time``) is restarted, so concurrent requests skip the
        account until that trial reports back. ``report_success`` resets
        failures; ``report_failure`` sets a new failure time. A trial that never
        reports simply waits out one more cooldown window, so a crashed request
        can never block the account forever.

        Args:
            excluded: Account IDs to skip (tried in this failover loop or failed init)

        Returns:
            Selected account (possibly not yet initialized), or None.
        """
        # Special case: single account - bypass Circuit Breaker
        # Circuit Breaker is meaningless for single account - user should see real Kiro API errors
        # instead of generic "Account unavailable" after cooldown kicks in
        if len(self._accounts) == 1:
            account_id, account = next(iter(self._accounts.items()))
            if account_id in excluded:
                return None
            if account.auth_manager is not None:
                # Stale model cache: refresh in background, never block the request
                self._schedule_refresh_if_stale(account)
            # Always return single account (ignore cooldown/failures)
            # No model validation - let Kiro API decide (gateway, not gatekeeper)
            return account

        # Multi-account logic: GLOBAL sticky
        # ALWAYS start from GLOBAL index (one current account for ALL models)
        start_index = self._current_account_index

        # ALWAYS iterate over ALL accounts
        all_account_ids = list(self._accounts.keys())
        now = time.time()

        for i in range(len(all_account_ids)):
            current_index = (start_index + i) % len(all_account_ids)
            account_id = all_account_ids[current_index]
            account = self._accounts[account_id]

            # Skip accounts already tried in current failover loop
            if account_id in excluded:
                continue

            # Check Circuit Breaker (Half-Open state with exponential backoff)
            if account.failures > 0:
                time_since_failure = now - account.last_failure_time

                # Exponential backoff: base * 2^(failures - 1), capped at MAX_MULTIPLIER
                # 1 failure: 60s, 2: 120s, 3: 240s, ..., 12+: 86400s (1 day cap)
                backoff_multiplier = min(2 ** (account.failures - 1), ACCOUNT_MAX_BACKOFF_MULTIPLIER)
                effective_timeout = ACCOUNT_RECOVERY_TIMEOUT * backoff_multiplier

                if time_since_failure < effective_timeout:
                    # Probabilistic retry (10% chance)
                    if random.random() > ACCOUNT_PROBABILISTIC_RETRY_CHANCE:
                        continue
                    logger.info(f"Probabilistic retry for broken account {account_id}")
                else:
                    # Half-Open: recovery timeout passed. Hand out ONE trial and
                    # restart the cooldown so concurrent requests skip this account.
                    account.last_failure_time = now
                    self._dirty = True
                    logger.info(
                        f"Half-Open state for {account_id} (recovery timeout passed, "
                        f"effective={effective_timeout}s), sending a single trial request"
                    )

            if account.auth_manager is not None:
                # Stale model cache: refresh in background, never block the request
                self._schedule_refresh_if_stale(account)

            # No model validation - let Kiro API decide (gateway, not gatekeeper)
            # Account is suitable!
            return account

        # All accounts unavailable
        return None
    
    async def report_success(self, account_id: str, model: str) -> None:
        """
        Report successful request (reset failures, update stats, sticky, dynamic learning).
        
        Args:
            account_id: Account ID
            model: Model name
        """
        async with self._lock:
            account = self._accounts.get(account_id)
            if not account:
                return
            
            # Reset failures
            if account.failures > 0:
                account.failures = 0
                self._dirty = True
            
            # Update stats
            account.stats.total_requests += 1
            account.stats.successful_requests += 1
            self._dirty = True
            
            # Dynamic learning: add model to mapping if successful
            # This allows system to learn about new models not in FALLBACK_MODELS
            normalized_model = normalize_model_name(model)
            if normalized_model not in self._model_to_accounts:
                self._model_to_accounts[normalized_model] = ModelAccountList()
                logger.debug(f"Dynamic learning: discovered new model '{normalized_model}'")
            if account_id not in self._model_to_accounts[normalized_model].accounts:
                self._model_to_accounts[normalized_model].accounts.append(account_id)
                logger.debug(f"Dynamic learning: model '{normalized_model}' works on account {account_id}")
                self._dirty = True
            
            # GLOBAL STICKY: Update global current_account_index
            all_account_ids = list(self._accounts.keys())
            try:
                successful_index = all_account_ids.index(account_id)
                if self._current_account_index != successful_index:
                    self._current_account_index = successful_index
                    self._dirty = True
            except ValueError:
                pass
    
    async def report_failure(
        self,
        account_id: str,
        model: str,
        error_type: ErrorType,
        status_code: int,
        reason: Optional[str]
    ) -> None:
        """
        Report failed request (update failures, stats, failover).
        
        Args:
            account_id: Account ID
            model: Model name
            error_type: Error classification (FATAL or RECOVERABLE)
            status_code: HTTP status code
            reason: Error reason from Kiro API
        """
        async with self._lock:
            account = self._accounts.get(account_id)
            if not account:
                return
            
            # Special case: INVALID_MODEL_ID is discovery process, not account failure
            # Account is healthy, model is just not available on this account
            # Log for user visibility but don't penalize account statistics
            if reason == "INVALID_MODEL_ID":
                account.stats.total_requests += 1
                self._dirty = True
                logger.warning(
                    f"Model '{model}' not available on account {account_id}: "
                    f"status={status_code}, reason={reason}"
                )
                return
            
            # Update failure count (only for RECOVERABLE)
            if error_type == ErrorType.RECOVERABLE:
                account.failures += 1
                account.last_failure_time = time.time()
                self._dirty = True
                
                # Calculate backoff for logging
                backoff_multiplier = min(2 ** (account.failures - 1), ACCOUNT_MAX_BACKOFF_MULTIPLIER)
                effective_timeout = ACCOUNT_RECOVERY_TIMEOUT * backoff_multiplier
                logger.warning(
                    f"Account {account_id} failure #{account.failures}: "
                    f"status={status_code}, reason={reason}, "
                    f"cooldown={_format_duration(effective_timeout)}"
                )
            
            # Update stats
            account.stats.total_requests += 1
            account.stats.failed_requests += 1
            self._dirty = True
            
            # GLOBAL STICKY: Do NOT change _current_account_index on failure
            # It only changes on success (GLOBAL sticky behavior)
            # Failover happens through exclude_accounts in get_next_account()
    
    def get_first_account(self) -> Account:
        """
        Get first initialized account (for legacy mode).
        
        Returns:
            First initialized account
        
        Raises:
            RuntimeError: If no initialized accounts available
        """
        for account in self._accounts.values():
            if account.auth_manager is not None:
                return account
        raise RuntimeError("No initialized accounts available")
    
    def get_all_available_models(self) -> List[str]:
        """
        Collect unique models from all initialized accounts.
        
        Used by /v1/models endpoint in account system to show
        all available models across all accounts.
        
        Returns:
            Sorted list of unique model IDs
        """
        all_models = set()
        for account in self._accounts.values():
            if account.model_resolver:
                all_models.update(account.model_resolver.get_available_models())
        return sorted(all_models)
