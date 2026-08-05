"""
Unit Tests for Host-1 Global Router & Policy Gate.
"""

from aiswarm.agents.host1.router import Host1Router
from aiswarm.schemas.routing import ExecutionMode, RiskLevel


def test_host1_route_security_sensitive_task():
    """Tasks with security-sensitive keywords must route to PRODUCTION."""
    router = Host1Router()
    payload = {
        "task_id": "task_sec_01",
        "title": "Implement authentication and secret token storage",
        "description": "Store database login credentials safely",
        "target_files": ["auth.py"],
    }
    decision = router.evaluate_task(payload)
    assert decision.route == ExecutionMode.PRODUCTION
    assert decision.risk_level == RiskLevel.HIGH
    assert decision.confidence >= 0.90
    assert "security-sensitive" in decision.reason


def test_host1_route_multi_file_task():
    """Multi-file tasks should route to HYBRID mode."""
    router = Host1Router()
    payload = {
        "task_id": "task_hybrid_01",
        "title": "Refactor data pipelines",
        "description": "Update models across several modules",
        "target_files": ["model.py", "views.py", "utils.py", "config.py"],
    }
    decision = router.evaluate_task(payload)
    assert decision.route == ExecutionMode.HYBRID
    assert decision.risk_level == RiskLevel.MEDIUM


def test_host1_route_simple_task():
    """Single-file, low-risk utility task should route to FAST mode."""
    router = Host1Router()
    payload = {
        "task_id": "task_fast_01",
        "title": "Fix docstring typo in math helper",
        "description": "Correct spelling in helper function",
        "target_files": ["math_utils.py"],
    }
    decision = router.evaluate_task(payload)
    assert decision.route == ExecutionMode.FAST
    assert decision.risk_level == RiskLevel.LOW
