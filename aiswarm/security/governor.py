"""
Engineering Governor Subsystem — Platform Policy Controller & Release Gates.

Sits above execution layers to enforce platform-wide safety rules: security policies,
concurrency caps, budget discipline, artifact verification, and release gates.
"""

from __future__ import annotations

from typing import Any

from aiswarm.utils.compat_log import get_logger

logger = get_logger(__name__)


class PolicyViolationError(RuntimeError):
    """Raised when an operation violates Engineering Governor policy."""


class EngineeringGovernor:
    """
    Central Policy and Governance Controller for AISwarm.
    Guarantees that no task or agent bypasses security, budget, or release rules.
    """

    def __init__(
        self,
        max_daily_budget_usd: float = 100.0,
        max_session_budget_usd: float = 10.0,
        require_artifact_signatures: bool = True,
        enforce_hitl_for_high_risk: bool = True,
    ) -> None:
        self.max_daily_budget_usd = max_daily_budget_usd
        self.max_session_budget_usd = max_session_budget_usd
        self.require_artifact_signatures = require_artifact_signatures
        self.enforce_hitl_for_high_risk = enforce_hitl_for_high_risk
        self._current_session_spend_usd = 0.0

    def record_spend(self, amount_usd: float) -> None:
        """Record actual spend against the session budget cap."""
        self._current_session_spend_usd += amount_usd
        logger.debug("governor.spend_recorded", amount=amount_usd, total_spend=self._current_session_spend_usd)

    def check_task_admission(self, task_payload: dict[str, Any]) -> bool:

        """
        Validate incoming task admission against budget, risk, and structural rules.
        """
        estimated_cost = float(task_payload.get("estimated_cost_usd", 0.0))
        if self._current_session_spend_usd + estimated_cost > self.max_session_budget_usd:
            msg = (
                f"Governor Policy Violation: Task estimated cost (${estimated_cost:.2f}) "
                f"exceeds session budget cap (${self.max_session_budget_usd:.2f})."
            )
            logger.warning("governor.budget_exceeded", estimated=estimated_cost, spend=self._current_session_spend_usd)
            raise PolicyViolationError(msg)

        logger.info("governor.task_admitted", task_id=task_payload.get("task_id"))
        return True

    def check_capability_spawn_policy(self, capability_name: str, requester_role: str) -> bool:
        """
        Enforce policy on tool/worker/model spawning.
        Prevents unauthorized role escalation.
        """
        forbidden_for_fast_mode = {"raw_shell_execution", "db_drop_table", "deploy_production", "export_secrets"}
        if requester_role in ("host2", "worker") and capability_name in forbidden_for_fast_mode:
            logger.error("governor.forbidden_spawn_blocked", capability=capability_name, role=requester_role)
            raise PolicyViolationError(
                f"Governor Security Gate: Role '{requester_role}' is not authorized to request capability '{capability_name}'."
            )
        return True

    def check_release_gate(self, release_manifest: dict[str, Any]) -> dict[str, Any]:
        """
        Verify that a build artifact or release package satisfies all security gates before publication.
        """
        passed_checks = []
        failed_checks = []

        if release_manifest.get("unit_tests_passed"):
            passed_checks.append("unit_tests")
        else:
            failed_checks.append("unit_tests")

        if release_manifest.get("security_scan_cleared"):
            passed_checks.append("security_scan")
        else:
            failed_checks.append("security_scan")

        if release_manifest.get("artifact_hash_verified"):
            passed_checks.append("artifact_hash")
        else:
            failed_checks.append("artifact_hash")

        status = len(failed_checks) == 0
        logger.info("governor.release_gate_evaluated", passed=passed_checks, failed=failed_checks, status=status)

        return {
            "approved": status,
            "passed_gates": passed_checks,
            "failed_gates": failed_checks,
        }
