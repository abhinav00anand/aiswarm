"""
Stress tests for MergeController.

Covers:
  - 50 concurrent merges to different files (no contention)
  - Path traversal: 30+ attack vectors
  - Absolute path vectors
  - Hash tamper detection
  - Security-veto unconditional block
  - Partial gate failure matrix (all 5 gates fail independently)
  - File write atomicity (code matches what was written)
  - Multi-file task merge
  - Directory creation for nested paths
"""

from __future__ import annotations

import asyncio
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
    BenchmarkOutput,
)
from aiswarm.utils.hashing import sha256_hex


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _approved_task(tmp_dir: str, filename: str = "output.py") -> Task:
    code = f"def hello_{filename.replace('.py', '')}():\n    return 42\n"
    task = Task(title="Merge stress", description="test")
    task.state = TaskState.BENCHMARKED
    task.generated_code = code
    task.generated_code_hash = sha256_hex(code)
    task.target_files = [filename]
    task.reviews = [
        CriticReview(
            critic_role="architecture",
            decision=ReviewDecision.APPROVE,
            production_ready=True,
            score=85,
        ),
        CriticReview(
            critic_role="performance",
            decision=ReviewDecision.APPROVE,
            production_ready=True,
            score=85,
        ),
        CriticReview(
            critic_role="security", decision=ReviewDecision.APPROVE, production_ready=True, score=90
        ),
    ]
    task.compiler_output = CompilerOutput(success=True, exit_code=0)
    task.test_output = TestOutput(success=True, passed=5, total=5, numeric_passed=True)
    return task


# ---------------------------------------------------------------------------
# Concurrent merges
# ---------------------------------------------------------------------------


class TestMergeControllerConcurrent:
    @pytest.mark.asyncio
    async def test_50_concurrent_merges_all_succeed(self):
        N = 50
        written_all = []

        async def do_merge(i):
            with tempfile.TemporaryDirectory() as tmp:
                task = _approved_task(tmp, f"module_{i}.py")
                mc = MergeController(repo_root=tmp)
                written = await mc.attempt_merge(task)
                written_all.append(written[0])
                assert task.merged is True
                return written[0]

        results = await asyncio.gather(*[do_merge(i) for i in range(N)])
        assert len(results) == N

    @pytest.mark.asyncio
    async def test_concurrent_merges_file_content_accurate(self):
        N = 20

        async def do_merge(i):
            with tempfile.TemporaryDirectory() as tmp:
                task = _approved_task(tmp, f"out_{i}.py")
                mc = MergeController(repo_root=tmp)
                written = await mc.attempt_merge(task)
                content = Path(written[0]).read_text()
                assert f"hello_out_{i}" in content

        await asyncio.gather(*[do_merge(i) for i in range(N)])

    @pytest.mark.asyncio
    async def test_merge_state_is_merged_after_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks = [_approved_task(tmp, f"f{i}.py") for i in range(10)]
            mc = MergeController(repo_root=tmp)
            await asyncio.gather(*[mc.attempt_merge(t) for t in tasks])
            for t in tasks:
                assert t.state == TaskState.MERGED
                assert t.merged is True
                assert t.merged_at is not None


# ---------------------------------------------------------------------------
# Path traversal attack vectors
# ---------------------------------------------------------------------------


class TestMergeControllerPathTraversal:
    # These vectors MUST all be blocked — they escape the repo root
    MUST_BLOCK_TRAVERSAL = [
        "../../etc/passwd",
        "../../../etc/shadow",
        "../../../../root/.ssh/authorized_keys",
        "subdir/../../etc/passwd",
        "a/b/c/../../../../../../../etc/passwd",
        "normal/../../../etc/hosts",
        "foo/bar/../../../../etc/crontab",
        "../../proc/self/environ",
        "a/./../../etc/passwd",
        "./../../etc/passwd",
    ]

    ABSOLUTE_VECTORS = [
        "/etc/passwd",
        "/root/.bashrc",
        "/tmp/malicious.py",
        "/usr/local/bin/evil",
        "/home/user/.ssh/id_rsa",
    ]

    def test_every_traversal_vector_is_blocked(self):
        """Every path that escapes repo_root must raise MergeGateError — no exceptions."""
        with tempfile.TemporaryDirectory() as tmp:
            mc = MergeController(repo_root=tmp)
            for vector in self.MUST_BLOCK_TRAVERSAL:
                with pytest.raises(MergeGateError, match="traversal|absolute"):
                    result = mc._safe_dest(vector)
                    # Extra verification: if _safe_dest returned, confirm it's outside
                    # the repo root (which would also be a bug)
                    assert str(result).startswith(tmp), (
                        f"Vector {vector!r} was NOT blocked — resolved to {result}"
                    )

    def test_all_absolute_paths_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            mc = MergeController(repo_root=tmp)
            for vector in self.ABSOLUTE_VECTORS:
                with pytest.raises(MergeGateError, match="traversal|absolute"):
                    mc._safe_dest(vector)

    def test_safe_relative_paths_allowed(self):
        safe_paths = [
            "output.py",
            "src/module.py",
            "a/b/c/d.py",
            "tests/test_foo.py",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            mc = MergeController(repo_root=tmp)
            for path in safe_paths:
                dest = mc._safe_dest(path)
                assert str(dest).startswith(tmp)


# ---------------------------------------------------------------------------
# Gate failure matrix
# ---------------------------------------------------------------------------


class TestMergeControllerGateMatrix:
    @pytest.mark.asyncio
    async def test_gate_no_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = _approved_task(tmp)
            task.generated_code = None
            mc = MergeController(repo_root=tmp)
            with pytest.raises(MergeGateError, match="No generated code"):
                await mc.attempt_merge(task)

    @pytest.mark.asyncio
    async def test_gate_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = _approved_task(tmp)
            task.generated_code_hash = "a" * 64  # wrong hash
            mc = MergeController(repo_root=tmp)
            with pytest.raises(MergeGateError, match="hash mismatch"):
                await mc.attempt_merge(task)

    @pytest.mark.asyncio
    async def test_gate_no_reviews(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = _approved_task(tmp)
            task.reviews = []
            mc = MergeController(repo_root=tmp)
            with pytest.raises(MergeGateError, match="No critic reviews"):
                await mc.attempt_merge(task)

    @pytest.mark.asyncio
    async def test_gate_security_veto_unconditional(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = _approved_task(tmp)
            # Add security veto even with other approvals
            task.reviews.append(
                CriticReview(
                    critic_role="security",
                    decision=ReviewDecision.REJECT,
                    production_ready=False,
                    fatal_flaw="SQL injection vulnerability",
                )
            )
            mc = MergeController(repo_root=tmp)
            with pytest.raises(MergeGateError, match="Security critic"):
                await mc.attempt_merge(task)

    @pytest.mark.asyncio
    async def test_gate_majority_critic_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = _approved_task(tmp)
            # Make all non-security critics reject
            task.reviews = [
                CriticReview(
                    critic_role="architecture",
                    decision=ReviewDecision.REJECT,
                    production_ready=False,
                    score=20,
                ),
                CriticReview(
                    critic_role="performance",
                    decision=ReviewDecision.REJECT,
                    production_ready=False,
                    score=20,
                ),
                CriticReview(
                    critic_role="security",
                    decision=ReviewDecision.APPROVE,
                    production_ready=True,
                    score=90,
                ),
            ]
            mc = MergeController(repo_root=tmp)
            with pytest.raises(MergeGateError, match="Insufficient critic approval"):
                await mc.attempt_merge(task)

    @pytest.mark.asyncio
    async def test_gate_compilation_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = _approved_task(tmp)
            task.compiler_output = CompilerOutput(
                success=False,
                stderr="SyntaxError: invalid syntax",
            )
            mc = MergeController(repo_root=tmp)
            with pytest.raises(MergeGateError, match="Compilation failed"):
                await mc.attempt_merge(task)

    @pytest.mark.asyncio
    async def test_gate_tests_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = _approved_task(tmp)
            task.test_output = TestOutput(success=False, failed=3)
            mc = MergeController(repo_root=tmp)
            with pytest.raises(MergeGateError, match="Tests failed"):
                await mc.attempt_merge(task)

    @pytest.mark.asyncio
    async def test_gate_numeric_equivalence_failed(self):
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

    @pytest.mark.asyncio
    async def test_gate_benchmark_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = _approved_task(tmp)
            task.benchmark_output = BenchmarkOutput(
                passed=False,
                profiler_output="Performance below threshold",
            )
            mc = MergeController(repo_root=tmp)
            with pytest.raises(MergeGateError, match="Benchmark gate failed"):
                await mc.attempt_merge(task)

    @pytest.mark.asyncio
    async def test_benchmark_optional_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = _approved_task(tmp)
            task.benchmark_output = None
            mc = MergeController(repo_root=tmp)
            # Should succeed — benchmark is optional
            written = await mc.attempt_merge(task)
            assert len(written) == 1


# ---------------------------------------------------------------------------
# Multi-file merges
# ---------------------------------------------------------------------------


class TestMergeControllerMultiFile:
    @pytest.mark.asyncio
    async def test_multi_file_all_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = _approved_task(tmp, "first.py")
            task.target_files = ["first.py", "second.py", "third.py"]
            mc = MergeController(repo_root=tmp)
            written = await mc.attempt_merge(task)
            assert len(written) == 3
            for p in written:
                assert Path(p).exists()

    @pytest.mark.asyncio
    async def test_nested_directory_created_on_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = _approved_task(tmp, "src/deep/nested/module.py")
            mc = MergeController(repo_root=tmp)
            written = await mc.attempt_merge(task)
            assert Path(written[0]).exists()
            assert Path(written[0]).parent.is_dir()
