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
Streaming connection pool for Kiro Gateway.

Provides a lightweight LRU pool of reusable httpx clients for streaming requests.
Designed to reduce TCP connection overhead while avoiding CLOSE_WAIT leaks
on VPN disconnect by self-healing: errored clients are evicted and replaced.

Design constraints:
- Max pool size (configurable, default 8)
- Self-healing: clients with connection errors are evicted
- Graceful degradation: falls back to creating new clients if pool is exhausted
- Thread-safe with asyncio.Lock
"""

import asyncio
from collections import OrderedDict
from typing import Optional

import httpx
from loguru import logger


class StreamingPool:
    """
    Lightweight LRU pool of reusable httpx clients for streaming.

    Maintains a pool of httpx.AsyncClient instances for streaming requests.
    Clients are reused in LRU order. Errored clients are automatically evicted.
    Falls back to creating a new client when pool is exhausted.

    This is an optimization over per-request clients (which create a new TCP
    connection per request) while still avoiding CLOSE_WAIT leaks: if a client
    encounters an error, it's discarded rather than returned to the pool.

    Attributes:
        max_size: Maximum number of pooled clients
        keepalive: Keepalive timeout for pooled connections
        timeout: httpx.Timeout configuration for streaming

    Example:
        >>> pool = StreamingPool(max_size=8, keepalive=30)
        >>> client = await pool.acquire()
        >>> try:
        ...     async with client.stream("POST", url) as response:
        ...         ...
        ... finally:
        ...     await pool.release(client)
    """

    def __init__(
        self,
        max_size: int = 8,
        keepalive: int = 30,
        stream_read_timeout: float = 300.0,
    ):
        """
        Initialize streaming pool.

        Args:
            max_size: Maximum number of pooled clients
            keepalive: Keepalive timeout in seconds for pooled connections
            stream_read_timeout: Read timeout for streaming responses
        """
        self._max_size = max_size
        self._keepalive = keepalive
        self._timeout = httpx.Timeout(
            connect=30.0,
            read=stream_read_timeout,
            write=30.0,
            pool=30.0,
        )
        self._pool: OrderedDict[int, httpx.AsyncClient] = OrderedDict()
        self._lock = asyncio.Lock()

    async def acquire(self) -> httpx.AsyncClient:
        """
        Get a client from the pool or create a new one.

        Reuses the least-recently-used client from the pool.
        If pool is empty, creates a new httpx.AsyncClient.

        Returns:
            httpx.AsyncClient ready for streaming
        """
        async with self._lock:
            if self._pool:
                # Pop the least-recently-used client
                _key, client = self._pool.popitem(last=False)
                if not client.is_closed:
                    logger.debug("StreamingPool: reused pooled client")
                    return client
                logger.debug("StreamingPool: discarded closed client")

        # Create new client (always safe path)
        logger.debug("StreamingPool: created new client")
        return self._create_client()

    async def release(self, client: httpx.AsyncClient, errored: bool = False) -> None:
        """
        Return a client to the pool or discard it.

        Clients with errors are closed and discarded. Healthy clients are
        returned to the pool (up to max_size) or closed if pool is full.

        If the client is already in the pool (e.g. release called twice),
        it is removed first to prevent duplicate entries.

        Args:
            client: httpx.AsyncClient to release
            errored: True if the client experienced a connection error
        """
        if errored or client.is_closed:
            # Remove from pool if present (e.g. previously released healthy)
            client_id = id(client)
            async with self._lock:
                if client_id in self._pool:
                    del self._pool[client_id]
            await self._close_client(client)
            return

        async with self._lock:
            if len(self._pool) < self._max_size:
                # Return to pool (mark as recently used)
                client_id = id(client)
                self._pool[client_id] = client
                self._pool.move_to_end(client_id)
                logger.debug("StreamingPool: returned client to pool")
                return

        # Pool is full, close this client
        await self._close_client(client)

    async def evict(self, client: httpx.AsyncClient) -> None:
        """
        Evict a client from the pool (on connection error).

        Removes and closes the client regardless of pool state.

        Args:
            client: httpx.AsyncClient to evict
        """
        client_id = id(client)
        async with self._lock:
            if client_id in self._pool:
                del self._pool[client_id]
        await self._close_client(client)

    async def close_all(self) -> None:
        """Close all clients in the pool."""
        async with self._lock:
            for _key, client in self._pool.items():
                try:
                    await client.aclose()
                except Exception as e:
                    logger.debug(f"StreamingPool: error closing client: {e}")
            self._pool.clear()
        logger.info("StreamingPool: closed all clients")

    async def size(self) -> int:
        """Return current pool size."""
        async with self._lock:
            # Clean closed clients
            closed_keys = [
                k for k, v in self._pool.items() if v.is_closed
            ]
            for k in closed_keys:
                del self._pool[k]
            return len(self._pool)

    def _create_client(self) -> httpx.AsyncClient:
        """Create a new httpx.AsyncClient for streaming."""
        limits = httpx.Limits(
            max_keepalive_connections=1,
            max_connections=1,
            keepalive_expiry=self._keepalive,
        )
        return httpx.AsyncClient(
            timeout=self._timeout,
            limits=limits,
            follow_redirects=True,
        )

    async def _close_client(self, client: httpx.AsyncClient) -> None:
        """Safely close a client."""
        try:
            if not client.is_closed:
                await client.aclose()
        except Exception as e:
            logger.debug(f"StreamingPool: error closing client: {e}")
