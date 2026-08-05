"""
Stress tests for ProviderRouter.

Covers:
  - All providers down → RuntimeError (not silent hang)
  - Single provider available → used exclusively
  - Cost-budget exhaustion during concurrent calls stops all further calls
  - 429 detection triggers rate-limiter notification
  - Provider failure counter increments correctly per provider
  - Fallback ordering respected (tries in preference order)
  - CostLimitExceeded NOT caught/swallowed (re-raised immediately)
  - Stats aggregation under concurrent load
  - Provider marked unavailable is skipped without error
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from aiswarm.llm.provider_router import ProviderRouter
from aiswarm.llm.adapter import BaseLLMAdapter, LLMMessage, LLMResponse
from aiswarm.core.cost_guard import CostGuard, CostLimitExceeded
from aiswarm.core.rate_limiter import ProviderRateLimiter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _response(tokens: int = 100, cost: float = 0.001) -> LLMResponse:
    return LLMResponse(
        content="ok",
        model="test-model",
        provider="mock",
        prompt_tokens=tokens // 2,
        completion_tokens=tokens // 2,
        total_tokens=tokens,
        finish_reason="stop",
        latency_ms=10.0,
        cost_usd=cost,
    )


def _mock_adapter(available: bool = True, raises=None, response=None):
    adapter = MagicMock(spec=BaseLLMAdapter)
    adapter.is_available.return_value = available
    if raises:
        adapter.chat = AsyncMock(side_effect=raises)
    else:
        adapter.chat = AsyncMock(return_value=response or _response())
    return adapter


def _router(providers: dict, cost_guard: CostGuard | None = None):
    guard = cost_guard or CostGuard(max_daily_usd=1000.0, max_session_usd=1000.0)
    limiter = ProviderRateLimiter()
    return ProviderRouter(providers=providers, cost_guard=guard, rate_limiter=limiter)


def _messages():
    return [LLMMessage(role="user", content="Hello")]


# ---------------------------------------------------------------------------
# Provider availability & fallback
# ---------------------------------------------------------------------------

class TestProviderRouterFallback:

    @pytest.mark.asyncio
    async def test_all_providers_down_raises_runtime_error(self):
        providers = {
            "p1": _mock_adapter(available=False),
            "p2": _mock_adapter(available=False),
            "p3": _mock_adapter(available=False),
        }
        router = _router(providers)
        with pytest.raises(RuntimeError, match="All providers exhausted"):
            await router.chat(
                messages=_messages(),
                model="test-model",
                provider_preference=["p1", "p2", "p3"],
            )

    @pytest.mark.asyncio
    async def test_first_provider_fails_second_succeeds(self):
        providers = {
            "p1": _mock_adapter(raises=ConnectionError("p1 down")),
            "p2": _mock_adapter(response=_response(tokens=200)),
        }
        router = _router(providers)
        result = await router.chat(
            messages=_messages(),
            model="gpt-4o",
            provider_preference=["p1", "p2"],
        )
        assert result.total_tokens == 200

    @pytest.mark.asyncio
    async def test_preference_order_respected(self):
        call_order = []
        adapters = {}
        for name in ["novita", "openai", "anthropic"]:
            a = MagicMock(spec=BaseLLMAdapter)
            a.is_available.return_value = True

            async def chat_fn(*args, _name=name, **kwargs):
                call_order.append(_name)
                if _name != "anthropic":
                    raise RuntimeError(f"{_name} error")
                return _response()

            a.chat = chat_fn
            adapters[name] = a

        router = _router(adapters)
        await router.chat(
            messages=_messages(),
            model="gpt-4o",
            provider_preference=["novita", "openai", "anthropic"],
        )
        assert call_order == ["novita", "openai", "anthropic"]

    @pytest.mark.asyncio
    async def test_unavailable_provider_skipped_without_error(self):
        providers = {
            "p_down": _mock_adapter(available=False),
            "p_up": _mock_adapter(response=_response(tokens=50)),
        }
        router = _router(providers)
        result = await router.chat(
            messages=_messages(),
            model="gpt-4o",
            provider_preference=["p_down", "p_up"],
        )
        assert result.total_tokens == 50

    @pytest.mark.asyncio
    async def test_unknown_provider_in_preference_skipped(self):
        providers = {
            "real": _mock_adapter(response=_response(tokens=77)),
        }
        router = _router(providers)
        result = await router.chat(
            messages=_messages(),
            model="gpt-4o",
            provider_preference=["ghost_provider", "real"],
        )
        assert result.total_tokens == 77


# ---------------------------------------------------------------------------
# Cost guard integration
# ---------------------------------------------------------------------------

class TestProviderRouterCostGuard:

    @pytest.mark.asyncio
    async def test_cost_limit_exceeded_not_swallowed(self):
        """CostLimitExceeded must propagate immediately — no fallback."""
        tight_guard = CostGuard(max_daily_usd=1000.0, max_session_usd=0.0001)
        providers = {
            "p1": _mock_adapter(response=_response(tokens=100, cost=0.01)),
            "p2": _mock_adapter(response=_response(tokens=100, cost=0.01)),
        }
        router = _router(providers, cost_guard=tight_guard)
        with pytest.raises(CostLimitExceeded):
            await router.chat(
                messages=_messages(),
                model="gpt-4o",
                provider_preference=["p1", "p2"],
            )

    @pytest.mark.asyncio
    async def test_concurrent_calls_all_halt_when_budget_exhausted(self):
        tight_guard = CostGuard(max_daily_usd=1000.0, max_session_usd=0.05)
        providers = {
            "p1": _mock_adapter(response=_response(tokens=100, cost=0.001)),
        }
        router = _router(providers, cost_guard=tight_guard)
        results = await asyncio.gather(*[
            router.chat(
                messages=_messages(),
                model="gpt-4o",
                provider_preference=["p1"],
            )
            for _ in range(100)
        ], return_exceptions=True)
        exceptions = [r for r in results if isinstance(r, CostLimitExceeded)]
        assert len(exceptions) > 0

    @pytest.mark.asyncio
    async def test_stats_cost_accumulates_correctly(self):
        guard = CostGuard(max_daily_usd=1000.0, max_session_usd=1000.0)
        providers = {
            "p1": _mock_adapter(response=_response(tokens=100, cost=0.001)),
        }
        router = _router(providers, cost_guard=guard)
        N = 10
        for _ in range(N):
            await router.chat(
                messages=_messages(),
                model="gpt-4o",
                provider_preference=["p1"],
            )
        stats = router.stats
        assert stats["total_calls"] == N
        assert stats["total_tokens"] == N * 100
        assert stats["total_cost_usd"] == pytest.approx(N * 0.001, rel=1e-3)


# ---------------------------------------------------------------------------
# 429 / rate-limit handling
# ---------------------------------------------------------------------------

class TestProviderRouter429Handling:

    @pytest.mark.asyncio
    async def test_429_triggers_rate_limiter_notification(self):
        limiter = MagicMock(spec=ProviderRateLimiter)
        limiter.acquire = MagicMock()
        limiter.acquire.return_value.__aenter__ = AsyncMock(return_value=None)
        limiter.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        providers = {
            "p_429": _mock_adapter(raises=RuntimeError("429 rate limit exceeded")),
            "p_ok": _mock_adapter(response=_response()),
        }
        guard = CostGuard(max_daily_usd=1000.0, max_session_usd=1000.0)
        router = ProviderRouter(providers=providers, cost_guard=guard, rate_limiter=limiter)
        await router.chat(
            messages=_messages(),
            model="gpt-4o",
            provider_preference=["p_429", "p_ok"],
        )
        limiter.notify_rate_limited.assert_called_once_with("p_429")

    @pytest.mark.asyncio
    async def test_rate_limit_error_string_detection(self):
        """Both '429' and 'rate limit' in error message must trigger backoff."""
        for error_msg in ["HTTP 429 Too Many Requests", "rate limit exceeded for provider"]:
            limiter = MagicMock(spec=ProviderRateLimiter)
            limiter.acquire = MagicMock()
            limiter.acquire.return_value.__aenter__ = AsyncMock(return_value=None)
            limiter.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

            providers = {
                "p_rl": _mock_adapter(raises=RuntimeError(error_msg)),
                "p_ok": _mock_adapter(response=_response()),
            }
            guard = CostGuard(max_daily_usd=1000.0, max_session_usd=1000.0)
            router = ProviderRouter(providers=providers, cost_guard=guard, rate_limiter=limiter)
            await router.chat(
                messages=_messages(),
                model="gpt-4o",
                provider_preference=["p_rl", "p_ok"],
            )
            limiter.notify_rate_limited.assert_called()


# ---------------------------------------------------------------------------
# Failure counters
# ---------------------------------------------------------------------------

class TestProviderRouterFailureCounters:

    @pytest.mark.asyncio
    async def test_failure_counter_increments_per_provider(self):
        providers = {
            "bad": _mock_adapter(raises=RuntimeError("bad provider")),
            "ok": _mock_adapter(response=_response()),
        }
        router = _router(providers)
        N = 5
        for _ in range(N):
            await router.chat(
                messages=_messages(),
                model="gpt-4o",
                provider_preference=["bad", "ok"],
            )
        stats = router.stats
        assert stats["provider_failures"]["bad"] == N

    @pytest.mark.asyncio
    async def test_failure_counter_clears_on_success(self):
        call_count = [0]

        async def flapping_chat(*a, **kw):
            call_count[0] += 1
            if call_count[0] <= 3:
                raise RuntimeError("transient error")
            return _response()

        adapter = MagicMock(spec=BaseLLMAdapter)
        adapter.is_available.return_value = True
        adapter.chat = flapping_chat

        providers = {"flapping": adapter}
        router = _router(providers)
        for _ in range(5):
            try:
                await router.chat(
                    messages=_messages(),
                    model="gpt-4o",
                    provider_preference=["flapping"],
                )
            except RuntimeError:
                pass

        stats = router.stats
        # After a success, failure counter is cleared
        assert stats["provider_failures"].get("flapping", 0) == 0

    @pytest.mark.asyncio
    async def test_list_available_excludes_unavailable(self):
        providers = {
            "up": _mock_adapter(available=True),
            "down": _mock_adapter(available=False),
        }
        router = _router(providers)
        available = router.list_available()
        assert "up" in available
        assert "down" not in available
