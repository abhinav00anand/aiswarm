"""
Pipeline integration stress tests.

Simulates complete end-to-end pipeline flows without real LLM calls:
  - Full happy-path pipeline for 50 concurrent tasks
  - Retry loop: task fails precheck, retries, succeeds
  - Deadlock detection mid-pipeline
  - Budget exhaustion halts the pipeline
  - Event bus propagation across pipeline stage transitions
  - Scheduler + StateMachine + EventBus wired together under load
  - MergeController as final gate in pipeline
  - Concurrent pipeline instances (no shared state bleed)
  - Cancellation mid-pipeline
  - Mixed priority tasks dispatched in correct order
"""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone, timedelta
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest

from aiswarm.core.cost_guard import CostGuard, CostLimitExceeded
from aiswarm.core.deadlock_detector import DeadlockDetector
from aiswarm.core.event_bus import EventBus
from aiswarm.core.merge_controller import MergeController
from aiswarm.core.retry_engine import RetryEngine, RetryPolicy, RetryExhausted
from aiswarm.core.scheduler import TaskScheduler
from aiswarm.core.state_machine import StateMachine, TaskStateError
from aiswarm.schemas.events import Event, EventType
from aiswarm.schemas.task import (
    Task, TaskState, TaskPriority, CriticReview, ReviewDecision,
    CompilerOutput, TestOutput,
)
from aiswarm.utils.hashing import sha256_hex


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _task(priority: TaskPriority = TaskPriority.NORMAL) -> Task:
    return Task(title="Pipeline task", description="stress", priority=priority)


def _approved_task(tmp_dir: str, idx: int = 0) -> Task:
    code = f"def func_{idx}(): return {idx}\n"
    task = Task(title=f"Task {idx}", description="pipeline stress", priority=TaskPriority.NORMAL)
    task.state = TaskState.BENCHMARKED
    task.generated_code = code
    task.generated_code_hash = sha256_hex(code)
    task.target_files = [f"out_{idx}.py"]
    task.reviews = [
        CriticReview(critic_role="architecture", decision=ReviewDecision.APPROVE,
                     production_ready=True, score=80),
        CriticReview(critic_role="security", decision=ReviewDecision.APPROVE,
                     production_ready=True, score=90),
    ]
    task.compiler_output = CompilerOutput(success=True, exit_code=0)
    task.test_output = TestOutput(success=True, passed=3, total=3, numeric_passed=True)
    return task


# ---------------------------------------------------------------------------
# Full happy-path pipeline
# ---------------------------------------------------------------------------

class TestPipelineHappyPath:

    @pytest.mark.asyncio
    async def test_50_concurrent_tasks_full_pipeline(self):
        PIPELINE = [
            TaskState.PROMPTED,
            TaskState.GENERATED,
            TaskState.PRECHECKED,
            TaskState.REVIEWED,
            TaskState.COMPILED,
            TaskState.TESTED,
            TaskState.BENCHMARKED,
        ]
        N = 50
        tasks = [_task() for _ in range(N)]

        async def run_pipeline(t):
            for state in PIPELINE:
                StateMachine.transition(t, state, reason="pipeline", agent="test")
            return t

        results = await asyncio.gather(*[run_pipeline(t) for t in tasks])
        for t in results:
            assert t.state == TaskState.BENCHMARKED
            assert len(t.state_history) == len(PIPELINE)

    @pytest.mark.asyncio
    async def test_50_concurrent_merges_through_controller(self):
        N = 50
        merged_ids = []

        async def run_and_merge(i):
            with tempfile.TemporaryDirectory() as tmp:
                task = _approved_task(tmp, i)
                mc = MergeController(repo_root=tmp)
                await mc.attempt_merge(task)
                merged_ids.append(task.task_id)
                assert task.state == TaskState.MERGED

        await asyncio.gather(*[run_and_merge(i) for i in range(N)])
        assert len(merged_ids) == N
        assert len(set(merged_ids)) == N  # all distinct

    @pytest.mark.asyncio
    async def test_pipeline_event_bus_fires_on_each_stage(self):
        bus = EventBus()
        transitions_logged = []

        @bus.subscribe(EventType.TASK_STARTED)
        async def on_start(event):
            transitions_logged.append(("start", event.payload.get("task_id")))

        @bus.subscribe(EventType.TASK_COMPLETED)
        async def on_complete(event):
            transitions_logged.append(("complete", event.payload.get("task_id")))

        N = 20
        tasks = [_task() for _ in range(N)]

        async def pipeline_with_events(t):
            await bus.publish(Event(
                event_type=EventType.TASK_STARTED,
                source="orchestrator",
                payload={"task_id": t.task_id},
            ))
            for state in [TaskState.PROMPTED, TaskState.GENERATED,
                          TaskState.PRECHECKED, TaskState.REVIEWED]:
                StateMachine.transition(t, state, "test", "test")
            await bus.publish(Event(
                event_type=EventType.TASK_COMPLETED,
                source="orchestrator",
                payload={"task_id": t.task_id},
            ))

        await asyncio.gather(*[pipeline_with_events(t) for t in tasks])
        starts = [e for e in transitions_logged if e[0] == "start"]
        completes = [e for e in transitions_logged if e[0] == "complete"]
        assert len(starts) == N
        assert len(completes) == N


# ---------------------------------------------------------------------------
# Retry loop within pipeline
# ---------------------------------------------------------------------------

class TestPipelineRetryLoop:

    @pytest.mark.asyncio
    async def test_task_retries_on_precheck_failure(self):
        """Simulate precheck → fail → re-prompt → precheck → pass (2 failures, 3rd succeeds)."""
        task = _task()
        retry_count = [0]

        async def pipeline_with_retry():
            retry_count[0] += 1
            if task.state == TaskState.NEW:
                StateMachine.transition(task, TaskState.PROMPTED, "init", "test")
            StateMachine.transition(task, TaskState.GENERATED, "gen", "coder")
            StateMachine.transition(task, TaskState.PRECHECKED, "check", "precheck")
            if retry_count[0] < 3:
                StateMachine.transition(task, TaskState.PROMPTED, "retry", "precheck")
                raise ValueError("precheck failed, retry")
            # Complete pipeline on 3rd attempt
            StateMachine.transition(task, TaskState.REVIEWED, "reviewed", "critics")
            return "done"

        engine = RetryEngine(RetryPolicy(max_attempts=5, base_delay=0.0))
        result = await engine.run_with_retry("pipeline", pipeline_with_retry)
        assert result == "done"
        assert task.state == TaskState.REVIEWED
        assert retry_count[0] == 3

    @pytest.mark.asyncio
    async def test_deadlock_detection_during_pipeline(self):
        det = DeadlockDetector(deadlock_timeout=300.0)
        task = _task(TaskPriority.HIGH)
        task.state = TaskState.GENERATED
        task.retry_count = task.max_retries  # force deadlock condition
        det.notify_state_change(task)

        deadlocked = await det.scan([task])
        assert task.task_id in deadlocked
        assert task.state == TaskState.DEADLOCK

    @pytest.mark.asyncio
    async def test_concurrent_retry_loops_no_state_bleed(self):
        N = 30
        engines = [RetryEngine(RetryPolicy(max_attempts=4, base_delay=0.0)) for _ in range(N)]
        tasks_list = [_task() for _ in range(N)]
        counters = [0] * N

        async def run(i):
            async def fn():
                counters[i] += 1
                if counters[i] < 2:
                    raise ValueError(f"task {i} not ready")
                return f"ok-{i}"

            return await engines[i].run_with_retry(f"t{i}", fn)

        results = await asyncio.gather(*[run(i) for i in range(N)])
        assert all(r.startswith("ok-") for r in results)


# ---------------------------------------------------------------------------
# Scheduler + StateMachine integration
# ---------------------------------------------------------------------------

class TestSchedulerStateMachineIntegration:

    @pytest.mark.asyncio
    async def test_priority_scheduler_dispatches_critical_first(self):
        sched = TaskScheduler(max_queue=100)
        tasks_to_enqueue = [
            _task(TaskPriority.LOW),
            _task(TaskPriority.NORMAL),
            _task(TaskPriority.HIGH),
            _task(TaskPriority.CRITICAL),
            _task(TaskPriority.LOW),
        ]
        for t in tasks_to_enqueue:
            await sched.enqueue(t)

        first = await sched.next()
        assert first.priority == TaskPriority.CRITICAL

    @pytest.mark.asyncio
    async def test_100_tasks_scheduler_and_pipeline_complete(self):
        sched = TaskScheduler(max_queue=200)
        N = 100
        tasks_list = [_task() for _ in range(N)]
        for t in tasks_list:
            await sched.enqueue(t)

        completed = []
        for _ in range(N):
            t = await sched.next()
            StateMachine.transition(t, TaskState.PROMPTED, "dispatch", "orchestrator")
            StateMachine.transition(t, TaskState.CANCELLED, "cancel", "operator")
            completed.append(t.task_id)

        assert len(completed) == N
        assert sched.is_empty()


# ---------------------------------------------------------------------------
# Cancellation mid-pipeline
# ---------------------------------------------------------------------------

class TestPipelineCancellation:

    @pytest.mark.asyncio
    async def test_cancel_from_every_non_terminal_state(self):
        cancelable = [
            TaskState.NEW,
            TaskState.PROMPTED,
            TaskState.GENERATED,
            TaskState.PRECHECKED,
            TaskState.REVIEWED,
            TaskState.COMPILED,
            TaskState.TESTED,
            TaskState.PAUSED,
        ]
        for state in cancelable:
            task = Task(title="t", description="d", state=state)
            StateMachine.transition(task, TaskState.CANCELLED, "operator cancel", "test")
            assert task.state == TaskState.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_stops_retry_engine(self):
        engine = RetryEngine(RetryPolicy(max_attempts=10, base_delay=0.0))
        cancelled = [False]

        async def cancelable_fn():
            if cancelled[0]:
                raise asyncio.CancelledError()
            raise ValueError("not done")

        async def runner():
            cancelled[0] = True
            await engine.run_with_retry("cancel-test", cancelable_fn)

        with pytest.raises((RetryExhausted, asyncio.CancelledError)):
            await runner()


# ---------------------------------------------------------------------------
# Cost exhaustion in pipeline
# ---------------------------------------------------------------------------

class TestPipelineCostExhaustion:

    @pytest.mark.asyncio
    async def test_budget_exhaustion_halts_concurrent_pipeline_stages(self):
        guard = CostGuard(max_daily_usd=9999.0, max_session_usd=0.05)
        errors = []

        async def simulate_llm_call(i):
            try:
                await guard.record(provider="openai", tokens=200, cost_usd=0.01)
                return f"ok-{i}"
            except CostLimitExceeded as e:
                errors.append(str(e))
                return None

        results = await asyncio.gather(*[simulate_llm_call(i) for i in range(30)])
        assert len(errors) > 0
        ok_results = [r for r in results if r is not None]
        assert len(ok_results) + len(errors) == 30

    @pytest.mark.asyncio
    async def test_budget_exhaustion_leaves_state_consistent(self):
        guard = CostGuard(max_daily_usd=9999.0, max_session_usd=0.05)
        tasks_completed = []

        async def run_task(i):
            try:
                await guard.record(provider="openai", tokens=100, cost_usd=0.01)
                tasks_completed.append(i)
            except CostLimitExceeded:
                pass

        await asyncio.gather(*[run_task(i) for i in range(20)])
        status = guard.check_budget_remaining()
        # remaining must never go negative
        assert status["session_remaining_usd"] >= 0.0
        # cost must have been recorded (some calls succeeded)
        assert status["session_cost_usd"] > 0.0


# ---------------------------------------------------------------------------
# State isolation between pipeline instances
# ---------------------------------------------------------------------------

class TestPipelineStateIsolation:

    @pytest.mark.asyncio
    async def test_100_independent_pipeline_state_machines(self):
        """No task should observe another task's state transitions."""
        N = 100
        tasks = [_task() for _ in range(N)]

        async def full_pipeline(t):
            for s in [TaskState.PROMPTED, TaskState.GENERATED,
                      TaskState.PRECHECKED, TaskState.REVIEWED]:
                StateMachine.transition(t, s, "test", "agent")
            return t.task_id

        await asyncio.gather(*[full_pipeline(t) for t in tasks])
        for t in tasks:
            assert t.state == TaskState.REVIEWED
            assert len(t.state_history) == 4
            # History must only contain this task's transitions
            for record in t.state_history:
                assert record.agent == "agent"

    @pytest.mark.asyncio
    async def test_event_bus_events_not_cross_contaminated(self):
        bus = EventBus()
        task_events: dict = {}

        @bus.subscribe(EventType.TASK_COMPLETED)
        async def handler(event):
            tid = event.payload.get("task_id")
            task_events.setdefault(tid, []).append(event.event_id)

        N = 50
        tasks = [_task() for _ in range(N)]
        await asyncio.gather(*[
            bus.publish(Event(
                event_type=EventType.TASK_COMPLETED,
                source="orchestrator",
                payload={"task_id": t.task_id},
            ))
            for t in tasks
        ])

        # Each task should have received exactly one event
        for t in tasks:
            assert len(task_events.get(t.task_id, [])) == 1
