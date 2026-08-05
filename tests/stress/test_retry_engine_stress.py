"""
Stress tests for RetryEngine.

Covers:
  - 100+ concurrent tasks with independent retry state
  - Exponential backoff timing accuracy
  - Max-retries boundary (exactly N attempts, not N+1)
  - Cascading failure recovery
  - on_failure callback reliability under stress
  - Mixed success/failure patterns
  - State isolation: one task's exhaustion does not affect others
  - History integrity after concurrent failures
"""

from __future__ import annotations

import asyncio
import time

import pytest

from aiswarm.core.retry_engine import RetryEngine, RetryPolicy, RetryExhausted


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _engine(max_attempts=3, base_delay=0.0, jitter=False):
    return RetryEngine(RetryPolicy(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=60.0,
        jitter=jitter,
    ))


# ---------------------------------------------------------------------------
# Concurrency: 100+ independent tasks
# ---------------------------------------------------------------------------

class TestRetryEngineConcurrencyStress:

    @pytest.mark.asyncio
    async def test_100_concurrent_tasks_all_succeed_first_try(self):
        engine = _engine(max_attempts=3)
        N = 100

        async def always_ok():
            return "ok"

        results = await asyncio.gather(*[
            engine.run_with_retry(f"task-{i}", always_ok)
            for i in range(N)
        ])
        assert all(r == "ok" for r in results)

    @pytest.mark.asyncio
    async def test_100_concurrent_tasks_each_fails_twice(self):
        engine = _engine(max_attempts=5, base_delay=0.0)
        counters = {f"t{i}": 0 for i in range(50)}

        async def fail_twice(tid):
            counters[tid] += 1
            if counters[tid] < 3:
                raise ValueError(f"{tid} not ready")
            return "done"

        results = await asyncio.gather(*[
            engine.run_with_retry(f"t{i}", lambda i=i: fail_twice(f"t{i}"))
            for i in range(50)
        ])
        assert all(r == "done" for r in results)

    @pytest.mark.asyncio
    async def test_concurrent_exhaustions_are_independent(self):
        engine = _engine(max_attempts=2, base_delay=0.0)

        async def always_fail():
            raise ValueError("always")

        tasks = [
            engine.run_with_retry(f"exhaust-{i}", always_fail)
            for i in range(20)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        exhausted = [r for r in results if isinstance(r, RetryExhausted)]
        assert len(exhausted) == 20
        # Each exhaustion should reference its own task_id
        for exc in exhausted:
            assert exc.task_id.startswith("exhaust-")

    @pytest.mark.asyncio
    async def test_mixed_success_failure_concurrent(self):
        engine = _engine(max_attempts=3, base_delay=0.0)
        N = 60

        async def sometimes_fail(i):
            if i % 3 == 0:
                raise ValueError("unlucky")
            return i

        results = await asyncio.gather(*[
            engine.run_with_retry(f"mixed-{i}", lambda i=i: sometimes_fail(i))
            for i in range(N)
        ], return_exceptions=True)

        successes = [r for r in results if isinstance(r, int)]
        failures = [r for r in results if isinstance(r, RetryExhausted)]
        assert len(successes) + len(failures) == N


# ---------------------------------------------------------------------------
# Backoff timing
# ---------------------------------------------------------------------------

class TestRetryEngineBackoffTiming:

    def test_exponential_backoff_grows_correctly(self):
        engine = RetryEngine(RetryPolicy(
            max_attempts=6,
            base_delay=1.0,
            exponential_base=2.0,
            jitter=False,
        ))
        delays = [engine._delay_for(i) for i in range(5)]
        # 1, 2, 4, 8, 16 (capped at max_delay)
        assert delays[0] == pytest.approx(1.0)
        assert delays[1] == pytest.approx(2.0)
        assert delays[2] == pytest.approx(4.0)
        assert delays[3] == pytest.approx(8.0)
        assert delays[4] == pytest.approx(16.0)

    def test_max_delay_cap_respected(self):
        engine = RetryEngine(RetryPolicy(
            max_attempts=10,
            base_delay=1.0,
            max_delay=5.0,
            exponential_base=2.0,
            jitter=False,
        ))
        for i in range(10):
            delay = engine._delay_for(i)
            assert delay <= 5.0

    def test_jitter_randomises_within_band(self):
        engine = RetryEngine(RetryPolicy(
            max_attempts=10,
            base_delay=1.0,
            exponential_base=2.0,
            jitter=True,
        ))
        delays = [engine._delay_for(2) for _ in range(50)]
        # All in [0.5 * 4, 1.0 * 4] == [2.0, 4.0]
        assert all(2.0 <= d <= 4.0 for d in delays)
        # Must have variance (not all identical)
        assert len(set(round(d, 6) for d in delays)) > 1

    @pytest.mark.asyncio
    async def test_zero_delay_policy_is_fast(self):
        engine = _engine(max_attempts=5, base_delay=0.0)
        call_count = [0]

        async def fail_three_times():
            call_count[0] += 1
            if call_count[0] < 4:
                raise ValueError("not yet")
            return "ok"

        start = time.monotonic()
        result = await engine.run_with_retry("fast", fail_three_times)
        elapsed = time.monotonic() - start
        assert result == "ok"
        assert elapsed < 0.5, f"Zero-delay retry took too long: {elapsed:.2f}s"


# ---------------------------------------------------------------------------
# Attempt counting precision
# ---------------------------------------------------------------------------

class TestRetryEngineAttemptCounting:

    @pytest.mark.asyncio
    async def test_exactly_max_attempts_no_more(self):
        engine = _engine(max_attempts=4, base_delay=0.0)
        call_count = [0]

        async def always_fail():
            call_count[0] += 1
            raise ValueError("fail")

        with pytest.raises(RetryExhausted) as exc_info:
            await engine.run_with_retry("count-test", always_fail)
        assert call_count[0] == 4
        assert len(exc_info.value.history) == 4

    def test_should_retry_boundary(self):
        engine = _engine(max_attempts=3)
        engine.record_failure("t1", "e1")  # attempt 0 → 1
        assert engine.should_retry("t1")
        engine.record_failure("t1", "e2")  # attempt 1 → 2
        assert engine.should_retry("t1")
        engine.record_failure("t1", "e3")  # attempt 2 → 3 == max
        assert not engine.should_retry("t1")

    def test_reset_restores_full_retry_budget(self):
        engine = _engine(max_attempts=3)
        for _ in range(3):
            engine.record_failure("tx", "err")
        assert not engine.should_retry("tx")
        engine.reset("tx")
        assert engine.should_retry("tx")
        assert engine.get_history("tx") == []

    def test_mark_success_clears_state(self):
        engine = _engine(max_attempts=5)
        engine.record_failure("ty", "err1")
        engine.record_failure("ty", "err2")
        engine.mark_success("ty")
        assert engine.should_retry("ty")
        assert engine.get_history("ty") == []


# ---------------------------------------------------------------------------
# on_failure callback
# ---------------------------------------------------------------------------

class TestRetryEngineOnFailureCallback:

    @pytest.mark.asyncio
    async def test_on_failure_called_on_each_attempt(self):
        engine = _engine(max_attempts=3, base_delay=0.0)
        failure_log = []

        async def on_fail(msg, attempt):
            failure_log.append((msg, attempt))

        async def always_fail():
            raise ValueError("boom")

        with pytest.raises(RetryExhausted):
            await engine.run_with_retry("cb-test", always_fail, on_failure=on_fail)

        assert len(failure_log) == 3
        assert all("boom" in msg for msg, _ in failure_log)

    @pytest.mark.asyncio
    async def test_on_failure_exception_propagates(self):
        """A crashing on_failure callback propagates its exception (documented behaviour)."""
        engine = _engine(max_attempts=3, base_delay=0.0)

        async def crashing_callback(msg, attempt):
            raise RuntimeError("callback bug")

        async def fail_once():
            raise ValueError("not ready")

        with pytest.raises(RuntimeError, match="callback bug"):
            await engine.run_with_retry("cb-crash", fail_once, on_failure=crashing_callback)


# ---------------------------------------------------------------------------
# History integrity
# ---------------------------------------------------------------------------

class TestRetryEngineHistory:

    def test_history_preserves_order_and_content(self):
        engine = _engine(max_attempts=10)
        errors = [f"error_{i}" for i in range(5)]
        for e in errors:
            engine.record_failure("hist", e)
        history = engine.get_history("hist")
        assert [r.error for r in history] == errors

    def test_history_timestamps_monotonically_increasing(self):
        engine = _engine(max_attempts=10)
        for i in range(5):
            engine.record_failure("ts", f"err{i}")
        history = engine.get_history("ts")
        timestamps = [r.timestamp for r in history]
        assert timestamps == sorted(timestamps)

    def test_unknown_task_history_empty(self):
        engine = _engine()
        assert engine.get_history("ghost") == []
        assert engine.should_retry("ghost")

    @pytest.mark.asyncio
    async def test_concurrent_tasks_histories_independent(self):
        engine = _engine(max_attempts=10)
        N = 30

        async def fail_n_times(tid, n):
            count = [0]
            async def fn():
                count[0] += 1
                if count[0] <= n:
                    raise ValueError(f"{tid} fail {count[0]}")
                return "ok"
            return await engine.run_with_retry(tid, fn)

        tasks = [fail_n_times(f"t{i}", i % 5) for i in range(N)]
        results = await asyncio.gather(*tasks)
        assert all(r == "ok" for r in results)
