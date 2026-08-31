"""Review-related schemas for critic agents."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class FlawSeverity(str, Enum):
    CRITICAL = "CRITICAL"  # must fix before merge
    HIGH = "HIGH"  # should fix
    MEDIUM = "MEDIUM"  # can defer
    LOW = "LOW"  # nice to have
    INFO = "INFO"  # informational only


class ReviewFlaw(BaseModel):
    """A single flaw identified by a critic."""

    severity: FlawSeverity
    category: str
    description: str
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    mandatory_fix: str
    code_snippet: str | None = None
    references: list[str] = Field(default_factory=list)


class ArchitectureReview(BaseModel):
    """Architecture critic structured output."""

    decision: str  # APPROVE | REJECT | ESCALATE
    production_ready: bool
    solid_compliance: bool
    separation_of_concerns: bool
    coupling_score: int = Field(ge=0, le=10)
    cohesion_score: int = Field(ge=0, le=10)
    abstraction_quality: int = Field(ge=0, le=10)
    fatal_flaw: str | None = None
    mandatory_fix: str = ""
    flaws: list[ReviewFlaw] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    overall_score: int = Field(ge=0, le=100)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PerformanceReview(BaseModel):
    """Performance critic structured output."""

    decision: str
    production_ready: bool
    has_algorithmic_issues: bool
    has_memory_issues: bool
    has_io_bottlenecks: bool
    has_concurrency_issues: bool
    time_complexity: str = ""
    space_complexity: str = ""
    fatal_flaw: str | None = None
    mandatory_fix: str = ""
    flaws: list[ReviewFlaw] = Field(default_factory=list)
    optimization_suggestions: list[str] = Field(default_factory=list)
    overall_score: int = Field(ge=0, le=100)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SecurityReview(BaseModel):
    """Security critic structured output."""

    decision: str
    production_ready: bool
    has_injection_risk: bool
    has_auth_issues: bool
    has_data_exposure: bool
    has_dependency_risk: bool
    has_crypto_issues: bool
    has_input_validation: bool
    cve_references: list[str] = Field(default_factory=list)
    fatal_flaw: str | None = None
    mandatory_fix: str = ""
    flaws: list[ReviewFlaw] = Field(default_factory=list)
    mitigations: list[str] = Field(default_factory=list)
    overall_score: int = Field(ge=0, le=100)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
