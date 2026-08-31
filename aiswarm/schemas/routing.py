"""
Routing Schemas — Route Decisions, Risk Levels, and Routing Traces.
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class ExecutionMode(str, Enum):
    """Supported pipeline execution modes in AISwarm."""
    FAST = "FAST"
    PRODUCTION = "PRODUCTION"
    HYBRID = "HYBRID"


class RiskLevel(str, Enum):
    """Evaluated risk classification level for an incoming task."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RouteDecision(BaseModel):
    """Structured decision output produced by Host-1 Global Router."""
    route: ExecutionMode = Field(..., description="Target execution lane (FAST, PRODUCTION, or HYBRID)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Router confidence score between 0.0 and 1.0")
    reason: str = Field(..., description="Human-readable justification for the selected route")
    risk_level: RiskLevel = Field(default=RiskLevel.LOW, description="Evaluated risk level")
    estimated_cost_usd: float = Field(default=0.01, ge=0.0, description="Estimated execution cost in USD")
    estimated_runtime_seconds: float = Field(default=30.0, ge=0.0, description="Estimated wall-clock execution time")
    required_capabilities: list[str] = Field(default_factory=list, description="Capabilities required for execution")
    escalation_policy: str = Field(
        default="ESCALATE_IF_COMPLEXITY_OR_RISK_GROWS",
        description="Trigger policy for escalating to Boss",
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional context metadata")
