"""Unit tests for telemetry/metrics schemas."""

from __future__ import annotations

from aiswarm.schemas.metrics import AgentMetrics, PipelineMetrics, SystemMetrics


class TestAgentMetrics:
    def test_defaults_are_zero(self) -> None:
        m = AgentMetrics(agent_role="coder", task_id="t1", model="gpt-4o", provider="openai")
        assert m.prompt_tokens == 0
        assert m.total_tokens == 0
        assert m.cost_usd == 0.0

    def test_success_defaults_true(self) -> None:
        m = AgentMetrics(agent_role="coder", task_id="t1", model="m", provider="p")
        assert m.success is True
        assert m.error is None

    def test_error_can_be_recorded(self) -> None:
        m = AgentMetrics(
            agent_role="coder", task_id="t1", model="m", provider="p",
            success=False, error="timeout",
        )
        assert m.success is False
        assert m.error == "timeout"

    def test_timestamp_auto_populated(self) -> None:
        m = AgentMetrics(agent_role="coder", task_id="t1", model="m", provider="p")
        assert m.timestamp is not None


class TestPipelineMetrics:
    def test_defaults_zero_duration(self) -> None:
        m = PipelineMetrics(task_id="t1")
        assert m.total_duration_seconds == 0.0
        assert m.retry_count == 0

    def test_merged_defaults_false(self) -> None:
        m = PipelineMetrics(task_id="t1")
        assert m.merged is False

    def test_can_accumulate_stage_durations(self) -> None:
        m = PipelineMetrics(
            task_id="t1", coder_latency_seconds=2.5,
            critic_latency_seconds=1.1, compile_duration_seconds=0.3,
        )
        assert m.coder_latency_seconds == 2.5
        assert m.critic_latency_seconds == 1.1


class TestSystemMetrics:
    def test_defaults_all_zero_or_empty(self) -> None:
        m = SystemMetrics()
        assert m.active_tasks == 0
        assert m.merged_tasks == 0
        assert m.compile_success_rate == 0.0

    def test_rates_can_be_set(self) -> None:
        m = SystemMetrics(compile_success_rate=0.95, test_pass_rate=0.88)
        assert m.compile_success_rate == 0.95
        assert m.test_pass_rate == 0.88

    def test_timestamp_auto_populated(self) -> None:
        m = SystemMetrics()
        assert m.timestamp is not None
