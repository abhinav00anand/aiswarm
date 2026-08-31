"""Deadlock detector."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog

from aiswarm.schemas.task import Task, TaskState
from aiswarm.core.state_machine import StateMachine

logger = structlog.get_logger(__name__)


class DeadlockPacket:
    """Summary packet sent to the Boss agent when a deadlock is detected."""

    def __init__(self, task: Task) -> None:
        self.task_id = task.task_id
        self.title = task.title
        self.retry_count = task.retry_count
        self.current_state = task.state
        self.history_summary = self._summarize(task)
        self.rejection_reasons = task.rejection_reasons()
        self.latest_code = task.generated_code or ""
        self.compiler_errors = task.compiler_output.stderr if task.compiler_output else ""
        self.test_failures = task.test_output.stdout if task.test_output else ""
        self.detected_at = datetime.now(timezone.utc)

    def _summarize(self, task: Task) -> list[str]:
        return [
            f"[{t.timestamp.isoformat()}] {t.from_state.value} → {t.to_state.value}: {t.reason}"
            for t in task.state_history[-20:]
        ]

    def to_prompt_block(self) -> str:
        lines = [
            f"=== DEADLOCK PACKET: {self.task_id} ===",
            f"Title: {self.title}",
            f"Retries: {self.retry_count}",
            f"Current state: {self.current_state.value}",
            "",
            "--- Rejection Reasons ---",
            *self.rejection_reasons,
            "",
            "--- Compiler Errors ---",
            self.compiler_errors or "(none)",
            "",
            "--- State History (last 20) ---",
            *self.history_summary,
            "",
            "--- Latest Code Snapshot ---",
            self.latest_code[:3000] if self.latest_code else "(none)",
            "=== END DEADLOCK PACKET ===",
        ]
        return "\n".join(lines)


class DeadlockDetector:
    """
    Runs as a background task scanning active tasks for stalls and loops.
    """

    def __init__(
        self,
        deadlock_timeout: float = 300.0,
        scan_interval: float = 30.0,
    ) -> None:
        self._timeout = deadlock_timeout
        self._scan_interval = scan_interval
        self._state_entered: dict[str, datetime] = {}
        self._running = False
        self._callbacks: list = []

    def on_deadlock(self, fn) -> None:  # type: ignore[type-arg]
        """Register a callback(task_id, packet) called when a deadlock is detected."""
        self._callbacks.append(fn)

    def notify_state_change(self, task: Task) -> None:
        """
        Called by the orchestrator whenever a task changes state.

        Must be called on EVERY state transition — not just on submission.
        The timestamp tracks when the task entered its CURRENT state, so a
        task progressing normally will never be mis-detected as deadlocked.
        """
        self._state_entered[task.task_id] = datetime.now(timezone.utc)
        logger.debug(
            "deadlock_detector.state_updated",
            task_id=task.task_id,
            state=task.state.value,
        )

    def forget(self, task_id: str) -> None:
        """Remove a task from tracking (called when it reaches a terminal state)."""
        self._state_entered.pop(task_id, None)

    def check_task(self, task: Task) -> bool:
        """Return True if the task appears deadlocked."""
        if StateMachine.is_terminal(task.state):
            return False
        if task.retry_count >= task.max_retries:
            logger.warning(
                "deadlock.retries_exceeded",
                task_id=task.task_id,
                retry_count=task.retry_count,
            )
            return True
        entered = self._state_entered.get(task.task_id)
        if entered:
            elapsed = (datetime.now(timezone.utc) - entered).total_seconds()
            if elapsed > self._timeout:
                logger.warning(
                    "deadlock.state_timeout",
                    task_id=task.task_id,
                    state=task.state.value,
                    elapsed=elapsed,
                )
                return True
        return False

    async def _fire_callbacks(self, task: Task, packet: DeadlockPacket) -> None:
        for cb in self._callbacks:
            try:
                await cb(task.task_id, packet)
            except Exception as exc:  # noqa: BLE001
                logger.error("deadlock.callback_error", error=str(exc))

    async def scan(self, tasks: list[Task]) -> list[str]:
        """Scan a list of tasks; return task_ids of newly detected deadlocks."""
        deadlocked: list[str] = []
        for task in tasks:
            if task.state == TaskState.DEADLOCK:
                continue
            if self.check_task(task):
                packet = DeadlockPacket(task)
                task.transition(
                    TaskState.DEADLOCK,
                    reason="Deadlock detected by DeadlockDetector",
                    agent="deadlock_detector",
                    evidence={"retry_count": task.retry_count},
                )
                deadlocked.append(task.task_id)
                await self._fire_callbacks(task, packet)
        return deadlocked

    async def run_forever(self, task_registry_fn) -> None:  # type: ignore[type-arg]
        """
        Background loop — call task_registry_fn() to get the current task list.
        """
        self._running = True
        logger.info("deadlock_detector.started", timeout=self._timeout)
        while self._running:
            await asyncio.sleep(self._scan_interval)
            try:
                tasks = await task_registry_fn()
                detected = await self.scan(tasks)
                if detected:
                    logger.warning("deadlock_detector.detected", task_ids=detected)
            except Exception as exc:  # noqa: BLE001
                logger.error("deadlock_detector.scan_error", error=str(exc))

    def stop(self) -> None:
        self._running = False
