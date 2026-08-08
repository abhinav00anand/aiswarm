"""Per."""

from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_DEFAULTS: dict[str, dict[str, int]] = {
    "novita":    {"rpm": 60,  "concurrency": 5},
    "openai":    {"rpm": 60,  "concurrency": 5},
    "anthropic": {"rpm": 50,  "concurrency": 4},
    "gemini":    {"rpm": 60,  "concurrency": 5},
    "deepseek":  {"rpm": 30,  "concurrency": 3},
    "bedrock":   {"rpm": 30,  "concurrency": 3},
    "local":     {"rpm": 999, "concurrency": 2},
}

class ProviderRateLimiter:
    """
    Per-provider rate limiter with:
      - Sliding window RPM enforcement
      - Concurrent request cap (semaphore)
      - Automatic backoff on 429 responses

    Usage (as async context manager)::

        limiter = ProviderRateLimiter()
        async with limiter.acquire("novita"):
            response = await provider.chat(...)
    """

    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = {}
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._rpm: dict[str, int] = {}
        self._backoff_until: dict[str, float] = {}

        for provider, defaults in _DEFAULTS.items():
            rpm = int(os.getenv(f"RATE_LIMIT_{provider.upper()}_RPM", str(defaults["rpm"])))
            conc = int(os.getenv(f"RATE_LIMIT_{provider.upper()}_CONC", str(defaults["concurrency"])))
            self._rpm[provider] = rpm
            self._semaphores[provider] = asyncio.Semaphore(conc)
            self._windows[provider] = deque()

    def acquire(self, provider: str) -> "_AcquireCtx":
        return _AcquireCtx(self, provider)

    async def _acquire(self, provider: str) -> None:
        """Wait until the provider is within rate limits, then acquire the semaphore."""
        # Respect any active backoff (from 429 responses)
        backoff = self._backoff_until.get(provider, 0.0)
        if backoff > time.monotonic():
            wait = backoff - time.monotonic()
            logger.info("rate_limiter.backoff_wait", provider=provider, wait_s=round(wait, 2))
            await asyncio.sleep(wait)

        # Acquire the concurrency semaphore
        sem = self._semaphores.get(provider)
        if sem is None:
            # Unknown provider — create on-demand with conservative defaults
            sem = asyncio.Semaphore(3)
            self._semaphores[provider] = sem
            self._windows[provider] = deque()
            self._rpm[provider] = 30

        await sem.acquire()

        # Enforce RPM sliding window
        rpm = self._rpm[provider]
        window = self._windows[provider]
        now = time.monotonic()

        # Evict timestamps older than 60 seconds
        while window and now - window[0] > 60.0:
            window.popleft()

        if len(window) >= rpm:
            # Wait until the oldest request falls outside the 60-second window
            wait = 60.0 - (now - window[0]) + 0.01
            logger.debug(
                "rate_limiter.rpm_wait",
                provider=provider,
                window_size=len(window),
                wait_s=round(wait, 2),
            )
            sem.release()
            await asyncio.sleep(wait)
            await sem.acquire()
            # Re-evict after waiting
            now = time.monotonic()
            while window and now - window[0] > 60.0:
                window.popleft()

        window.append(time.monotonic())
        logger.debug("rate_limiter.acquired", provider=provider, rpm_used=len(window))

    def _release(self, provider: str) -> None:
        sem = self._semaphores.get(provider)
        if sem:
            sem.release()

    def notify_rate_limited(self, provider: str, retry_after_seconds: float = 30.0) -> None:
        """Call this when a provider returns HTTP 429."""
        self._backoff_until[provider] = time.monotonic() + retry_after_seconds
        logger.warning(
            "rate_limiter.429_received",
            provider=provider,
            backoff_s=retry_after_seconds,
        )

    def stats(self) -> dict[str, Any]:
        now = time.monotonic()
        return {
            provider: {
                "rpm_limit": self._rpm.get(provider, 0),
                "current_window": len(
                    [t for t in self._windows.get(provider, deque()) if now - t <= 60.0]
                ),
                "in_backoff": self._backoff_until.get(provider, 0.0) > now,
            }
            for provider in _DEFAULTS
        }

class _AcquireCtx:
    """Async context manager returned by ProviderRateLimiter.acquire()."""

    def __init__(self, limiter: ProviderRateLimiter, provider: str) -> None:
        self._limiter = limiter
        self._provider = provider

    async def __aenter__(self) -> "_AcquireCtx":
        await self._limiter._acquire(self._provider)
        return self

    async def __aexit__(self, *_: Any) -> None:
        self._limiter._release(self._provider)
