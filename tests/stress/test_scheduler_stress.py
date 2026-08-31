"""
Stress tests for TaskScheduler.

Covers:
  - Queue-full backpressure (RuntimeError at exactly max_queue)
  - Priority ordering under flood (CRITICAL always dequeued first)
  - 1000 concurrent enqueues
  - Producer/consumer race with mismatched speeds
  - FIFO within same priority (by enqueue time)
  - Depth tracking accuracy
  - Empty / is_empty semantics
  - Round-trip: enqueue N → dequeue N preserves total order
"""

from __future__ import annotations

import asyncio

import pytest

from aiswarm.core.scheduler import TaskScheduler
from aiswarm.schemas.task import Task, TaskPriority


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _task(priority: TaskPriority = TaskPriority.NORMAL, title: str = "t") -> Task:
    return Task(title=title, description="stress", priority=priority)


# ---------------------------------------------------------------------------
# Queue-full backpressure
# ---------------------------------------------------------------------------


class TestSchedulerQueueFull:
    @pytest.mark.asyncio
    async def test_queue_full_raises_at_exact_limit(self):
        sched = TaskScheduler(max_queue=5)
        for _ in range(5):
            await sched.enqueue(_task())
        with pytest.raises(RuntimeError, match="queue full"):
            await sched.enqueue(_task())

    @pytest.mark.asyncio
    async def test_queue_depth_tracks_accurately(self):
        sched = TaskScheduler(max_queue=100)
        N = 50
        for _ in range(N):
            await sched.enqueue(_task())
        assert sched.depth() == N

    @pytest.mark.asyncio
    async def test_dequeue_reduces_depth(self):
        sched = TaskScheduler(max_queue=10)
        for _ in range(5):
            await sched.enqueue(_task())
        # Dequeue one task directly (no background task, no sleep)
        await sched.next()
        assert sched.depth() == 4

    @pytest.mark.asyncio
    async def test_is_empty_after_draining(self):
        sched = TaskScheduler(max_queue=10)
        N = 3
        for _ in range(N):
            await sched.enqueue(_task())
        # Drain deterministically
        for _ in range(N):
            await sched.next()
        assert sched.is_empty()


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------


class TestSchedulerPriorityOrdering:
    @pytest.mark.asyncio
    async def test_critical_dequeued_before_low(self):
        sched = TaskScheduler(max_queue=100)
        await sched.enqueue(_task(TaskPriority.LOW, "low"))
        await sched.enqueue(_task(TaskPriority.CRITICAL, "critical"))
        await sched.enqueue(_task(TaskPriority.NORMAL, "normal"))
        await sched.enqueue(_task(TaskPriority.HIGH, "high"))

        t1 = await sched.next()
        assert t1.priority == TaskPriority.CRITICAL

    @pytest.mark.asyncio
    async def test_full_priority_order(self):
        sched = TaskScheduler(max_queue=100)
        priorities = [
            TaskPriority.LOW,
            TaskPriority.NORMAL,
            TaskPriority.HIGH,
            TaskPriority.CRITICAL,
        ]
        # Enqueue in worst order
        for p in priorities:
            await sched.enqueue(_task(p, p.value))

        # Dequeue should come out CRITICAL, HIGH, NORMAL, LOW
        expected = [
            TaskPriority.CRITICAL,
            TaskPriority.HIGH,
            TaskPriority.NORMAL,
            TaskPriority.LOW,
        ]
        for exp in expected:
            t = await sched.next()
            assert t.priority == exp, f"Expected {exp}, got {t.priority}"

    @pytest.mark.asyncio
    async def test_100_mixed_priority_tasks_correct_order(self):
        sched = TaskScheduler(max_queue=500)
        import random

        all_priorities = list(TaskPriority)
        tasks_by_priority = {p: 0 for p in all_priorities}
        task_list = [_task(random.choice(all_priorities)) for _ in range(100)]
        for t in task_list:
            await sched.enqueue(t)
            tasks_by_priority[t.priority] += 1

        # Drain all
        prev_weight = -1
        _WEIGHT = {
            TaskPriority.CRITICAL: 0,
            TaskPriority.HIGH: 1,
            TaskPriority.NORMAL: 2,
            TaskPriority.LOW: 3,
        }
        for _ in range(100):
            t = await sched.next()
            w = _WEIGHT[t.priority]
            assert w >= prev_weight, f"Out-of-order dequeue: got weight {w} after {prev_weight}"
            prev_weight = w

    @pytest.mark.asyncio
    async def test_fifo_within_same_priority(self):
        """Tasks of equal priority must dequeue in insertion order."""
        sched = TaskScheduler(max_queue=20)
        N = 10
        for i in range(N):
            await sched.enqueue(_task(TaskPriority.NORMAL, f"task-{i}"))
            await asyncio.sleep(0.001)  # ensure distinct timestamps

        dequeued = []
        for _ in range(N):
            t = await sched.next()
            dequeued.append(t.title)

        expected = [f"task-{i}" for i in range(N)]
        assert dequeued == expected


# ---------------------------------------------------------------------------
# High-concurrency producer/consumer
# ---------------------------------------------------------------------------


class TestSchedulerConcurrency:
    @pytest.mark.asyncio
    async def test_1000_concurrent_enqueues(self):
        sched = TaskScheduler(max_queue=1000)
        N = 1000
        await asyncio.gather(*[sched.enqueue(_task()) for _ in range(N)])
        assert sched.depth() == N

    @pytest.mark.asyncio
    async def test_producer_consumer_race(self):
        """Producers and consumers running simultaneously — no deadlock, no loss."""
        sched = TaskScheduler(max_queue=500)
        N = 200
        consumed = []

        async def producer():
            for _ in range(N):
                await sched.enqueue(_task())
                await asyncio.sleep(0)

        async def consumer():
            for _ in range(N):
                t = await sched.next()
                consumed.append(t.task_id)

        await asyncio.gather(producer(), consumer())
        assert len(consumed) == N
        assert len(set(consumed)) == N  # no duplicates

    @pytest.mark.asyncio
    async def test_multiple_consumers_no_duplicate_dispatch(self):
        """N tasks, N consumers — each task dispatched exactly once, no duplicates, no loss."""
        N = 50
        sched = TaskScheduler(max_queue=N)
        for _ in range(N):
            await sched.enqueue(_task())

        consumed = []
        lock = asyncio.Lock()
        remaining = [N]

        async def consumer():
            while True:
                async with lock:
                    if remaining[0] <= 0:
                        return
                    remaining[0] -= 1
                t = await sched.next()
                async with lock:
                    consumed.append(t.task_id)

        await asyncio.gather(*[consumer() for _ in range(5)])
        # Every task consumed exactly once
        assert len(consumed) == N
        assert len(set(consumed)) == N
