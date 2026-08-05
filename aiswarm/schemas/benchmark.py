"""Benchmark schemas — performance measurement data contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class BenchmarkSuite(BaseModel):
    """Definition of a benchmark suite for a task class."""
    suite_id: str
    task_class: str
    description: str
    metrics: list[str]         # e.g. ["throughput", "latency", "memory"]
    baseline_values: dict[str, float] = Field(default_factory=dict)
    tolerance_pct: float = 10.0  # allowed regression %


class BenchmarkRun(BaseModel):
    """A single benchmark run result."""
    run_id: str
    suite_id: str
    task_id: str
    metrics: dict[str, float] = Field(default_factory=dict)
    baseline_comparison: dict[str, float] = Field(default_factory=dict)
    passed: bool = False
    profiler_output: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_seconds: float = 0.0
    worker_type: str = "local"
