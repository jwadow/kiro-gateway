# -*- coding: utf-8 -*-

"""Shared pacing for requests sent to the Kiro runtime API."""

import asyncio
import random
from asyncio import sleep as _sleep

from loguru import logger

from kiro.config import KIRO_429_COOLDOWN_SECONDS, KIRO_429_JITTER_SECONDS, KIRO_REQUEST_MIN_INTERVAL_SECONDS


class UpstreamRequestPacer:
    """Coordinate request starts and rate-limit cooldowns across HTTP clients."""

    def __init__(self, min_interval: float, cooldown: float, jitter: float) -> None:
        self._min_interval = max(0.0, min_interval)
        self._cooldown = max(0.0, cooldown)
        self._jitter = max(0.0, jitter)
        self._next_start = 0.0
        self._cooldown_until = 0.0
        self._lock = asyncio.Lock()

    async def wait_for_slot(self) -> None:
        """Wait until both start pacing and any shared cooldown permit a request."""
        while True:
            async with self._lock:
                loop = asyncio.get_running_loop()
                now = loop.time()
                delay = max(self._next_start, self._cooldown_until) - now
                if delay <= 0:
                    self._next_start = now + self._min_interval
                    return

            # Do not hold the lock while sleeping. A concurrent 429 must be able
            # to extend the cooldown, which this loop re-checks before admission.
            logger.debug(f"Pacing upstream request for {delay:.2f}s")
            await _sleep(delay)

    async def register_rate_limit(self, retry_after: float | None = None) -> float:
        """Extend the process-wide cooldown and return its remaining duration."""
        async with self._lock:
            cooldown = max(self._cooldown, retry_after or 0.0)
            if cooldown <= 0:
                return 0.0

            cooldown += random.uniform(0.0, self._jitter)
            loop = asyncio.get_running_loop()
            self._cooldown_until = max(self._cooldown_until, loop.time() + cooldown)
            remaining = max(0.0, self._cooldown_until - loop.time())
            logger.warning(f"Shared upstream cooldown extended by {remaining:.2f}s")
            return remaining

    def configure_for_tests(self, min_interval: float, cooldown: float, jitter: float) -> None:
        """Reset timing and configuration for deterministic unit tests."""
        self._min_interval = max(0.0, min_interval)
        self._cooldown = max(0.0, cooldown)
        self._jitter = max(0.0, jitter)
        self._next_start = 0.0
        self._cooldown_until = 0.0
        self._lock = asyncio.Lock()


upstream_request_pacer = UpstreamRequestPacer(
    min_interval=KIRO_REQUEST_MIN_INTERVAL_SECONDS,
    cooldown=KIRO_429_COOLDOWN_SECONDS,
    jitter=KIRO_429_JITTER_SECONDS,
)
