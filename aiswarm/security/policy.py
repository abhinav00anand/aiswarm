from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from aiswarm.utils.compat_log import get_logger

logger = get_logger(__name__)


@dataclass
class PolicyRule:
    name: str
    description: str
    applies_to_roles: list[str]
    condition_fn: Callable[[str, str, dict[str, Any]], bool]
    action: str  # ALLOW, DENY, REQUIRE_HITL


@dataclass
class PolicyDecision:
    allowed: bool
    action: str
    rule_name: str
    reason: str


class PolicyEngine:
    def __init__(self) -> None:
        self.rules: list[PolicyRule] = [
            PolicyRule(
                name="allow_system_roles",
                description="Allow all capabilities for boss and system roles",
                applies_to_roles=["boss", "system"],
                condition_fn=lambda cap, role, ctx: True,
                action="ALLOW",
            ),
            PolicyRule(
                name="deny_sensitive_paths",
                description="Deny access to /etc, /sys, /proc paths in sandbox",
                applies_to_roles=["*"],
                condition_fn=lambda cap, role, ctx: cap == "file_access"
                and any(path in ctx.get("target_path", "") for path in ("/etc", "/sys", "/proc")),
                action="DENY",
            ),
            PolicyRule(
                name="deny_raw_shell",
                description="DENY raw_shell_execution for worker/host2 roles",
                applies_to_roles=["worker", "host2"],
                condition_fn=lambda cap, role, ctx: cap == "raw_shell_execution",
                action="DENY",
            ),
            PolicyRule(
                name="require_hitl_critical_actions",
                description="REQUIRE_HITL for deploy_production, db_drop_table, export_secrets capabilities",
                applies_to_roles=["*"],
                condition_fn=lambda cap, role, ctx: cap
                in ("deploy_production", "db_drop_table", "export_secrets")
                and role not in ("system", "boss"),
                action="REQUIRE_HITL",
            ),
        ]

    def evaluate(self, capability: str, role: str, context: dict[str, Any]) -> PolicyDecision:
        for rule in self.rules:
            if "*" in rule.applies_to_roles or role in rule.applies_to_roles:
                if rule.condition_fn(capability, role, context):
                    allowed = rule.action == "ALLOW"
                    decision = PolicyDecision(
                        allowed=allowed,
                        action=rule.action,
                        rule_name=rule.name,
                        reason=f"Matched rule {rule.name}",
                    )
                    logger.info(
                        "policy.evaluated",
                        capability=capability,
                        role=role,
                        action=rule.action,
                        rule_name=rule.name,
                        allowed=allowed,
                    )
                    return decision

        logger.info(
            "policy.default",
            capability=capability,
            role=role,
            action="DENY",
            rule_name="default_deny",
            allowed=False,
        )
        return PolicyDecision(
            allowed=False,
            action="DENY",
            rule_name="default_deny",
            reason="No matching policy rule, default deny applied",
        )


_ENGINE = PolicyEngine()


def get_policy_engine() -> PolicyEngine:
    return _ENGINE
