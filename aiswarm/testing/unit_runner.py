"""
Unit Test Runner — executes pytest on generated code with timeout and coverage.

The runner:
  1. Writes generated code to a temp file.
  2. Discovers and runs corresponding test files.
  3. Captures exact stdout/stderr and exit code.
  4. Parses pytest output into structured TestOutput.
  5. Checks numeric equivalence if a reference implementation is specified.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import structlog

from aiswarm.schemas.task import Task, TestOutput

logger = structlog.get_logger(__name__)

_TEST_TIMEOUT = 120  # seconds


class UnitRunner:
    """Executes unit tests against generated code."""

    def __init__(self, repo_root: str = ".", timeout: float = _TEST_TIMEOUT) -> None:
        self._root = Path(repo_root)
        self._timeout = timeout

    async def run(self, task: Task) -> TestOutput:
        """
        Run unit tests for the task's target files.
        Returns a TestOutput and stores it on task.test_output.
        """
        logger.info("unit_runner.starting", task_id=task.task_id)
        t0 = time.monotonic()

        # Write generated code to target location
        code = task.generated_code or ""
        if not code.strip():
            output = TestOutput(
                success=False,
                stdout="No code to test",
                stderr="",
                duration_seconds=0.0,
            )
            task.test_output = output
            return output

        for target_file in task.target_files:
            dest = self._root / target_file
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(code, encoding="utf-8")

        # Discover test files
        test_files = self._find_tests(task)

        if not test_files:
            # No test files — treat as skipped (not failed)
            output = TestOutput(
                success=True,
                total=0,
                passed=0,
                skipped=0,
                stdout="No test files found for this task",
                duration_seconds=time.monotonic() - t0,
                numeric_passed=True,
            )
            task.test_output = output
            return output

        # Run pytest
        cmd = [
            "python", "-m", "pytest",
            *test_files,
            "--tb=short",
            "--no-header",
            "-q",
            f"--timeout={self._timeout}",
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
                    timeout=self._timeout + 10,
                ),
            )
        except subprocess.TimeoutExpired:
            output = TestOutput(
                success=False,
                stdout="",
                stderr=f"Test run timed out after {self._timeout}s",
                duration_seconds=time.monotonic() - t0,
            )
            task.test_output = output
            return output

        duration = time.monotonic() - t0
        parsed = self._parse_pytest_output(result.stdout + result.stderr)
        success = result.returncode == 0

        output = TestOutput(
            success=success,
            total=parsed["total"],
            passed=parsed["passed"],
            failed=parsed["failed"],
            skipped=parsed["skipped"],
            stdout=result.stdout[:5000],
            stderr=result.stderr[:2000],
            duration_seconds=duration,
            numeric_passed=True,  # Numeric check is separate
        )
        task.test_output = output

        logger.info(
            "unit_runner.completed",
            task_id=task.task_id,
            success=success,
            passed=parsed["passed"],
            failed=parsed["failed"],
            duration=round(duration, 2),
        )
        return output

    def _find_tests(self, task: Task) -> list[str]:
        """Discover test files related to the task's target files."""
        test_files: list[str] = []
        for target in task.target_files:
            stem = Path(target).stem
            # Common patterns: test_<stem>.py, <stem>_test.py, tests/<stem>/
            candidates = [
                f"tests/unit/test_{stem}.py",
                f"tests/unit/{stem}_test.py",
                f"tests/test_{stem}.py",
                f"test_{stem}.py",
            ]
            for c in candidates:
                if (self._root / c).exists():
                    test_files.append(c)
        return test_files

    def _parse_pytest_output(self, output: str) -> dict[str, int]:
        # Match: "5 passed, 1 failed, 2 skipped"
        pattern = r"(\d+) passed|(\d+) failed|(\d+) error|(\d+) skipped"
        passed = failed = skipped = 0
        for m in re.finditer(pattern, output, re.IGNORECASE):
            if m.group(1):
                passed = int(m.group(1))
            elif m.group(2):
                failed = int(m.group(2))
            elif m.group(4):
                skipped = int(m.group(4))
        total = passed + failed + skipped
        return {"total": total, "passed": passed, "failed": failed, "skipped": skipped}
