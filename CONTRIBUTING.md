# Contributing to AISwarm

Thank you for your interest in contributing to **AISwarm**! We welcome contributions from the community.

---

## 🛠️ Local Development Setup

### 1. Clone the Repository
```bash
git clone https://github.com/abhinav00anand/aiswarm-next.git
cd aiswarm-next
```

### 2. Create a Virtual Environment & Install Dependencies
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

---

## 🧪 Running Tests

Before submitting a Pull Request, ensure all unit tests and stress tests pass:

```bash
# Run unit test suite (210 tests)
python -m pytest tests/unit/ -v

# Run stress & fuzzing test suite (131 tests)
python -m pytest tests/stress/ -v

# Code style checking
ruff check .
mypy .
```

---

## 📋 Pull Request Process

1. Create a descriptive feature branch: `git checkout -b feature/my-new-feature`
2. Write unit tests for all new functionality.
3. Ensure no credentials or API keys are committed.
4. Verify `pytest` passes with 100% success rate.
5. Push your branch and open a Pull Request against `main`.
