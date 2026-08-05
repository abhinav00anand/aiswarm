# AISwarm Security Policy & Threat Model

---

## 🔒 Security Architecture Overview

AISwarm is engineered with a **Zero-Trust Security** model to safely run multi-agent code generation, execute untrusted scripts, and interact with external LLM APIs without risking data loss or credential leakage.

---

## 🛡️ Core Security Controls

### 1. Mandatory Fail-Fast Authentication (`APIKeyValidator`)
- Requires valid API keys at application startup.
- Unauthenticated initialization immediately throws `SecurityAuthError` and aborts execution.

### 2. Isolated Process Execution (`ExecutionSandbox`)
- All user/agent code is executed in isolated subprocesses.
- Command allowlisting prevents unauthorized binary execution.
- Path resolution blocks any attempts to access files outside the allocated workspace.

### 3. Multi-Pattern Secret Redaction (`SecretRedactor`)
- Every prompt, response, log entry, and audit payload is scrubbed before disk write or display.
- Detects and replaces OpenAI, Anthropic, GitHub, PyPI, Google, and AWS key patterns with `***REDACTED***`.

### 4. Engineering Governor (`EngineeringGovernor`)
- Session and daily cost caps prevent unauthorized API usage spikes.
- Restricts capability invocation based on user roles (`WORKER`, `MANAGER`, `BOSS`).

### 5. Immutable Audit Trail (`AuditLedger`)
- All security decisions, route choices, policy evaluations, and merge attempts are recorded in `~/.aiswarm/audit.jsonl`.

---

## 🚨 Reporting a Vulnerability

If you discover a potential security vulnerability within AISwarm:

1. **Do NOT open a public issue on GitHub.**
2. Send a confidential report to `security@aiswarm.org` or contact the repository maintainer directly.
3. Include detailed steps to reproduce the issue, along with any relevant code snippets or environment details.
4. The maintainers will respond within **24 hours** and provide a patch release timeline.
