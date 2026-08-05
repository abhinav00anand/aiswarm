"""
Host-2 Fast-Mode Executive & Capability Manager.

Orchestrates Fast-Mode task execution, manages dynamic capabilities (models, tools, workers),
and builds structured EscalationPackets to promote tasks to Boss when complexity or risk increases.
"""

from __future__ import annotations

import asyncio
from typing import Any

from aiswarm.runtime.capability_registry import CapabilityRegistry
from aiswarm.schemas.capabilities import CapabilityHandle, CapabilityRequest, EscalationPacket
from aiswarm.security.governor import EngineeringGovernor

from aiswarm.utils.compat_log import get_logger

logger = get_logger(__name__)


class Host2CapabilityManager:
    """
    Host-2 Executive Manager for Fast-Mode Execution.
    Decomposes fast-path tasks, invokes tools/workers via CapabilityRegistry,
    and escalates to Boss if execution thresholds are crossed.
    """

    def __init__(
        self,
        capability_registry: CapabilityRegistry | None = None,
        governor: EngineeringGovernor | None = None,
        max_retries: int = 2,
    ) -> None:
        self.capability_registry = capability_registry or CapabilityRegistry()
        self.governor = governor or EngineeringGovernor()
        self.max_retries = max_retries

    async def execute_fast_task(self, task_payload: dict[str, Any]) -> dict[str, Any]:
        """
        Execute a fast-mode task using optimal capabilities.
        Returns task completion dictionary or escalates to Boss via EscalationPacket.
        """
        task_id = task_payload.get("task_id", "fast_task")
        code = task_payload.get("code", "")
        test_command = task_payload.get("test_command", "pytest")
        completed_steps = []

        logger.info("host2.execute_start", task_id=task_id)

        # Check governance spawn permissions
        self.governor.check_capability_spawn_policy("python_exec", "host2")

        # Step 1: Run code/test capability in sandbox
        retry_count = 0
        while retry_count <= self.max_retries:
            logger.info("host2.step_execute", task_id=task_id, attempt=retry_count + 1)
            
            # Invoke pytest capability via registry
            request = CapabilityRequest(
                capability_name="pytest",
                requester_role="host2",
                parameters={"path": "."},
            )
            handle: CapabilityHandle = await self.capability_registry.invoke(request)

            if handle.status == "SUCCESS":
                completed_steps.append(f"Execution passed on attempt {retry_count + 1}")
                logger.info("host2.execute_success", task_id=task_id)
                return {
                    "status": "COMPLETED",
                    "task_id": task_id,
                    "completed_steps": completed_steps,
                    "handle": handle.model_dump(),
                    "escalated": False,
                }

            retry_count += 1
            completed_steps.append(f"Attempt {retry_count} failed: {handle.output}")

        # Retries exhausted — promote task to Boss via EscalationPacket
        logger.warning("host2.retries_exhausted_escalating", task_id=task_id, retries=retry_count)
        escalation_packet = EscalationPacket(
            task_id=task_id,
            reason=f"Fast-mode execution failed after {retry_count} attempts.",
            completed_steps=completed_steps,
            failed_stage="EXECUTING_TESTS",
            remaining_risks=["Test failure in fast mode", "Requires deep reasoning / Boss deadlock resolution"],
            suggested_next_action="PROMOTE_TO_PRODUCTION_PIPELINE",
        )

        return {
            "status": "ESCALATED",
            "task_id": task_id,
            "escalation_packet": escalation_packet.model_dump(),
            "escalated": True,
        }
