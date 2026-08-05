"""Unit tests for the retry engine."""

from __future__ import annotations

import pytest

from aiswarm.core.retry_engine import RetryEngine, RetryPolicy, RetryExhausted


class TestRetryEngine:
    def test_success_on_first_attempt(self) -> None:
        engine = RetryEngine(RetryPolicy(max_attempts=3))

        async def always_succeed() -> str:
            return "ok"

        import asyncio
        result = asyncio.run(engine.run_with_retry("t1", always_succeed))
        assert result == "ok"

    def test_retry_on_failure(self) -> None:
        engine = RetryEngine(RetryPolicy(max_attempts=3, base_delay=0.0))
        call_count = [0]

        async def fail_twice() -> str:
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("not yet")
            return "ok"

        import asyncio
        result = asyncio.run(engine.run_with_retry("t2", fail_twice))
        assert result == "ok"
        assert call_count[0] == 3

    def test_exhausted_raises(self) -> None:
        engine = RetryEngine(RetryPolicy(max_attempts=2, base_delay=0.0))

        async def always_fail() -> str:
            raise ValueError("always fails")

        import asyncio
        with pytest.raises(RetryExhausted) as exc_info:
            asyncio.run(engine.run_with_retry("t3", always_fail))
        assert "t3" in str(exc_info.value)

    def test_should_retry_logic(self) -> None:
        engine = RetryEngine(RetryPolicy(max_attempts=3))
        engine.record_failure("t4", "err1")
        assert engine.should_retry("t4")
        engine.record_failure("t4", "err2")
        assert engine.should_retry("t4")
        engine.record_failure("t4", "err3")
        assert not engine.should_retry("t4")

    def test_reset_clears_state(self) -> None:
        engine = RetryEngine(RetryPolicy(max_attempts=2))
        engine.record_failure("t5", "err")
        engine.record_failure("t5", "err2")
        assert not engine.should_retry("t5")
        engine.reset("t5")
        assert engine.should_retry("t5")

    def test_history_preserved(self) -> None:
        engine = RetryEngine(RetryPolicy(max_attempts=5))
        engine.record_failure("t6", "error one")
        engine.record_failure("t6", "error two")
        history = engine.get_history("t6")
        assert len(history) == 2
        assert history[0].error == "error one"
        assert history[1].error == "error two"
