"""
Cost Guard — circuit breaker for LLM API spend.

Enforces:
  - Per-session token/cost limits
  - Daily spend cap with persistent accounting (Redis-backed when available)
  - Alert thresholds (e.g. 80% of daily cap triggers a warning)
  - Per-provider spend tracking
  - Hard stop when limits are breached — raises CostLimitExceeded

This is a mandatory production safety mechanism. Without it, a prompt
templating bug or infinite retry loop could exhaust API budgets silently.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class CostLimitExceeded(Exception):
    """Raised when a cost or token limit is breached."""


class CostGuard:
    """
    Thread-safe cost circuit breaker.

    All monetary values are in USD.
    All token values are raw token counts.

    Usage::

        guard = CostGuard()
        guard.record(provider="novita", tokens=1500, cost_usd=0.0014)
        # raises CostLimitExceeded if any limit is breached
    """

    def __init__(
        self,
        max_daily_usd: float | None = None,
        max_session_usd: float | None = None,
        max_session_tokens: int | None = None,
        alert_threshold_pct: float = 0.80,
        redis_client: Any | None = None,
        governor: Any | None = None,
    ) -> None:
        self._max_daily = max_daily_usd or float(
            os.getenv("MAX_DAILY_SPEND_USD", "100.0")
        )
        self._max_session = max_session_usd or float(
            os.getenv("MAX_SESSION_SPEND_USD", "10.0")
        )
        self._max_tokens = max_session_tokens or int(
            os.getenv("MAX_SESSION_TOKENS", "10000000")
        )
        self._alert_pct = alert_threshold_pct
        self._redis = redis_client
        self._governor = governor


        # In-process accumulators (source of truth when Redis unavailable)
        self._session_cost: float = 0.0
        self._session_tokens: int = 0
        self._provider_cost: dict[str, float] = {}
        self._provider_tokens: dict[str, int] = {}
        self._session_start = datetime.now(timezone.utc)
        self._alerted_daily = False
        self._alerted_session = False
        self._lock = asyncio.Lock()

    # ── Public API ─────────────────────────────────────────────────────────

    async def record(
        self,
        provider: str,
        tokens: int,
        cost_usd: float,
        task_id: str = "",
    ) -> None:
        """
        Record an LLM call. Raises CostLimitExceeded if any hard limit is hit.
        This must be awaited after every successful LLM response.
        """
        async with self._lock:
            self._session_cost += cost_usd
            self._session_tokens += tokens
            self._provider_cost[provider] = (
                self._provider_cost.get(provider, 0.0) + cost_usd
            )
            self._provider_tokens[provider] = (
                self._provider_tokens.get(provider, 0) + tokens
            )
            if self._governor:
                try:
                    self._governor.record_spend(cost_usd)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("cost_guard.governor_notify_error", error=str(exc))

            # Persist to Redis for cross-process daily accounting

            daily_total = await self._get_daily_total(cost_usd)

            logger.debug(
                "cost_guard.recorded",
                provider=provider,
                tokens=tokens,
                cost_usd=round(cost_usd, 6),
                session_total=round(self._session_cost, 4),
                daily_total=round(daily_total, 4),
                task_id=task_id,
            )

            # ── Alert thresholds ──────────────────────────────────────────
            if not self._alerted_daily and daily_total >= self._max_daily * self._alert_pct:
                self._alerted_daily = True
                logger.warning(
                    "cost_guard.daily_alert",
                    daily_total=round(daily_total, 4),
                    limit=self._max_daily,
                    pct=self._alert_pct * 100,
                )

            if (
                not self._alerted_session
                and self._session_cost >= self._max_session * self._alert_pct
            ):
                self._alerted_session = True
                logger.warning(
                    "cost_guard.session_alert",
                    session_cost=round(self._session_cost, 4),
                    limit=self._max_session,
                    pct=self._alert_pct * 100,
                )

            # ── Hard limits ───────────────────────────────────────────────
            if daily_total > self._max_daily:
                raise CostLimitExceeded(
                    f"Daily spend limit exceeded: ${daily_total:.4f} > ${self._max_daily:.2f}. "
                    "AISwarm halted to protect budget."
                )
            if self._session_cost > self._max_session:
                raise CostLimitExceeded(
                    f"Session spend limit exceeded: ${self._session_cost:.4f} > "
                    f"${self._max_session:.2f}."
                )
            if self._session_tokens > self._max_tokens:
                raise CostLimitExceeded(
                    f"Session token limit exceeded: {self._session_tokens:,} > "
                    f"{self._max_tokens:,}."
                )

    def check_budget_remaining(self) -> dict[str, Any]:
        """Return budget status without raising. Safe to call anytime."""
        return {
            "session_cost_usd": round(self._session_cost, 4),
            "session_tokens": self._session_tokens,
            "session_limit_usd": self._max_session,
            "daily_limit_usd": self._max_daily,
            "session_remaining_usd": round(
                max(0.0, self._max_session - self._session_cost), 4
            ),
            "provider_breakdown": {
                k: round(v, 6) for k, v in self._provider_cost.items()
            },
        }

    # ── Redis daily accounting ─────────────────────────────────────────────

    async def _get_daily_total(self, increment: float) -> float:
        """
        Add increment to today's running total.
        Returns the new total. Falls back to in-process memory when Redis absent.
        """
        if self._redis is None:
            # No Redis — use session cost as proxy (conservative)
            return self._session_cost

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"aiswarm:cost:daily:{today}"
        try:
            new_val = await self._redis.incrbyfloat(key, increment)
            # Expire key at midnight + 1h buffer
            await self._redis.expire(key, 90000)
            return float(new_val)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cost_guard.redis_error", error=str(exc))
            return self._session_cost
