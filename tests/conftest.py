"""
Pytest configuration and shared fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: mark test as requiring real API access")
    config.addinivalue_line("markers", "slow: mark test as slow")


@pytest.fixture(autouse=True)
def _load_env() -> None:
    """Auto-load .env file for all tests."""
    env_file = Path(".env")
    if env_file.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_file, override=False)  # Don't override existing env
        except ImportError:
            pass


@pytest.fixture
def sample_task():
    """A minimal valid Task for testing."""
    from aiswarm.schemas.task import Task

    return Task(
        title="Sample task",
        description="A simple test task",
        target_files=["sample.py"],
        target_language="python",
    )


@pytest.fixture
def approved_task(sample_task, tmp_path):
    """A Task pre-loaded with passing review, compile, and test results."""
    from aiswarm.schemas.task import (
        TaskState,
        CriticReview,
        ReviewDecision,
        CompilerOutput,
        TestOutput,
    )
    from aiswarm.utils.hashing import sha256_hex

    code = 'def hello() -> str:\n    """Return greeting."""\n    return \'hello\'\n'
    sample_task.state = TaskState.BENCHMARKED
    sample_task.generated_code = code
    sample_task.generated_code_hash = sha256_hex(code)
    sample_task.target_files = [str(tmp_path / "hello.py")]
    sample_task.reviews = [
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
    sample_task.compiler_output = CompilerOutput(success=True, exit_code=0)
    sample_task.test_output = TestOutput(success=True, passed=3, total=3, numeric_passed=True)
    return sample_task
