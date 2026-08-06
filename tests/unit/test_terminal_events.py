"""
Unit tests for terminal state event mapping in Orchestrator.
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from aiswarm.schemas.task import Task, TaskState
from aiswarm.schemas.events import EventType
from aiswarm.core.orchestrator import Orchestrator


@pytest.mark.asyncio
async def test_orchestrator_publishes_distinct_terminal_events():
    orc = Orchestrator()
    orc._bus = MagicMock()
    orc._bus.publish = AsyncMock()

    # Task merged -> TASK_COMPLETED
    task_merged = Task(title="Merged Task")
    task_merged.state = TaskState.MERGED
    await orc._execute(task_merged)
    event_published = orc._bus.publish.call_args[0][0]
    assert event_published.event_type == EventType.TASK_COMPLETED

    # Task rejected -> TASK_REJECTED
    task_rejected = Task(title="Rejected Task")
    task_rejected.state = TaskState.REJECTED
    await orc._execute(task_rejected)
    event_published = orc._bus.publish.call_args[0][0]
    assert event_published.event_type == EventType.TASK_REJECTED

    # Task deadlock -> TASK_DEADLOCK
    task_deadlock = Task(title="Deadlocked Task")
    task_deadlock.state = TaskState.DEADLOCK
    await orc._execute(task_deadlock)
    event_published = orc._bus.publish.call_args[0][0]
    assert event_published.event_type == EventType.TASK_DEADLOCK

    # Task cancelled -> TASK_CANCELLED
    task_cancelled = Task(title="Cancelled Task")
    task_cancelled.state = TaskState.CANCELLED
    await orc._execute(task_cancelled)
    event_published = orc._bus.publish.call_args[0][0]
    assert event_published.event_type == EventType.TASK_CANCELLED
