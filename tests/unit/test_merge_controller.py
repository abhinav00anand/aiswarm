"""Unit tests for the merge controller gate logic."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from aiswarm.core.merge_controller import MergeController, MergeGateError
from aiswarm.schemas.task import (
    Task,
    TaskState,
    CriticReview,
    ReviewDecision,
    CompilerOutput,
    TestOutput,
)
from aiswarm.utils.hashing import sha256_hex


def _approved_task(tmp_dir: str) -> Task:
    code = "def hello():\n    return 'world'\n"
    task = Task(title="Test", description="Test task")
    task.state = TaskState.BENCHMARKED
    task.generated_code = code
    task.generated_code_hash = sha256_hex(code)
    task.target_files = ["output.py"]
    task.reviews = [
        CriticReview(
            critic_role="architecture",
            decision=ReviewDecision.APPROVE,
            production_ready=True,
            score=80,
        ),
        CriticReview(
            critic_role="performance",
            decision=ReviewDecision.APPROVE,
            production_ready=True,
            score=80,
        ),
        CriticReview(
            critic_role="security", decision=ReviewDecision.APPROVE, production_ready=True, score=80
        ),
    ]
    task.compiler_output = CompilerOutput(success=True, exit_code=0)
    task.test_output = TestOutput(success=True, passed=5, total=5, numeric_passed=True)
    return task


@pytest.mark.asyncio
class TestMergeController:
    async def test_successful_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task = _approved_task(tmp)
            mc = MergeController(repo_root=tmp)
            written = await mc.attempt_merge(task)
            assert len(written) == 1
            assert task.merged is True
            assert task.state == TaskState.MERGED
            assert Path(written[0]).read_text() == task.generated_code

    async def test_no_code_blocks_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task = _approved_task(tmp)
            task.generated_code = None
            mc = MergeController(repo_root=tmp)
            with pytest.raises(MergeGateError, match="No generated code"):
                await mc.attempt_merge(task)

    async def test_security_veto_blocks_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task = _approved_task(tmp)
            task.reviews[2] = CriticReview(
                critic_role="security",
                decision=ReviewDecision.REJECT,
                production_ready=False,
                fatal_flaw="RCE vulnerability",
            )
            mc = MergeController(repo_root=tmp)
            with pytest.raises(MergeGateError, match="Security critic"):
                await mc.attempt_merge(task)

    async def test_compile_failure_blocks_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task = _approved_task(tmp)
            task.compiler_output = CompilerOutput(success=False, stderr="SyntaxError")
            mc = MergeController(repo_root=tmp)
            with pytest.raises(MergeGateError, match="Compilation failed"):
                await mc.attempt_merge(task)

    async def test_test_failure_blocks_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task = _approved_task(tmp)
            task.test_output = TestOutput(success=False, failed=2)
            mc = MergeController(repo_root=tmp)
            with pytest.raises(MergeGateError, match="Tests failed"):
                await mc.attempt_merge(task)

    async def test_numeric_failure_blocks_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task = _approved_task(tmp)
            task.test_output = TestOutput(
                success=True,
                passed=5,
                numeric_passed=False,
            )
            mc = MergeController(repo_root=tmp)
            with pytest.raises(MergeGateError, match="Numeric"):
                await mc.attempt_merge(task)

    async def test_hash_mismatch_blocks_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task = _approved_task(tmp)
            task.generated_code_hash = "deadbeef" * 8  # wrong hash
            mc = MergeController(repo_root=tmp)
            with pytest.raises(MergeGateError, match="hash mismatch"):
                await mc.attempt_merge(task)

    async def test_path_traversal_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mc = MergeController(repo_root=tmp)
            with pytest.raises(MergeGateError, match="traversal|absolute"):
                mc._safe_dest("../../etc/passwd")

    async def test_absolute_path_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mc = MergeController(repo_root=tmp)
            with pytest.raises(MergeGateError, match="traversal|absolute"):
                mc._safe_dest("/etc/passwd")

    async def test_valid_relative_path_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mc = MergeController(repo_root=tmp)
            dest = mc._safe_dest("output/module.py")
            assert str(dest).startswith(tmp)
            assert "module.py" in str(dest)
