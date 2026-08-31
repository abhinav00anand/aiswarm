# Google Antigravity PR Review Agent for Zymis

This document describes the autonomous AI-powered Pull Request (PR) code review agent for the **Zymis** multi-agent orchestration framework, powered by **Google Antigravity** (Google Gemini).

---

## 🛸 Overview

The Antigravity PR Review Agent provides automated, senior-level code reviews on every incoming Pull Request to `abhinav00anand/zymis`. It evaluates submitted changes against Zymis's core architectural tenets, security safeguards, and multi-critic quality standards.

The reviewer performs deep inspection, generating:
1. **Executive Verdict & Score (0-100)**: Quick assessment of production readiness and merge safety.
2. **5-Gate Merge Controller Audit**: Gate-by-gate verification (Compilation, Unit Tests, Performance, Security, Path Resolution).
3. **8-Critic Architectural Matrix**: Granular scores across Security, Architecture, Maintainability, Reliability, Performance, Testing, Style, and Documentation.
4. **Actionable Inline Comments**:
   - **What is wrong**: Clear, specific explanation of defect or risk.
   - **What is needed**: Exact instructions on required fixes.
   - **One-Click Code Suggestions**: GitHub markdown diff blocks allowing maintainers to accept fixes directly on GitHub.

---

## ⚙️ Setup & Configuration

### 1. Configure GitHub Secrets

The review agent requires a Google Gemini / Antigravity API key to perform automated reasoning.

1. Obtain an API key from [Google AI Studio](https://aistudio.google.com/app/api-keys).
2. Go to your GitHub repository: **Settings > Secrets and variables > Actions**.
3. Click **New repository secret**:
   - **Name**: `ANTIGRAVITY_API_KEY` (or `GEMINI_API_KEY`)
   - **Secret**: `<Your Google API Key>`
4. The workflow utilizes the default `GITHUB_TOKEN` provided by GitHub Actions for commenting and reviewing.

---

## 🚀 Triggering Reviews

The agent can be invoked through three mechanisms:

### A. Automatic on Pull Request Events
Whenever a Pull Request is opened, synchronized (new commits pushed), or reopened against `main`, the workflow automatically runs.

### B. On-Demand PR Comment Trigger
Repository collaborators and contributors can trigger a review or re-review anytime by commenting on the PR:

```text
@agy /review
```
or:
```text
/review focus on concurrency safety and memory limits
```
Any custom text following `/review` is passed as specific review instructions to the agent.

### C. Manual Trigger (`workflow_dispatch`)
In the GitHub Actions tab, navigate to **Antigravity PR Review**, click **Run workflow**, enter the PR number and any custom instructions.

---

## 🧪 Local Dry-Run Testing

Developers can run the Antigravity review locally before pushing changes:

```bash
# Review uncommitted changes or branch diff against origin/main
export ANTIGRAVITY_API_KEY="your-api-key"
python scripts/review_agent.py --dry-run

# Review a specific diff file
python scripts/review_agent.py --diff-file /path/to/sample.diff --dry-run
```

---

## 🏛 Review Criteria Reference

The agent is strictly grounded in Zymis's engineering standards:

| Gate / Critic | Evaluation Focus |
| :--- | :--- |
| **SecurityCritic** | Zero hardcoded keys (`sk-...`, `AIza...`, `ghp_...`), path traversal protection, subprocess isolation via `ExecutionSandbox`. *(Holds Veto Power)* |
| **ArchitectureCritic** | Dual-Router alignment (Host-1 lanes, Host-2 capabilities), Boss/Manager/Planner/Coder pipeline contracts, FSM states. |
| **MaintainabilityCritic** | Functions ≤ 50 lines (must decompose if >50), clean naming, no dead/commented-out code, full type annotations. |
| **ReliabilityCritic** | Robust error boundaries, async cancellation handling, bounded timeouts, null/None safety. |
| **PerformanceCritic** | Algorithmic complexity, non-blocking async loops, bounded memory. |
| **TestingCritic** | Pytest unit test coverage for new edge cases with 100% pass rate. |
| **StyleCritic** | Python 3.11+, Ruff strict compliance, structured logging via `structlog.get_logger(__name__)`. No bare `print()`. |
