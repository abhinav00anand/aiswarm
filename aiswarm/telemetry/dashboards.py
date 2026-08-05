"""Dashboard data aggregator — computes summary metrics for the API/UI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aiswarm.schemas.task import Task, TaskState
from aiswarm.schemas.metrics import SystemMetrics


def compute_system_metrics(tasks: list[Task]) -> SystemMetrics:
    """Compute a SystemMetrics snapshot from the current task list."""
    if not tasks:
        return SystemMetrics()

    terminal = {TaskState.MERGED, TaskState.REJECTED, TaskState.CANCELLED}
    active = [t for t in tasks if t.state not in terminal]
    completed = [t for t in tasks if t.state == TaskState.MERGED]
    rejected = [t for t in tasks if t.state == TaskState.REJECTED]
    deadlocked = [t for t in tasks if t.state == TaskState.DEADLOCK]

    durations = [
        t.duration_seconds()
        for t in completed
        if t.duration_seconds() is not None
    ]

    review_cycles = [t.retry_count for t in tasks if t.retry_count > 0]

    compile_results = [t for t in tasks if t.compiler_output is not None]
    test_results = [t for t in tasks if t.test_output is not None]

    return SystemMetrics(
        timestamp=datetime.now(timezone.utc),
        active_tasks=len(active),
        completed_tasks=len(completed),
        rejected_tasks=len(rejected),
        deadlocked_tasks=len(deadlocked),
        merged_tasks=len(completed),
        avg_review_cycles=sum(review_cycles) / len(review_cycles) if review_cycles else 0.0,
        avg_task_duration_seconds=sum(durations) / len(durations) if durations else 0.0,
        total_cost_usd=sum(t.estimated_cost_usd for t in tasks),
        total_tokens=sum(t.total_tokens_used for t in tasks),
        compile_success_rate=(
            sum(1 for t in compile_results if t.compiler_output and t.compiler_output.success)  # type: ignore[union-attr]
            / len(compile_results)
            if compile_results else 0.0
        ),
        test_pass_rate=(
            sum(1 for t in test_results if t.test_output and t.test_output.success)  # type: ignore[union-attr]
            / len(test_results)
            if test_results else 0.0
        ),
        critic_rejection_rate=(
            len(rejected) / len(tasks) if tasks else 0.0
        ),
    )
