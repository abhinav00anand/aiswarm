"""
Unit Tests for Engineering Governor Policy Controller.
"""

from aiswarm.security.governor import EngineeringGovernor, PolicyViolationError


def test_governor_task_admission_pass():
    """Task within budget should pass admission."""
    governor = EngineeringGovernor(max_session_budget_usd=10.0)
    result = governor.check_task_admission({"task_id": "t1", "estimated_cost_usd": 2.5})
    assert result is True


def test_governor_task_admission_budget_exceeded():
    """Task exceeding budget cap should raise PolicyViolationError."""
    governor = EngineeringGovernor(max_session_budget_usd=5.0)
    raised = False
    try:
        governor.check_task_admission({"task_id": "t2", "estimated_cost_usd": 15.0})
    except PolicyViolationError:
        raised = True
    assert raised is True


def test_governor_spawn_policy():
    """Forbidden capabilities for fast mode should be blocked."""
    governor = EngineeringGovernor()

    # Authorized capability
    assert governor.check_capability_spawn_policy("pytest", "host2") is True

    # Forbidden capability for host2
    raised = False
    try:
        governor.check_capability_spawn_policy("raw_shell_execution", "host2")
    except PolicyViolationError:
        raised = True
    assert raised is True


def test_governor_release_gate():
    """Release gate should evaluate release manifests correctly."""
    governor = EngineeringGovernor()

    manifest_ok = {
        "unit_tests_passed": True,
        "security_scan_cleared": True,
        "artifact_hash_verified": True,
    }
    evaluation = governor.check_release_gate(manifest_ok)
    assert evaluation["approved"] is True
    assert len(evaluation["failed_gates"]) == 0

    manifest_bad = {
        "unit_tests_passed": False,
        "security_scan_cleared": True,
        "artifact_hash_verified": True,
    }
    evaluation_bad = governor.check_release_gate(manifest_bad)
    assert evaluation_bad["approved"] is False
    assert "unit_tests" in evaluation_bad["failed_gates"]
