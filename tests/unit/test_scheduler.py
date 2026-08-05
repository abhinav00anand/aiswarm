"""Unit tests for TaskScheduler — priority ordering and backpressure."""

from __future__ import annotations

import asyncio

import pytest

from aiswarm.core.scheduler import TaskScheduler
from aiswarm.schemas.task import Task, TaskPriority


def _task(priority: TaskPriority, title: str = "t") -> Task:
    return Task(title=title, description="d", priority=priority)


class TestTaskScheduler:
    @pytest.mark.asyncio
    async def test_empty_scheduler_reports_empty(self) -> None:
        s = TaskScheduler()
        assert s.is_empty()
        assert s.depth() == 0

    @pytest.mark.asyncio
    async def test_enqueue_increases_depth(self) -> None:
        s = TaskScheduler()
        await s.enqueue(_task(TaskPriority.NORMAL))
        assert s.depth() == 1
        assert not s.is_empty()

    @pytest.mark.asyncio
    async def test_critical_dispatched_before_normal(self) -> None:
        s = TaskScheduler()
        normal = _task(TaskPriority.NORMAL, "normal")
        critical = _task(TaskPriority.CRITICAL, "critical")
        await s.enqueue(normal)
        await s.enqueue(critical)
        first = await s.next()
        assert first.task_id == critical.task_id

    @pytest.mark.asyncio
    async def test_fifo_within_same_priority(self) -> None:
        s = TaskScheduler()
        first = _task(TaskPriority.NORMAL, "first")
        await s.enqueue(first)
        second = _task(TaskPriority.NORMAL, "second")
        await s.enqueue(second)
        got = await s.next()
        assert got.task_id == first.task_id

    @pytest.mark.asyncio
    async def test_next_removes_from_queue(self) -> None:
        s = TaskScheduler()
        await s.enqueue(_task(TaskPriority.LOW))
        await s.next()
        assert s.is_empty()

    @pytest.mark.asyncio
    async def test_queue_full_raises_runtime_error(self) -> None:
        s = TaskScheduler(max_queue=1)
        await s.enqueue(_task(TaskPriority.NORMAL))
        with pytest.raises(RuntimeError):
            await s.enqueue(_task(TaskPriority.NORMAL))

    @pytest.mark.asyncio
    async def test_next_blocks_until_item_available(self) -> None:
        s = TaskScheduler()

        async def producer() -> None:
            await asyncio.sleep(0.02)
            await s.enqueue(_task(TaskPriority.HIGH))

        asyncio.create_task(producer())
        task = await asyncio.wait_for(s.next(), timeout=1.0)
        assert task.priority == TaskPriority.HIGH

    @pytest.mark.asyncio
    async def test_all_priority_levels_ordered_correctly(self) -> None:
        s = TaskScheduler()
        low = _task(TaskPriority.LOW, "low")
        high = _task(TaskPriority.HIGH, "high")
        critical = _task(TaskPriority.CRITICAL, "critical")
        normal = _task(TaskPriority.NORMAL, "normal")
        for t in (low, high, critical, normal):
            await s.enqueue(t)
        order = [(await s.next()).title for _ in range(4)]
        assert order == ["critical", "high", "normal", "low"]
