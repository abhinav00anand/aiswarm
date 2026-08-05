# AISwarm Changelog

All notable changes to the AISwarm project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-08-05

### 🚀 Added
- **Host-1 Global Router**: Intelligent task surface sensitivity evaluation, blast radius assessment, and multi-lane routing (`FAST`, `PRODUCTION`, `HYBRID`).
- **Host-2 Capability Manager**: High-speed fast-path task execution engine with automatic `EscalationPacket` fallback.
- **Enterprise Security Subsystem**:
  - `APIKeyValidator`: Fail-fast startup authentication enforcement.
  - `ExecutionSandbox`: Subprocess isolation with command allowlisting and path restriction.
  - `SecretRedactor`: Multi-pattern regex secret scrubbing (OpenAI, Anthropic, GitHub, PyPI, Google, AWS).
  - `EngineeringGovernor`: Live cost guard, budget caps, and capability spawn gating.
  - `AuditLedger`: Thread-safe, append-only JSONL audit event logging (`~/.aiswarm/audit.jsonl`).
- **PyPI Package (`aiswarm-next`)**: PEP 517 compliant setuptools packaging with `aiswarm` CLI entry points.

### ⚡ Verified Benchmarks
- 210 Unit Tests (100% Passed)
- 131 Stress & Fuzzing Tests (100% Passed)
- 6,700 EventBus events / sec
- 23,800 TaskScheduler tasks / sec
- 12,300 AuditLedger events / sec
