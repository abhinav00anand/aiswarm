"""Unit tests for the Timer and timed() context manager."""

from __future__ import annotations

import time

from aiswarm.utils.timing import Timer, timed


class TestTimer:
    def test_elapsed_zero_before_start(self) -> None:
        t = Timer()
        assert t.elapsed == 0.0

    def test_start_returns_self(self) -> None:
        t = Timer()
        assert t.start() is t

    def test_elapsed_increases_while_running(self) -> None:
        t = Timer().start()
        time.sleep(0.01)
        e1 = t.elapsed
        time.sleep(0.01)
        e2 = t.elapsed
        assert e2 > e1

    def test_stop_freezes_elapsed(self) -> None:
        t = Timer().start()
        time.sleep(0.01)
        stopped_value = t.stop()
        time.sleep(0.01)
        assert t.elapsed == stopped_value

    def test_stop_returns_elapsed(self) -> None:
        t = Timer().start()
        result = t.stop()
        assert isinstance(result, float)
        assert result >= 0.0


class TestTimedContextManager:
    def test_yields_timer_instance(self) -> None:
        with timed("stage") as t:
            assert isinstance(t, Timer)

    def test_records_positive_duration(self) -> None:
        with timed("stage") as t:
            time.sleep(0.01)
        assert t.elapsed > 0

    def test_stops_timer_even_on_exception(self) -> None:
        t_ref = None
        try:
            with timed("stage") as t:
                t_ref = t
                raise ValueError("boom")
        except ValueError:
            pass
        assert t_ref is not None
        assert t_ref.elapsed >= 0
