"""
Capability Schemas — Requests, Handles, Manifests, and Escalation Packets.
"""

from __future__ import annotations

import uuid
from typing import Any
from pydantic import BaseModel, Field


class CapabilityRequest(BaseModel):
    """Request sent by Host-2 or Boss to request a specific capability/tool."""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    capability_name: str = Field(..., description="Name of the requested capability (e.g. pytest, tiny_coder, ruff)")
    requester_role: str = Field(..., description="Role requesting the capability (e.g. host2, boss)")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Parameters for the capability invocation")
    timeout_seconds: float = Field(default=60.0, ge=1.0)


class CapabilityHandle(BaseModel):
    """Returned handle representing an allocated capability or tool execution result."""
    request_id: str = Field(...)
    handle_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    capability_name: str = Field(...)
    status: str = Field(default="SUCCESS", description="SUCCESS, FAILED, or TIMED_OUT")
    output: Any = Field(default=None, description="Returned payload or result object")
    execution_time_seconds: float = Field(default=0.0)


class EscalationPacket(BaseModel):
    """Packet submitted by Host-2 when promoting a Fast-Mode task to Boss Production mode."""
    task_id: str = Field(...)
    reason: str = Field(..., description="Why the fast lane escalated (e.g. complexity, retries, security risk)")
    completed_steps: list[str] = Field(default_factory=list, description="Steps completed before escalation")
    failed_stage: str | None = Field(default=None, description="Stage where failure occurred")
    artifacts_created: list[str] = Field(default_factory=list, description="Paths to generated scratch artifacts")
    remaining_risks: list[str] = Field(default_factory=list, description="Identified unmitigated risks")
    suggested_next_action: str = Field(default="DECOMPOSE_AND_PLAN", description="Suggested action for Boss")
