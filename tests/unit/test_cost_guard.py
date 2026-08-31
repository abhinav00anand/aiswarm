"""Unit tests for CostGuard circuit breaker."""

from __future__ import annotations

import asyncio
import pytest

from aiswarm.core.cost_guard import CostGuard, CostLimitExceeded


@pytest.mark.asyncio
async def test_record_accumulates_session_cost():
    guard = CostGuard(max_daily_usd=100.0, max_session_usd=5.0, max_session_tokens=1_000_000)
    await guard.record(provider="novita", tokens=100, cost_usd=0.001)
    await guard.record(provider="novita", tokens=200, cost_usd=0.002)
    status = guard.check_budget_remaining()
    assert status["session_cost_usd"] == pytest.approx(0.003, rel=1e-4)
    assert status["session_tokens"] == 300


@pytest.mark.asyncio
async def test_session_cost_limit_triggers():
    guard = CostGuard(max_daily_usd=100.0, max_session_usd=0.01)
    with pytest.raises(CostLimitExceeded, match="Session spend limit"):
        for _ in range(20):
            await guard.record(provider="openai", tokens=10, cost_usd=0.001)


@pytest.mark.asyncio
async def test_session_token_limit_triggers():
    guard = CostGuard(max_session_tokens=500)
    with pytest.raises(CostLimitExceeded, match="Session token limit"):
        for _ in range(10):
            await guard.record(provider="novita", tokens=100, cost_usd=0.0001)


@pytest.mark.asyncio
async def test_provider_breakdown_tracked():
    guard = CostGuard(max_daily_usd=100.0, max_session_usd=50.0)
    await guard.record(provider="novita", tokens=100, cost_usd=0.001)
    await guard.record(provider="openai", tokens=50, cost_usd=0.005)
    await guard.record(provider="novita", tokens=200, cost_usd=0.002)
    status = guard.check_budget_remaining()
    assert "novita" in status["provider_breakdown"]
    assert "openai" in status["provider_breakdown"]
    assert status["provider_breakdown"]["novita"] == pytest.approx(0.003, rel=1e-4)
    assert status["provider_breakdown"]["openai"] == pytest.approx(0.005, rel=1e-4)


@pytest.mark.asyncio
async def test_remaining_budget_decreases():
    guard = CostGuard(max_session_usd=1.0)
    await guard.record(provider="novita", tokens=10, cost_usd=0.25)
    status = guard.check_budget_remaining()
    assert status["session_remaining_usd"] == pytest.approx(0.75, rel=1e-4)


@pytest.mark.asyncio
async def test_no_redis_fallback_to_memory():
    guard = CostGuard(max_daily_usd=5.0, max_session_usd=2.0, redis_client=None)
    await guard.record(provider="novita", tokens=100, cost_usd=0.10)
    status = guard.check_budget_remaining()
    assert status["session_cost_usd"] == pytest.approx(0.10, rel=1e-4)


@pytest.mark.asyncio
async def test_concurrent_records_thread_safe():
    guard = CostGuard(max_session_usd=100.0, max_session_tokens=10_000_000)
    tasks = [guard.record(provider="novita", tokens=100, cost_usd=0.001) for _ in range(50)]
    await asyncio.gather(*tasks)
    status = guard.check_budget_remaining()
    assert status["session_tokens"] == 5000
    assert status["session_cost_usd"] == pytest.approx(0.05, rel=1e-3)
