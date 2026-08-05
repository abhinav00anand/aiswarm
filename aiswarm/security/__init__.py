"""Security subsystem — authentication, sandboxing, governance, redaction, audit, and policy."""
from aiswarm.security.auth import APIKeyValidator, SecurityAuthError, Role
from aiswarm.security.sandbox import ExecutionSandbox, SandboxViolationError, scrub_secrets
from aiswarm.security.governor import EngineeringGovernor, PolicyViolationError
from aiswarm.security.redaction import SecretRedactor, scrub, scrub_dict
from aiswarm.security.audit import AuditLedger, AuditEvent, get_audit_ledger
from aiswarm.security.policy import PolicyEngine, PolicyDecision, get_policy_engine

__all__ = [
    "APIKeyValidator", "SecurityAuthError", "Role",
    "ExecutionSandbox", "SandboxViolationError", "scrub_secrets",
    "EngineeringGovernor", "PolicyViolationError",
    "SecretRedactor", "scrub", "scrub_dict",
    "AuditLedger", "AuditEvent", "get_audit_ledger",
    "PolicyEngine", "PolicyDecision", "get_policy_engine",
]
