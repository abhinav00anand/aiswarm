"""Confidence Engine Subsystem."""

from __future__ import annotations

from typing import Any
from aiswarm.utils.compat_log import get_logger

logger = get_logger(__name__)

class ConfidenceEngine:
    """Computes holistic confidence scores across engineering quality dimensions."""

    def evaluate_confidence(self, task_summary: dict[str, Any]) -> dict[str, Any]:
        """
        Evaluate task metrics and return multi-dimensional confidence breakdown.
        """
        # 1. Correctness (unit tests + compilation)
        compilation_ok = task_summary.get("compilation_success", True)
        tests_ok = task_summary.get("unit_tests_passed", True)
        correctness_score = 100.0 if (compilation_ok and tests_ok) else 40.0

        # 2. Security (code scanner & policy gates)
        security_veto = task_summary.get("security_veto", False)
        security_score = 0.0 if security_veto else 95.0

        # 3. Architecture (critic approval ratio)
        critic_approvals = task_summary.get("critic_approvals", 2)
        total_critics = task_summary.get("total_critics", 3)
        architecture_score = (critic_approvals / max(total_critics, 1)) * 100.0

        # 4. Test Coverage
        coverage_pct = float(task_summary.get("coverage_pct", 85.0))
        coverage_score = min(coverage_pct, 100.0)

        # 5. Performance
        benchmark_passed = task_summary.get("benchmark_passed", True)
        performance_score = 90.0 if benchmark_passed else 50.0

        # Weighted Overall Score
        overall = (
            (correctness_score * 0.30)
            + (security_score * 0.25)
            + (architecture_score * 0.20)
            + (coverage_score * 0.15)
            + (performance_score * 0.10)
        )

        breakdown = {
            "overall_pct": round(overall, 1),
            "dimensions": {
                "correctness": round(correctness_score, 1),
                "security": round(security_score, 1),
                "architecture": round(architecture_score, 1),
                "test_coverage": round(coverage_score, 1),
                "performance": round(performance_score, 1),
            },
            "recommendation": "ACCEPT" if overall >= 80.0 else "REVIEW_REQUIRED",
        }

        logger.info("confidence_engine.evaluated", overall_pct=breakdown["overall_pct"])
        return breakdown
