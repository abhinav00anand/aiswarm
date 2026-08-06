"""
Pre-Check Agent — lightweight, fast validation before sending code to Critics.

Catches obvious issues before spending expensive critic tokens:
  - Syntax errors (via compile() for Python)
  - Forbidden import patterns
  - Placeholder / TODO detection
  - Minimum length sanity check
  - Basic structural checks (class/function presence)

Uses a micro-model for speed and cost efficiency.
"""

from __future__ import annotations

import ast
import re
from typing import Any

import structlog

from aiswarm.agents.base.agent import BaseAgent
from aiswarm.llm.adapter import LLMMessage
from aiswarm.schemas.task import Task
from aiswarm.security.code_scanner import CodeScanner

logger = structlog.get_logger(__name__)

_FORBIDDEN_PATTERNS = [
    (r"\bTODO\b", "Placeholder TODO found"),
    (r"\bFIXME\b", "Placeholder FIXME found"),
    (r"\bpass\s*#.*placeholder", "Placeholder pass found"),
    (r"raise\s+NotImplementedError", "NotImplementedError placeholder"),
    (r"\.\.\.(\s*#.*)?$", "Ellipsis placeholder (...)"),
    (r"os\.system\s*\(", "Forbidden: os.system"),
    (r"subprocess\.Popen", "Forbidden: subprocess.Popen"),
    (r"\beval\s*\(", "Forbidden: eval()"),
    (r"\bexec\s*\(", "Forbidden: exec()"),
    (r"pickle\.loads\s*\(", "Forbidden: pickle.loads (unsafe deserialization)"),
]

_SYSTEM_PROMPT = """\
You are the Pre-Check Agent. Perform a rapid quality check on the submitted code.

Check for:
1. Any TODO, FIXME, placeholder, or mock implementation
2. Missing type annotations on public functions/methods
3. Missing docstrings on public classes and functions
4. Obvious logical errors (wrong return types, undefined variables)
5. Use of forbidden APIs (os.system, eval, exec, pickle.loads)

Output JSON:
{
  "passed": true|false,
  "issues": ["issue description if any"],
  "severity": "BLOCK|WARN"
}
If passed=false, the coder must rewrite before critics see the code.
"""


class PreCheckAgent(BaseAgent):
    """Lightweight pre-validation before critic review."""

    role = "precheck"
    _scanner: CodeScanner = CodeScanner()

    async def run(self, task: Task) -> bool:
        """
        Run pre-checks on task.generated_code.
        Sets task.precheck_passed.
        Returns True if code passed all checks.
        """
        code = task.generated_code or ""
        if not code.strip():
            task.precheck_passed = False
            logger.warning("precheck.empty_code", task_id=task.task_id)
            return False

        # ── Security scan (hard gate — fail-closed on CRITICAL/HIGH) ─────────
        scan_result = self._scanner.scan(code, language=task.target_language)
        if not scan_result.clean:
            task.precheck_passed = False
            task.metadata["scan_violations"] = scan_result.violations
            task.metadata["scan_warnings"] = scan_result.warnings
            logger.warning(
                "precheck.security_scan_failed",
                task_id=task.task_id,
                violations=scan_result.violations,
            )
            return False
        # Persist warnings (non-blocking) for critic context
        if scan_result.warnings:
            task.metadata["scan_warnings"] = scan_result.warnings

        # ── Static checks (no LLM needed) ────────────────────────────────────
        static_issues = self._static_check(code, task.target_language)
        if static_issues:
            task.precheck_passed = False
            # Append issues as a pseudo-review so coder can see them
            task.metadata["precheck_issues"] = static_issues
            logger.warning(
                "precheck.static_failed",
                task_id=task.task_id,
                issues=static_issues,
            )
            return False

        # ── LLM-assisted check ────────────────────────────────────────────────
        messages = [
            LLMMessage(role="system", content=_SYSTEM_PROMPT),
            LLMMessage(
                role="user",
                content=f"Language: {task.target_language}\n\nCode:\n```\n{code[:6000]}\n```",
            ),
        ]
        response = await self.call_llm(messages, task=task, temperature=0.0)
        result = self._parse_result(response.content)

        passed = result.get("passed", True)
        issues = result.get("issues", [])
        task.precheck_passed = passed
        if not passed:
            task.metadata["precheck_issues"] = issues
            logger.warning(
                "precheck.llm_failed",
                task_id=task.task_id,
                issues=issues,
            )
        else:
            logger.info("precheck.passed", task_id=task.task_id)
        return passed

    def _static_check(self, code: str, language: str) -> list[str]:
        issues: list[str] = []

        # Forbidden patterns
        for pattern, msg in _FORBIDDEN_PATTERNS:
            if re.search(pattern, code, re.MULTILINE | re.IGNORECASE):
                issues.append(msg)

        # Python syntax check
        if language == "python":
            try:
                ast.parse(code)
            except SyntaxError as exc:
                issues.append(f"Syntax error: {exc.msg} at line {exc.lineno}")

        # Minimum length
        if len(code.strip()) < 50:
            issues.append("Code too short — likely incomplete")

        return issues

    def _parse_result(self, content: str) -> dict[str, Any]:
        import json
        text = content.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                res = json.loads(text[start:end])
                if isinstance(res, dict) and "passed" in res:
                    return res
            except json.JSONDecodeError:
                pass
        logger.warning("precheck.parse_malformed_failing_closed", content_snippet=content[:100])
        return {"passed": False, "issues": ["Malformed precheck output from model — failing closed"], "severity": "BLOCK"}

