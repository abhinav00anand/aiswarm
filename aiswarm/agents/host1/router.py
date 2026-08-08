"""Host."""

from __future__ import annotations

import re
from typing import Any

from aiswarm.utils.compat_log import get_logger

logger = get_logger(__name__)

from aiswarm.schemas.routing import ExecutionMode, RiskLevel, RouteDecision

# Sensitive keywords that force PRODUCTION or HYBRID routing
_SECURITY_SURFACES = [
    r"\bauth\b",
    r"\blogin\b",
    r"\bpassword\b",
    r"\bsecret\b",
    r"\bcredential\b",
    r"\bpayment\b",
    r"\btoken\b",
    r"\bdatabase\b",
    r"\bmigration\b",
    r"\brelease\b",
    r"\bdeploy\b",
    r"\bpermission\b",
    r"\bsandbox\b",
]

_SECURITY_REGEX = re.compile("|".join(_SECURITY_SURFACES), re.IGNORECASE)

class Host1Router:
    """
    Host-1 Global Traffic Controller and Policy Evaluator.
    Determines execution mode, confidence, estimated costs, and required capabilities.
    """

    def __init__(self, confidence_threshold: float = 0.70) -> None:
        self.confidence_threshold = confidence_threshold

    def evaluate_task(self, task_payload: dict[str, Any]) -> RouteDecision:
        """
        Evaluate a task description and context to generate a structured RouteDecision.
        """
        task_id = task_payload.get("task_id", "unknown_task")
        title = task_payload.get("title", "")
        description = task_payload.get("description", "")
        target_files = task_payload.get("target_files", [])
        budget_tier = task_payload.get("budget_tier", "normal")
        full_text = f"{title} {description}".strip()

        # Step 1: Detect security sensitivity
        security_match = _SECURITY_REGEX.search(full_text)
        is_security_sensitive = bool(security_match)

        # Step 2: Determine blast radius
        file_count = len(target_files)
        is_large_scope = file_count > 3 or "all" in target_files

        # Step 3: Classify Risk Level
        if is_security_sensitive:
            risk_level = RiskLevel.HIGH
        elif is_large_scope:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW

        # Step 4: Route Decision Policy Logic
        if is_security_sensitive:
            matched_word = security_match.group(0) if security_match else "security"
            route = ExecutionMode.PRODUCTION
            confidence = 0.95
            reason = (
                f"Routed to PRODUCTION due to security-sensitive surface detected ('{matched_word}'). "
                f"Requires full Boss administration, critic reviews, and compiler validation."
            )
            estimated_cost = 0.15
            estimated_runtime = 120.0
            capabilities = ["boss_pipeline", "critic_board", "compiler_validation"]

        elif is_large_scope:
            route = ExecutionMode.HYBRID
            confidence = 0.85
            reason = (
                f"Routed to HYBRID: Multi-file impact detected ({file_count} target files). "
                f"Boss coordinates architecture while Host-2 executes isolated sub-tasks."
            )
            estimated_cost = 0.08
            estimated_runtime = 60.0
            capabilities = ["boss_pipeline", "host2_capability_manager", "sandbox"]

        else:
            route = ExecutionMode.FAST
            confidence = 0.90
            reason = (
                "Routed to FAST: Bounded, low-risk single-file/utility task. "
                "Managed directly by Host-2 Capability Manager for rapid, low-cost execution."
            )
            estimated_cost = 0.01
            estimated_runtime = 15.0
            capabilities = ["python", "pytest", "ruff", "sandbox"]

        decision = RouteDecision(
            route=route,
            confidence=confidence,
            reason=reason,
            risk_level=risk_level,
            estimated_cost_usd=estimated_cost,
            estimated_runtime_seconds=estimated_runtime,
            required_capabilities=capabilities,
            escalation_policy="ESCALATE_TO_BOSS_IF_RETRYS_EXCEED_2_OR_CONTEXT_EXPLODES",
            metadata={"task_id": task_id, "file_count": file_count, "budget_tier": budget_tier},
        )

        logger.info(
            "host1.route_decision",
            task_id=task_id,
            route=decision.route.value,
            confidence=decision.confidence,
            risk_level=decision.risk_level.value,
        )

        return decision

    async def route_task(self, task: Any) -> RouteDecision:
        """
        Convenience adapter method taking a Task object or dict, generating a RouteDecision.
        """
        if hasattr(task, "task_id"):
            payload = {
                "task_id": getattr(task, "task_id", "unknown"),
                "title": getattr(task, "title", ""),
                "description": getattr(task, "description", ""),
                "target_files": getattr(task, "target_files", []),
                "budget_tier": getattr(task, "budget_tier", "normal"),
            }
        elif isinstance(task, dict):
            payload = task
        else:
            payload = {"title": str(task)}

        return self.evaluate_task(payload)
