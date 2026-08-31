"""Timing utilities — precise duration measurement for pipeline stages."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Generator


class Timer:
    """Simple wall-clock timer."""

    def __init__(self) -> None:
        self._start: float | None = None
        self._end: float | None = None

    def start(self) -> "Timer":
        self._start = time.monotonic()
        return self

    def stop(self) -> float:
        self._end = time.monotonic()
        return self.elapsed

    @property
    def elapsed(self) -> float:
        if self._start is None:
            return 0.0
        end = self._end or time.monotonic()
        return end - self._start


@contextmanager
def timed(label: str = "") -> Generator[Timer, None, None]:
    """Context manager that measures elapsed time."""
    t = Timer().start()
    try:
        yield t
    finally:
        t.stop()
