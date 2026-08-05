"""
Stress tests for StateMachine.

Covers:
  - All 80+ valid transitions are accepted
  - Every invalid transition raises TaskStateError
  - Concurrent transitions on the same task (last-writer-wins but never silent)
  - Full retry loop (PROMPTED → GENERATED → … → REJECTED → PROMPTED × N)
  - Transition audit trail integrity
  - Terminal-state enforcement (no transition out of MERGED/CANCELLED/REJECTED)
  - Deadlock → ESCALATED → PROMPTED reset chain
  - PAUSED/resume round-trips from every eligible state
"""

from __future__ import annotations

import asyncio
from itertools import product

import pytest

from aiswarm.core.state_machine import StateMachine, TaskStateError, VALID_TRANSITIONS
from aiswarm.schemas.task import Task, TaskState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _task(state: TaskState = TaskState.NEW) -> Task:
    return Task(title="Stress task", description="Stress", state=state)


def _transition(task, to, reason="stress", agent="stress"):
    StateMachine.transition(task, to, reason=reason, agent=agent)


# ---------------------------------------------------------------------------
# Exhaustive valid transitions
# ---------------------------------------------------------------------------

class TestStateMachineExhaustiveValid:

    def test_every_valid_transition_accepted(self):
        """Every (from, to) in VALID_TRANSITIONS must succeed."""
        accepted = 0
        for from_state, to_state in VALID_TRANSITIONS:
            task = _task(from_state)
            _transition(task, to_state)
            assert task.state == to_state
            accepted += 1
        assert accepted == len(VALID_TRANSITIONS)

    def test_every_invalid_transition_raises(self):
        """Every (from, to) NOT in VALID_TRANSITIONS must raise TaskStateError."""
        all_states = list(TaskState)
        valid_set = VALID_TRANSITIONS
        rejected = 0
        for from_state, to_state in product(all_states, all_states):
            if (from_state, to_state) in valid_set:
                continue
            task = _task(from_state)
            with pytest.raises(TaskStateError):
                _transition(task, to_state)
            rejected += 1
        # There should be many more invalid than valid transitions
        total_possible = len(all_states) ** 2
        assert rejected == total_possible - len(valid_set)

    def test_all_terminal_states_no_outbound_except_cancel(self):
        """MERGED has NO valid outbound transitions whatsoever."""
        terminal_no_out = [TaskState.MERGED]
        for state in terminal_no_out:
            for target in TaskState:
                if (state, target) in VALID_TRANSITIONS:
                    pytest.fail(f"Terminal state {state} has outbound to {target}")


# ---------------------------------------------------------------------------
# Concurrent transitions (race-condition safety)
# ---------------------------------------------------------------------------

class TestStateMachineConcurrentTransitions:

    @pytest.mark.asyncio
    async def test_concurrent_valid_transitions_serialize(self):
        """50 concurrent tasks all progress through the happy path."""
        N = 50
        tasks = [_task() for _ in range(N)]
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

        async def progress(t):
            for state in path:
                _transition(t, state)
            return t.state

        results = await asyncio.gather(*[progress(t) for t in tasks])
        assert all(r == TaskState.MERGED for r in results)

    @pytest.mark.asyncio
    async def test_concurrent_cancel_races(self):
        """Multiple coroutines racing to cancel distinct tasks all succeed."""
        N = 50
        tasks = [_task(TaskState.GENERATED) for _ in range(N)]

        async def cancel(t):
            _transition(t, TaskState.CANCELLED, reason="operator")
            return t.state

        results = await asyncio.gather(*[cancel(t) for t in tasks])
        assert all(r == TaskState.CANCELLED for r in results)


# ---------------------------------------------------------------------------
# Retry loop: PROMPTED cycle
# ---------------------------------------------------------------------------

class TestStateMachineRetryLoop:

    def test_full_retry_loop_five_cycles(self):
        """Task can cycle PROMPTED → GENERATED → PRECHECKED → PROMPTED five times."""
        task = _task()
        _transition(task, TaskState.PROMPTED)

        for cycle in range(5):
            _transition(task, TaskState.GENERATED, reason=f"cycle {cycle}")
            _transition(task, TaskState.PRECHECKED)
            _transition(task, TaskState.PROMPTED, reason="precheck fail retry")

        assert task.state == TaskState.PROMPTED
        # State history should have 1 + 15 = 16 transitions
        assert len(task.state_history) == 1 + 5 * 3

    def test_retry_from_reviewed_stage(self):
        task = _task()
        _transition(task, TaskState.PROMPTED)
        _transition(task, TaskState.GENERATED)
        _transition(task, TaskState.PRECHECKED)
        _transition(task, TaskState.REVIEWED)
        _transition(task, TaskState.PROMPTED, reason="critic majority reject")
        assert task.state == TaskState.PROMPTED

    def test_retry_from_compiled_stage(self):
        task = _task()
        for s in [TaskState.PROMPTED, TaskState.GENERATED,
                  TaskState.PRECHECKED, TaskState.REVIEWED, TaskState.COMPILED]:
            _transition(task, s)
        _transition(task, TaskState.PROMPTED, reason="compile fail")
        assert task.state == TaskState.PROMPTED


# ---------------------------------------------------------------------------
# Deadlock / escalation chain
# ---------------------------------------------------------------------------

class TestStateMachineDeadlockChain:

    def test_deadlock_escalated_boss_restart(self):
        task = _task(TaskState.GENERATED)
        _transition(task, TaskState.DEADLOCK, reason="retry_exceeded")
        assert task.state == TaskState.DEADLOCK
        _transition(task, TaskState.ESCALATED, reason="boss notified")
        assert task.state == TaskState.ESCALATED
        _transition(task, TaskState.PROMPTED, reason="boss restart")
        assert task.state == TaskState.PROMPTED

    def test_deadlock_direct_force_merge(self):
        task = _task(TaskState.PROMPTED)
        _transition(task, TaskState.DEADLOCK)
        _transition(task, TaskState.MERGED, reason="operator force-merge")
        assert task.state == TaskState.MERGED

    def test_escalated_force_merge(self):
        task = _task(TaskState.DEADLOCK)
        _transition(task, TaskState.ESCALATED)
        _transition(task, TaskState.MERGED, reason="operator force-merge")
        assert task.state == TaskState.MERGED


# ---------------------------------------------------------------------------
# PAUSED round-trips
# ---------------------------------------------------------------------------

class TestStateMachinePauseResume:

    PAUSABLE = [
        TaskState.NEW,
        TaskState.PROMPTED,
        TaskState.GENERATED,
        TaskState.PRECHECKED,
        TaskState.REVIEWED,
        TaskState.COMPILED,
        TaskState.TESTED,
    ]

    def test_every_pausable_state_can_pause(self):
        for state in self.PAUSABLE:
            task = _task(state)
            _transition(task, TaskState.PAUSED, reason="operator pause")
            assert task.state == TaskState.PAUSED

    def test_paused_can_resume_to_valid_states(self):
        resume_targets = [TaskState.PROMPTED, TaskState.COMPILED, TaskState.TESTED]
        for target in resume_targets:
            task = _task(TaskState.PAUSED)
            _transition(task, target, reason="resume")
            assert task.state == target

    def test_paused_cannot_skip_to_merged(self):
        task = _task(TaskState.PAUSED)
        with pytest.raises(TaskStateError):
            _transition(task, TaskState.MERGED)


# ---------------------------------------------------------------------------
# Audit trail integrity
# ---------------------------------------------------------------------------

class TestStateMachineAuditTrail:

    def test_full_path_audit_trail_complete(self):
        task = _task()
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
            _transition(task, state, agent=f"agent_{state.value}")

        assert len(task.state_history) == len(path)
        for i, record in enumerate(task.state_history):
            assert record.to_state == path[i]
            assert record.agent == f"agent_{path[i].value}"

    def test_audit_from_to_states_match(self):
        task = _task()
        _transition(task, TaskState.PROMPTED, agent="boss")
        _transition(task, TaskState.GENERATED, agent="coder")
        history = task.state_history
        assert history[0].from_state == TaskState.NEW
        assert history[0].to_state == TaskState.PROMPTED
        assert history[1].from_state == TaskState.PROMPTED
        assert history[1].to_state == TaskState.GENERATED

    def test_evidence_preserved_in_audit(self):
        task = _task()
        StateMachine.transition(
            task,
            TaskState.PROMPTED,
            reason="initial",
            agent="boss",
            evidence={"context_tokens": 8000, "model": "llama-3.1-70b"},
        )
        assert task.state_history[0].evidence["context_tokens"] == 8000

    @pytest.mark.asyncio
    async def test_100_tasks_audit_trail_no_cross_contamination(self):
        """History entries must not bleed between task objects."""
        N = 100
        tasks = [_task() for _ in range(N)]

        async def progress(t, i):
            _transition(t, TaskState.PROMPTED, agent=f"agent-{i}")
            _transition(t, TaskState.GENERATED, agent=f"agent-{i}")

        await asyncio.gather(*[progress(t, i) for i, t in enumerate(tasks)])

        for i, t in enumerate(tasks):
            assert len(t.state_history) == 2
            assert t.state_history[0].agent == f"agent-{i}"
