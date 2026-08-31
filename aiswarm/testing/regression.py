"""Regression test runner — detects regressions between code versions."""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


class RegressionDetector:
    """
    Compares current test results against historical baselines to detect regressions.
    """

    def __init__(self, tolerance_pct: float = 10.0) -> None:
        self._tolerance = tolerance_pct
        self._baselines: dict[str, dict[str, float]] = {}

    def set_baseline(self, task_class: str, metrics: dict[str, float]) -> None:
        self._baselines[task_class] = metrics

    def is_regression(
        self,
        task_class: str,
        current_metrics: dict[str, float],
    ) -> tuple[bool, list[str]]:
        """
        Check if current metrics represent a regression vs baseline.
        Returns (is_regression, list_of_regressions).
        """
        baseline = self._baselines.get(task_class, {})
        if not baseline:
            return False, []

        regressions: list[str] = []
        for metric, baseline_val in baseline.items():
            current = current_metrics.get(metric)
            if current is None:
                continue
            if baseline_val == 0:
                continue
            change_pct = abs((current - baseline_val) / baseline_val) * 100
            if change_pct > self._tolerance and current < baseline_val:
                regressions.append(
                    f"{metric}: {current:.3f} vs baseline {baseline_val:.3f} "
                    f"({change_pct:.1f}% regression)"
                )

        return len(regressions) > 0, regressions
