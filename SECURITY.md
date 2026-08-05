# AISwarm-Next Security Policy & Threat Model

---

## 🔒 Security Architecture & Vision

**AISwarm-Next** is designed with a **Zero-Trust Security Architecture**. Because autonomous AI agents generate, compile, and execute code dynamically, AISwarm-Next enforces strict boundaries to ensure generated code cannot breach process isolation, leak credentials, access host file systems, or exceed token budgets.

---

## 🛡 Security Controls Matrix

| Security Layer | Implementation Component | Defense Mechanism |
|---|---|---|
| **Authentication** | `APIKeyValidator` | Fail-fast boot guard; aborts startup if no valid API key is present. |
| **Process Isolation** | `ExecutionSandbox` | Subprocess sandboxing, command allowlisting (`python`, `pytest`, `git`, `pip`). |
| **Path Protection** | `ExecutionSandbox` | Canonical path verification preventing directory traversal escaping repository root. |
| **Secret Scrubbing** | `SecretRedactor` | Multi-pattern regex redacting OpenAI, Anthropic, GitHub, PyPI, Google, AWS keys. |
| **Governance** | `EngineeringGovernor` | Real-time USD spend caps (`CostGuard`), token budgets, capability spawn gates. |
| **Observability** | `AuditLedger` | Thread-safe, append-only JSONL log (`~/.aiswarm/audit.jsonl`) with startup recovery. |
| **Policy Engine** | `PolicyEngine` | Central rule engine evaluating `ALLOW`, `DENY`, `REQUIRE_HITL`. |

---

## 🔍 Detailed Security Controls

### 1. Fail-Fast Startup Authentication (`APIKeyValidator`)
`APIKeyValidator` inspects the environment during initialization (`aiswarm/security/auth.py`). If no valid provider key (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`) is found, initialization halts immediately with a `SecurityAuthError`.

### 2. Subprocess Execution Sandbox (`ExecutionSandbox`)
All code execution occurs inside isolated subprocesses managed by `ExecutionSandbox` (`aiswarm/security/sandbox.py`):
- **Command Allowlisting**: Only explicitly approved commands can be executed. Attempts to run arbitrary binaries (`curl`, `bash`, `powershell`, `rm`) trigger a `SandboxViolationError`.
- **Path Traversal Protection**: Prevents path manipulation attacks (`../etc/passwd`, `C:\Windows`) by validating canonical resolved paths against `workspace_dir`.

### 3. Multi-Pattern Secret Redaction (`SecretRedactor`)
`SecretRedactor` (`aiswarm/security/redaction.py`) intercepts all strings flowing to logs, stdout, prompts, or audit event payloads:
```text
OpenAI Key      : sk-proj-123456789...  ──►  ***OPENAI_KEY***
Anthropic Key   : sk-ant-123456789...   ──►  ***ANTHROPIC_KEY***
GitHub PAT      : ghp_123456789...      ──►  ***GH_PAT***
PyPI Token      : pypi-AgEI12345...     ──►  ***REDACTED***
Google Key      : AIzaSy12345...        ──►  ***GOOGLE_KEY***
AWS Access Key  : AKIA12345678...       ──►  ***AWS_KEY***
```

### 4. Immutable Audit Ledger (`AuditLedger`)
Every event is assigned a UUID, timestamped, typed (`ROUTE_DECISION`, `TOOL_SPAWN`, `POLICY_VIOLATION`, `MERGE`), and appended to `~/.aiswarm/audit.jsonl` using an async `Lock` (`aiswarm/security/audit.py`).

---

## 🚨 Confidential Vulnerability Reporting

If you discover a security vulnerability in AISwarm-Next:

1. **Do NOT open a public issue on GitHub.**
2. Send a confidential report to `security@aiswarm.org`.
3. Include reproduction steps, sample payloads, and impact assessment.
4. Maintainers will respond within **24 hours** and issue a patch release.
