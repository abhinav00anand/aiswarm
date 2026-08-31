"""Unit tests for the state machine."""

from __future__ import annotations

import pytest

from aiswarm.core.state_machine import StateMachine, TaskStateError
from aiswarm.schemas.task import Task, TaskState


def _make_task(**kwargs) -> Task:
    return Task(title="Test task", description="Test", **kwargs)


class TestStateMachine:
    def test_valid_forward_transition(self) -> None:
        task = _make_task()
        assert task.state == TaskState.NEW
        StateMachine.transition(task, TaskState.PROMPTED, "starting", agent="test")
        assert task.state == TaskState.PROMPTED

    def test_invalid_transition_raises(self) -> None:
        task = _make_task()
        with pytest.raises(TaskStateError):
            StateMachine.transition(task, TaskState.MERGED, "skip all", agent="test")

    def test_full_happy_path(self) -> None:
        task = _make_task()
        path = [
            TaskState.PROMPTED,
            TaskState.GENERATED,
            TaskState.PRECHECKED,
            TaskState.REVIEWED,
            TaskState.COMPILED,
            TaskState.TESTED,
            TaskState.BENCHMARKED,
            TaskState.MERGED,
        ]
        for state in path:
            StateMachine.transition(task, state, f"→{state.value}", agent="test")
        assert task.state == TaskState.MERGED
        assert task.merged is False  # merge_controller sets this, not state machine

    def test_rejection_transition(self) -> None:
        task = _make_task(state=TaskState.REVIEWED)
        StateMachine.transition(task, TaskState.REJECTED, "critic veto", agent="security")
        assert task.state == TaskState.REJECTED

    def test_deadlock_transition(self) -> None:
        task = _make_task(state=TaskState.GENERATED)
        StateMachine.transition(task, TaskState.DEADLOCK, "max retries", agent="orchestrator")
        assert task.state == TaskState.DEADLOCK

    def test_is_terminal(self) -> None:
        assert StateMachine.is_terminal(TaskState.MERGED)
        assert StateMachine.is_terminal(TaskState.REJECTED)
        assert StateMachine.is_terminal(TaskState.CANCELLED)
        assert not StateMachine.is_terminal(TaskState.NEW)
        assert not StateMachine.is_terminal(TaskState.REVIEWED)

    def test_state_history_recorded(self) -> None:
        task = _make_task()
        StateMachine.transition(task, TaskState.PROMPTED, "test", agent="pytest")
        assert len(task.state_history) == 1
        assert task.state_history[0].from_state == TaskState.NEW
        assert task.state_history[0].to_state == TaskState.PROMPTED
        assert task.state_history[0].agent == "pytest"

    def test_cancel_from_any_active_state(self) -> None:
        for state in (TaskState.NEW, TaskState.PROMPTED, TaskState.GENERATED):
            task = _make_task(state=state)
            StateMachine.transition(task, TaskState.CANCELLED, "operator cancel", agent="test")
            assert task.state == TaskState.CANCELLED
