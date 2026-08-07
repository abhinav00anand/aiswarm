# Blynx — Verified Test Results & Benchmark Report

Generated: August 5, 2026 | Python 3.14 | pytest 9.1.1

## Overall Test Execution Summary

| Suite | Passed | Skipped | Failed | Total | Pass Rate | Execution Time |
|---|---|---|---|---|---|---|
| **Unit Tests** | **210** | **3** | **0** | **213** | **100%** | 23.97s |
| **Stress & Fuzzing Tests** | **131** | **3** | **0** | **134** | **100%** | 100.86s |
| **Heavy Concurrency Benchmark** | **5 / 5** | **0** | **0** | **5** | **100%** | 1.89s |
| **TOTAL** | **346** | **6** | **0** | **352** | **100%** | **126.72s** |

---

## Heavy Concurrency Benchmark Benchmarks

| Subsystem | Benchmark Metric | Result | Status |
|---|---|---|---|
| **EventBus** | High-throughput concurrent publishing | **6,700 events / sec** (10,000 events in 1.49s) | ✅ PASSED |
| **TaskScheduler** | Priority queue enqueue + dequeue | **23,800 tasks / sec** (1,000 tasks in 0.042s) | ✅ PASSED |
| **AuditLedger** | Disk persistence + JSONL flush | **12,300 audit events / sec** (1,000 events in 0.081s) | ✅ PASSED |
| **Orchestrator** | Concurrent task submission & routing | **390 submissions / sec** (50 tasks in 0.128s) | ✅ PASSED |
| **SecretRedactor** | Multi-pattern secret scrubbing | **18,200 secrets / sec** (1,000 secrets in 0.054s) | ✅ PASSED |

---

## Stress & Fuzzing Test Coverage Breakdown

- `tests/stress/test_cost_guard_stress.py` (Passed)
- `tests/stress/test_deadlock_detector_stress.py` (Passed)
- `tests/stress/test_event_bus_stress.py` (Passed)
- `tests/stress/test_merge_controller_stress.py` (Passed)
- `tests/stress/test_network_failure_stress.py` (Passed)
- `tests/stress/test_pipeline_stress.py` (Passed)
- `tests/stress/test_provider_router_stress.py` (Passed)
- `tests/stress/test_rate_limiter_stress.py` (Passed)
- `tests/stress/test_retry_engine_stress.py` (Passed)
- `tests/stress/test_scheduler_stress.py` (Passed)
- `tests/stress/test_state_machine_stress.py` (Passed)

---

*Skipped tests reflect optional external services (Redis server, vector database). All core platform logic, routing, governance, sandboxing, and control plane subsystems pass with zero failures.*
