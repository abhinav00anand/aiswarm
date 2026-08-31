"""Unit tests for the Task schema."""

from __future__ import annotations


from aiswarm.schemas.task import (
    Task,
    TaskState,
    CriticReview,
    ReviewDecision,
    CompilerOutput,
    TestOutput,
)


class TestTask:
    def test_default_state_is_new(self) -> None:
        task = Task(title="T", description="D")
        assert task.state == TaskState.NEW

    def test_task_id_is_generated(self) -> None:
        t1 = Task(title="T1", description="D")
        t2 = Task(title="T2", description="D")
        assert t1.task_id != t2.task_id

    def test_is_approved_majority(self) -> None:
        task = Task(title="T", description="D")
        task.reviews = [
            CriticReview(
                critic_role="architecture", decision=ReviewDecision.APPROVE, production_ready=True
            ),
            CriticReview(
                critic_role="performance", decision=ReviewDecision.APPROVE, production_ready=True
            ),
            CriticReview(
                critic_role="security",
                decision=ReviewDecision.REJECT,
                production_ready=False,
                fatal_flaw="sql injection",
            ),
        ]
        assert task.is_approved()  # 2/3 approve

    def test_is_not_approved_minority(self) -> None:
        task = Task(title="T", description="D")
        task.reviews = [
            CriticReview(
                critic_role="architecture", decision=ReviewDecision.APPROVE, production_ready=True
            ),
            CriticReview(
                critic_role="performance",
                decision=ReviewDecision.REJECT,
                production_ready=False,
                fatal_flaw="O(n^2)",
            ),
            CriticReview(
                critic_role="security",
                decision=ReviewDecision.REJECT,
                production_ready=False,
                fatal_flaw="hardcoded key",
            ),
        ]
        assert not task.is_approved()

    def test_security_veto(self) -> None:
        task = Task(title="T", description="D")
        task.reviews = [
            CriticReview(
                critic_role="architecture", decision=ReviewDecision.APPROVE, production_ready=True
            ),
            CriticReview(
                critic_role="performance", decision=ReviewDecision.APPROVE, production_ready=True
            ),
            CriticReview(
                critic_role="security",
                decision=ReviewDecision.REJECT,
                production_ready=False,
                fatal_flaw="RCE",
            ),
        ]
        assert task.is_security_vetoed()
        # Even though majority approves, security veto exists

    def test_no_security_veto_when_approved(self) -> None:
        task = Task(title="T", description="D")
        task.reviews = [
            CriticReview(
                critic_role="security", decision=ReviewDecision.APPROVE, production_ready=True
            ),
        ]
        assert not task.is_security_vetoed()

    def test_rejection_reasons(self) -> None:
        task = Task(title="T", description="D")
        task.reviews = [
            CriticReview(
                critic_role="security",
                decision=ReviewDecision.REJECT,
                production_ready=False,
                fatal_flaw="eval on input",
                mandatory_fix="Use ast.literal_eval instead",
            ),
        ]
        reasons = task.rejection_reasons()
        assert len(reasons) == 1
        assert "security" in reasons[0]
        assert "eval on input" in reasons[0]

    def test_rejection_reasons_includes_security_violations_and_metadata(self) -> None:
        task = Task(title="Security scan test", description="Testing metadata violations")
        task.metadata["security_violations"] = ["HIGH: Hardcoded secret"]
        task.metadata["precheck_issues"] = ["Syntax error on line 4"]
        reasons = task.rejection_reasons()
        assert len(reasons) == 2
        assert any("HIGH: Hardcoded secret" in r for r in reasons)
        assert any("Syntax error on line 4" in r for r in reasons)

    def test_serialization_roundtrip(self) -> None:
        task = Task(title="Round-trip test", description="Testing serialization")
        task.generated_code = "def hello(): return 'world'"
        json_str = task.model_dump_json()
        restored = Task.model_validate_json(json_str)
        assert restored.task_id == task.task_id
        assert restored.title == task.title
        assert restored.generated_code == task.generated_code

    def test_compiler_output_structure(self) -> None:
        out = CompilerOutput(
            success=True, stdout="OK", stderr="", exit_code=0, duration_seconds=0.5
        )
        assert out.success
        assert out.exit_code == 0

    def test_test_output_structure(self) -> None:
        out = TestOutput(
            success=True, total=10, passed=9, failed=1, skipped=0, duration_seconds=2.0
        )
        assert out.passed == 9
        assert out.success  # success=True was explicitly set
        out2 = TestOutput(success=False, total=5, passed=3, failed=2)
        assert not out2.success
