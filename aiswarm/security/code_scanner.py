"""
Static code scanner — detects dangerous patterns before execution.

Runs synchronously (no LLM) and is the first gate in the security pipeline.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field


@dataclass
class ScanResult:
    clean: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_DANGEROUS_PATTERNS = [
    (r"os\.system\s*\(", "CRITICAL: os.system() call"),
    (
        r"subprocess\.(Popen|call|check_call|check_output|run)\s*\(.*shell\s*=\s*True",
        "CRITICAL: shell=True subprocess",
    ),
    (r"\beval\s*\(", "CRITICAL: eval() usage"),
    (r"\bexec\s*\(", "CRITICAL: exec() usage"),
    (r"pickle\.loads?\s*\(", "CRITICAL: pickle deserialization"),
    (r"yaml\.load\s*\([^,)]+\)", "HIGH: yaml.load without Loader"),
    (r"hashlib\.(md5|sha1)\s*\(", "HIGH: Weak hash algorithm for security use"),
    (r"verify\s*=\s*False", "HIGH: verify=False disables TLS certificate verification"),
    (r"(?:SECRET|PASSWORD|TOKEN|API_KEY)\s*=\s*['\"][^'\"]+['\"]", "HIGH: Hardcoded secret"),
    (r"sk-[a-zA-Z0-9_\-]{32,}", "CRITICAL: Hardcoded OpenAI API key"),
    (r"ghp_[a-zA-Z0-9]{36}", "CRITICAL: Hardcoded GitHub PAT"),
    (r"AIza[0-9A-Za-z\-_]{35}", "CRITICAL: Hardcoded Google API key"),
    (r"pypi-[a-zA-Z0-9_\-]{50,}", "CRITICAL: Hardcoded PyPI API token"),
    (r"DEBUG\s*=\s*True", "MEDIUM: Debug mode enabled"),
    (r"__import__\s*\(", "MEDIUM: Dynamic import"),
    (r"getattr\s*\(.*,\s*input\s*\(", "HIGH: Unsafe getattr with user input"),
]


class CodeScanner:
    """
    Fast static scanner — runs regex + AST checks on generated code.
    """

    def scan(self, code: str, language: str = "python") -> ScanResult:
        violations: list[str] = []
        warnings: list[str] = []

        for pattern, msg in _DANGEROUS_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                severity = msg.split(":")[0]
                if severity in ("CRITICAL", "HIGH"):
                    violations.append(msg)
                else:
                    warnings.append(msg)

        if language == "python":
            ast_issues = self._ast_scan(code)
            violations.extend(ast_issues)

        return ScanResult(
            clean=len(violations) == 0,
            violations=violations,
            warnings=warnings,
        )

    def _ast_scan(self, code: str) -> list[str]:
        issues: list[str] = []
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return ["CRITICAL: SyntaxError — code is not valid Python"]

        for node in ast.walk(tree):
            # Detect bare except clauses (swallows all errors)
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                issues.append("MEDIUM: Bare except clause — swallows all exceptions")

            # Detect assert statements in production code
            if isinstance(node, ast.Assert):
                issues.append("LOW: assert statement (optimized away with -O flag)")

        return issues
