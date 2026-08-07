# Zymis Deep Architecture Specification

---

## 🏛 Executive Summary & Core Philosophy

**Zymis** is designed as a distributed, event-driven multi-agent orchestration architecture. Unlike linear AI code generators, Zymis models a complete software engineering lifecycle—incorporating executive decision-making, planning, coding, multi-perspective critic auditing, subprocess sandboxing, and immutable event ledger auditing.

The design principles behind Zymis are:
1. **Multi-Lane Execution Efficiency**: Match the complexity of the task with the depth of the pipeline. Low-risk actions run fast; high-risk changes undergo full engineering debate.
2. **Zero-Trust Process Isolation**: Assume all generated code is untrusted until compiled, sandboxed, tested, and audited.
3. **Immutable Observability**: Every state transition, routing choice, token spend, and security evaluation must be recorded in an append-only ledger.

---

## 🔄 Dual-Router Multi-Lane Workflow

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
                               └───────────┬────────────┘
                                           │
                                           ▼
                               ┌────────────────────────┐
                               │  5-GATE MERGE CONTROL  │
                               └────────────────────────┘
```

---

## 🧩 Comprehensive Component Overview

### 1. Host-1 Global Router (`zymis/agents/host1/router.py`)
- Evaluates task surface sensitivity (14 security keywords: `auth`, `payment`, `crypto`, `exec`, `shell`, `chmod`, `sudo`, `eval`, `sandbox`, `delete`, `drop`, `truncate`, `key`, `secret`).
- Determines scope and potential blast radius.
- Assigns route decisions:
  - `FAST`: Task is simple, non-sensitive, and maps to known capabilities.
  - `PRODUCTION`: Task alters critical code or requires architectural deliberation.
  - `HYBRID`: Decomposes large tasks, assigning simple parts to Host-2 and complex parts to Boss.

### 2. Host-2 Capability Manager (`zymis/agents/host2/manager.py`)
- Maintains a registry of pre-approved capabilities (`CapabilityRegistry`).
- Executes fast-path requests in ~0.1s without invoking multi-critic debate.
- If capability execution fails or encounters ambiguity, it constructs an `EscalationPacket` and delegates to the Boss pipeline.

### 3. Boss Agent Pipeline (`zymis/agents/boss/agent.py`)
- **Boss Agent**: Serves as CTO, resolving deadlocks, reviewing blueprints, and approving force merges.
- **Manager Agent**: Acts as Engineering Lead, creating subtask dependency trees.
- **Task Planner Agent**: Generates step-by-step technical blueprints before code generation begins.
- **Coder Agent**: Translates blueprints into clean Python code and pytest suites.

### 4. 8 Specialized Critic Agents (`zymis/agents/critics/`)
Executed concurrently during Stage 7:
1. `SecurityCritic`: OWASP Top 10, injection, path traversal, hardcoded key audit. Holds veto power.
2. `ArchitectureCritic`: SOLID design, pattern consistency, module decoupling.
3. `PerformanceCritic`: Time/space complexity, memory allocation efficiency.
4. `MaintainabilityCritic`: Cyclomatic complexity, code duplicate detection.
5. `ReliabilityCritic`: Exception boundary checks, null handling, edge cases.
6. `StyleCritic`: PEP 8 compliance, docstrings, formatting.
7. `TestingCritic`: Pytest suite coverage and assertion quality.
8. `DocumentationCritic`: Docstrings, type hint coverage, guide clarity.

---

## 🔒 Security Subsystem

```text
┌────────────────────────────────────────────────────────────────────────┐
│                   ENTERPRISE SECURITY SUBSYSTEM                        │
├───────────────────┬───────────────────┬────────────────────────────────┤
│ APIKeyValidator   │ ExecutionSandbox  │ SecretRedactor                 │
│ Fail-Fast Startup │ Subprocess Caps   │ Multi-Pattern Regex Scrubbing  │
├───────────────────┼───────────────────┼────────────────────────────────┤
│ EngineeringGov    │ PolicyEngine      │ AuditLedger                    │
│ USD Spend Caps    │ Central Rule Engine│ Immutable JSONL Persistence   │
└───────────────────┴───────────────────┴────────────────────────────────┘
```

### 1. `ExecutionSandbox` (`zymis/security/sandbox.py`)
- Executes Python scripts and Pytest suites in isolated subprocesses.
- Command Allowlisting: Restricts commands to `python`, `pytest`, `git`, `pip`.
- Path Isolation: Resolves paths canonically to verify they stay inside `workspace_dir`.

### 2. `SecretRedactor` (`zymis/security/redaction.py`)
- Intercepts all output channels (logs, terminal stdout, audit events).
- Scrubs API keys using multi-pattern regex matching:
  - OpenAI (`sk-...` / `sk-proj-...`)
  - Anthropic (`sk-ant-...`)
  - GitHub (`ghp_...`)
  - PyPI (`pypi-...`)
  - Google (`AIza...`)
  - AWS (`AKIA...`)

### 3. `EngineeringGovernor` (`zymis/security/governor.py`)
- Monitors token usage via `CostGuard` and calculates real-time USD costs.
- Enforces session budget caps and daily spend limits.
- Evaluates capability spawn permissions by role (`WORKER`, `MANAGER`, `BOSS`).

### 4. `AuditLedger` (`zymis/security/audit.py`)
- Thread-safe `asyncio.Lock` append-only audit trail.
- Persists all platform events to `~/.zymis/audit.jsonl`.
- Automatically recovers historical log state on startup.

---

## 🚦 Finite State Machine (FSM) Lifecycle

```text
NEW ──► PROMPTED ──► COMPILED ──► REVIEWED ──► MERGED (Terminal)
 │          │            │            │
 ├──────────┴────────────┴────────────┼──► REJECTED (Terminal)
 │                                    │
 ├────────────────────────────────────┼──► DEADLOCK ──► ESCALATED ──► MERGED
 │                                    │
 └────────────────────────────────────┴──► CANCELLED (Terminal)
```

---

## 🛡 5-Gate Merge Controller

Before generated code is written to the repository path, it must pass 5 sequential quality gates:
1. **Compilation Gate**: Bytecode compilation and AST syntax validation.
2. **Unit Test Gate**: Execution of generated pytest suite inside sandbox with 0 failures.
3. **Performance Gate**: Algorithmic complexity and time budget check.
4. **Security Gate**: Security Critic review with 0 fatal flaws and 0 security vetoes.
5. **Path Resolution Gate**: Canonical path verification ensuring output file remains inside project root.
