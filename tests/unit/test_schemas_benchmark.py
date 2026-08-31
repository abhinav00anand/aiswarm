"""Unit tests for benchmark schemas."""

from __future__ import annotations

from aiswarm.schemas.benchmark import BenchmarkSuite, BenchmarkRun


class TestBenchmarkSuite:
    def test_default_tolerance_is_10_percent(self) -> None:
        s = BenchmarkSuite(
            suite_id="s1", task_class="PERFORMANCE", description="d", metrics=["latency"]
        )
        assert s.tolerance_pct == 10.0

    def test_baseline_values_default_empty(self) -> None:
        s = BenchmarkSuite(
            suite_id="s1", task_class="PERFORMANCE", description="d", metrics=["latency"]
        )
        assert s.baseline_values == {}

    def test_can_set_custom_tolerance(self) -> None:
        s = BenchmarkSuite(
            suite_id="s1",
            task_class="PERFORMANCE",
            description="d",
            metrics=["throughput"],
            tolerance_pct=5.0,
        )
        assert s.tolerance_pct == 5.0

    def test_metrics_list_preserved(self) -> None:
        s = BenchmarkSuite(
            suite_id="s1",
            task_class="PERFORMANCE",
            description="d",
            metrics=["throughput", "latency", "memory"],
        )
        assert len(s.metrics) == 3


class TestBenchmarkRun:
    def test_defaults_not_passed(self) -> None:
        r = BenchmarkRun(run_id="r1", suite_id="s1", task_id="t1")
        assert r.passed is False

    def test_default_worker_type_is_local(self) -> None:
        r = BenchmarkRun(run_id="r1", suite_id="s1", task_id="t1")
        assert r.worker_type == "local"

    def test_metrics_dict_can_carry_values(self) -> None:
        r = BenchmarkRun(
            run_id="r1",
            suite_id="s1",
            task_id="t1",
            metrics={"latency_ms": 12.5, "throughput_rps": 900.0},
        )
        assert r.metrics["latency_ms"] == 12.5

    def test_worker_type_can_be_sandbox(self) -> None:
        r = BenchmarkRun(run_id="r1", suite_id="s1", task_id="t1", worker_type="sandbox")
        assert r.worker_type == "sandbox"

    def test_timestamp_auto_populated(self) -> None:
        r = BenchmarkRun(run_id="r1", suite_id="s1", task_id="t1")
        assert r.timestamp is not None
