# AISwarm-Next Release Changelog

All notable changes to **AISwarm-Next** are documented here.
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-08-05

### 🚀 Major Platform Architecture
- **Host-1 Global Router**: Multi-lane routing system supporting `FAST` (~0.1s latency), `PRODUCTION` (12-stage Boss pipeline), and `HYBRID` execution paths based on task sensitivity and blast radius.
- **Host-2 Capability Manager**: High-performance fast-path capability engine with automatic `EscalationPacket` fallback to Boss Agent.
- **Enterprise Security Subsystem**:
  - `APIKeyValidator`: Fail-fast startup authentication enforcement across CLI, API server, and core modules.
  - `ExecutionSandbox`: Subprocess isolation with path traversal protection and command allowlisting (`python`, `pytest`, `git`, `pip`).
  - `SecretRedactor`: Multi-pattern secret scrubber for OpenAI, Anthropic, GitHub, PyPI, Google, and AWS keys.
  - `EngineeringGovernor`: USD token spend tracking, cost limits, and capability spawn gates.
  - `AuditLedger`: Thread-safe, append-only event logging (`~/.aiswarm/audit.jsonl`).
- **5-Gate Merge Controller**: Strict 5-stage validation (Compilation, Unit Test, Performance, Security, Path Resolution) before code merges.

### 📦 PyPI Package & GitHub Sync
- Published package `aiswarm-next` on PyPI ([https://pypi.org/project/aiswarm-next/1.0.0/](https://pypi.org/project/aiswarm-next/1.0.0/)).
- Created official GitHub repository ([https://github.com/abhinav00anand/aiswarm-next](https://github.com/abhinav00anand/aiswarm-next)).
- Added PEP 561 `py.typed` marker for strict type checking support.
- CLI console script entry point `aiswarm` and API server `aiswarm-api`.

### 📊 Benchmark Metrics
- **210 / 210 Unit Tests Passed** (100% pass rate in 23.01s).
- **131 / 131 Stress & Fuzzing Tests Passed** (100% pass rate in 100.86s).
- **6,700 events / sec** EventBus throughput.
- **23,800 tasks / sec** TaskScheduler priority queue throughput.
- **12,300 events / sec** AuditLedger disk persistence throughput.
