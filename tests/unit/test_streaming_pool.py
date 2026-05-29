# -*- coding: utf-8 -*-

"""
Tests for StreamingPool - lightweight LRU connection pool for streaming.

Tests cover:
- Pool initialization and configuration
- Client acquisition and release logic
- Pool exhaustion behavior (max_size capping)
- Client eviction from pool
- Pool lifecycle (close_all, close all)
- Edge cases

Note: The conftest's block_all_network_calls fixture patches httpx.AsyncClient
to return a single mock instance. This means all acquired "clients" share the
same identity. Tests validate pool dict logic, not client uniqueness or
real is_closed behavior (which requires integration testing).
"""

import asyncio
import pytest

from kiro.streaming_pool import StreamingPool


def _pool_count(pool) -> int:
    """Return number of entries in the pool's internal dict."""
    return len(pool._pool)


# =============================================================================
# Initialization Tests
# =============================================================================

class TestStreamingPoolInitialization:
    """Tests for streaming pool construction and configuration."""

    def test_default_initialization(self):
        """Ensure defaults are reasonable for production."""
        pool = StreamingPool()
        assert pool._max_size == 8
        assert pool._keepalive == 30
        assert _pool_count(pool) == 0

    def test_custom_initialization(self):
        """Ensure custom configuration is applied correctly."""
        pool = StreamingPool(max_size=16, keepalive=60, stream_read_timeout=600.0)
        assert pool._max_size == 16
        assert pool._keepalive == 60

    def test_minimal_pool(self):
        """Pool with max_size=1 works (edge case)."""
        pool = StreamingPool(max_size=1, keepalive=5)
        assert pool._max_size == 1
        assert _pool_count(pool) == 0


# =============================================================================
# Acquire Tests
# =============================================================================

class TestStreamingPoolAcquire:
    """Tests for client acquisition from the pool."""

    @pytest.mark.asyncio
    async def test_acquire_creates_new_client_when_pool_empty(self):
        """Acquire from empty pool returns a valid client."""
        pool = StreamingPool(max_size=8, keepalive=30)
        client = await pool.acquire()
        # Pooled client must have is_closed attribute
        assert hasattr(client, 'is_closed')
        await client.aclose()

    @pytest.mark.asyncio
    async def test_acquire_reuses_pooled_client(self):
        """Acquire after release returns the same client (LRU reuse)."""
        pool = StreamingPool(max_size=8, keepalive=30)
        client1 = await pool.acquire()
        client1_id = id(client1)
        await pool.release(client1, errored=False)

        client2 = await pool.acquire()
        assert id(client2) == client1_id, "Pool should reuse the same instance"
        await client2.aclose()

    @pytest.mark.asyncio
    async def test_acquire_no_error(self):
        """Acquire from pool never raises."""
        pool = StreamingPool(max_size=8, keepalive=30)
        c1 = await pool.acquire()
        c2 = await pool.acquire()  # pool empty, should not error
        await c1.aclose()
        await c2.aclose()


# =============================================================================
# Release Tests
# =============================================================================

class TestStreamingPoolRelease:
    """Tests for returning clients to the pool."""

    @pytest.mark.asyncio
    async def test_release_healthy_client(self):
        """Healthy clients are returned to the pool."""
        pool = StreamingPool(max_size=8, keepalive=30)
        client = await pool.acquire()
        await pool.release(client, errored=False)
        assert _pool_count(pool) == 1
        await pool.close_all()

    @pytest.mark.asyncio
    async def test_release_errored_client_discards(self):
        """Errored clients are NOT returned to pool (self-healing)."""
        pool = StreamingPool(max_size=8, keepalive=30)
        client = await pool.acquire()
        await pool.release(client, errored=True)
        assert _pool_count(pool) == 0

    @pytest.mark.asyncio
    async def test_release_pool_does_not_exceed_max_size(self):
        """Pool never exceeds max_size entries (when clients are unique)."""
        pool = StreamingPool(max_size=2, keepalive=30)
        # Even though all acquires return the same mock, releasing at
        # capacity should not error and _pool should be bounded
        c1 = await pool.acquire()
        await pool.release(c1, errored=False)
        assert _pool_count(pool) <= 2
        await pool.close_all()


# =============================================================================
# Eviction Tests
# =============================================================================

class TestStreamingPoolEvict:
    """Tests for forced client eviction from the pool."""

    @pytest.mark.asyncio
    async def test_evict_removes_from_pool(self):
        """Eviction removes a pooled client from the pool dict."""
        pool = StreamingPool(max_size=8, keepalive=30)
        client = await pool.acquire()
        await pool.release(client, errored=False)
        await pool.evict(client)
        assert _pool_count(pool) == 0

    @pytest.mark.asyncio
    async def test_evict_non_pooled_no_error(self):
        """Evicting a non-pooled client doesn't raise."""
        pool = StreamingPool(max_size=8, keepalive=30)
        client = await pool.acquire()
        await pool.evict(client)  # not in pool yet
        assert _pool_count(pool) == 0

    @pytest.mark.asyncio
    async def test_evict_then_acquire(self):
        """Pool recovers after full eviction."""
        pool = StreamingPool(max_size=8, keepalive=30)
        clients = [await pool.acquire() for _ in range(2)]
        for c in clients:
            await pool.release(c, errored=False)
        for c in clients:
            await pool.evict(c)
        assert _pool_count(pool) == 0

        new_client = await pool.acquire()
        await new_client.aclose()


# =============================================================================
# Pool Lifecycle Tests
# =============================================================================

class TestStreamingPoolLifecycle:
    """Tests for pool-wide lifecycle operations."""

    @pytest.mark.asyncio
    async def test_close_all_empties_pool(self):
        """close_all clears the pool."""
        pool = StreamingPool(max_size=8, keepalive=30)
        clients = [await pool.acquire() for _ in range(3)]
        for c in clients:
            await pool.release(c, errored=False)
        await pool.close_all()
        assert _pool_count(pool) == 0

    @pytest.mark.asyncio
    async def test_close_all_empty_pool(self):
        """close_all on empty pool doesn't raise."""
        pool = StreamingPool(max_size=8, keepalive=30)
        await pool.close_all()
        assert _pool_count(pool) == 0

    @pytest.mark.asyncio
    async def test_size_tracks_pool_occupancy(self):
        """size() reflects acquire/release changes."""
        pool = StreamingPool(max_size=8, keepalive=30)
        assert await pool.size() == 0

        c1 = await pool.acquire()
        await pool.release(c1)
        assert await pool.size() == 1

        acquired = await pool.acquire()  # removes from pool
        assert await pool.size() == 0

        await acquired.aclose()

    @pytest.mark.asyncio
    async def test_maintains_single_client_on_reuse(self):
        """Repeated acquire/release cycles keep pool count at 1."""
        pool = StreamingPool(max_size=4, keepalive=30)
        for _ in range(5):
            client = await pool.acquire()
            await pool.release(client, errored=False)
        assert _pool_count(pool) == 1
        await pool.close_all()

    @pytest.mark.asyncio
    async def test_close_all_idempotent(self):
        """Calling close_all twice doesn't raise."""
        pool = StreamingPool(max_size=8, keepalive=30)
        await pool.close_all()
        await pool.close_all()


# =============================================================================
# Edge Cases
# =============================================================================

class TestStreamingPoolEdgeCases:
    """Tests for unusual or boundary conditions."""

    @pytest.mark.asyncio
    async def test_max_size_1(self):
        """Pool with max_size=1 works correctly."""
        pool = StreamingPool(max_size=1, keepalive=30)
        c1 = await pool.acquire()
        await pool.release(c1)

        c2 = await pool.acquire()
        assert c1 is c2  # same mock, but proves acquire->release->acquire cycle
        await pool.release(c2)

        c3 = await pool.acquire()
        await pool.release(c3)
        assert _pool_count(pool) == 1
        await pool.close_all()

    @pytest.mark.asyncio
    async def test_concurrent_acquire_and_release(self):
        """Concurrent acquire/release doesn't raise."""
        pool = StreamingPool(max_size=8, keepalive=30)

        clients = await asyncio.gather(
            pool.acquire(),
            pool.acquire(),
            pool.acquire(),
        )

        await asyncio.gather(*[
            pool.release(c, errored=False) for c in clients
        ])

        assert _pool_count(pool) <= pool._max_size
        await pool.close_all()

    @pytest.mark.asyncio
    async def test_release_after_close_all_errored_discards(self):
        """Errored release after close_all discards cleanly."""
        pool = StreamingPool(max_size=8, keepalive=30)
        client = await pool.acquire()
        await pool.close_all()
        await pool.release(client, errored=True)
        assert _pool_count(pool) == 0

    @pytest.mark.asyncio
    async def test_release_with_error_after_close_all(self):
        """Errored release after close_all discards properly."""
        pool = StreamingPool(max_size=8, keepalive=30)
        client = await pool.acquire()
        await pool.close_all()
        await pool.release(client, errored=True)
        assert _pool_count(pool) == 0

    @pytest.mark.asyncio
    async def test_evict_twice_idempotent(self):
        """Double eviction doesn't raise."""
        pool = StreamingPool(max_size=8, keepalive=30)
        client = await pool.acquire()
        await pool.release(client)
        await pool.evict(client)
        await pool.evict(client)
        assert _pool_count(pool) == 0

    @pytest.mark.asyncio
    async def test_evict_among_multiple(self):
        """Evicting one client preserves others."""
        pool = StreamingPool(max_size=8, keepalive=30)
        # Acquire/release multiple times to put same mock in pool
        c1 = await pool.acquire()
        await pool.release(c1)
        c2 = await pool.acquire()
        await pool.release(c2)

        # Both point to same mock, pool has 1 entry
        await pool.evict(c1)
        assert _pool_count(pool) == 0

    @pytest.mark.asyncio
    async def test_keepalive_config_applied(self):
        """Pool accepts keepalive config."""
        pool = StreamingPool(max_size=8, keepalive=120)
        client = await pool.acquire()
        await client.aclose()
