# -*- coding: utf-8 -*-

"""
Unit tests for non-blocking model discovery in kiro/account_manager.py.

Covers: runtime-endpoint short-circuit, failed-refresh TTL reset, background
refresh (never awaited under the lock), probe classification, opt-in probing,
shutdown cancellation. All network I/O is mocked.
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import kiro.account_manager as am
from kiro.account_manager import (
    Account,
    AccountManager,
    _classify_probe_response,
    _probe_candidate_models,
    _probe_model,
)
from kiro.config import ACCOUNT_CACHE_RETRY_INTERVAL, ACCOUNT_CACHE_TTL, HIDDEN_MODELS


async def _make_manager(tmp_path, count: int = 1) -> AccountManager:
    """Build a manager with ``count`` json accounts (not yet initialized)."""
    entries = []
    for i in range(count):
        f = tmp_path / f"acc{i}.json"
        f.write_text(json.dumps({
            "refreshToken": f"t{i}",
            "accessToken": f"a{i}",
            "expiresAt": "2099-01-01T00:00:00.000Z",
        }))
        entries.append({"type": "json", "path": str(f), "enabled": True})
    creds = tmp_path / "credentials.json"
    creds.write_text(json.dumps(entries))
    manager = AccountManager(str(creds), str(tmp_path / "state.json"))
    await manager.load_credentials()
    return manager


def _fake_auth(host: str = "https://q.us-east-1.amazonaws.com") -> MagicMock:
    auth = MagicMock()
    auth.api_host = host
    auth.q_host = host
    auth.profile_arn = None
    auth.fingerprint = "fp"
    auth.get_access_token = AsyncMock(return_value="tok")
    return auth


def _stream_client(status: int, body: str = "", exc: Exception = None) -> MagicMock:
    """Fake httpx client whose .stream() yields a response with given status/body."""
    response = MagicMock()
    response.status_code = status
    response.aread = AsyncMock(return_value=body.encode())
    cm = MagicMock()
    if exc is not None:
        cm.__aenter__ = AsyncMock(side_effect=exc)
    else:
        cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=False)
    client = MagicMock()
    client.stream = MagicMock(return_value=cm)
    return client


class TestClassifyProbeResponse:
    """Status code is decisive; body only matters for ambiguous 4xx."""

    @pytest.mark.parametrize("status,body,expected", [
        (200, "", True),
        (404, "", False),
        (400, "model not found", False),
        (400, "InvalidModelId".lower(), False),
        (400, "something else", None),
        (403, "model not found", None),   # status wins over body
        (401, "", None),
        (429, "not found", None),
        (500, "does not exist", None),
        (503, "", None),
    ])
    def test_classification(self, status, body, expected):
        assert _classify_probe_response(status, body) is expected


class TestProbeModel:
    """_probe_model returns True / False / None for each outcome."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status,body,expected", [
        (200, "", True),
        (404, "", False),
        (403, "", None),
        (429, "", None),
        (502, "", None),
    ])
    async def test_status_mapping(self, status, body, expected):
        client = _stream_client(status, body)
        result = await _probe_model(client, _fake_auth(), "tok", "claude-x", "")
        assert result is expected

    @pytest.mark.asyncio
    async def test_timeout_is_unknown(self):
        client = _stream_client(0, exc=httpx.ReadTimeout("slow"))
        assert await _probe_model(client, _fake_auth(), "tok", "m", "") is None

    @pytest.mark.asyncio
    async def test_network_error_is_unknown(self):
        client = _stream_client(0, exc=httpx.ConnectError("boom"))
        assert await _probe_model(client, _fake_auth(), "tok", "m", "") is None

    @pytest.mark.asyncio
    async def test_uses_kiro_headers_and_profile_arn(self):
        client = _stream_client(200)
        await _probe_model(client, _fake_auth(), "tok", "m", "arn:x")
        _, kwargs = client.stream.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer tok"
        assert "x-amz-target" in kwargs["headers"]
        assert json.loads(kwargs["content"])["profileArn"] == "arn:x"


class TestProbeCandidateModels:
    """Aggregation semantics for inconclusive results."""

    @pytest.mark.asyncio
    async def test_unknown_not_added_unless_previously_known(self):
        results = {"a": True, "b": False, "c": None, "d": None}

        async def fake_probe(client, auth, token, model_id, arn):
            return results[model_id]

        with patch.object(am, "_probe_model", fake_probe):
            out = await _probe_candidate_models(
                MagicMock(), _fake_auth(), list(results), "", known=["d"]
            )
        ids = [m["modelId"] for m in out]
        assert ids == ["auto", "a", "d"]  # b missing, c unknown+unseen dropped, d kept

    @pytest.mark.asyncio
    async def test_exception_in_probe_is_treated_as_unknown_and_logged(self):
        async def fake_probe(client, auth, token, model_id, arn):
            raise RuntimeError("bug")

        with patch.object(am, "_probe_model", fake_probe), \
                patch.object(am.logger, "warning") as warn:
            out = await _probe_candidate_models(MagicMock(), _fake_auth(), ["a"], "")
        assert out == [{"modelId": "auto"}]
        assert any("RuntimeError" in str(c) for c in warn.call_args_list)

    @pytest.mark.asyncio
    async def test_single_token_fetch_and_shared_client(self):
        auth = _fake_auth()
        client = _stream_client(200)
        await _probe_candidate_models(client, auth, ["a", "b", "c"], "")
        assert auth.get_access_token.await_count == 1
        assert client.stream.call_count == 3


class TestRuntimeEndpointShortCircuit:
    """Runtime endpoints skip Tier 1 (/ListAvailableModels)."""

    @pytest.mark.asyncio
    async def test_runtime_endpoint_skips_tier1_and_probing_off_means_no_network(self, tmp_path):
        manager = await _make_manager(tmp_path)
        assert await manager._initialize_account(next(iter(manager._accounts)))
        account = next(iter(manager._accounts.values()))
        account.auth_manager._api_host = "https://runtime.us-east-1.kiro.dev"
        account.models_cached_at = 1.0

        with patch.object(am, "_fetch_listed_models", AsyncMock()) as tier1, \
                patch.object(am, "MODEL_PROBING_ENABLED", False):
            await manager._refresh_account_models(account.id)

        tier1.assert_not_awaited()
        assert account.models_cached_at > 1.0  # clock reset, nothing else happened

    @pytest.mark.asyncio
    async def test_runtime_endpoint_with_probing_skips_tier1_only(self, tmp_path):
        manager = await _make_manager(tmp_path)
        await manager._initialize_account(next(iter(manager._accounts)))
        account = next(iter(manager._accounts.values()))
        account.auth_manager._api_host = "https://runtime.us-east-1.kiro.dev"

        probed = [{"modelId": "auto"}, {"modelId": "claude-new-9"}]
        with patch.object(am, "_fetch_listed_models", AsyncMock()) as tier1, \
                patch.object(am, "_probe_candidate_models", AsyncMock(return_value=probed)), \
                patch.object(am, "MODEL_PROBING_ENABLED", True):
            await manager._refresh_account_models(account.id)

        tier1.assert_not_awaited()
        assert "claude-new-9" in account.model_resolver.get_available_models()

    @pytest.mark.asyncio
    async def test_non_runtime_endpoint_uses_tier1_and_probing_disabled_by_default(self, tmp_path):
        manager = await _make_manager(tmp_path)
        await manager._initialize_account(next(iter(manager._accounts)))
        account = next(iter(manager._accounts.values()))
        account.auth_manager._api_host = "https://q.us-east-1.amazonaws.com"

        with patch.object(am, "_fetch_listed_models", AsyncMock(return_value=None)) as tier1, \
                patch.object(am, "_probe_candidate_models", AsyncMock()) as probe:
            await manager._refresh_account_models(account.id)

        tier1.assert_awaited_once()
        probe.assert_not_awaited()  # MODEL_PROBING_ENABLED defaults to false

    def test_probing_disabled_by_default(self):
        import kiro.config as cfg
        assert cfg.MODEL_PROBING_ENABLED is False


class TestFetchListedModels:
    """Tier 1: single attempt, tolerant of every failure mode."""

    @pytest.mark.asyncio
    async def test_success(self):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"models": [{"modelId": "x"}]}
        client = MagicMock(get=AsyncMock(return_value=resp))
        assert await am._fetch_listed_models(client, _fake_auth()) == [{"modelId": "x"}]
        assert client.get.await_count == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [403, 429, 500])
    async def test_bad_status_returns_none(self, status):
        client = MagicMock(get=AsyncMock(return_value=MagicMock(status_code=status)))
        assert await am._fetch_listed_models(client, _fake_auth()) is None

    @pytest.mark.asyncio
    async def test_timeout_logs_warning_with_type(self):
        client = MagicMock(get=AsyncMock(side_effect=httpx.ReadTimeout("t")))
        with patch.object(am.logger, "warning") as warn:
            assert await am._fetch_listed_models(client, _fake_auth()) is None
        assert "ReadTimeout" in str(warn.call_args)

    @pytest.mark.asyncio
    async def test_bad_json_returns_none(self):
        resp = MagicMock(status_code=200)
        resp.json.side_effect = ValueError("bad")
        client = MagicMock(get=AsyncMock(return_value=resp))
        assert await am._fetch_listed_models(client, _fake_auth()) is None

    @pytest.mark.asyncio
    async def test_empty_models_returns_none(self):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"models": []}
        client = MagicMock(get=AsyncMock(return_value=resp))
        assert await am._fetch_listed_models(client, _fake_auth()) is None


class TestRefreshTtlAndFailure:
    """Failed refresh must not retrigger discovery on every request."""

    @pytest.mark.asyncio
    async def test_failed_refresh_bumps_ttl_clock(self, tmp_path):
        manager = await _make_manager(tmp_path)
        await manager._initialize_account(next(iter(manager._accounts)))
        account = next(iter(manager._accounts.values()))
        account.auth_manager._api_host = "https://q.us-east-1.amazonaws.com"
        account.models_cached_at = time.time() - ACCOUNT_CACHE_TTL - 100  # stale

        with patch.object(am, "_fetch_listed_models", AsyncMock(return_value=None)):
            await manager._refresh_account_models(account.id)

        age = time.time() - account.models_cached_at
        assert age < ACCOUNT_CACHE_TTL  # no longer stale
        remaining = ACCOUNT_CACHE_TTL - age
        assert remaining <= ACCOUNT_CACHE_RETRY_INTERVAL + 1  # retry soon, not after full TTL

    @pytest.mark.asyncio
    async def test_failed_refresh_keeps_existing_cache(self, tmp_path):
        manager = await _make_manager(tmp_path)
        await manager._initialize_account(next(iter(manager._accounts)))
        account = next(iter(manager._accounts.values()))
        account.auth_manager._api_host = "https://q.us-east-1.amazonaws.com"
        before = set(account.model_cache.get_all_model_ids())

        with patch.object(am, "_fetch_listed_models", AsyncMock(side_effect=httpx.ConnectError("x"))):
            await manager._refresh_account_models(account.id)

        assert set(account.model_cache.get_all_model_ids()) == before

    @pytest.mark.asyncio
    async def test_discovery_timeout_is_capped_and_resets_clock(self, tmp_path):
        manager = await _make_manager(tmp_path)
        await manager._initialize_account(next(iter(manager._accounts)))
        account = next(iter(manager._accounts.values()))
        account.auth_manager._api_host = "https://q.us-east-1.amazonaws.com"
        account.models_cached_at = time.time() - ACCOUNT_CACHE_TTL - 100

        async def hang(*a, **k):
            await asyncio.sleep(60)

        with patch.object(am, "_fetch_listed_models", hang), \
                patch.object(am, "MODEL_DISCOVERY_TIMEOUT", 0.05):
            await asyncio.wait_for(manager._refresh_account_models(account.id), 2)

        assert time.time() - account.models_cached_at < ACCOUNT_CACHE_TTL

    @pytest.mark.asyncio
    async def test_successful_refresh_updates_cache_and_mapping(self, tmp_path):
        manager = await _make_manager(tmp_path)
        await manager._initialize_account(next(iter(manager._accounts)))
        account = next(iter(manager._accounts.values()))
        account.auth_manager._api_host = "https://q.us-east-1.amazonaws.com"
        manager._dirty = False

        with patch.object(am, "_fetch_listed_models",
                          AsyncMock(return_value=[{"modelId": "brand-new"}])):
            await manager._refresh_account_models(account.id)

        assert "brand-new" in manager._model_to_accounts
        assert account.id in manager._model_to_accounts["brand-new"].accounts
        assert manager._dirty is True
        for hidden in HIDDEN_MODELS:  # hidden models survive a refresh
            assert hidden in account.model_resolver.get_available_models()


class TestBackgroundScheduling:
    """get_next_account never awaits discovery; one refresh per account."""

    @pytest.mark.asyncio
    async def test_refresh_not_awaited_under_lock(self, tmp_path):
        manager = await _make_manager(tmp_path)
        account_id = next(iter(manager._accounts))
        await manager._initialize_account(account_id)
        account = manager._accounts[account_id]
        account.models_cached_at = time.time() - ACCOUNT_CACHE_TTL - 10

        started = asyncio.Event()
        release = asyncio.Event()

        async def slow_refresh(_id):
            started.set()
            await release.wait()

        with patch.object(manager, "_refresh_account_models", slow_refresh):
            got = await asyncio.wait_for(manager.get_next_account("m"), 1)
            assert got is account  # returned while refresh still blocked
            await asyncio.wait_for(started.wait(), 1)
            assert not manager._lock.locked()  # lock free during refresh
            assert account.refreshing is True
            release.set()
            await asyncio.gather(*manager._tasks)
        assert account.refreshing is False

    @pytest.mark.asyncio
    async def test_only_one_refresh_per_account(self, tmp_path):
        manager = await _make_manager(tmp_path)
        account_id = next(iter(manager._accounts))
        await manager._initialize_account(account_id)
        release = asyncio.Event()
        calls = []

        async def slow_refresh(_id):
            calls.append(_id)
            await release.wait()

        with patch.object(manager, "_refresh_account_models", slow_refresh):
            assert manager._schedule_refresh(account_id) is True
            assert manager._schedule_refresh(account_id) is False
            await asyncio.sleep(0)
            release.set()
            await asyncio.gather(*manager._tasks)
        assert calls == [account_id]

    @pytest.mark.asyncio
    async def test_schedule_refresh_skips_uninitialized(self, tmp_path):
        manager = await _make_manager(tmp_path)
        assert manager._schedule_refresh(next(iter(manager._accounts))) is False
        assert manager._schedule_refresh("nope") is False

    @pytest.mark.asyncio
    async def test_fresh_cache_does_not_schedule(self, tmp_path):
        manager = await _make_manager(tmp_path)
        account_id = next(iter(manager._accounts))
        await manager._initialize_account(account_id)
        with patch.object(manager, "_schedule_refresh") as sched:
            await manager.get_next_account("m")
        sched.assert_not_called()

    @pytest.mark.asyncio
    async def test_lazy_init_is_fast_and_does_not_discover(self, tmp_path):
        manager = await _make_manager(tmp_path, count=2)
        with patch.object(am, "_fetch_listed_models", AsyncMock()) as tier1:
            account = await manager.get_next_account("m")
            assert account is not None and account.auth_manager is not None
            tier1.assert_not_awaited()  # discovery only in background task
            await asyncio.gather(*manager._tasks, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_initialize_falls_back_to_static_models(self, tmp_path):
        manager = await _make_manager(tmp_path)
        account_id = next(iter(manager._accounts))
        assert await manager._initialize_account(account_id)
        models = manager._accounts[account_id].model_resolver.get_available_models()
        assert "claude-sonnet-5" in models and "claude-opus-4.8" in models
        assert account_id in manager._model_to_accounts["claude-sonnet-5"].accounts

    @pytest.mark.asyncio
    async def test_start_background_init_initializes_remaining_accounts_concurrently(self, tmp_path):
        manager = await _make_manager(tmp_path, count=3)
        ids = list(manager._accounts)
        await manager._initialize_account(ids[0])

        with patch.object(manager, "_refresh_account_models", AsyncMock()):
            manager.start_background_init()
            await asyncio.gather(*manager._tasks, return_exceptions=True)

        assert all(a.auth_manager is not None for a in manager._accounts.values())

    @pytest.mark.asyncio
    async def test_failed_background_init_does_not_raise(self, tmp_path):
        manager = await _make_manager(tmp_path, count=2)
        with patch.object(manager, "_initialize_account", AsyncMock(return_value=False)):
            manager.start_background_init()
            await asyncio.gather(*manager._tasks, return_exceptions=True)
        assert not manager._tasks


class TestShutdown:
    """Background tasks are cancelled and the shared client closed."""

    @pytest.mark.asyncio
    async def test_shutdown_cancels_running_tasks(self, tmp_path):
        manager = await _make_manager(tmp_path)
        account_id = next(iter(manager._accounts))
        await manager._initialize_account(account_id)
        cancelled = asyncio.Event()

        async def forever(_id):
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        with patch.object(manager, "_refresh_account_models", forever):
            manager._schedule_refresh(account_id)
            await asyncio.sleep(0)
            await manager.shutdown()

        assert cancelled.is_set()
        assert not manager._tasks
        assert manager._accounts[account_id].refreshing is False

    @pytest.mark.asyncio
    async def test_shutdown_closes_discovery_client_and_is_idempotent(self, tmp_path):
        manager = await _make_manager(tmp_path)
        client = MagicMock()
        client.aclose = AsyncMock()
        manager._discovery_client = client
        assert manager._get_discovery_client() is client  # shared
        await manager.shutdown()
        client.aclose.assert_awaited_once()
        await manager.shutdown()  # no error

    @pytest.mark.asyncio
    async def test_shutdown_with_nothing_running(self, tmp_path):
        manager = await _make_manager(tmp_path)
        await manager.shutdown()
