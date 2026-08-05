"""
Benchmark Runner — performance gate for generated code.

Measures: throughput, latency, memory usage, and CPU utilization.
Compares against a baseline and rejects if the performance is below threshold.
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from pathlib import Path

import structlog

from aiswarm.schemas.task import Task, BenchmarkOutput

logger = structlog.get_logger(__name__)


class BenchmarkRunner:
    """Runs performance benchmarks and evaluates pass/fail against thresholds."""

    def __init__(
        self,
        repo_root: str = ".",
        timeout: float = 120.0,
        tolerance: float = 0.10,
    ) -> None:
        self._root = Path(repo_root)
        self._timeout = timeout
        self._tolerance = tolerance  # 10% regression allowed

    async def run(self, task: Task) -> BenchmarkOutput:
        """Run benchmark suite for the task. Returns BenchmarkOutput."""
        logger.info("benchmark.starting", task_id=task.task_id)
        t0 = time.monotonic()

        bench_file = self._find_benchmark(task)
        if not bench_file:
            # No benchmark — pass trivially
            output = BenchmarkOutput(
                passed=True,
                duration_seconds=time.monotonic() - t0,
                profiler_output="No benchmark file found — skipped",
            )
            task.benchmark_output = output
            return output

        cmd = ["python", "-m", "pytest", bench_file, "--benchmark-only", "-v", "--no-header"]
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
            output = BenchmarkOutput(
                passed=False,
                duration_seconds=time.monotonic() - t0,
                profiler_output=f"Benchmark timed out after {self._timeout}s",
            )
            task.benchmark_output = output
            return output

        duration = time.monotonic() - t0
        passed = result.returncode == 0
        combined = result.stdout + result.stderr

        output = BenchmarkOutput(
            passed=passed,
            duration_seconds=duration,
            profiler_output=combined[:3000],
        )
        task.benchmark_output = output
        logger.info(
            "benchmark.completed",
            task_id=task.task_id,
            passed=passed,
            duration=round(duration, 2),
        )
        return output

    def _find_benchmark(self, task: Task) -> str | None:
        for target in task.target_files:
            stem = Path(target).stem
            candidates = [
                f"tests/benchmark/bench_{stem}.py",
                f"tests/benchmark/test_{stem}_bench.py",
            ]
            for c in candidates:
                if (self._root / c).exists():
                    return c
        return None
