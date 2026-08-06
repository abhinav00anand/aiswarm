"""
Finite state machine for task lifecycle.

Valid transitions are defined explicitly; any attempt to move to an
invalid state raises TaskStateError to prevent silent corruption.
"""

from __future__ import annotations

import structlog

from aiswarm.schemas.task import Task, TaskState

logger = structlog.get_logger(__name__)

# (from_state, to_state) → True means the transition is allowed
VALID_TRANSITIONS: set[tuple[TaskState, TaskState]] = {
    # Forward path
    (TaskState.NEW,         TaskState.PROMPTED),
    (TaskState.PROMPTED,    TaskState.GENERATED),
    (TaskState.GENERATED,   TaskState.PRECHECKED),
    (TaskState.PRECHECKED,  TaskState.REVIEWED),
    (TaskState.REVIEWED,    TaskState.COMPILED),
    (TaskState.COMPILED,    TaskState.TESTED),
    (TaskState.TESTED,      TaskState.BENCHMARKED),
    (TaskState.BENCHMARKED, TaskState.MERGED),

    # Rejection / retry paths
    (TaskState.PRECHECKED,  TaskState.PROMPTED),       # precheck failed → re-prompt
    (TaskState.REVIEWED,    TaskState.PROMPTED),       # majority reject → re-prompt
    (TaskState.COMPILED,    TaskState.PROMPTED),       # compile fail → re-prompt
    (TaskState.TESTED,      TaskState.PROMPTED),       # tests fail → re-prompt
    (TaskState.BENCHMARKED, TaskState.PROMPTED),       # perf fail → re-prompt

    # Terminal states
    (TaskState.GENERATED,   TaskState.REJECTED),
    (TaskState.PRECHECKED,  TaskState.REJECTED),
    (TaskState.REVIEWED,    TaskState.REJECTED),
    (TaskState.COMPILED,    TaskState.REJECTED),
    (TaskState.TESTED,      TaskState.REJECTED),
    (TaskState.BENCHMARKED, TaskState.REJECTED),

    # Deadlock / escalation
    (TaskState.PROMPTED,    TaskState.DEADLOCK),
    (TaskState.GENERATED,   TaskState.DEADLOCK),
    (TaskState.REVIEWED,    TaskState.DEADLOCK),
    (TaskState.COMPILED,    TaskState.DEADLOCK),
    (TaskState.DEADLOCK,    TaskState.ESCALATED),
    (TaskState.ESCALATED,   TaskState.PROMPTED),       # boss can restart
    # Operator force-merge — allowed from deadlock/escalated only via state machine
    (TaskState.DEADLOCK,    TaskState.MERGED),
    (TaskState.ESCALATED,   TaskState.MERGED),

    # Pause / cancel (allowed from many states)
    *{
        (s, TaskState.PAUSED)
        for s in (
            TaskState.NEW, TaskState.PROMPTED, TaskState.GENERATED,
            TaskState.PRECHECKED, TaskState.REVIEWED, TaskState.COMPILED,
            TaskState.TESTED,
        )
    },
    *{
        (TaskState.PAUSED, s)
        for s in (
            TaskState.PROMPTED, TaskState.COMPILED, TaskState.TESTED,
        )
    },
    *{
        (s, TaskState.CANCELLED)
        for s in TaskState
        if s not in (TaskState.MERGED, TaskState.CANCELLED)
    },
}


class TaskStateError(Exception):
    """Raised when an invalid state transition is attempted."""


class StateMachine:
    """
    Validates and applies task state transitions.

    Every state change goes through StateMachine.transition() so the
    transition graph is always enforced.
    """

    @staticmethod
    def can_transition(current: TaskState, target: TaskState) -> bool:
        return (current, target) in VALID_TRANSITIONS

    @staticmethod
    def transition(
        task: Task,
        target: TaskState,
        reason: str,
        agent: str = "",
        evidence: dict | None = None,
    ) -> None:
        """
        Apply a state transition to a task.

        Raises TaskStateError if the transition is not valid.
        Mutates the task in place and records the audit trail.
        """
        if not StateMachine.can_transition(task.state, target):
            raise TaskStateError(
                f"Invalid transition {task.state!r} -> {target!r} "
                f"for task {task.task_id}"
            )


        logger.info(
            "task.state_transition",
            task_id=task.task_id,
            from_state=task.state.value,
            to_state=target.value,
            reason=reason,
            agent=agent,
        )
        task.transition(target, reason=reason, agent=agent, evidence=evidence or {})

    @staticmethod
    def is_terminal(state: TaskState) -> bool:
        """Return True if the state is a terminal (non-retryable) state."""
        return state in {
            TaskState.MERGED,
            TaskState.REJECTED,
            TaskState.CANCELLED,
            TaskState.DEADLOCK,
            TaskState.ESCALATED,
        }

    @staticmethod
    def is_failed(state: TaskState) -> bool:
        return state in {
            TaskState.REJECTED,
            TaskState.DEADLOCK,
            TaskState.CANCELLED,
        }
