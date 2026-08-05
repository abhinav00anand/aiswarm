"""Test result parser — extracts structured data from pytest/compiler output."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ParsedTestResult:
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    total: int = 0
    duration_seconds: float = 0.0
    failure_messages: list[str] = field(default_factory=list)
    coverage_pct: float = 0.0


def parse_pytest_output(output: str) -> ParsedTestResult:
    """Parse pytest terminal output into structured data."""
    result = ParsedTestResult()

    # Match summary line: "5 passed, 2 failed, 1 skipped in 3.14s"
    summary_pattern = r"(\d+)\s+passed|(\d+)\s+failed|(\d+)\s+skipped|(\d+)\s+error"
    for m in re.finditer(summary_pattern, output, re.IGNORECASE):
        if m.group(1):
            result.passed = int(m.group(1))
        elif m.group(2):
            result.failed = int(m.group(2))
        elif m.group(3):
            result.skipped = int(m.group(3))
        elif m.group(4):
            result.errors = int(m.group(4))

    # Duration
    duration_match = re.search(r"in\s+([\d.]+)s", output)
    if duration_match:
        result.duration_seconds = float(duration_match.group(1))

    # Coverage
    cov_match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)
    if cov_match:
        result.coverage_pct = float(cov_match.group(1))

    # Failure messages
    fail_blocks = re.findall(r"FAILED\s+(.+?)(?=FAILED|\Z)", output, re.DOTALL)
    result.failure_messages = [b.strip()[:500] for b in fail_blocks[:10]]

    result.total = result.passed + result.failed + result.skipped + result.errors
    return result


def parse_compiler_output(output: str, language: str = "python") -> dict[str, object]:
    """Extract key info from compiler/interpreter output."""
    has_error = any(kw in output for kw in ("Error:", "error:", "SyntaxError", "ImportError", "Traceback"))
    errors: list[str] = []
    if language == "python":
        errors = re.findall(r"(?:Error|Exception):\s+(.+)", output)
    return {
        "has_error": has_error,
        "errors": errors[:5],
        "output_preview": output[:500],
    }
