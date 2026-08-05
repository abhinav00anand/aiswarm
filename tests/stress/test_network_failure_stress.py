"""
Network failure simulation stress tests.

Simulates the full range of real-world network and provider outage scenarios:
  - Complete provider outage (all adapters down)
  - Intermittent connectivity (flapping providers)
  - Timeout storms (all providers time out simultaneously)
  - Cascading 429 floods across all providers
  - DNS / connection-refused simulation
  - Partial response / truncated stream errors
  - Sudden budget exhaustion mid-pipeline
  - Provider returning malformed / empty responses
  - Retry engine recovering from transient outages
  - Cost guard protecting budget during outage retry loops
"""

from __future__ import annotations

import asyncio
import random
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from aiswarm.llm.adapter import BaseLLMAdapter, LLMMessage, LLMResponse
from aiswarm.llm.provider_router import ProviderRouter
from aiswarm.core.cost_guard import CostGuard, CostLimitExceeded
from aiswarm.core.rate_limiter import ProviderRateLimiter
from aiswarm.core.retry_engine import RetryEngine, RetryPolicy, RetryExhausted


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _response(tokens=100, cost=0.001):
    return LLMResponse(
        content="ok",
        model="test",
        provider="mock",
        prompt_tokens=tokens // 2,
        completion_tokens=tokens // 2,
        total_tokens=tokens,
        finish_reason="stop",
        latency_ms=10.0,
        cost_usd=cost,
    )


def _router(providers, cost_guard=None, rate_limiter=None):
    guard = cost_guard or CostGuard(max_daily_usd=9999.0, max_session_usd=9999.0)
    lim = rate_limiter or ProviderRateLimiter()
    return ProviderRouter(providers=providers, cost_guard=guard, rate_limiter=lim)


def _messages():
    return [LLMMessage(role="user", content="test")]


# ---------------------------------------------------------------------------
# Complete provider outage
# ---------------------------------------------------------------------------

class TestCompleteProviderOutage:

    @pytest.mark.asyncio
    async def test_all_providers_down_raises_immediately(self):
        providers = {
            p: MagicMock(spec=BaseLLMAdapter, is_available=MagicMock(return_value=False))
            for p in ["novita", "openai", "anthropic", "gemini", "deepseek"]
        }
        router = _router(providers)
        with pytest.raises(RuntimeError, match="All providers exhausted"):
            await router.chat(messages=_messages(), model="gpt-4o")

    @pytest.mark.asyncio
    async def test_sequential_provider_failures_all_tried(self):
        """All providers are tried exactly once before giving up."""
        tried = []
        providers = {}
        for name in ["p1", "p2", "p3", "p4"]:
            a = MagicMock(spec=BaseLLMAdapter)
            a.is_available.return_value = True

            async def chat_fn(*args, _n=name, **kwargs):
                tried.append(_n)
                raise ConnectionError(f"{_n} connection refused")

            a.chat = chat_fn
            providers[name] = a

        router = _router(providers)
        with pytest.raises(RuntimeError):
            await router.chat(
                messages=_messages(),
                model="gpt-4o",
                provider_preference=["p1", "p2", "p3", "p4"],
            )
        assert tried == ["p1", "p2", "p3", "p4"]

    @pytest.mark.asyncio
    async def test_outage_does_not_corrupt_cost_state(self):
        guard = CostGuard(max_daily_usd=9999.0, max_session_usd=9999.0)
        providers = {
            "p1": MagicMock(spec=BaseLLMAdapter, is_available=MagicMock(return_value=False)),
        }
        router = _router(providers, cost_guard=guard)
        with pytest.raises(RuntimeError):
            await router.chat(messages=_messages(), model="gpt-4o", provider_preference=["p1"])
        status = guard.check_budget_remaining()
        # No cost was recorded during failed calls
        assert status["session_cost_usd"] == 0.0


# ---------------------------------------------------------------------------
# Intermittent / flapping provider
# ---------------------------------------------------------------------------

class TestFlappingProvider:

    @pytest.mark.asyncio
    async def test_flapping_provider_retried_by_engine(self):
        """RetryEngine + flapping provider: eventually succeeds."""
        engine = RetryEngine(RetryPolicy(max_attempts=6, base_delay=0.0))
        call_count = [0]

        async def flapping_call():
            call_count[0] += 1
            if call_count[0] < 4:
                raise ConnectionError("transient network error")
            return "success"

        result = await engine.run_with_retry("flap-task", flapping_call)
        assert result == "success"
        assert call_count[0] == 4

    @pytest.mark.asyncio
    async def test_50_concurrent_flapping_calls_all_recover(self):
        engine = RetryEngine(RetryPolicy(max_attempts=5, base_delay=0.0))
        results = []
        call_counts = {}

        async def make_call(tid):
            call_counts[tid] = 0

            async def fn():
                call_counts[tid] += 1
                if call_counts[tid] < 3:
                    raise TimeoutError("provider timeout")
                return f"ok-{tid}"

            return await engine.run_with_retry(tid, fn)

        tasks = [make_call(f"task-{i}") for i in range(50)]
        results = await asyncio.gather(*tasks)
        assert all(r.startswith("ok-") for r in results)

    @pytest.mark.asyncio
    async def test_flapping_router_uses_stable_fallback(self):
        """Primary flaps, secondary stable — router should succeed via fallback."""
        call_count = [0]

        async def flapping_primary(*a, **kw):
            call_count[0] += 1
            raise ConnectionResetError("connection reset by peer")

        primary = MagicMock(spec=BaseLLMAdapter)
        primary.is_available.return_value = True
        primary.chat = flapping_primary

        secondary = MagicMock(spec=BaseLLMAdapter)
        secondary.is_available.return_value = True
        secondary.chat = AsyncMock(return_value=_response(tokens=42))

        router = _router({"primary": primary, "secondary": secondary})
        N = 10
        for _ in range(N):
            result = await router.chat(
                messages=_messages(),
                model="gpt-4o",
                provider_preference=["primary", "secondary"],
            )
            assert result.total_tokens == 42
        assert call_count[0] == N


# ---------------------------------------------------------------------------
# Timeout storm
# ---------------------------------------------------------------------------

class TestTimeoutStorm:

    @pytest.mark.asyncio
    async def test_all_providers_timeout_raises(self):
        providers = {}
        for name in ["p1", "p2", "p3"]:
            a = MagicMock(spec=BaseLLMAdapter)
            a.is_available.return_value = True

            async def timeout_fn(*a, **k):
                raise TimeoutError("request timed out after 30s")

            a.chat = timeout_fn
            providers[name] = a

        router = _router(providers)
        with pytest.raises(RuntimeError, match="All providers exhausted"):
            await router.chat(
                messages=_messages(),
                model="gpt-4o",
                provider_preference=["p1", "p2", "p3"],
            )

    @pytest.mark.asyncio
    async def test_retry_exhaustion_on_persistent_timeout(self):
        engine = RetryEngine(RetryPolicy(max_attempts=3, base_delay=0.0))

        async def always_timeout():
            raise TimeoutError("always times out")

        with pytest.raises(RetryExhausted) as exc_info:
            await engine.run_with_retry("timeout-task", always_timeout)

        assert len(exc_info.value.history) == 3
        assert "always times out" in exc_info.value.history[-1].error

    @pytest.mark.asyncio
    async def test_timeout_does_not_exhaust_budget(self):
        """Timeouts that never complete should NOT charge the cost guard."""
        guard = CostGuard(max_daily_usd=9999.0, max_session_usd=0.01)
        providers = {}
        for name in ["p1", "p2"]:
            a = MagicMock(spec=BaseLLMAdapter)
            a.is_available.return_value = True

            async def timeout(*a, **k):
                raise TimeoutError("timeout")

            a.chat = timeout
            providers[name] = a

        router = _router(providers, cost_guard=guard)
        for _ in range(5):
            with pytest.raises(RuntimeError):
                await router.chat(messages=_messages(), model="gpt-4o", provider_preference=["p1", "p2"])

        status = guard.check_budget_remaining()
        assert status["session_cost_usd"] == 0.0


# ---------------------------------------------------------------------------
# 429 cascade
# ---------------------------------------------------------------------------

class TestCascading429:

    @pytest.mark.asyncio
    async def test_cascading_429_across_all_providers(self):
        """When every provider returns 429, all are rate-limited and request fails."""
        providers = {}
        for name in ["novita", "openai", "anthropic"]:
            a = MagicMock(spec=BaseLLMAdapter)
            a.is_available.return_value = True

            async def rate_limited(*args, **kwargs):
                raise RuntimeError("429 Too Many Requests")

            a.chat = rate_limited
            providers[name] = a

        limiter = ProviderRateLimiter()
        router = _router(providers, rate_limiter=limiter)
        with pytest.raises(RuntimeError):
            await router.chat(
                messages=_messages(),
                model="gpt-4o",
                provider_preference=["novita", "openai", "anthropic"],
            )

        # All three providers should be in backoff
        stats = limiter.stats()
        for p in ["novita", "openai", "anthropic"]:
            assert stats[p]["in_backoff"], f"{p} should be in backoff after 429"

    @pytest.mark.asyncio
    async def test_429_recovery_after_backoff_expires(self):
        limiter = ProviderRateLimiter()
        limiter.notify_rate_limited("novita", retry_after_seconds=0.05)

        # After backoff, requests should proceed
        await asyncio.sleep(0.07)
        assert not limiter.stats()["novita"]["in_backoff"]

        a = MagicMock(spec=BaseLLMAdapter)
        a.is_available.return_value = True
        a.chat = AsyncMock(return_value=_response(tokens=55))
        router = _router({"novita": a}, rate_limiter=limiter)
        result = await router.chat(
            messages=_messages(),
            model="gpt-4o",
            provider_preference=["novita"],
        )
        assert result.total_tokens == 55


# ---------------------------------------------------------------------------
# Budget exhaustion mid-pipeline
# ---------------------------------------------------------------------------

class TestBudgetExhaustionMidPipeline:

    @pytest.mark.asyncio
    async def test_budget_exhaustion_stops_concurrent_requests(self):
        """Exhausting budget mid-run stops all further calls, not just one."""
        guard = CostGuard(max_daily_usd=9999.0, max_session_usd=0.05)

        call_count = [0]

        async def expensive_chat(*a, **k):
            call_count[0] += 1
            return _response(tokens=100, cost=0.01)

        a = MagicMock(spec=BaseLLMAdapter)
        a.is_available.return_value = True
        a.chat = expensive_chat

        router = _router({"p": a}, cost_guard=guard)
        results = await asyncio.gather(*[
            router.chat(messages=_messages(), model="gpt-4o", provider_preference=["p"])
            for _ in range(20)
        ], return_exceptions=True)

        budget_errors = [r for r in results if isinstance(r, CostLimitExceeded)]
        assert len(budget_errors) > 0

    @pytest.mark.asyncio
    async def test_cost_guard_does_not_fallback_on_budget_error(self):
        """When CostLimitExceeded fires, the second provider must NOT be tried."""
        guard = CostGuard(max_daily_usd=9999.0, max_session_usd=0.0001)

        p1_calls = [0]
        p2_calls = [0]

        async def p1_chat(*a, **k):
            p1_calls[0] += 1
            return _response(cost=0.01)  # over budget

        async def p2_chat(*a, **k):
            p2_calls[0] += 1
            return _response()

        p1 = MagicMock(spec=BaseLLMAdapter)
        p1.is_available.return_value = True
        p1.chat = p1_chat

        p2 = MagicMock(spec=BaseLLMAdapter)
        p2.is_available.return_value = True
        p2.chat = p2_chat

        router = _router({"p1": p1, "p2": p2}, cost_guard=guard)
        with pytest.raises(CostLimitExceeded):
            await router.chat(
                messages=_messages(),
                model="gpt-4o",
                provider_preference=["p1", "p2"],
            )
        # p2 must never have been tried
        assert p2_calls[0] == 0


# ---------------------------------------------------------------------------
# Malformed / empty responses
# ---------------------------------------------------------------------------

class TestMalformedResponses:

    @pytest.mark.asyncio
    async def test_provider_returns_wrong_type_falls_back(self):
        """If a provider returns something other than LLMResponse, fall back."""
        bad = MagicMock(spec=BaseLLMAdapter)
        bad.is_available.return_value = True
        bad.chat = AsyncMock(return_value={"wrong": "type"})  # not LLMResponse

        good = MagicMock(spec=BaseLLMAdapter)
        good.is_available.return_value = True
        good.chat = AsyncMock(return_value=_response(tokens=77))

        router = _router({"bad": bad, "good": good})
        # Accessing .total_tokens on a dict will raise AttributeError
        # Router should catch generic exceptions and fall back
        result = await router.chat(
            messages=_messages(),
            model="gpt-4o",
            provider_preference=["bad", "good"],
        )
        assert result.total_tokens == 77

    @pytest.mark.asyncio
    async def test_provider_raises_oom_error_falls_back(self):
        a = MagicMock(spec=BaseLLMAdapter)
        a.is_available.return_value = True
        a.chat = AsyncMock(side_effect=MemoryError("OOM in model server"))

        good = MagicMock(spec=BaseLLMAdapter)
        good.is_available.return_value = True
        good.chat = AsyncMock(return_value=_response())

        router = _router({"bad": a, "good": good})
        result = await router.chat(
            messages=_messages(),
            model="gpt-4o",
            provider_preference=["bad", "good"],
        )
        assert result is not None
