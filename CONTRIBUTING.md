# Contributing to Zymis

Thank you for your interest in contributing to **Zymis**! Follow this guide to set up your local development environment, run test suites, and submit pull requests.

---

## 🛠 Local Development Setup

### 1. Clone the Repository
```bash
git clone https://github.com/abhinav00anand/zymis.git
cd zymis
```

### 2. Create & Activate Virtual Environment
```bash
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate

# On Windows PowerShell:
.venv\Scripts\activate
```

### 3. Install Editable Package & Dev Dependencies
```bash
pip install -e ".[dev]"
```

---

## 🧪 Running Test Suites

Zymis includes comprehensive unit, stress, and concurrency benchmark suites:

```bash
# 1. Run Unit Test Suite (210 tests)
python -m pytest tests/unit/ -v

# 2. Run Stress & Fuzzing Test Suite (131 tests)
python -m pytest tests/stress/ -v

# 3. Code Formatting & Static Analysis
ruff check .
mypy .
```

---

## 📋 Pull Request Submission Checklist

Before submitting your Pull Request:

1. **Unit Test Coverage**: Ensure all new features include unit tests in `tests/unit/`.
2. **Zero Credentials**: Verify no API keys, secrets, or tokens are committed.
3. **Pass Rate**: Confirm 100% pass rate across unit and stress test suites.
4. **Documentation**: Update docstrings and relevant markdown files.
5. **PR Target**: Submit your PR against the `main` branch.

---

## 🛸 Automated Code Review (Google Antigravity)

All pull requests are automatically audited by our **Google Antigravity PR Review Agent** against Zymis's 8-Critic Architecture and 5-Gate Merge standards.

- The agent evaluates Architecture, Security, Maintainability, Reliability, Performance, Testing, and Style.
- Inline suggestions (`what is wrong` and `what is needed`) with one-click GitHub suggestions will be posted directly to your PR.
- You can trigger or re-run a review anytime by commenting `@agy /review` or `/review` on your PR.
- For complete details, see [docs/antigravity_pr_review.md](docs/antigravity_pr_review.md).

