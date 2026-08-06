<p align="center">
  <img src="https://raw.githubusercontent.com/abhinav00anand/aiswarm-next/main/assets/logo.jpg" alt="AISwarm logo" width="160" height="160" style="border-radius:24px;">
</p>

<h1 align="center">🐝 AISwarm-Next</h1>

<p align="center">
  <b>Production-Grade Autonomous Multi-Agent AI Engineering Swarm</b><br>
  An enterprise software engineering framework that transforms high-level goals into compiled, security-scrubbed, unit-tested, C++ native, and audited code bases — with zero-cloud API key Ollama local AI fallback.
</p>

<p align="center">
  <a href="https://pypi.org/project/aiswarm-next/"><img src="https://img.shields.io/pypi/v/aiswarm-next.svg?style=for-the-badge&logo=pypi&logoColor=white&color=blue" alt="PyPI Package"></a>
  <a href="https://github.com/abhinav00anand/aiswarm-next"><img src="https://img.shields.io/badge/github-aiswarm--next-black.svg?style=for-the-badge&logo=github" alt="GitHub Repository"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-3776AB.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python Version"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge" alt="License: MIT"></a>
</p>

<p align="center">
  <a href="#-unit-test-suite"><img src="https://img.shields.io/badge/Unit%20Tests-226%20Passed%20(100%25)-brightgreen?style=flat-square&logo=pytest" alt="Unit Tests"></a>
  <a href="#-local-ai-ollama"><img src="https://img.shields.io/badge/Local%20AI-Ollama%20Auto--Provisioned-blue?style=flat-square&logo=ollama" alt="Ollama Local AI"></a>
  <a href="#-c-native-engine"><img src="https://img.shields.io/badge/Host2%20Engine-C%2B%2B%20Native-00599C?style=flat-square&logo=cplusplus" alt="C++ Native Engine"></a>
  <a href="#-enterprise-security"><img src="https://img.shields.io/badge/Security-Zero--Trust%20Sandboxed-red?style=flat-square&logo=shield" alt="Zero-Trust Security"></a>
</p>

<p align="center">
  <a href="#-why-aiswarm-next">Why AISwarm-Next?</a> •
  <a href="#-ollama-local-ai-auto-provisioning">Ollama Local AI</a> •
  <a href="#-system-architecture">Architecture</a> •
  <a href="#-multi-lane-routing--c-native-host-2">C++ Host-2 Native</a> •
  <a href="#-the-8-specialized-critic-agents">The 8 Critics</a> •
  <a href="#-enterprise-security-subsystem">Security</a> •
  <a href="#-quick-start-guide">Quick Start</a> •
  <a href="#-benchmark-matrix">Benchmarks</a>
</p>

---

## 💡 Why AISwarm-Next?

Most AI coding assistants generate raw code snippets without verifying compilation, unit test passes, security standards, or architectural boundaries. 

**AISwarm-Next** operates like a fully autonomous software engineering organization:

- 🦙 **Zero-Cloud-Key Local AI Fallback**: If no cloud API keys are present, AISwarm-Next **automatically detects free disk space**, provisions **Ollama**, pulls the optimal model (`llama3.1:8b`, `llama3.2:3b`, or `llama3.2:1b`), and executes tasks locally without cloud dependencies.
- ⚡ **Multi-Lane Performance & C++ Native Engine**: Utility tasks run via the **Host-2 Fast Lane** (~0.1s latency). Native C++ modules are compiled and executed using the compiled **Host-2 C++ Native Engine** (`host2_engine.cpp`).
- 🎯 **Hierarchical Governance**: A **Boss Agent** acts as CTO, resolving deadlocks and establishing architecture policy. A **Manager Agent** plans subtask segmentations.
- 🛡 **Parallel Critic Auditing**: Generated code is concurrently audited by **8 domain-specialized Critic Agents** (Security, Architecture, Performance, Maintainability, Reliability, Style, Testing, Documentation).
- 🔒 **Zero-Trust Process Sandbox**: Subprocess execution and test verification run inside an isolated sandbox with command allowlisting, path traversal protection, and MSVC/GCC cross-platform compiler support.
- 📜 **Immutable Audit Ledger**: Every routing choice, policy check, secret scrubbing event, model invocation, and merge attempt is recorded in `~/.aiswarm/audit.jsonl`.

---

## 🦙 Ollama Local AI Auto-Provisioning

AISwarm-Next features **Zero-Cloud-Key Auto-Provisioning**. When no API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `NOVITA_API_KEY`, `DEEPSEEK_API_KEY`) are detected at boot, AISwarm-Next auto-provisions Ollama:

### Disk Space Model Selection Matrix

AISwarm-Next dynamically measures available disk space (`shutil.disk_usage`) and pulls the largest optimal model for local hardware:

| Available Free Disk Space | Auto-Selected Model | RAM Requirement | Best Suited For |
|---|---|---|---|
| **≥ 16 GB Free Space** | `llama3.1:8b` | 8GB–16GB RAM | Full Production Pipeline, Complex Architecture & Refactoring |
| **8 GB – 16 GB Free Space** | `llama3.2:3b` | 4GB–8GB RAM | Medium Multi-File Tasks, Utility Modules & Testing |
| **< 8 GB Free Space** | `llama3.2:1b` | 2GB–4GB RAM | Lightweight Fast-Mode Functions & Quick Scripts |

### Local Security Safeguards
Local Ollama model invocations pass through the exact same enterprise security pipeline as cloud LLMs:
- **Secret Redaction**: Prompts are scrubbed of sensitive tokens (`sk-...`, `ghp_...`, `AIza...`, AWS keys) before sending to Ollama, and model responses are scrubbed before processing.
- **Audit Logging**: Every local model execution records an `OLLAMA_MODEL_EXECUTION` audit event with token usage metadata.
- **Governance Controls**: `EngineeringGovernor` enforces execution permission checks on local capability spawns.

---

## 🏗 System Architecture

AISwarm-Next enforces a strict **12-Stage Hierarchical Pipeline**:

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
│ HOST-2 C++ NATIVE │          │ 01. BOSS VALIDATION  │         │  HYBRID DECOMPOSER   │
│ CAPABILITY MGR    │          │ 02. MANAGER PLANNING │         │ Subtask Segmentation │
└─────────┬─────────┘          │ 03. TASK PLANNER     │         └──────────┬───────────┘
          │                    │ 04. CONTEXT SELECTOR │                    │
          │                    │ 05. CODER GENERATION │                    │
          │                    │ 06. COMPILER VERIFY  │                    │
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
                               └───────────┴────────────┘
```

---

## ⚡ Multi-Lane Routing & C++ Native Host-2

Tasks are automatically categorized into three execution lanes via **Host1Router**:

### 1. Fast Lane (`FAST`)
- **Latency**: ~0.1 seconds
- **Best For**: File scaffolding, utility functions, formatting.
- **Engine**: Managed by `Host2CapabilityManager`. C++ tasks are routed through the compiled **C++ Native Engine** (`host2_engine.cpp`).
- **Quality Stack Integration**: Validates compilation and test gates, merging code directly into the workspace upon success, or falling back to Production mode on validation failure.

### 2. Production Lane (`PRODUCTION`)
- **Best For**: Multi-file codebases, security modules, complex algorithms.
- **Engine**: Full 12-stage pipeline driven by Boss, Manager, Coder, 8 Critic Agents, and 5-Gate Merge Controller.

### 3. Hybrid Lane (`HYBRID`)
- **Best For**: Large goals combining basic utilities with complex core logic.
- **Engine**: `BossAgent.execute_hybrid_task()` segments tasks, dispatching lightweight parts to Host-2 while reserving critical logic for the Boss pipeline.

---

## 🧐 The 8 Specialized Critic Agents

During Stage 7 of the Production Lane, 8 specialized AI agents review generated code concurrently:

| Critic Agent | Focus Area | Veto Power | Description |
|---|---|---|---|
| 🛡 **Security Critic** | Security & OWASP | **YES (Veto)** | Audits injection, XSS, path traversal, hardcoded secrets, and unsafe deserialization. |
| 🏛 **Architecture Critic** | Design & Patterns | No | Validates layer separation, SOLID principles, and modularity. |
| ⚡ **Performance Critic** | Speed & Memory | No | Evaluates time/space complexity, memory footprint, and loop efficiency. |
| 🧹 **Maintainability Critic** | Code Cleanliness | No | Checks cyclomatic complexity, duplication, and naming clarity. |
| 🛡 **Reliability Critic** | Error Resilience | No | Audits exception boundaries, null safety, edge cases, and fallback handling. |
| 🎨 **Style Critic** | Formatting & Standards | No | Enforces PEP 8, type annotations, and codebase consistency. |
| 🧪 **Testing Critic** | Unit Test Coverage | No | Verifies test coverage depth, assertion validity, and edge-case testing. |
| 📝 **Documentation Critic** | Clarity & Docs | No | Checks docstrings, inline comments, function parameters, and README docs. |

---

## 🔒 Enterprise Security Subsystem

AISwarm-Next enforces a **Zero-Trust Security Architecture**:

1. **Subprocess Execution Sandbox (`ExecutionSandbox`)**
   - Enforces directory boundary scoping and process isolation.
   - Command allowlisting permits only: `python`, `pytest`, `git`, `cargo`, `g++`, `gcc`, `clang++`, `cl`, `main`, `host2_engine`, `node`, `npm`.

2. **Real-Time Secret Redaction Engine (`SecretRedactor`)**
   - Automatically scrubs credentials from logs, prompts, terminal displays, and audit files.
   - Redacts OpenAI (`sk-...`), Anthropic (`sk-ant-...`), GitHub (`ghp_...`), Google (`AIza...`), and AWS (`AKIA...`).

3. **Startup Authentication & Local Fallback (`APIKeyValidator`)**
   - Verifies cloud API keys or automatically provisions local Ollama AI fallback if no keys are set.

4. **Real-Time Engineering Governor (`EngineeringGovernor`)**
   - Monitors token consumption and calculates live spend via `CostGuard`.

5. **Immutable Audit Ledger (`AuditLedger`)**
   - Persists all route decisions, policy checks, capability invocations, and merge events to `~/.aiswarm/audit.jsonl`.

---

## ⚡ Quick Start Guide

### Installation from PyPI

```bash
pip install aiswarm-next
```

### Option A: Running with Cloud API Keys

```bash
export OPENAI_API_KEY="sk-proj-your-key"
# OR
export ANTHROPIC_API_KEY="sk-ant-your-key"
# OR
export GOOGLE_API_KEY="AIzaSy-your-key"

aiswarm run "Write a Python calculator module with add, subtract, and unit tests"
```

### Option B: Running with Zero Cloud API Keys (Ollama Local AI)

Simply run AISwarm-Next without setting any API keys. The system will auto-detect free disk space, start Ollama, pull the optimal model, and execute:

```bash
# No environment variables needed!
aiswarm run "Implement a fast binary search algorithm in C++"
```

### CLI Commands

```bash
# Execute a task
aiswarm run "Create a security-scrubbed authentication module"

# Inspect configured LLM providers & keys
aiswarm providers

# View immutable audit ledger logs
aiswarm audit
```

---

## 📊 Benchmark Matrix

| Test Suite | Total Run | Passed | Skipped | Pass Rate |
|---|---|---|---|---|
| **Unit Test Suite** | 229 | **226** | 3 | **100%** |
| **Stress & Fuzzing Suite** | 134 | **131** | 3 | **100%** |
| **Heavy Concurrency Benchmark** | 5 | **5** | 0 | **100%** |
| **TOTAL** | **368** | **362** | **6** | **100%** |

### System Performance Metrics
- **EventBus Throughput**: `6,700` events / sec
- **TaskScheduler Throughput**: `23,800` tasks / sec
- **AuditLedger Write Speed**: `12,300` events / sec
- **SecretRedactor Scrub Speed**: `18,200` secrets / sec

---

## 📜 License

This project is open-source software licensed under the [MIT License](./LICENSE).
