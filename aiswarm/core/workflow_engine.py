"""
Workflow engine — executes the full task pipeline as a directed graph.

Each pipeline stage is a node. The engine drives a task from NEW to
MERGED (or a terminal failure state), respecting the state machine,
retry policy, and deadlock detector.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

from aiswarm.schemas.task import Task, TaskState
from aiswarm.core.state_machine import StateMachine
from aiswarm.core.retry_engine import RetryEngine, RetryPolicy, RetryExhausted

if TYPE_CHECKING:
    from aiswarm.core.orchestrator import Orchestrator

logger = structlog.get_logger(__name__)


class WorkflowEngine:
    """
    Drives a single task through all pipeline stages.

    Stage sequence:
      prompt → generate → precheck → review → compile → test → benchmark → merge
    """

    def __init__(self, orchestrator: "Orchestrator") -> None:
        self._orc = orchestrator
        self._retry = RetryEngine(RetryPolicy(max_attempts=5, base_delay=2.0))

    async def run(self, task: Task) -> Task:
        """Execute the full pipeline for a task and return the final task."""
        from datetime import datetime, timezone
        task.started_at = datetime.now(timezone.utc)

        logger.info("workflow.started", task_id=task.task_id, title=task.title)

        try:
            # Ensure Host-1 routing decision is attached
            from aiswarm.schemas.routing import ExecutionMode
            router = getattr(self._orc, "host1_router", None) or self._orc.get_agent("host1_router")
            metadata = getattr(task, "metadata", {}) or {}
            decision = metadata.get("route_decision")
            if decision is None and router is not None:
                decision = await router.route_task(task)
                if task.metadata is None:
                    task.metadata = {}
                task.metadata["route_decision"] = decision
            route = getattr(decision, "route", ExecutionMode.PRODUCTION) if decision else ExecutionMode.PRODUCTION

            if route == ExecutionMode.FAST:
                logger.info("workflow.route_fast", task_id=task.task_id)
                from aiswarm.agents.host2.manager import Host2CapabilityManager
                mgr = self._orc.get_agent("host2") or Host2CapabilityManager()
                fast_payload = {
                    "task_id": task.task_id,
                    "code": getattr(task, "generated_code", "") or "",
                    "target_file": task.target_files[0] if task.target_files else ".",
                    "language": getattr(task, "target_language", "python"),
                    "test_command": getattr(task, "test_command", None),
                }
                result = await mgr.execute_fast_task(fast_payload)
                if result.get("escalated"):
                    # Fast path escalated — fall through to full pipeline
                    logger.warning("workflow.fast_escalated_to_production", task_id=task.task_id)
                    route = ExecutionMode.PRODUCTION
                else:
                    # Execute compile & test validation before merge evaluation
                    await self._stage_compile(task)
                    await self._stage_test(task)

                    try:
                        merge_ctrl = self._orc.get_agent("merge_controller")
                        if not merge_ctrl:
                            from aiswarm.core.merge_controller import MergeController
                            boss = self._orc.get_agent("boss")
                            repo_root = getattr(boss, "_repo_root", ".") if boss else "."
                            merge_ctrl = MergeController(repo_root=repo_root)

                        # This will run gates and write files to disk
                        await merge_ctrl.attempt_merge(task)
                        return task
                    except Exception as merge_exc:
                        logger.warning("workflow.fast_quality_gate_failed", task_id=task.task_id, reason=str(merge_exc))
                        route = ExecutionMode.PRODUCTION



            # ── Stage 1: Plan & contextualize ──────────────────────────────
            await self._stage_plan(task)

            # ── Retry loop: Prompt → Generate → PreCheck → Review → Compile → Test → Bench ──
            while True:
                if task.retry_count >= task.max_retries:
                    task.transition(
                        TaskState.DEADLOCK,
                        reason=f"Max retries ({task.max_retries}) exceeded",
                        agent="workflow_engine",
                    )
                    break

                try:
                    # Stage 2: Prompt coder
                    await self._stage_prompt(task)
                    # Stage 3: Generate code
                    await self._stage_generate(task)
                    # Stage 4: Pre-check (syntax, basic sanity)
                    if not await self._stage_precheck(task):
                        task.retry_count += 1
                        self._retry.record_failure(task.task_id, "Pre-check failed")
                        await self._retry.wait(task.task_id)
                        continue
                    # Stage 5: Critic review
                    if not await self._stage_review(task):
                        task.retry_count += 1
                        self._retry.record_failure(task.task_id, "Critic review failed")
                        await self._retry.wait(task.task_id)
                        continue
                    # Stage 6: Compile
                    if not await self._stage_compile(task):
                        task.retry_count += 1
                        self._retry.record_failure(task.task_id, "Compilation failed")
                        await self._retry.wait(task.task_id)
                        continue
                    # Stage 7: Test
                    if not await self._stage_test(task):
                        task.retry_count += 1
                        self._retry.record_failure(task.task_id, "Testing failed")
                        await self._retry.wait(task.task_id)
                        continue
                    # Stage 8: Benchmark
                    if not await self._stage_benchmark(task):
                        task.retry_count += 1
                        self._retry.record_failure(task.task_id, "Benchmarking failed")
                        await self._retry.wait(task.task_id)
                        continue
                    # Stage 9: Merge
                    await self._stage_merge(task)
                    self._retry.mark_success(task.task_id)
                    break

                except RetryExhausted as exc:
                    logger.error("workflow.retry_exhausted", task_id=task.task_id, error=str(exc))
                    task.transition(
                        TaskState.DEADLOCK,
                        reason=str(exc),
                        agent="workflow_engine",
                    )
                    break

        except asyncio.CancelledError:
            task.transition(TaskState.CANCELLED, reason="Workflow cancelled", agent="workflow_engine")
            raise

        except Exception as exc:  # noqa: BLE001
            logger.error("workflow.unexpected_error", task_id=task.task_id, error=str(exc))
            task.transition(
                TaskState.REJECTED,
                reason=f"Unexpected error: {exc}",
                agent="workflow_engine",
            )

        from datetime import datetime, timezone
        task.completed_at = datetime.now(timezone.utc)
        logger.info(
            "workflow.finished",
            task_id=task.task_id,
            final_state=task.state.value,
            retries=task.retry_count,
        )
        return task

    # ── Stage implementations ─────────────────────────────────────────────────

    async def _stage_plan(self, task: Task) -> None:
        planner = self._orc.get_agent("planner")
        ctx_selector = self._orc.get_agent("context_selector")
        if planner:
            await planner.run(task)
        if ctx_selector:
            await ctx_selector.run(task)

    async def _stage_prompt(self, task: Task) -> None:
        if task.state != TaskState.PROMPTED:
            StateMachine.transition(task, TaskState.PROMPTED, "Preparing prompt", agent="workflow_engine")


    async def _stage_generate(self, task: Task) -> None:
        coder = self._orc.get_agent("coder")
        if coder:
            await coder.run(task)
        StateMachine.transition(task, TaskState.GENERATED, "Code generated", agent="coder")

    async def _stage_precheck(self, task: Task) -> bool:
        precheck = self._orc.get_agent("precheck")
        if precheck:
            passed = await precheck.run(task)
            StateMachine.transition(task, TaskState.PRECHECKED, "Pre-check done", agent="precheck")
            if not passed:
                StateMachine.transition(task, TaskState.PROMPTED, "Pre-check failed, re-prompting", agent="precheck")
                return False
        else:
            StateMachine.transition(task, TaskState.PRECHECKED, "Pre-check skipped", agent="workflow_engine")
        return True

    async def _stage_review(self, task: Task) -> bool:
        critics = [
            self._orc.get_agent("critic_architecture"),
            self._orc.get_agent("critic_performance"),
            self._orc.get_agent("critic_security"),
        ]
        tasks_ = [c.run(task) for c in critics if c]
        await asyncio.gather(*tasks_)
        StateMachine.transition(task, TaskState.REVIEWED, "Critics reviewed", agent="workflow_engine")
        if not task.is_approved() or task.is_security_vetoed():
            reasons = task.rejection_reasons()
            logger.warning("workflow.review_rejected", task_id=task.task_id, reasons=reasons)
            StateMachine.transition(
                task, TaskState.PROMPTED,
                reason="Critics rejected, re-prompting",
                agent="workflow_engine",
            )
            return False
        return True

    async def _stage_compile(self, task: Task) -> bool:
        compiler = self._orc.get_agent("compiler")
        if compiler:
            await compiler.run(task)
        StateMachine.transition(task, TaskState.COMPILED, "Compilation done", agent="compiler")
        if task.compiler_output and not task.compiler_output.success:
            StateMachine.transition(task, TaskState.PROMPTED, "Compile failed", agent="compiler")
            return False
        return True

    async def _stage_test(self, task: Task) -> bool:
        tester = self._orc.get_agent("tester")
        if tester:
            await tester.run(task)
        StateMachine.transition(task, TaskState.TESTED, "Tests done", agent="tester")
        if task.test_output and not task.test_output.success:
            StateMachine.transition(task, TaskState.PROMPTED, "Tests failed", agent="tester")
            return False
        return True

    async def _stage_benchmark(self, task: Task) -> bool:
        bencher = self._orc.get_agent("benchmark")
        if bencher:
            await bencher.run(task)
        StateMachine.transition(task, TaskState.BENCHMARKED, "Benchmark done", agent="benchmark")
        if task.benchmark_output and not task.benchmark_output.passed:
            StateMachine.transition(task, TaskState.PROMPTED, "Benchmark failed", agent="benchmark")
            return False
        return True

    async def _stage_merge(self, task: Task) -> None:
        merge_ctrl = self._orc.get_agent("merge_controller")
        if merge_ctrl:
            await merge_ctrl.run(task)
        else:
            # Fallback: direct merge
            from aiswarm.core.merge_controller import MergeController
            mc = MergeController()
            await mc.attempt_merge(task)
