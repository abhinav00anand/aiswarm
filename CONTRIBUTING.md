# Contributing to AISwarm-Next

Thank you for your interest in contributing to **AISwarm-Next**! Follow this guide to set up your local development environment, run test suites, and submit pull requests.

---

## 🛠 Local Development Setup

### 1. Clone the Repository
```bash
git clone https://github.com/abhinav00anand/aiswarm-next.git
cd aiswarm-next
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

AISwarm-Next includes comprehensive unit, stress, and concurrency benchmark suites:

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
