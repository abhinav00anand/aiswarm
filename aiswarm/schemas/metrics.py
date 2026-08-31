"""Telemetry and metrics schemas."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class AgentMetrics(BaseModel):
    agent_role: str
    task_id: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    success: bool = True
    error: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PipelineMetrics(BaseModel):
    task_id: str
    total_duration_seconds: float = 0.0
    prompt_creation_seconds: float = 0.0
    coder_latency_seconds: float = 0.0
    critic_latency_seconds: float = 0.0
    compile_duration_seconds: float = 0.0
    test_duration_seconds: float = 0.0
    benchmark_duration_seconds: float = 0.0
    total_llm_calls: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    retry_count: int = 0
    final_state: str = ""
    merged: bool = False
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SystemMetrics(BaseModel):
    """Snapshot of system-wide telemetry."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    active_tasks: int = 0
    completed_tasks: int = 0
    rejected_tasks: int = 0
    deadlocked_tasks: int = 0
    merged_tasks: int = 0
    avg_review_cycles: float = 0.0
    avg_task_duration_seconds: float = 0.0
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    compile_success_rate: float = 0.0
    test_pass_rate: float = 0.0
    critic_rejection_rate: float = 0.0
    tasks_per_hour: float = 0.0
