"""Force."""

from __future__ import annotations

from datetime import datetime, timezone

import structlog

from aiswarm.schemas.task import Task, TaskState
from aiswarm.core.state_machine import StateMachine

logger = structlog.get_logger(__name__)

class ForceMergeOperator:
    """
    Operator-level override that bypasses the normal 5-gate merge controller.

    Usage::

        op = ForceMergeOperator()
        await op.force_merge(task, reason="Performance critic wrong about FFT algorithm")
    """

    async def force_merge(
        self,
        task: Task,
        reason: str,
        operator: str = "unknown",
    ) -> None:
        """
        Force a task into MERGED state, bypassing all gates.

        Args:
            task: The Task to force-merge.
            reason: Mandatory explanation for why gates are being bypassed.
            operator: Identity of the operator (for audit trail).

        Raises:
            ValueError: If reason is empty (reason is mandatory).
        """
        if not reason or len(reason.strip()) < 10:
            raise ValueError(
                "Force-merge requires a non-empty reason (at least 10 characters). "
                "Document explicitly why quality gates are being bypassed."
            )

        if task.state == TaskState.MERGED:
            logger.warning(
                "force_merge.already_merged",
                task_id=task.task_id,
            )
            return

        # Record to immutable audit ledger
        try:
            from aiswarm.security.audit import get_audit_ledger
            get_audit_ledger().record_event(
                event_type="FORCE_MERGE_EXECUTED",
                agent=f"operator:{operator}",
                details={
                    "task_id": task.task_id,
                    "operator": operator,
                    "reason": reason,
                    "previous_state": task.state.value,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("force_merge.audit_ledger_failed", error=str(exc))

        task.boss_override = f"[FORCE-MERGE by {operator}] {reason}"
        task.merged = True
        task.merged_at = datetime.now(timezone.utc)
        task.merged_by = f"force_merge:{operator}"
        task.completed_at = datetime.now(timezone.utc)
        task.metadata["force_merged"] = True
        task.metadata["force_merge_reason"] = reason
        task.metadata["force_merge_operator"] = operator
        task.metadata["force_merge_at"] = datetime.now(timezone.utc).isoformat()

        # Force-merge bypasses the FSM transition graph — this is intentional.
        # It is a break-glass mechanism that must work from ANY state.
        # We directly call task.transition() which records the audit trail
        # without going through StateMachine.can_transition() validation.
        task.transition(
            TaskState.MERGED,
            reason=f"[FORCE-MERGE] {reason}",
            agent=f"force_merge_operator:{operator}",
            evidence={
                "bypassed_gates": True,
                "operator": operator,
                "reason": reason,
            },
        )

        # Emit a high-severity warning so this always appears in logs
        logger.warning(
            "force_merge.executed",
            task_id=task.task_id,
            operator=operator,
            reason=reason,
            state_before=task.state_history[-2].from_state.value
            if len(task.state_history) >= 2
            else "unknown",
        )
