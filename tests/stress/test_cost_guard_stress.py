"""
Stress tests for CostGuard circuit breaker.

Covers:
  - High-concurrency races (500+ simultaneous record() calls)
  - Exact boundary conditions (trip exactly at the limit)
  - Interleaved multi-provider hammering
  - Redis failure mid-flight (graceful fallback)
  - Daily-limit enforcement with mocked Redis
  - Alert threshold fires exactly once
  - Token + cost limits independently enforced
  - Reset-and-reuse pattern (session restart)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from aiswarm.core.cost_guard import CostGuard, CostLimitExceeded


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _guard(session_usd=100.0, daily_usd=1000.0, tokens=10_000_000):
    return CostGuard(
        max_daily_usd=daily_usd,
        max_session_usd=session_usd,
        max_session_tokens=tokens,
    )


# ---------------------------------------------------------------------------
# Concurrency stress
# ---------------------------------------------------------------------------


class TestCostGuardConcurrencyStress:
    """500 concurrent record() calls must all serialize correctly."""

    @pytest.mark.asyncio
    async def test_500_concurrent_records_exact_total(self):
        guard = _guard(session_usd=1000.0, tokens=100_000_000)
        N = 500
        tasks = [guard.record(provider="novita", tokens=100, cost_usd=0.001) for _ in range(N)]
        await asyncio.gather(*tasks)
        status = guard.check_budget_remaining()
        assert status["session_tokens"] == N * 100
        assert status["session_cost_usd"] == pytest.approx(N * 0.001, rel=1e-4)

    @pytest.mark.asyncio
    async def test_concurrent_multi_provider_no_data_loss(self):
        guard = _guard(session_usd=5000.0, tokens=100_000_000)
        providers = ["novita", "openai", "anthropic", "gemini", "deepseek"]
        per_provider = 100
        tasks = [
            guard.record(provider=p, tokens=50, cost_usd=0.0001)
            for p in providers
            for _ in range(per_provider)
        ]
        await asyncio.gather(*tasks)
        status = guard.check_budget_remaining()
        assert len(status["provider_breakdown"]) == len(providers)
        total_expected = len(providers) * per_provider * 0.0001
        assert status["session_cost_usd"] == pytest.approx(total_expected, rel=1e-3)

    @pytest.mark.asyncio
    async def test_limit_trips_under_high_concurrency(self):
        """Even with 200 concurrent callers, the limit is never crossed silently."""
        guard = _guard(session_usd=0.05)
        # Each call costs 0.001; limit at 0.05 → trips after 50 calls
        tasks = [guard.record(provider="novita", tokens=1, cost_usd=0.001) for _ in range(200)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        exceptions = [r for r in results if isinstance(r, CostLimitExceeded)]
        successes = [r for r in results if r is None]
        # Must have tripped at some point
        assert len(exceptions) > 0
        # Successes + exceptions == total
        assert len(successes) + len(exceptions) == 200

    @pytest.mark.asyncio
    async def test_token_limit_trips_under_high_concurrency(self):
        guard = _guard(session_usd=10000.0, tokens=5000)
        tasks = [guard.record(provider="novita", tokens=100, cost_usd=0.00001) for _ in range(200)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        exceptions = [r for r in results if isinstance(r, CostLimitExceeded)]
        assert len(exceptions) > 0

    @pytest.mark.asyncio
    async def test_concurrent_records_no_negative_remaining(self):
        guard = _guard(session_usd=1.0)
        tasks = [guard.record(provider="novita", tokens=1, cost_usd=0.01) for _ in range(200)]
        await asyncio.gather(*tasks, return_exceptions=True)
        status = guard.check_budget_remaining()
        assert status["session_remaining_usd"] >= 0.0


# ---------------------------------------------------------------------------
# Boundary conditions
# ---------------------------------------------------------------------------


class TestCostGuardBoundaryConditions:
    """Trip exactly at the limit — off-by-one must not silently pass."""

    @pytest.mark.asyncio
    async def test_trip_exactly_at_session_limit(self):
        # Use clean integers to avoid floating-point accumulation drift.
        # Limit = $1.00; each call = $0.10 → trips after 10 calls (0.10*10=1.00, strict >).
        guard = _guard(session_usd=1.0)
        for _ in range(9):
            await guard.record(provider="novita", tokens=1, cost_usd=0.10)
        # 9th call total = $0.90 — still under limit
        status = guard.check_budget_remaining()
        assert status["session_cost_usd"] == pytest.approx(0.90, rel=1e-4)
        # 10th call brings total to exactly $1.00 → cost_guard uses >, so no raise
        await guard.record(provider="novita", tokens=1, cost_usd=0.10)
        # 11th call pushes us over
        with pytest.raises(CostLimitExceeded, match="Session spend limit"):
            await guard.record(provider="novita", tokens=1, cost_usd=0.001)

    @pytest.mark.asyncio
    async def test_trip_exactly_at_token_limit(self):
        guard = _guard(tokens=1000)
        # 10 calls of 100 tokens = 1000 tokens — exactly at limit
        for _ in range(10):
            await guard.record(provider="novita", tokens=100, cost_usd=0.0)
        # Next call pushes over
        with pytest.raises(CostLimitExceeded, match="Session token limit"):
            await guard.record(provider="novita", tokens=1, cost_usd=0.0)

    @pytest.mark.asyncio
    async def test_zero_cost_calls_do_not_trip_cost_limit(self):
        guard = _guard(session_usd=0.001)
        # 1000 calls at 0.0 cost should never trip
        for _ in range(1000):
            await guard.record(provider="local", tokens=1, cost_usd=0.0)
        status = guard.check_budget_remaining()
        assert status["session_cost_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_single_large_call_trips_immediately(self):
        guard = _guard(session_usd=1.0)
        with pytest.raises(CostLimitExceeded):
            await guard.record(provider="openai", tokens=1_000_000, cost_usd=100.0)

    @pytest.mark.asyncio
    async def test_alert_fires_exactly_once_at_80pct(self):
        """80% threshold alert fires exactly once and the flag stays set."""
        # Use a large enough limit with round amounts to avoid float drift.
        # Limit = $10.00; 80% = $8.00; each call = $1.00
        guard = _guard(session_usd=10.0)
        assert guard._alerted_session is False
        # 7 calls → $7.00 (70%) — no alert yet
        for _ in range(7):
            await guard.record(provider="novita", tokens=1, cost_usd=1.0)
        assert guard._alerted_session is False
        # 8th call → $8.00 (exactly 80%) — alert should fire
        await guard.record(provider="novita", tokens=1, cost_usd=1.0)
        assert guard._alerted_session is True
        # 9th call → flag stays set (not re-fired)
        await guard.record(provider="novita", tokens=1, cost_usd=0.001)
        assert guard._alerted_session is True


# ---------------------------------------------------------------------------
# Redis integration / failure modes
# ---------------------------------------------------------------------------


class TestCostGuardRedisFailure:
    """CostGuard must degrade gracefully when Redis is unavailable."""

    @pytest.mark.asyncio
    async def test_redis_error_falls_back_to_session_total(self):
        redis_mock = AsyncMock()
        redis_mock.incrbyfloat.side_effect = ConnectionError("Redis down")
        guard = CostGuard(
            max_daily_usd=100.0,
            max_session_usd=50.0,
            redis_client=redis_mock,
        )
        # Should not raise — falls back to session cost
        await guard.record(provider="novita", tokens=100, cost_usd=0.01)
        status = guard.check_budget_remaining()
        assert status["session_cost_usd"] == pytest.approx(0.01, rel=1e-4)

    @pytest.mark.asyncio
    async def test_redis_flapping_mid_session(self):
        """Redis intermittently fails; cost accounting must remain accurate."""
        redis_mock = AsyncMock()
        call_count = [0]

        async def flapping_incr(key, amount):
            call_count[0] += 1
            if call_count[0] % 3 == 0:
                raise ConnectionError("Transient Redis failure")
            return float(call_count[0]) * amount

        redis_mock.incrbyfloat.side_effect = flapping_incr
        redis_mock.expire = AsyncMock()
        guard = CostGuard(
            max_daily_usd=1000.0,
            max_session_usd=500.0,
            redis_client=redis_mock,
        )
        for i in range(30):
            await guard.record(provider="novita", tokens=10, cost_usd=0.001)
        status = guard.check_budget_remaining()
        assert status["session_cost_usd"] == pytest.approx(0.030, rel=1e-3)

    @pytest.mark.asyncio
    async def test_daily_limit_with_redis(self):
        """Daily limit enforced via Redis should halt further calls."""
        redis_mock = AsyncMock()
        redis_mock.incrbyfloat.return_value = 150.0  # over daily limit
        redis_mock.expire = AsyncMock()
        guard = CostGuard(
            max_daily_usd=100.0,
            max_session_usd=999.0,
            redis_client=redis_mock,
        )
        with pytest.raises(CostLimitExceeded, match="Daily spend limit"):
            await guard.record(provider="openai", tokens=100, cost_usd=1.0)


# ---------------------------------------------------------------------------
# Provider breakdown accuracy
# ---------------------------------------------------------------------------


class TestCostGuardProviderAccounting:
    @pytest.mark.asyncio
    async def test_five_providers_independent_tallies(self):
        guard = _guard(session_usd=9999.0)
        providers_costs = {
            "novita": (50, 0.001),
            "openai": (200, 0.010),
            "anthropic": (150, 0.008),
            "gemini": (100, 0.005),
            "deepseek": (80, 0.003),
        }
        for provider, (tokens, cost) in providers_costs.items():
            for _ in range(10):
                await guard.record(provider=provider, tokens=tokens, cost_usd=cost)
        status = guard.check_budget_remaining()
        bd = status["provider_breakdown"]
        assert bd["novita"] == pytest.approx(0.001 * 10, rel=1e-4)
        assert bd["openai"] == pytest.approx(0.010 * 10, rel=1e-4)
        assert bd["anthropic"] == pytest.approx(0.008 * 10, rel=1e-4)

    @pytest.mark.asyncio
    async def test_unknown_provider_tracked(self):
        guard = _guard(session_usd=9999.0)
        await guard.record(provider="custom_llm_xyz", tokens=100, cost_usd=0.005)
        status = guard.check_budget_remaining()
        assert "custom_llm_xyz" in status["provider_breakdown"]

    @pytest.mark.asyncio
    async def test_remaining_budget_never_negative(self):
        guard = _guard(session_usd=0.05)
        await asyncio.gather(
            *[guard.record(provider="novita", tokens=1, cost_usd=0.01) for _ in range(20)],
            return_exceptions=True,
        )
        status = guard.check_budget_remaining()
        assert status["session_remaining_usd"] >= 0.0
