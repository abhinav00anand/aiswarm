"""
Prometheus metrics — exposes AISwarm telemetry as a /metrics endpoint.

Counters and histograms for:
  - Task throughput by state
  - LLM call latency by provider and role
  - Critic approval/rejection rates
  - Compile success rate
  - Test pass rate
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Generator

try:
    from prometheus_client import (
        Counter,
        Histogram,
        Gauge,
        start_http_server,
        REGISTRY,
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False


class ZymisMetrics:
    """Prometheus metrics registry for AISwarm."""

    def __init__(self) -> None:
        if not _PROMETHEUS_AVAILABLE:
            return

        self.tasks_total = Counter(
            "zymis_tasks_total",
            "Total tasks created",
            ["priority", "task_class"],
        )
        self.tasks_state = Counter(
            "zymis_task_state_transitions_total",
            "Task state transitions",
            ["from_state", "to_state"],
        )
        self.tasks_merged = Counter(
            "zymis_tasks_merged_total",
            "Tasks successfully merged",
        )
        self.tasks_rejected = Counter(
            "zymis_tasks_rejected_total",
            "Tasks rejected",
            ["reason"],
        )
        self.llm_calls = Counter(
            "zymis_llm_calls_total",
            "LLM API calls",
            ["provider", "role", "model"],
        )
        self.llm_tokens = Counter(
            "zymis_llm_tokens_total",
            "LLM tokens consumed",
            ["provider", "role", "token_type"],
        )
        self.llm_cost = Counter(
            "zymis_llm_cost_usd_total",
            "Estimated LLM cost in USD",
            ["provider"],
        )
        self.llm_latency = Histogram(
            "zymis_llm_latency_seconds",
            "LLM call latency",
            ["provider", "role"],
            buckets=[0.5, 1, 2, 5, 10, 30, 60, 120],
        )
        self.critic_decisions = Counter(
            "zymis_critic_decisions_total",
            "Critic agent decisions",
            ["critic", "decision"],
        )
        self.compile_results = Counter(
            "zymis_compile_results_total",
            "Compiler results",
            ["language", "success"],
        )
        self.test_results = Counter(
            "zymis_test_results_total",
            "Test run results",
            ["success"],
        )
        self.active_tasks = Gauge(
            "zymis_active_tasks",
            "Currently active tasks",
        )
        self.retry_count = Histogram(
            "zymis_task_retry_count",
            "Number of retries per task",
            buckets=[0, 1, 2, 3, 4, 5],
        )

    def record_llm_call(
        self,
        provider: str,
        role: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float,
        cost_usd: float,
    ) -> None:
        if not _PROMETHEUS_AVAILABLE:
            return
        self.llm_calls.labels(provider=provider, role=role, model=model).inc()
        self.llm_tokens.labels(provider=provider, role=role, token_type="prompt").inc(prompt_tokens)
        self.llm_tokens.labels(provider=provider, role=role, token_type="completion").inc(completion_tokens)
        self.llm_latency.labels(provider=provider, role=role).observe(latency_ms / 1000.0)
        self.llm_cost.labels(provider=provider).inc(cost_usd)

    def start_server(self, port: int = 9090) -> None:
        if _PROMETHEUS_AVAILABLE:
            start_http_server(port)


# Singleton
metrics = ZymisMetrics()
