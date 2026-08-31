"""Unit tests for ProviderRateLimiter."""

from __future__ import annotations

import asyncio
import time
import pytest

from aiswarm.core.rate_limiter import ProviderRateLimiter


@pytest.mark.asyncio
async def test_acquire_and_release_succeed():
    limiter = ProviderRateLimiter()
    async with limiter.acquire("novita"):
        pass  # should not raise


@pytest.mark.asyncio
async def test_unknown_provider_creates_on_demand():
    limiter = ProviderRateLimiter()
    async with limiter.acquire("mystery_provider"):
        pass  # should not raise


@pytest.mark.asyncio
async def test_concurrent_under_limit_succeed():
    limiter = ProviderRateLimiter()
    results = []

    async def _call():
        async with limiter.acquire("novita"):
            results.append(1)

    await asyncio.gather(*[_call() for _ in range(3)])
    assert len(results) == 3


@pytest.mark.asyncio
async def test_backoff_wait_respected():
    limiter = ProviderRateLimiter()
    limiter.notify_rate_limited("novita", retry_after_seconds=0.05)
    start = time.monotonic()
    async with limiter.acquire("novita"):
        pass
    elapsed = time.monotonic() - start
    # Should have waited at least ~50ms backoff
    assert elapsed >= 0.04, f"Expected >= 40ms backoff, got {elapsed * 1000:.1f}ms"


def test_notify_rate_limited_sets_backoff():
    limiter = ProviderRateLimiter()
    limiter.notify_rate_limited("openai", retry_after_seconds=30.0)
    import time as _t

    assert limiter._backoff_until.get("openai", 0) > _t.monotonic()


def test_stats_returns_all_providers():
    limiter = ProviderRateLimiter()
    stats = limiter.stats()
    assert "novita" in stats
    assert "openai" in stats
    assert "anthropic" in stats
    assert isinstance(stats["novita"]["rpm_limit"], int)
    assert isinstance(stats["novita"]["in_backoff"], bool)
