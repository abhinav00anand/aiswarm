"""
Integration test — end-to-end AISwarm pipeline.

Tests the full Boss → Manager → Planner → Coder → Critics → Merge pipeline.
Uses whatever LLM provider is configured via environment variables.

Provider priority (first available wins):
  1. NOVITA_API_KEY / NOVITA_TOKEN
  2. OPENAI_API_KEY
  3. ANTHROPIC_API_KEY
  4. DEEPSEEK_API_KEY

If none are configured, the test is skipped.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from aiswarm.schemas.task import Task, TaskState, TaskPriority


def _any_llm_configured() -> bool:
    """Return True if at least one LLM provider API key is set."""
    return any(
        os.getenv(k)
        for k in (
            "NOVITA_API_KEY", "NOVITA_TOKEN",
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
            "DEEPSEEK_API_KEY", "GOOGLE_API_KEY",
        )
    )


@pytest.mark.integration
@pytest.mark.asyncio
class TestFullPipeline:
    """Tests the full Boss → Manager → Coder → Critics → Merge pipeline."""

    def setup_method(self) -> None:
        if not _any_llm_configured():
            pytest.skip(
                "No LLM provider API key found. Set one of: "
                "NOVITA_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, DEEPSEEK_API_KEY. "
                "Skipping pipeline integration tests."
            )

    async def test_simple_function_generation(self) -> None:
        """
        Submit a simple task (write a Python add function) and verify
        the pipeline produces code that compiles and passes critics.
        """
        from aiswarm.bootstrap.startup import build_orchestrator

        with tempfile.TemporaryDirectory() as tmp:
            orc, lifecycle = build_orchestrator(repo_root=tmp)
            await lifecycle.startup()

            try:
                task = Task(
                    title="Write a Python add function",
                    description=(
                        "Write a production-grade Python module with a single function: "
                        "`add(a: int, b: int) -> int`. "
                        "The function must have a docstring, type hints, and return a + b. "
                        "No imports needed. No placeholders."
                    ),
                    target_files=["output/add.py"],
                    target_language="python",
                    priority=TaskPriority.HIGH,
                    acceptance_criteria=[
                        "Function signature: add(a: int, b: int) -> int",
                        "Must have a docstring",
                        "Must return a + b",
                        "Must have type annotations",
                    ],
                    max_retries=3,
                )

                submitted = await orc.submit_task(task)

                # Wait up to 180 seconds for completion
                loop = asyncio.get_event_loop()
                deadline = loop.time() + 180
                while loop.time() < deadline:
                    t = await orc.get_task(submitted.task_id)
                    if t and t.state in (
                        TaskState.MERGED, TaskState.REJECTED,
                        TaskState.DEADLOCK, TaskState.CANCELLED,
                    ):
                        break
                    await asyncio.sleep(3)

                final = await orc.get_task(submitted.task_id)
                assert final is not None, "Task not found after submission"

                # Code should have been generated
                assert final.generated_code is not None, "No code was generated"
                assert "def add" in final.generated_code, (
                    "Function 'add' not found in generated code"
                )

                # Reviews should exist
                assert len(final.reviews) > 0, "No critic reviews recorded"

                print(f"\n[Pipeline Test] Final state: {final.state.value}")
                print(f"Retries: {final.retry_count}")
                print(f"Tokens:  {final.total_tokens_used:,}")
                for r in final.reviews:
                    print(f"  Critic [{r.critic_role}]: {r.decision.value} (score={r.score})")

            finally:
                await lifecycle.shutdown()
