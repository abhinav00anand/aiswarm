"""
Unit tests for terminal state event mapping in Orchestrator.
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiswarm.schemas.task import Task, TaskState
from aiswarm.schemas.events import EventType
from aiswarm.core.orchestrator import Orchestrator


@pytest.mark.asyncio
async def test_orchestrator_publishes_distinct_terminal_events():
    orc = Orchestrator()
    orc._bus = MagicMock()
    orc._bus.publish = AsyncMock()

    with patch("aiswarm.core.workflow_engine.WorkflowEngine.run", new_callable=AsyncMock) as mock_run:
        # Task merged -> TASK_COMPLETED
        task_merged = Task(title="Merged Task", description="Merged description")
        async def set_merged(t):
            t.state = TaskState.MERGED
            return t
        mock_run.side_effect = set_merged

        await orc._execute(task_merged)
        event_published = orc._bus.publish.call_args[0][0]
        assert event_published.event_type == EventType.TASK_COMPLETED

        # Task rejected -> TASK_REJECTED
        task_rejected = Task(title="Rejected Task", description="Rejected description")
        async def set_rejected(t):
            t.state = TaskState.REJECTED
            return t
        mock_run.side_effect = set_rejected

        await orc._execute(task_rejected)
        event_published = orc._bus.publish.call_args[0][0]
        assert event_published.event_type == EventType.TASK_REJECTED

        # Task deadlock -> TASK_DEADLOCK
        task_deadlock = Task(title="Deadlocked Task", description="Deadlocked description")
        async def set_deadlock(t):
            t.state = TaskState.DEADLOCK
            return t
        mock_run.side_effect = set_deadlock

        await orc._execute(task_deadlock)
        event_published = orc._bus.publish.call_args[0][0]
        assert event_published.event_type == EventType.TASK_DEADLOCK

        # Task cancelled -> TASK_CANCELLED
        task_cancelled = Task(title="Cancelled Task", description="Cancelled description")
        async def set_cancelled(t):
            t.state = TaskState.CANCELLED
            return t
        mock_run.side_effect = set_cancelled

        await orc._execute(task_cancelled)
        event_published = orc._bus.publish.call_args[0][0]
        assert event_published.event_type == EventType.TASK_CANCELLED
