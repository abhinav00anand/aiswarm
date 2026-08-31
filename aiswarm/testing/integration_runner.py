"""Integration test runner — executes integration tests across services."""

from __future__ import annotations

import asyncio
import subprocess
import time
from pathlib import Path

import structlog

from aiswarm.schemas.task import Task, TestOutput

logger = structlog.get_logger(__name__)


class IntegrationRunner:
    """Runs integration tests that span multiple components."""

    def __init__(self, repo_root: str = ".", timeout: float = 300.0) -> None:
        self._root = Path(repo_root)
        self._timeout = timeout

    async def run(self, task: Task) -> TestOutput:
        """Run integration tests for the task."""
        logger.info("integration_runner.starting", task_id=task.task_id)
        t0 = time.monotonic()

        test_dir = self._root / "tests" / "integration"
        if not test_dir.exists():
            return TestOutput(
                success=True,
                stdout="No integration tests directory found",
                duration_seconds=time.monotonic() - t0,
            )

        cmd = [
            "python",
            "-m",
            "pytest",
            str(test_dir),
            "-m",
            "not integration",  # skip tests requiring real APIs
            "--tb=short",
            "-q",
            "--no-header",
        ]

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    cwd=str(self._root),
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                ),
            )
        except subprocess.TimeoutExpired:
            return TestOutput(
                success=False,
                stderr=f"Integration tests timed out after {self._timeout}s",
                duration_seconds=time.monotonic() - t0,
            )

        output = TestOutput(
            success=result.returncode == 0,
            stdout=result.stdout[:3000],
            stderr=result.stderr[:1000],
            duration_seconds=time.monotonic() - t0,
        )
        task.test_output = output
        return output
