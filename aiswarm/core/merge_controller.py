"""Merge Controller."""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

import aiofiles
import structlog

from aiswarm.schemas.task import Task, TaskState
from aiswarm.core.state_machine import StateMachine

logger = structlog.get_logger(__name__)

class MergeGateError(Exception):
    """Raised when a merge gate is not satisfied."""

class MergeController:
    """
    Validates all gates and writes code to the target files.
    """

    def __init__(self, repo_root: str = ".") -> None:
        self._repo_root = Path(repo_root)

    def _gate_code_present(self, task: Task) -> None:
        if not task.generated_code:
            raise MergeGateError("No generated code on task.")
        # Verify hash integrity
        actual_hash = hashlib.sha256(task.generated_code.encode()).hexdigest()
        if task.generated_code_hash and actual_hash != task.generated_code_hash:
            raise MergeGateError(
                f"Code hash mismatch. Expected {task.generated_code_hash!r}, "
                f"got {actual_hash!r}."
            )

    def _gate_critic_approval(self, task: Task) -> None:
        from aiswarm.schemas.routing import ExecutionMode
        metadata = getattr(task, "metadata", {}) or {}
        decision = metadata.get("route_decision")
        is_fast = False
        if decision:
            route = getattr(decision, "route", None)
            if route == ExecutionMode.FAST or route == "FAST":
                is_fast = True

        if is_fast:
            # FAST route tasks bypass critic reviews by design
            logger.info("merge.critic_gate_bypassed_for_fast_mode", task_id=task.task_id)
            return

        if not task.reviews:
            raise MergeGateError("No critic reviews found.")
        if task.is_security_vetoed():
            raise MergeGateError(
                "Security critic issued a veto — merge blocked unconditionally."
            )
        if not task.is_approved():
            reasons = task.rejection_reasons()
            raise MergeGateError(
                f"Insufficient critic approval ({len(task.reviews)} reviews). "
                f"Reasons: {reasons}"
            )

    def _gate_compilation(self, task: Task) -> None:
        if task.compiler_output is None:
            raise MergeGateError("No compiler output recorded.")
        if not task.compiler_output.success:
            raise MergeGateError(
                f"Compilation failed:\n{task.compiler_output.stderr[:1000]}"
            )

    def _gate_tests(self, task: Task) -> None:
        if task.test_output is None:
            raise MergeGateError("No test output recorded.")
        if not task.test_output.success:
            raise MergeGateError(
                f"Tests failed ({task.test_output.failed} failures)."
            )
        if not task.test_output.numeric_passed:
            raise MergeGateError(
                "Numeric equivalence test failed — wrong numerical result. "
                "Critic approval cannot override this gate."
            )

    def _gate_benchmark(self, task: Task) -> None:
        if task.benchmark_output is None:
            # Benchmark is optional for non-performance tasks
            return
        if not task.benchmark_output.passed:
            raise MergeGateError(
                "Benchmark gate failed. Performance below threshold.\n"
                f"Profiler output:\n{task.benchmark_output.profiler_output[:500]}"
            )

    def _safe_dest(self, file_path: str) -> Path:
        """
        Resolve destination path and enforce it stays within repo_root.

        Raises MergeGateError on any path traversal attempt (e.g. ``../../etc/passwd``
        or absolute paths that escape the repository root).
        """
        repo_abs = self._repo_root.resolve()
        # Reject absolute paths supplied by the task (could be /etc, /tmp, etc.)
        raw = Path(file_path)
        if raw.is_absolute():
            raise MergeGateError(
                f"Merge rejected: target file path is absolute: {file_path!r}. "
                "Target paths must be relative to the repository root."
            )
        dest = (repo_abs / raw).resolve()
        # Check that the resolved path is still inside the repo root
        try:
            dest.relative_to(repo_abs)
        except ValueError:
            raise MergeGateError(
                f"Merge rejected: path traversal detected. "
                f"Resolved path {str(dest)!r} escapes repository root {str(repo_abs)!r}."
            ) from None
        return dest

    async def _write_files(self, task: Task) -> list[Path]:
        """Write generated code to target files (creates dirs as needed)."""
        written: list[Path] = []
        if not task.target_files:
            raise MergeGateError("No target files defined on task.")
        for file_path in task.target_files:
            dest = self._safe_dest(file_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(dest, "w", encoding="utf-8") as f:
                await f.write(task.generated_code or "")
            written.append(dest)
            logger.info("merge.file_written", path=str(dest), task_id=task.task_id)
        return written

    async def attempt_merge(self, task: Task) -> list[Path]:
        """
        Run all gates and write files if every gate passes.

        Returns the list of written file paths.
        Raises MergeGateError on any failure.
        """
        logger.info("merge.attempt_started", task_id=task.task_id)

        self._gate_code_present(task)
        self._gate_critic_approval(task)
        self._gate_compilation(task)
        self._gate_tests(task)
        self._gate_benchmark(task)

        written = await self._write_files(task)

        task.merged = True
        task.merged_at = datetime.now(timezone.utc)
        task.merged_by = "merge_controller"
        task.completed_at = datetime.now(timezone.utc)

        StateMachine.transition(
            task,
            TaskState.MERGED,
            reason="All merge gates passed",
            agent="merge_controller",
            evidence={"files_written": [str(p) for p in written]},
        )

        logger.info(
            "merge.success",
            task_id=task.task_id,
            files=[str(p) for p in written],
        )
        return written

    async def run(self, task: Task) -> None:
        """Polymorphic agent run wrapper."""
        await self.attempt_merge(task)
