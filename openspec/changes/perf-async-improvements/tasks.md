# Tasks: perf-async-improvements

- **Status:** tasks_complete
- **Change name:** `perf-async-improvements`
- **Type:** architecture / performance
- **Delivery:** Chained PRs, stacked to main (#1 → #2 → #3)
- **TDD mode:** Strict — tests MUST be written BEFORE the implementation in every task
- **Next recommended phase:** apply

---

## PR #1 — Shared streaming client + auth singleton

**Branch:** `feat/perf-async-pr1-shared-client`  
**Stacks onto:** `main`  
**Files:** `kiro/auth.py`, `kiro/routes_openai.py`, `kiro/routes_anthropic.py`, `kiro/account_manager.py`, `main.py`  
**New test file:** `tests/unit/test_perf_pr1_shared_client.py`

- [x] T1.1 [TEST] Write `test_kiro_auth_manager_accepts_refresh_client` — assert `KiroAuthManager(refresh_client=mock_client)` stores it as `self._refresh_client` without raising — `tests/unit/test_perf_pr1_shared_client.py`
- [x] T1.2 [IMPL] Add `refresh_client: Optional[httpx.AsyncClient] = None` parameter to `KiroAuthManager.__init__` (`auth.py:119`); store as `self._refresh_client` — `kiro/auth.py`
- [x] T1.3 [TEST] Write `test_auth_refresh_desktop_uses_refresh_client` — patch `app.state.auth_http_client` with a mock; trigger `force_refresh()`; assert mock's `.post` is called and no new `httpx.AsyncClient()` is constructed — `tests/unit/test_perf_pr1_shared_client.py`
- [x] T1.4 [IMPL] Replace `async with httpx.AsyncClient(timeout=30)` in `_refresh_token_kiro_desktop` (`auth.py:708`) with injected-client pattern: use `self._refresh_client` when set, fall back to a per-call client (with `owns` guard + `aclose()` in finally) — `kiro/auth.py`
- [x] T1.5 [IMPL] Same injected-client replacement in `_refresh_token_aws_sso_oidc` (`auth.py:825`) — `kiro/auth.py`
- [x] T1.6 [TEST] Write `test_streaming_openai_uses_shared_client` — spy on `KiroHttpClient.__init__`; assert `shared_client` arg `is request.app.state.http_client`; assert no new `httpx.AsyncClient()` constructed during streaming OpenAI request — `tests/unit/test_perf_pr1_shared_client.py`
- [x] T1.7 [IMPL] Change streaming branch in `routes_openai.py` (lines ~351, ~603): replace `shared_client=None` with `shared_client=getattr(request.app.state, "http_client", None)`; add warning log when `None` — `kiro/routes_openai.py`
- [x] T1.8 [TEST] Write `test_streaming_anthropic_uses_shared_client` — same as T1.6 but targeting Anthropic streaming endpoint (lines ~414, ~726) — `tests/unit/test_perf_pr1_shared_client.py`
- [x] T1.9 [IMPL] Change streaming branch in `routes_anthropic.py` (lines ~414, ~726): same `getattr` pattern as T1.7 — `kiro/routes_anthropic.py`
- [x] T1.10 [TEST] Write `test_connection_close_header_on_stream` — intercept outgoing request via `MockTransport`; call `http_client.request_with_retry(..., stream=True)`; assert `Connection: close` in captured request headers (regression for issues #38, #54) — `tests/unit/test_perf_pr1_shared_client.py`
- [x] T1.11 [TEST] Write `test_auth_singleton_lifecycle` — boot app via `httpx.ASGITransport`; assert `app.state.auth_http_client` is not `None` after startup and `is_closed == True` after shutdown — `tests/unit/test_perf_pr1_shared_client.py`
- [x] T1.12 [IMPL] Create `app.state.auth_http_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=True)` in lifespan startup (`main.py:351` block); add `await app.state.auth_http_client.aclose()` in lifespan shutdown (`main.py:530`) — `main.py`
- [x] T1.13 [IMPL] Add optional `auth_http_client: Optional[httpx.AsyncClient] = None` to `AccountManager.__init__`; store as `self._auth_http_client`; forward as `refresh_client=self._auth_http_client` in all three `KiroAuthManager(...)` constructions (`account_manager.py:473/480/487`) — `kiro/account_manager.py`
- [x] T1.14 [IMPL] Pass `auth_http_client=app.state.auth_http_client` to `AccountManager(...)` in `main.py:456` — `main.py`
- [x] T1.15 [TEST] Write `test_no_close_wait_regression` — 5 concurrent streaming requests via `asyncio.gather()` with a connection-counting `MockTransport`; assert active connection count returns to 0 after all responses are consumed — `tests/unit/test_perf_pr1_shared_client.py`
- [x] T1.16 [TEST] Run full suite: `.venv/bin/pytest tests/unit/` — all 1673 baseline tests + new T1.x tests must pass

**PR #1 acceptance gates:**
- `rg 'httpx\.AsyncClient\(' kiro/auth.py kiro/routes_openai.py kiro/routes_anthropic.py` returns 0 matches in hot-path handlers (only module-level or startup wiring permitted)
- `Connection: close` header preserved (T1.10)
- No CLOSE_WAIT regression (T1.15)
- Full suite passes (T1.16)

---

## PR #2 — Async file/SQLite I/O via asyncio.to_thread

**Branch:** `feat/perf-async-pr2-offloop-io`  
**Stacks onto:** `feat/perf-async-pr1-shared-client`  
**Files:** `kiro/auth.py`, `kiro/account_manager.py`  
**New test file:** `tests/unit/test_perf_pr2_async_io.py`

- [ ] T2.1 [TEST] Write `test_save_state_runs_off_event_loop` — patch `asyncio.to_thread` to record calls; create `AccountManager` with a temp state file; call `await account_manager._save_state()`; assert `asyncio.to_thread` was called with a callable and a concurrent `asyncio.sleep(0)` task completes before the save callable finishes — `tests/unit/test_perf_pr2_async_io.py`
- [ ] T2.2 [IMPL] Make `AccountManager._save_state()` `async def`; build the `state_data` snapshot on the event loop; wrap the `json.dump` + `tmp_path.replace(state_path)` sequence as a single `_write` closure passed to `asyncio.to_thread`; acquire `self._save_lock` before calling `to_thread` — `kiro/account_manager.py`
- [ ] T2.3 [IMPL] Add `self._save_lock = asyncio.Lock()` to `AccountManager.__init__`; update all callers of `_save_state()` to `await` it (callers in `main.py:503`, `main.py:525`, `account_manager.py:429` already `await` — verify no sync callers remain) — `kiro/account_manager.py`
- [ ] T2.4 [TEST] Write `test_save_state_atomic_write` — set up temp dir with a real state file; patch `os.replace` / `Path.replace` to raise after `json.dump`; call `await account_manager._save_state()`; assert original state file is intact and not corrupted — `tests/unit/test_perf_pr2_async_io.py`
- [ ] T2.5 [TEST] Write `test_save_state_periodically_with_async_save` — assert `save_state_periodically()` correctly `await`s the new async `_save_state()` without `RuntimeWarning` or `TypeError` — `tests/unit/test_perf_pr2_async_io.py`
- [ ] T2.6 [TEST] Write `test_save_credentials_to_file_runs_off_event_loop` — patch `asyncio.to_thread`; create `Auth` instance with a temp credentials file; call `await auth._save_credentials_to_file()`; assert `asyncio.to_thread` was called and no synchronous `open()` occurs on the calling coroutine's frame — `tests/unit/test_perf_pr2_async_io.py`
- [ ] T2.7 [IMPL] Make `auth._save_credentials_to_file()` (`auth.py:489`) `async def`; move read-existing + write body into a single closure passed to `asyncio.to_thread`; acquire `self._save_lock` before entering the thread — `kiro/auth.py`
- [ ] T2.8 [IMPL] Add `self._save_lock = asyncio.Lock()` to `KiroAuthManager.__init__`; update caller at `auth.py:741` to `await self._save_credentials_to_file()` — `kiro/auth.py`
- [ ] T2.9 [TEST] Write `test_save_credentials_to_sqlite_runs_off_event_loop` — patch `asyncio.to_thread`; create `Auth` instance with a temp SQLite DB; call `await auth._save_credentials_to_sqlite()`; assert `asyncio.to_thread` was called and `sqlite3.connect` is not called from the event loop thread — `tests/unit/test_perf_pr2_async_io.py`
- [ ] T2.10 [IMPL] Make `auth._save_credentials_to_sqlite()` (`auth.py:524`) `async def`; keep `SQLITE_READONLY` and `self._sqlite_db` guards on the loop (early return before entering thread); move `sqlite3.connect` + read-merge-write + commit into a single closure passed to `asyncio.to_thread`; acquire `self._save_lock`; update caller at `auth.py:739` to `await self._save_credentials_to_sqlite()` — `kiro/auth.py`
- [ ] T2.11 [TEST] Write `test_load_credentials_from_sqlite_remains_sync` — assert `not asyncio.iscoroutinefunction(auth._load_credentials_from_sqlite)`; call it directly from a non-async context; assert no `RuntimeWarning` raised — `tests/unit/test_perf_pr2_async_io.py`
- [ ] T2.12 [NOTE] `_load_credentials_from_sqlite()` stays `def` — called from synchronous `__init__`. No change needed. This is verified by T2.11.
- [ ] T2.13 [TEST] Write `test_concurrent_saves_serialized` — patch `asyncio.to_thread` to record call timestamps; issue 5 concurrent `await auth._save_credentials_to_sqlite()` calls via `asyncio.gather()`; assert no two save callables overlap in execution (timestamp ranges disjoint), proving `_save_lock` serializes them — `tests/unit/test_perf_pr2_async_io.py`
- [ ] T2.14 [TEST] Write `test_event_loop_unblocked_during_save` — start a background task that appends timestamps on every `asyncio.sleep(0)` iteration; trigger `_save_state()` with a thread body that `time.sleep(0.02)`; assert the background task appended at least one timestamp during the save — `tests/unit/test_perf_pr2_async_io.py`
- [ ] T2.15 [TEST] Write `test_sqlite_readonly_flag_skips_write` — set `SQLITE_READONLY=true` in environment; call `await auth._save_credentials_to_sqlite()`; assert `asyncio.to_thread` is NOT called and the DB is unchanged — `tests/unit/test_perf_pr2_async_io.py`
- [ ] T2.16 [TEST] Write `test_get_access_token_reload_path` — assert `get_access_token()` reload path works correctly when `_load_credentials_from_sqlite` remains sync (no coroutine wrapping) — `tests/unit/test_perf_pr2_async_io.py`
- [ ] T2.17 [TEST] Run full suite: `.venv/bin/pytest tests/unit/` — all baseline + T1.x + T2.x tests must pass

**PR #2 acceptance gates:**
- `_save_state`, `_save_credentials_to_file`, `_save_credentials_to_sqlite` are all `async def` and delegate blocking work to `asyncio.to_thread`
- `_load_credentials_from_sqlite` remains `def` (synchronous) — verified by T2.11
- `rg 'sqlite3\.connect|open\(' kiro/account_manager.py kiro/auth.py` shows no blocking I/O calls in async functions outside of `asyncio.to_thread` wrappers
- Full suite passes (T2.17)

---

## PR #3 — Lock decomposition in AccountManager

**Branch:** `feat/perf-async-pr3-lock-decomp`  
**Stacks onto:** `feat/perf-async-pr2-offloop-io`  
**Files:** `kiro/account_manager.py`  
**New test file:** `tests/unit/test_perf_pr3_lock_decomp.py`

- [ ] T3.1 [TEST] Write `test_no_http_under_global_lock` — patch `_refresh_account_models` to record whether `_coordination_lock.locked()` is `True` at the moment of the HTTP call; set up an account with an expired model TTL; call `await account_manager.get_next_account(model="test-model")`; assert `_coordination_lock.locked()` was `False` at HTTP-call time — `tests/unit/test_perf_pr3_lock_decomp.py`
- [ ] T3.2 [IMPL] Rename `self._lock` → `self._coordination_lock` in `AccountManager.__init__` (`account_manager.py:210`) and all references (`save_state_periodically`, `report_success`, `report_failure`, `get_next_account`) — `kiro/account_manager.py`
- [ ] T3.3 [IMPL] Add `self._account_locks: Dict[str, asyncio.Lock] = {}` and `self._refresh_in_flight: set[str] = set()` to `AccountManager.__init__`; add a comment block at lock declarations: `# Lock acquisition order (MUST hold): _coordination_lock (L1) → per-account lock (L2) → Auth._lock (L3). Never hold L1 across an await of an HTTP call.` — `kiro/account_manager.py`
- [ ] T3.4 [IMPL] Add `_get_account_lock(self, account_id: str) -> asyncio.Lock` helper (called only while holding `_coordination_lock`; creates and caches per-account locks in `self._account_locks`); add `async def _account_lock_for(self, account_id: str)` wrapper that briefly takes `_coordination_lock` to mutate `_account_locks` safely — `kiro/account_manager.py`
- [ ] T3.5 [TEST] Write `test_double_checked_locking_no_toctou` as a Hypothesis property test over `N` in `[2, 20]` — N concurrent coroutines all call `get_next_account()` for a model with an uninitialized account; patch `_initialize_account` to track call count; assert `_initialize_account` is called exactly once despite N concurrent callers — `tests/unit/test_perf_pr3_lock_decomp.py`
- [ ] T3.6 [IMPL] Extract `_select_candidate(self, model, exclude_accounts)` pure in-memory helper from `get_next_account` — returns `(account_id, account)` or `(None, None)`; no `await`, no HTTP; preserves circuit-breaker / sticky-index / probabilistic-retry logic — `kiro/account_manager.py`
- [ ] T3.7 [IMPL] Rewrite `get_next_account()` using the three-phase lock hierarchy:
  - **Phase A (L1):** `async with self._coordination_lock`: call `_select_candidate`, read `account.auth_manager is None` → `needs_init`, read TTL age → `needs_refresh`; release L1
  - **Phase B (L2, double-checked):** if `needs_init`: `async with self._account_lock_for(account_id)`: re-check `account.auth_manager is None`; if still `None`, `await self._initialize_account(account_id)` (HTTP under L2 only); commit failure/success under brief L1 re-acquire; set `needs_refresh = False`
  - **Phase C (L2, deduped stale-serve):** if `needs_refresh`: call `await self._maybe_refresh(account_id)`
  - Return `account`
  — `kiro/account_manager.py`
- [ ] T3.8 [TEST] Write `test_per_account_refresh_isolation` — 2 accounts (A, B); patch HTTP for account A to take 100 ms; set both accounts' model caches as expired; issue concurrent requests for both; assert account B's request completes without waiting for account A's refresh (wall-clock time for B < 50 ms) — `tests/unit/test_perf_pr3_lock_decomp.py`
- [ ] T3.9 [IMPL] Add `async def _maybe_refresh(self, account_id: str)` implementing the dedup + stale-serve pattern:
  - L1: check `_refresh_in_flight`; if already in flight return immediately (stale serve, no block)
  - L1: add to `_refresh_in_flight`, get per-account lock; release L1
  - L2: `await self._refresh_account_models(account_id)` (HTTP under L2 only)
  - `finally` L1: `_refresh_in_flight.discard(account_id)`
  — `kiro/account_manager.py`
- [ ] T3.10 [TEST] Write `test_concurrent_refresh_deduplication` — 1 account with expired TTL; patch `_refresh_account_models` to count HTTP invocations and take 50 ms each; 5 concurrent `get_next_account()` calls via `asyncio.gather()`; assert HTTP called exactly once and all 5 callers receive a valid account — `tests/unit/test_perf_pr3_lock_decomp.py`
- [ ] T3.11 [TEST] Write `test_stale_cache_served_during_refresh` — 1 account with expired TTL; slow HTTP mock (200 ms); while refresh is in flight issue a second request; assert second request is served (not blocked) using stale model list; no `TimeoutError` or deadlock — `tests/unit/test_perf_pr3_lock_decomp.py`
- [ ] T3.12 [IMPL] Rewrite `report_success()` and `report_failure()` to use only `_coordination_lock` (rename `_lock` → `_coordination_lock`); confirm no HTTP call or file I/O occurs while lock is held — `kiro/account_manager.py`
- [ ] T3.13 [TEST] Write `test_report_success_no_http` — assert `report_success()` triggers no `await` of an HTTP call; it only mutates in-memory counters (the off-loop `_save_state` from PR #2 is not a blocking concern) — `tests/unit/test_perf_pr3_lock_decomp.py`
- [ ] T3.14 [TEST] Write `test_lock_acquisition_order_documented` — read `kiro/account_manager.py` source; assert the string `# Lock acquisition order` appears near the lock declarations (code-review gate encoded as a source-inspection test) — `tests/unit/test_perf_pr3_lock_decomp.py`
- [ ] T3.15 [TEST] Write `test_no_deadlock_concurrent_multi_account` as a Hypothesis property test over `account_count` in `[2, 5]` and `request_count` in `[10, 50]` — concurrent requests spread across all accounts with expired TTL; `asyncio.gather(*requests)` with a 5 s timeout; assert all requests complete within timeout (0 `asyncio.TimeoutError`s) — `tests/unit/test_perf_pr3_lock_decomp.py`
- [ ] T3.16 [TEST] Write `test_lock_not_held_during_http` — wrap `_refresh_account_models` and `_initialize_account` with spies that read `self._coordination_lock.locked()` synchronously at entry; assert `locked()` is `False` in both cases (static verifiability via single-threaded asyncio) — `tests/unit/test_perf_pr3_lock_decomp.py`
- [ ] T3.17 [TEST] Write `test_concurrency_throughput_improvement` (integration) — baseline fixture runs 10 concurrent requests against a 3-account mock with 50 ms refresh under old single-lock code path (captured via separate fixture or feature flag); post-change fixture runs same scenario with lock decomposition; assert post-change wall-clock ≤ 50% of baseline (≥ 2× throughput) — `tests/unit/test_perf_pr3_lock_decomp.py`
- [ ] T3.18 [TEST] Run full suite: `.venv/bin/pytest tests/unit/` — all baseline + T1.x + T2.x + T3.x tests must pass

**PR #3 acceptance gates:**
- `rg 'await.*request_with_retry|await.*http' kiro/account_manager.py` shows no HTTP awaits inside any `_coordination_lock` context manager block
- T3.5 Hypothesis test finds no TOCTOU shrink case
- T3.15 deadlock test passes with 0 timeouts at N=50
- Lock acquisition order documented in source (T3.14)
- Full suite passes (T3.18)

---

## Review Workload Forecast

| Metric | Value |
|--------|-------|
| Estimated changed lines | ~300–400 lines across 5 files |
| Files touched | `kiro/auth.py`, `kiro/account_manager.py`, `kiro/routes_openai.py`, `kiro/routes_anthropic.py`, `main.py` |
| New test cases | +30–40 new test cases across 3 new test files |
| Existing tests needing async signature updates | Low — existing callers already `await` save methods |
| PR #1 diff | ~80 lines, low complexity |
| PR #2 diff | ~100 lines, medium complexity |
| PR #3 diff | ~200 lines, high complexity |
| 400-line budget risk | MEDIUM — borderline, especially if PR #3 grows |
| Chained PRs recommended | YES (already decided — stacked to main) |
| Decision needed before apply | NO — delivery strategy already set |

---

## Task summary by PR

| PR | Tasks | Tests | Impl |
|----|-------|-------|------|
| #1 | 16 | 7 new test cases | 9 impl steps |
| #2 | 17 | 10 new test cases | 6 impl steps + 1 note |
| #3 | 18 | 12 new test cases | 5 impl steps |
| **Total** | **51** | **29 new test cases** | **20 impl steps** |
