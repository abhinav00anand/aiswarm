"""
Unit Tests for Confidence Engine.
"""

from aiswarm.core.confidence_engine import ConfidenceEngine


def test_confidence_engine_pass():
    """High quality task metrics should yield high overall confidence."""
    engine = ConfidenceEngine()
    summary = {
        "compilation_success": True,
        "unit_tests_passed": True,
        "security_veto": False,
        "critic_approvals": 3,
        "total_critics": 3,
        "coverage_pct": 92.0,
        "benchmark_passed": True,
    }
    result = engine.evaluate_confidence(summary)
    assert result["overall_pct"] >= 85.0
    assert result["recommendation"] == "ACCEPT"
    assert result["dimensions"]["security"] == 95.0


def test_confidence_engine_security_veto():
    """Security veto should dramatically drop security score."""
    engine = ConfidenceEngine()
    summary = {
        "compilation_success": True,
        "unit_tests_passed": True,
        "security_veto": True,
        "critic_approvals": 2,
        "total_critics": 3,
        "coverage_pct": 80.0,
        "benchmark_passed": True,
    }
    result = engine.evaluate_confidence(summary)
    assert result["dimensions"]["security"] == 0.0
    assert result["recommendation"] == "REVIEW_REQUIRED"
