"""Retry engine with exponential back."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

import structlog

logger = structlog.get_logger(__name__)

@dataclass
class RetryPolicy:
    max_attempts: int = 5
    base_delay: float = 3.0      # seconds (protects rate limits on free-tier APIs)
    max_delay: float = 60.0      # seconds
    exponential_base: float = 2.0
    jitter: bool = True
    retriable_exceptions: tuple[type[Exception], ...] = (Exception,)

@dataclass
class RetryRecord:
    attempt: int
    error: str
    timestamp: float = field(default_factory=time.time)
    delay_before_retry: float = 0.0

class RetryExhausted(Exception):
    """Raised when a task has exhausted all retry attempts."""

    def __init__(self, task_id: str, history: list[RetryRecord]) -> None:
        self.task_id = task_id
        self.history = history
        super().__init__(
            f"Task {task_id} exhausted {len(history)} retry attempts. "
            f"Last error: {history[-1].error if history else 'unknown'}"
        )

class RetryEngine:
    """
    Manages per-task retry state with exponential back-off.

    Usage::

        engine = RetryEngine(policy=RetryPolicy(max_attempts=5))
        for attempt in engine.iterate(task_id):
            try:
                result = await do_work()
                engine.mark_success(task_id)
                break
            except SomeError as exc:
                engine.record_failure(task_id, str(exc))
                await engine.wait(task_id)
    """

    def __init__(self, policy: RetryPolicy | None = None) -> None:
        self._policy = policy or RetryPolicy()
        self._records: dict[str, list[RetryRecord]] = {}
        self._attempt: dict[str, int] = {}

    def _delay_for(self, attempt: int) -> float:
        delay = min(
            self._policy.base_delay * (self._policy.exponential_base ** attempt),
            self._policy.max_delay,
        )
        if self._policy.jitter:
            delay *= 0.5 + random.random() * 0.5
        return delay

    def record_failure(self, task_id: str, error: str) -> RetryRecord:
        attempt = self._attempt.get(task_id, 0)
        delay = self._delay_for(attempt)
        rec = RetryRecord(attempt=attempt, error=error, delay_before_retry=delay)
        self._records.setdefault(task_id, []).append(rec)
        self._attempt[task_id] = attempt + 1
        logger.warning(
            "retry.failure_recorded",
            task_id=task_id,
            attempt=attempt,
            error=error,
            next_delay=delay,
        )
        return rec

    async def wait(self, task_id: str) -> None:
        records = self._records.get(task_id, [])
        if records:
            delay = records[-1].delay_before_retry
            logger.debug("retry.waiting", task_id=task_id, delay=delay)
            await asyncio.sleep(delay)

    def should_retry(self, task_id: str) -> bool:
        attempts = self._attempt.get(task_id, 0)
        return attempts < self._policy.max_attempts

    def mark_success(self, task_id: str) -> None:
        self._attempt.pop(task_id, None)
        self._records.pop(task_id, None)

    def get_history(self, task_id: str) -> list[RetryRecord]:
        return self._records.get(task_id, [])

    def reset(self, task_id: str) -> None:
        """Boss agent can reset a task for a fresh attempt."""
        self._attempt.pop(task_id, None)
        self._records.pop(task_id, None)

    async def run_with_retry(
        self,
        task_id: str,
        fn: Callable[[], Awaitable[Any]],
        on_failure: Callable[[str, int], Awaitable[None]] | None = None,
    ) -> Any:
        """
        Execute an async callable with automatic retry.

        Args:
            task_id: Used for per-task attempt tracking.
            fn: The async function to retry.
            on_failure: Optional async callback(error_msg, attempt) called on each failure.
        """
        while True:
            try:
                result = await fn()
                self.mark_success(task_id)
                return result
            except self._policy.retriable_exceptions as exc:
                error_msg = str(exc)
                rec = self.record_failure(task_id, error_msg)
                if on_failure:
                    await on_failure(error_msg, rec.attempt)
                if not self.should_retry(task_id):
                    raise RetryExhausted(task_id, self.get_history(task_id)) from exc
                await self.wait(task_id)
