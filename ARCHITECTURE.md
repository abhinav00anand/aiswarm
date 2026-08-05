# AISwarm System Architecture Specification

---

## 🏛 Executive Architecture Overview

**AISwarm** is an enterprise-grade multi-agent AI orchestration system built for high-throughput code generation, security isolation, and reliable automated software development.

The system combines **Multi-Lane Task Routing**, **Zero-Trust Execution Sandboxing**, **Engineering Governance**, **Parallel Critic Auditing**, and an **Immutable Event Audit Trail**.

---

## 🔄 Dual-Router Multi-Lane Workflow

AISwarm uses a **Host-1 / Host-2 multi-lane architecture** to optimize speed, security, and cost:

```
                      ┌────────────────────────┐
                      │    USER TASK INPUT     │
                      └───────────┬────────────┘
                                  │
                                  ▼
                      ┌────────────────────────┐
                      │     HOST-1 ROUTER      │
                      └───────────┬────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │ (Fast Lane)           │ (Production Lane)     │ (Hybrid Lane)
          ▼                       ▼                       ▼
┌──────────────────┐   ┌────────────────────┐   ┌────────────────────┐
│ HOST-2 CAPABILITY│   │ BOSS AGENT CONTROL │   │ HYBRID DECOMPOSER  │
│     MANAGER      │   │     PIPELINE       │   │ (Fast + Boss)      │
└─────────┬────────┘   └──────────┬─────────┘   └──────────┬─────────┘
          │                       │                        │
          └───────────────────────┼────────────────────────┘
                                  │
                                  ▼
                      ┌────────────────────────┐
                      │  ENGINEERING GOVERNOR  │
                      └───────────┬────────────┘
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

### 1. Host-1 Global Router (`aiswarm/agents/host1/router.py`)
- Evaluates task surface sensitivity, blast radius, and scope.
- Automatically selects the optimal execution lane:
  - `FAST`: Direct capability execution via Host-2 (0.1s latency).
  - `PRODUCTION`: Full 12-stage hierarchical pipeline with Boss, Manager, Coder, and 8 Critics.
  - `HYBRID`: Subtask decomposition — fast execution for simple components, Boss pipeline for sensitive modules.

### 2. Host-2 Capability Manager (`aiswarm/agents/host2/manager.py`)
- Executes fast-path tasks using pre-approved, sandboxed capability plugins.
- Auto-escalates complex or failed subtasks to the Boss pipeline using `EscalationPacket`.

### 3. Boss Agent Pipeline (`aiswarm/agents/boss/agent.py`)
- Coordinates the Manager, Task Planner, Coder, and 8 Critics.
- Resolves deadlocks and performs architectural arbitration.

---

## 🛡️ Enterprise Security Subsystem

### 1. Execution Sandbox (`aiswarm/security/sandbox.py`)
- Isolated subprocess environment with strict memory/CPU resource limits.
- Enforces explicit command allowlisting (`python`, `pytest`, `git`, `pip`).
- Workspace path isolation preventing directory traversal attacks.

### 2. Secret Redaction Engine (`aiswarm/security/redaction.py`)
- Multi-pattern regex engine scrubbing secrets before logging or persistence:
  - OpenAI Keys (`sk-...`)
  - Anthropic Keys (`sk-ant-...`)
  - GitHub PATs (`ghp_...`)
  - PyPI API Tokens (`pypi-...`)
  - Google API Keys (`AIza...`)
  - AWS Access Keys (`AKIA...`)

### 3. Engineering Governor (`aiswarm/security/governor.py`)
- Live budget tracking per session and per day.
- Spawning capability gates and release checks.

### 4. Immutable Audit Ledger (`aiswarm/security/audit.py`)
- Thread-safe `asyncio.Lock` event ledger.
- Persists all platform events to `~/.aiswarm/audit.jsonl` with startup recovery.

---

## ⚙️ Core Subsystem Reference

| Module | Location | Responsibilities |
|---|---|---|
| **Orchestrator** | `aiswarm/core/orchestrator.py` | Task lifecycle, concurrency semaphores, router & governor integration |
| **Workflow Engine** | `aiswarm/core/workflow_engine.py` | State machine execution, retries, critic orchestration |
| **State Machine** | `aiswarm/core/state_machine.py` | Validates task transitions (`NEW` → `PROMPTED` → `COMPILED` → `REVIEWED` → `MERGED`) |
| **Merge Controller** | `aiswarm/core/merge_controller.py` | 5-gate quality control before merging code to target paths |
| **Cost Guard** | `aiswarm/core/cost_guard.py` | Real-time token usage & USD cost recording |
