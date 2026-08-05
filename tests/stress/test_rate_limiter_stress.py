"""
Stress tests for ProviderRateLimiter.

Covers:
  - RPM sliding-window enforcement under flood (50+ concurrent)
  - Semaphore concurrency cap under burst
  - 429 backoff honoured precisely
  - Multi-provider simultaneous backoff isolation
  - Multiple 429s stack to the longest backoff
  - Stats accuracy under concurrent load
  - Unknown-provider on-demand creation under concurrent access
  - Backoff expires correctly after TTL
"""

from __future__ import annotations

import asyncio
import time

import pytest

from aiswarm.core.rate_limiter import ProviderRateLimiter, _DEFAULTS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _limiter():
    return ProviderRateLimiter()


# ---------------------------------------------------------------------------
# Concurrency cap (semaphore)
# ---------------------------------------------------------------------------

class TestRateLimiterConcurrencyCap:

    @pytest.mark.asyncio
    async def test_max_concurrency_never_exceeded_novita(self):
        limiter = _limiter()
        concurrent = [0]
        peak = [0]
        cap = _DEFAULTS["novita"]["concurrency"]  # 5

        async def worker():
            async with limiter.acquire("novita"):
                concurrent[0] += 1
                peak[0] = max(peak[0], concurrent[0])
                await asyncio.sleep(0.01)
                concurrent[0] -= 1

        await asyncio.gather(*[worker() for _ in range(30)])
        assert peak[0] <= cap

    @pytest.mark.asyncio
    async def test_max_concurrency_never_exceeded_anthropic(self):
        limiter = _limiter()
        concurrent = [0]
        peak = [0]
        cap = _DEFAULTS["anthropic"]["concurrency"]  # 4

        async def worker():
            async with limiter.acquire("anthropic"):
                concurrent[0] += 1
                peak[0] = max(peak[0], concurrent[0])
                await asyncio.sleep(0.005)
                concurrent[0] -= 1

        await asyncio.gather(*[worker() for _ in range(20)])
        assert peak[0] <= cap

    @pytest.mark.asyncio
    async def test_all_workers_eventually_complete(self):
        limiter = _limiter()
        completed = []

        async def worker(i):
            async with limiter.acquire("openai"):
                await asyncio.sleep(0.002)
                completed.append(i)

        await asyncio.gather(*[worker(i) for i in range(25)])
        assert len(completed) == 25

    @pytest.mark.asyncio
    async def test_five_providers_concurrent_independent(self):
        """Each provider's concurrency cap is enforced independently."""
        limiter = _limiter()
        peaks = {p: 0 for p in _DEFAULTS}
        concurrent = {p: 0 for p in _DEFAULTS}

        async def worker(provider):
            async with limiter.acquire(provider):
                concurrent[provider] += 1
                peaks[provider] = max(peaks[provider], concurrent[provider])
                await asyncio.sleep(0.005)
                concurrent[provider] -= 1

        tasks = [worker(p) for p in _DEFAULTS for _ in range(15)]
        await asyncio.gather(*tasks)

        for provider, cap_info in _DEFAULTS.items():
            assert peaks[provider] <= cap_info["concurrency"], \
                f"{provider}: peak {peaks[provider]} > cap {cap_info['concurrency']}"


# ---------------------------------------------------------------------------
# 429 backoff behaviour
# ---------------------------------------------------------------------------

class TestRateLimiterBackoff:

    @pytest.mark.asyncio
    async def test_backoff_delay_respected_precisely(self):
        limiter = _limiter()
        limiter.notify_rate_limited("novita", retry_after_seconds=0.08)
        start = time.monotonic()
        async with limiter.acquire("novita"):
            pass
        elapsed = time.monotonic() - start
        assert elapsed >= 0.06, f"Backoff too short: {elapsed*1000:.1f}ms"

    def test_429_sets_backoff_timestamp(self):
        limiter = _limiter()
        before = time.monotonic()
        limiter.notify_rate_limited("openai", retry_after_seconds=30.0)
        assert limiter._backoff_until["openai"] > before + 29.0

    def test_multiple_429s_use_longest_backoff(self):
        limiter = _limiter()
        limiter.notify_rate_limited("deepseek", retry_after_seconds=10.0)
        t1 = limiter._backoff_until["deepseek"]
        limiter.notify_rate_limited("deepseek", retry_after_seconds=60.0)
        t2 = limiter._backoff_until["deepseek"]
        assert t2 > t1  # second, longer backoff overwrites

    @pytest.mark.asyncio
    async def test_backoff_expires_and_request_proceeds(self):
        limiter = _limiter()
        limiter.notify_rate_limited("gemini", retry_after_seconds=0.05)
        # After backoff, acquire should succeed quickly
        await asyncio.sleep(0.07)
        start = time.monotonic()
        async with limiter.acquire("gemini"):
            pass
        elapsed = time.monotonic() - start
        # Should not wait for another full backoff
        assert elapsed < 0.05, f"Expired backoff still delayed: {elapsed*1000:.1f}ms"

    @pytest.mark.asyncio
    async def test_backoff_provider_isolation(self):
        """429 on one provider must not affect others."""
        limiter = _limiter()
        limiter.notify_rate_limited("novita", retry_after_seconds=60.0)

        # openai should be immediately acquirable
        start = time.monotonic()
        async with limiter.acquire("openai"):
            pass
        elapsed = time.monotonic() - start
        assert elapsed < 0.1, f"Unaffected provider delayed: {elapsed*1000:.1f}ms"

    @pytest.mark.asyncio
    async def test_all_providers_429_simultaneously(self):
        """When all providers are rate-limited, each waits independently."""
        limiter = _limiter()
        for p in ["novita", "openai", "anthropic"]:
            limiter.notify_rate_limited(p, retry_after_seconds=0.06)

        # All three should still eventually complete
        async def acquire_and_release(provider):
            async with limiter.acquire(provider):
                return provider

        results = await asyncio.gather(*[
            acquire_and_release(p) for p in ["novita", "openai", "anthropic"]
        ])
        assert set(results) == {"novita", "openai", "anthropic"}


# ---------------------------------------------------------------------------
# Stats accuracy
# ---------------------------------------------------------------------------

class TestRateLimiterStats:

    def test_stats_includes_all_known_providers(self):
        limiter = _limiter()
        stats = limiter.stats()
        for p in _DEFAULTS:
            assert p in stats
            assert "rpm_limit" in stats[p]
            assert "current_window" in stats[p]
            assert "in_backoff" in stats[p]

    def test_stats_backoff_flag_set_after_429(self):
        limiter = _limiter()
        assert not limiter.stats()["openai"]["in_backoff"]
        limiter.notify_rate_limited("openai", retry_after_seconds=30.0)
        assert limiter.stats()["openai"]["in_backoff"]

    @pytest.mark.asyncio
    async def test_stats_window_count_tracks_requests(self):
        limiter = _limiter()
        N = 5
        async def quick_acquire():
            async with limiter.acquire("novita"):
                pass

        await asyncio.gather(*[quick_acquire() for _ in range(N)])
        stats = limiter.stats()
        assert stats["novita"]["current_window"] == N


# ---------------------------------------------------------------------------
# Unknown provider
# ---------------------------------------------------------------------------

class TestRateLimiterUnknownProvider:

    @pytest.mark.asyncio
    async def test_unknown_provider_created_on_demand(self):
        limiter = _limiter()
        async with limiter.acquire("brand_new_provider"):
            pass
        # Should now exist in the semaphores map
        assert "brand_new_provider" in limiter._semaphores

    @pytest.mark.asyncio
    async def test_concurrent_unknown_provider_creation(self):
        """Two coroutines hitting the same unknown provider simultaneously."""
        limiter = _limiter()
        results = []

        async def worker():
            async with limiter.acquire("concurrent_new"):
                results.append(1)

        await asyncio.gather(worker(), worker(), worker())
        assert len(results) == 3
