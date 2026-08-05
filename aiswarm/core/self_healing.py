"""
Self-Healing & Replay Engine — Automatic Failure Classification & Auto-Repair.

Analyzes compiler/test execution output to classify failure patterns (e.g. missing imports,
syntax errors, type mismatches) and applies safe auto-repairs or targeted retries.
"""

from __future__ import annotations

import re
from typing import Any

from aiswarm.utils.compat_log import get_logger

logger = get_logger(__name__)


class FailureCategory:
    MISSING_IMPORT = "MISSING_IMPORT"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    TYPE_ERROR = "TYPE_ERROR"
    ASSERTION_FAILURE = "ASSERTION_FAILURE"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


class SelfHealingEngine:
    """Classifies runtime and compiler failures and suggests deterministic repairs."""

    @staticmethod
    def classify_failure(stderr_output: str, stdout_output: str = "") -> dict[str, Any]:
        """Classify execution failure from error output."""
        combined = f"{stderr_output}\n{stdout_output}"

        if "ModuleNotFoundError" in combined or "No module named" in combined:
            match = re.search(r"No module named ['\"]([^'\"]+)['\"]", combined)
            missing_pkg = match.group(1) if match else "unknown"
            return {
                "category": FailureCategory.MISSING_IMPORT,
                "missing_package": missing_pkg,
                "repair_suggestion": f"Install or import missing package '{missing_pkg}'",
                "auto_fixable": True,
            }

        if "SyntaxError" in combined or "IndentationError" in combined:
            return {
                "category": FailureCategory.SYNTAX_ERROR,
                "repair_suggestion": "Format code with ruff/black and verify matching brackets/indentation",
                "auto_fixable": True,
            }

        if "TypeError" in combined or "AttributeError" in combined:
            return {
                "category": FailureCategory.TYPE_ERROR,
                "repair_suggestion": "Verify variable types and method signatures against schema",
                "auto_fixable": False,
            }

        if "AssertionError" in combined or "FAILED" in combined:
            return {
                "category": FailureCategory.ASSERTION_FAILURE,
                "repair_suggestion": "Review failed assertion assertions and update test logic or code implementation",
                "auto_fixable": False,
            }

        if "Timeout" in combined or "timed out" in combined:
            return {
                "category": FailureCategory.TIMEOUT,
                "repair_suggestion": "Increase execution timeout or optimize algorithmic performance",
                "auto_fixable": False,
            }

        return {
            "category": FailureCategory.UNKNOWN,
            "repair_suggestion": "Escalate to Boss for deep reasoning and deadlock resolution",
            "auto_fixable": False,
        }

    def attempt_auto_repair(self, code: str, failure_info: dict[str, Any]) -> dict[str, Any]:
        """Apply deterministic auto-repair patch if eligible."""
        cat = failure_info.get("category")
        if cat == FailureCategory.MISSING_IMPORT:
            pkg = failure_info.get("missing_package")
            if pkg and f"import {pkg}" not in code:
                repaired_code = f"import {pkg}\n" + code
                logger.info("self_healing.auto_repair_applied", category=cat, package=pkg)
                return {
                    "repaired": True,
                    "code": repaired_code,
                    "patch_description": f"Added missing import statement for '{pkg}'",
                }

        logger.info("self_healing.auto_repair_skipped", category=cat)
        return {"repaired": False, "code": code, "patch_description": "No auto-repair patch applicable"}
