"""Coverage checker — validates that generated code meets coverage thresholds."""

from __future__ import annotations

import asyncio
import subprocess

import structlog

logger = structlog.get_logger(__name__)


class CoverageChecker:
    """Runs coverage measurement and validates against thresholds."""

    def __init__(self, threshold: float = 80.0, timeout: float = 60.0) -> None:
        self._threshold = threshold
        self._timeout = timeout

    async def measure(self, test_path: str, source_path: str) -> dict[str, object]:
        """Run pytest with coverage and return the coverage percentage."""
        cmd = [
            "python",
            "-m",
            "pytest",
            test_path,
            f"--cov={source_path}",
            "--cov-report=term-missing",
            "-q",
            "--no-header",
        ]
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                ),
            )
            output = result.stdout + result.stderr
            # Parse coverage percentage
            import re

            cov_match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)
            pct = float(cov_match.group(1)) if cov_match else 0.0
            return {
                "coverage_pct": pct,
                "meets_threshold": pct >= self._threshold,
                "threshold": self._threshold,
                "output": output[:2000],
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("coverage.error", error=str(exc))
            return {"coverage_pct": 0.0, "meets_threshold": False, "error": str(exc)}
