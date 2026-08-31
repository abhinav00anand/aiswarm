"""Task scheduler."""

from __future__ import annotations

import asyncio
import heapq
import time
from dataclasses import dataclass, field

import structlog

from aiswarm.schemas.task import Task, TaskPriority

logger = structlog.get_logger(__name__)

_PRIORITY_WEIGHT = {
    TaskPriority.CRITICAL: 0,
    TaskPriority.HIGH: 1,
    TaskPriority.NORMAL: 2,
    TaskPriority.LOW: 3,
}


@dataclass(order=True)
class _QueueEntry:
    weight: int
    enqueued_at: float
    task: Task = field(compare=False)


class TaskScheduler:
    """
    Priority-aware async task scheduler.

    Producers call enqueue(); consumers await next().
    The scheduler emits backpressure warnings when the queue depth is high.
    """

    def __init__(self, max_queue: int = 1000) -> None:
        self._heap: list[_QueueEntry] = []
        self._max_queue = max_queue
        self._lock = asyncio.Lock()
        self._not_empty = asyncio.Event()

    async def enqueue(self, task: Task) -> None:
        async with self._lock:
            if len(self._heap) >= self._max_queue:
                logger.warning(
                    "scheduler.queue_full",
                    queue_depth=len(self._heap),
                    task_id=task.task_id,
                )
                raise RuntimeError(f"Scheduler queue full ({self._max_queue})")
            weight = _PRIORITY_WEIGHT.get(task.priority, 2)
            entry = _QueueEntry(weight=weight, enqueued_at=time.monotonic(), task=task)
            heapq.heappush(self._heap, entry)
            self._not_empty.set()
            logger.debug(
                "scheduler.enqueued",
                task_id=task.task_id,
                priority=task.priority.value,
                queue_depth=len(self._heap),
            )

    async def next(self) -> Task:
        """Block until a task is available and return the highest-priority task."""
        while True:
            await self._not_empty.wait()
            async with self._lock:
                if self._heap:
                    entry = heapq.heappop(self._heap)
                    if not self._heap:
                        self._not_empty.clear()
                    return entry.task
                self._not_empty.clear()

    def depth(self) -> int:
        return len(self._heap)

    def is_empty(self) -> bool:
        return len(self._heap) == 0
