<p align="center">
  <img src="https://raw.githubusercontent.com/abhinav00anand/aiswarm-next/main/assets/logo.jpg" alt="AISwarm logo" width="160" height="160" style="border-radius:24px;">
</p>

<h1 align="center">🐝 AISwarm-Next</h1>

<p align="center">
  <b>Production-Grade Multi-Agent AI Engineering Swarm</b><br>
  An autonomous software engineering framework that transforms high-level natural language goals into production-ready, compiled, security-scrubbed, unit-tested, and audited code bases.
</p>

<p align="center">
  <a href="https://pypi.org/project/aiswarm-next/"><img src="https://img.shields.io/pypi/v/aiswarm-next.svg?style=for-the-badge&logo=pypi&logoColor=white&color=blue" alt="PyPI Package"></a>
  <a href="https://github.com/abhinav00anand/aiswarm-next"><img src="https://img.shields.io/badge/github-aiswarm--next-black.svg?style=for-the-badge&logo=github" alt="GitHub Repository"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-3776AB.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python Version"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge" alt="License: MIT"></a>
</p>

<p align="center">
  <a href="#-unit-test-suite"><img src="https://img.shields.io/badge/Unit%20Tests-210%20Passed%20(100%25)-brightgreen?style=flat-square&logo=pytest" alt="Unit Tests"></a>
  <a href="#-stress-test-suite"><img src="https://img.shields.io/badge/Stress%20Tests-131%20Passed%20(100%25)-orange?style=flat-square&logo=pytest" alt="Stress Tests"></a>
  <a href="#-enterprise-security"><img src="https://img.shields.io/badge/Security-Zero--Trust%20Sandboxed-red?style=flat-square&logo=shield" alt="Zero-Trust Security"></a>
  <a href="#-eventbus-throughput"><img src="https://img.shields.io/badge/EventBus-6%2C700%20events%2Fsec-purple?style=flat-square" alt="EventBus Throughput"></a>
</p>

<p align="center">
  <a href="#-why-aiswarm-next">Why AISwarm-Next?</a> •
  <a href="#-system-architecture">Architecture</a> •
  <a href="#-dual-router-multi-lane-system">Multi-Lane Routing</a> •
  <a href="#-the-8-specialized-critic-agents">The 8 Critics</a> •
  <a href="#-enterprise-security-subsystem">Security</a> •
  <a href="#-quick-start-guide">Quick Start</a> •
  <a href="#-cli--rest-api-reference">CLI & API</a> •
  <a href="#-benchmark-matrix">Benchmarks</a>
</p>

---

## 💡 Why AISwarm-Next?

Most AI coding assistants generate code snippet suggestions without validating whether the code compiles, passes tests, satisfies security standards, or breaks existing architecture. 

**AISwarm-Next** functions like an entire autonomous software engineering organization:

- 🎯 **Hierarchical Governance**: A **Boss Agent** acts as CTO, resolving deadlocks and setting architectural policy. A **Manager Agent** acts as Engineering Manager, planning subtask dependencies.
- ⚡ **Multi-Lane Performance**: Simple utility requests bypass full LLM debate via the **Host-2 Fast Lane** (~0.1s latency). Production feature changes run through the full 12-stage **Boss Pipeline**.
- 🛡 **Parallel Critic Auditing**: Every line of code is simultaneously scrutinized by **8 domain-specialized Critic Agents** (Security, Architecture, Performance, Maintainability, Reliability, Style, Testing, Documentation).
- 🔒 **Zero-Trust Subprocess Sandbox**: Code execution and test verification run inside an isolated subprocess sandbox with command allowlisting and path traversal protection.
- 📜 **Immutable Audit Ledger**: Every action, routing choice, token spend, policy evaluation, and merge attempt is recorded in a thread-safe JSONL file (`~/.aiswarm/audit.jsonl`).

---

## 🏗 System Architecture

AISwarm-Next enforces a strict **12-Stage Hierarchical Pipeline**. Code moves forward only when each stage passes unconditionally:

```text
                               ┌────────────────────────┐
                               │  NATURAL LANGUAGE TASK │
                               └───────────┬────────────┘
                                           │
                                           ▼
                               ┌────────────────────────┐
                               │     HOST-1 ROUTER      │
                               └───────────┬────────────┘
                                           │
          ┌────────────────────────────────┼────────────────────────────────┐
          │ (Fast Lane: ~0.1s)             │ (Production Lane: 12 Stages)   │ (Hybrid Lane)
          ▼                                ▼                                ▼
┌───────────────────┐          ┌──────────────────────┐         ┌──────────────────────┐
│ HOST-2 CAPABILITY │          │ 01. BOSS VALIDATION  │         │  HYBRID DECOMPOSER   │
│      MANAGER      │          │ 02. MANAGER PLANNING │         │ Subtask Segmentation │
└─────────┬─────────┘          │ 03. TASK PLANNER     │         └──────────┬───────────┘
          │                    │ 04. CONTEXT SELECTOR │                    │
          │                    │ 05. CODER GENERATION │                    │
          │                    │ 06. PYTHON COMPILER  │                    │
          │                    │ 07. 8 PARALLEL CRITICS                    │
          │                    │ 08. CONFIDENCE ENGINE│                    │
          │                    │ 09. UNIT TEST RUNNER │                    │
          │                    │ 10. RECURSIVE HEALER │                    │
          │                    │ 11. 5-GATE MERGER    │                    │
          │                    │ 12. AUDIT LOGGING    │                    │
          │                    └──────────┬───────────┘                    │
          │                               │                                │
          └───────────────────────────────┼────────────────────────────────┘
                                          │
                                          ▼
                               ┌────────────────────────┐
                               │   EXECUTION SANDBOX    │
                               └───────────┬────────────┘
                                           │
                                           ▼
                               ┌────────────────────────┐
                               │  AUDIT LEDGER (JSONL)  │
                               └────────────────────────┘
```

---

## 🚀 Dual-Router Multi-Lane System

To maximize speed while guaranteeing enterprise safety, AISwarm-Next categorizes tasks into three execution lanes via **Host1Router**:

### 1. Fast Lane (`FAST`)
- **Latency**: ~0.1 seconds
- **Best For**: File scaffolding, basic script generation, standard utility functions, formatting.
- **Engine**: Executed directly by `Host2CapabilityManager` using pre-approved sandboxed capability plugins.
- **Fallback**: If capability execution fails or encounters ambiguity, it generates an `EscalationPacket` and automatically escalates to the Boss Pipeline.

### 2. Production Lane (`PRODUCTION`)
- **Latency**: Comprehensive LLM Engineering Pipeline
- **Best For**: Complex features, multi-file codebases, security-sensitive modules, refactoring.
- **Engine**: Full 12-stage pipeline with Boss, Manager, Coder, 8 Critic Agents, and 5-Gate Merge Controller.

### 3. Hybrid Lane (`HYBRID`)
- **Best For**: Large-scale projects containing both simple utilities and complex core logic.
- **Engine**: `BossAgent.execute_hybrid_task()` decomposes the goal into subtasks, delegating lightweight parts to Host-2 while reserving critical logic for the Boss pipeline.

---

## 🧐 The 8 Specialized Critic Agents

During Stage 7 of the Production Lane, 8 specialized AI agents review the generated code concurrently:

| Critic Agent | Focus Area | Veto Power | Description |
|---|---|---|---|
| 🛡 **Security Critic** | Security & OWASP | **YES (Veto)** | Audits injection, XSS, path traversal, hardcoded secrets, and unsafe deserialization. |
| 🏛 **Architecture Critic** | Design & Patterns | No | Validates layer separation, SOLID principles, and structural modularity. |
| ⚡ **Performance Critic** | Speed & Memory | No | Evaluates time/space complexity, resource consumption, and loop efficiency. |
| 🧹 **Maintainability Critic** | Code Cleanliness | No | Checks cyclomatic complexity, code duplication, and naming clarity. |
| 🛡 **Reliability Critic** | Error Resilience | No | Audits exception boundaries, null checks, edge-case safety, and fallback handling. |
| 🎨 **Style Critic** | Formatting & Standards | No | Enforces PEP 8, type hints, and codebase style consistency. |
| 🧪 **Testing Critic** | Unit Test Coverage | No | Verifies test coverage depth, assertion validity, and edge-case testing. |
| 📝 **Documentation Critic** | Clarity & Docs | No | Checks docstrings, inline comments, function parameters, and README instructions. |

---

## 🔒 Enterprise Security Subsystem

AISwarm-Next is engineered with a **Zero-Trust Security Framework**:

### 1. Subprocess Execution Sandbox (`ExecutionSandbox`)
- Runs code compilation and test commands inside isolated subprocesses.
- **Command Allowlisting**: Permitted binaries restricted to `python`, `pytest`, `git`, and `pip`.
- **Path Traversal Protection**: Enforces strict canonical path checks to prevent escaping the project root.

### 2. Real-Time Secret Redaction Engine (`SecretRedactor`)
- Automatically scrubs credentials from logs, prompts, terminal displays, and audit files.
- Redacts: OpenAI (`sk-...`), Anthropic (`sk-ant-...`), GitHub (`ghp_...`), PyPI (`pypi-...`), Google (`AIza...`), and AWS (`AKIA...`).

### 3. Startup Authentication Guard (`APIKeyValidator`)
- Fails fast during boot if no valid LLM provider API key is detected, preventing unauthenticated system initialization.

### 4. Real-Time Engineering Governor (`EngineeringGovernor`)
- Monitors token consumption and calculates live USD spend via `CostGuard`.
- Enforces session cost limits and daily budget caps.

### 5. Immutable Audit Ledger (`AuditLedger`)
- Persists every route choice, policy check, capability spawn, and merge event to `~/.aiswarm/audit.jsonl`.
- Thread-safe `asyncio.Lock` ensures zero log corruption under high concurrency.

---

## ⚡ Quick Start Guide

### Installation from PyPI

```bash
pip install aiswarm-next
```

### Configure Your API Key

Set your preferred provider API key:

```bash
# For OpenAI:
export OPENAI_API_KEY="sk-proj-your-openai-api-key"

# For Anthropic:
export ANTHROPIC_API_KEY="sk-ant-your-anthropic-api-key"
```

### Basic Usage via CLI

```bash
# 1. Run a natural language task
aiswarm run "Create a Python Calculator class with add, subtract, multiply, divide, power, and unit tests"

# 2. Inspect configured provider API keys
aiswarm providers

# 3. View live security audit ledger events
aiswarm audit
```

---

## 🖥 CLI & REST API Reference

### CLI Commands (`aiswarm`)

The `aiswarm` command line utility provides complete control over the system:

```text
Usage: aiswarm [OPTIONS] COMMAND [ARGS]...

  AISwarm-Next — Production Multi-Agent AI Engineering Platform.

Options:
  --help  Show this message and exit.

Commands:
  run        Submit and execute a natural-language task.
  providers  List active LLM providers and verified API keys.
  audit      Display the last 50 events from the immutable audit ledger.
  version    Display system version information.
```

### REST API Server (`aiswarm-api`)

Launch the asynchronous FastAPI service:

```bash
uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
```

#### API Endpoints

- **`GET /health`**: Returns system health status, version, and masked provider credentials status.
- **`POST /submit`**: Accepts a JSON task request payload (`{"title": "...", "description": "..."}`) and initiates multi-lane routing.
- **`GET /status/{task_id}`**: Retrieves real-time execution status, current state machine stage, and critic feedback.
- **`GET /audit`**: Queries recent immutable audit events from `~/.aiswarm/audit.jsonl`.

---

## 📊 Benchmark Matrix

AISwarm-Next undergoes continuous heavy stress testing and performance auditing:

| Test Suite | Total Run | Passed | Skipped | Pass Rate | Execution Time |
|---|---|---|---|---|---|
| **Unit Test Suite** | 213 | **210** | 3 | **100%** | 23.01s |
| **Stress & Fuzzing Suite** | 134 | **131** | 3 | **100%** | 100.86s |
| **Heavy Concurrency Benchmark** | 5 | **5** | 0 | **100%** | 1.89s |
| **TOTAL** | **352** | **346** | **6** | **100%** | **125.76s** |

### Throughput & Concurrency Metrics

- **EventBus**: `6,700` events / sec (10,000 events published & processed in 1.49s)
- **TaskScheduler**: `23,800` tasks / sec (1,000 priority tasks enqueued & dequeued in 0.042s)
- **AuditLedger**: `12,300` events / sec (1,000 audit events written & flushed in 0.081s)
- **Control Plane**: `390` tasks / sec (50 concurrent multi-lane tasks processed in 0.128s)
- **SecretRedactor**: `18,200` secrets / sec (1,000 sensitive tokens scrubbed in 0.054s)

---

## 📜 License

This project is open-source software licensed under the [MIT License](./LICENSE).
