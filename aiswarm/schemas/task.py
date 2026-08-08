"""Task schema — the central unit of work flowing through AISwarm."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, ConfigDict



class TaskState(str, Enum):
    """Finite state machine states for a task lifecycle."""
    NEW = "NEW"
    PROMPTED = "PROMPTED"
    GENERATED = "GENERATED"
    PRECHECKED = "PRECHECKED"
    REVIEWED = "REVIEWED"
    COMPILED = "COMPILED"
    TESTED = "TESTED"
    BENCHMARKED = "BENCHMARKED"
    MERGED = "MERGED"
    REJECTED = "REJECTED"
    DEADLOCK = "DEADLOCK"
    ESCALATED = "ESCALATED"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"


class TaskPriority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


class TaskClass(str, Enum):
    FEATURE = "FEATURE"
    BUGFIX = "BUGFIX"
    REFACTOR = "REFACTOR"
    PERFORMANCE = "PERFORMANCE"
    SECURITY = "SECURITY"
    DOCUMENTATION = "DOCUMENTATION"
    TEST = "TEST"
    MIGRATION = "MIGRATION"
    BENCHMARK = "BENCHMARK"


class FileContext(BaseModel):
    """A file included in the prompt context."""
    path: str
    content: str
    reason: str
    token_count: int
    relevance_score: float = 0.0
    lines_retrieved: list[tuple[int, int]] | None = None


class PromptLedger(BaseModel):
    """Immutable record of what was sent in each prompt."""
    prompt_version: str
    files_included: list[FileContext] = Field(default_factory=list)
    total_tokens: int = 0
    model_used: str = ""
    provider_used: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    selection_strategy: str = ""
    system_prompt_tokens: int = 0
    user_prompt_tokens: int = 0


class CompilerOutput(BaseModel):
    """Output from the compiler/interpreter step."""
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_seconds: float = 0.0
    command: str = ""


class TestOutput(BaseModel):
    """Output from the test runner step."""
    success: bool
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    coverage_pct: float = 0.0
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    numeric_passed: bool = True
    numeric_tolerance: float = 1e-6


class BenchmarkOutput(BaseModel):
    """Output from the performance benchmark step."""
    passed: bool
    throughput: float = 0.0
    latency_ms: float = 0.0
    memory_mb: float = 0.0
    cpu_pct: float = 0.0
    bandwidth_gbps: float = 0.0
    utilization_pct: float = 0.0
    baseline_comparison: float = 0.0  # ratio vs baseline (>1 = better)
    profiler_output: str = ""
    duration_seconds: float = 0.0


class ReviewDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"


class CriticReview(BaseModel):
    """Structured review emitted by a Critic agent."""
    critic_role: str
    decision: ReviewDecision
    production_ready: bool
    fatal_flaw: str | None = None
    flaw_category: str | None = None
    flaw_explanation: str = ""
    mandatory_fix: str = ""
    suggestions: list[str] = Field(default_factory=list)
    score: int = Field(default=0, ge=0, le=100)
    model_used: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    token_count: int = 0
    latency_ms: float = 0.0


class StateTransition(BaseModel):
    """Audit trail entry for each state change."""
    from_state: TaskState
    to_state: TaskState
    reason: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    agent: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)


class Task(BaseModel):
    """The primary unit of work flowing through AISwarm."""

    # Identity
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_task_id: str | None = None
    subtask_ids: list[str] = Field(default_factory=list)

    # Classification
    title: str
    description: str
    task_class: TaskClass = TaskClass.FEATURE
    priority: TaskPriority = TaskPriority.NORMAL
    tags: list[str] = Field(default_factory=list)

    # State machine
    state: TaskState = TaskState.NEW
    state_history: list[StateTransition] = Field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 5

    # Target
    target_files: list[str] = Field(default_factory=list)
    target_language: str = "python"
    acceptance_criteria: list[str] = Field(default_factory=list)

    # Context & prompts
    prompt_ledger: list[PromptLedger] = Field(default_factory=list)
    context_files: list[FileContext] = Field(default_factory=list)

    # Outputs
    generated_code: str | None = None
    generated_code_hash: str | None = None
    diff_patch: str | None = None

    # Pipeline results
    precheck_passed: bool | None = None
    reviews: list[CriticReview] = Field(default_factory=list)
    compiler_output: CompilerOutput | None = None
    test_output: TestOutput | None = None
    benchmark_output: BenchmarkOutput | None = None

    # Merge
    merged: bool = False
    merged_at: datetime | None = None
    merged_by: str | None = None

    # Timing
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Cost tracking
    total_tokens_used: int = 0
    total_llm_calls: int = 0
    estimated_cost_usd: float = 0.0

    # Worker
    worker_job_id: str | None = None
    worker_state_hash: str | None = None

    # Escalation
    deadlock_summary: str | None = None
    boss_override: str | None = None
    escalated_at: datetime | None = None

    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("task_id", "parent_task_id", mode="before")
    @classmethod
    def coerce_str(cls, v: Any) -> Any:
        return str(v) if v is not None else v

    def transition(
        self,
        new_state: TaskState,
        reason: str,
        agent: str = "",
        evidence: dict[str, Any] | None = None,
    ) -> None:
        """Transition to a new state, recording the audit trail entry."""
        self.state_history.append(
            StateTransition(
                from_state=self.state,
                to_state=new_state,
                reason=reason,
                agent=agent,
                evidence=evidence or {},
            )
        )
        self.state = new_state

    def is_approved(self) -> bool:
        """Return True if majority of critics approved."""
        if not self.reviews:
            return False
        approvals = sum(1 for r in self.reviews if r.decision == ReviewDecision.APPROVE)
        required_approvals = max(2, (len(self.reviews) + 1) // 2)
        return approvals >= required_approvals



    def is_security_vetoed(self) -> bool:
        """Return True if the security critic issued a veto."""
        for r in self.reviews:
            if r.critic_role == "security" and r.decision == ReviewDecision.REJECT:
                return True
        return False

    def rejection_reasons(self) -> list[str]:
        """Collect all fatal flaws from rejecting critics, precheck failures, and build errors."""
        reasons = [
            f"[{r.critic_role}] {r.fatal_flaw}: {r.mandatory_fix}"
            for r in self.reviews
            if r.decision == ReviewDecision.REJECT and r.fatal_flaw
        ]
        if self.precheck_passed is False:
            precheck_issues = self.metadata.get("precheck_issues", [])
            if isinstance(precheck_issues, list):
                for issue in precheck_issues:
                    reasons.append(f"[PreCheck] {issue}")
            scan_violations = self.metadata.get("scan_violations", [])
            if isinstance(scan_violations, list):
                for v in scan_violations:
                    reasons.append(f"[SecurityScan] {v}")
        if self.compiler_output and not self.compiler_output.success and self.compiler_output.stderr:
            reasons.append(f"[CompilerError] {self.compiler_output.stderr[:500]}")
        if self.test_output and not self.test_output.passed and self.test_output.stdout:
            reasons.append(f"[TestFailure] {self.test_output.stdout[:500]}")
        return reasons

    def duration_seconds(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    model_config = ConfigDict(use_enum_values=False)

