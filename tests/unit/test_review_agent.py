"""Unit tests for Antigravity PR Review Agent."""

from __future__ import annotations

from scripts.review_agent import (
    build_review_markdown,
    parse_diff_valid_lines,
)


def test_parse_diff_valid_lines() -> None:
    sample_diff = """\
diff --git a/foo.py b/foo.py
--- a/foo.py
+++ b/foo.py
@@ -10,3 +10,5 @@ def bar():
+    x = 1
+    y = 2
"""
    result = parse_diff_valid_lines(sample_diff)
    assert "foo.py" in result
    assert 10 in result["foo.py"]
    assert 11 in result["foo.py"]
    assert 14 in result["foo.py"]


def test_build_review_markdown() -> None:
    sample_review = {
        "verdict": "REQUEST_CHANGES",
        "overall_score": 65,
        "production_ready": False,
        "executive_summary": "PR contains critical security and maintainability flaws.",
        "gate_evaluations": {
            "CompilationGate": {"status": "PASS", "notes": "Syntax valid"},
            "UnitTestGate": {"status": "FAIL", "notes": "Missing unit tests"},
            "PerformanceGate": {"status": "PASS", "notes": "O(1) complexity"},
            "SecurityGate": {"status": "FAIL", "notes": "Plaintext secret detected"},
            "PathResolutionGate": {"status": "PASS", "notes": "Within repo"},
        },
        "critic_evaluations": {
            "SecurityCritic": {"status": "FAIL", "score": 2, "notes": "Exposed key"},
            "ArchitectureCritic": {"status": "PASS", "score": 8, "notes": "Modular"},
            "MaintainabilityCritic": {"status": "WARN", "score": 5, "notes": "Long function"},
        },
        "critical_flaws": [
            {
                "title": "Hardcoded Secret",
                "what_is_wrong": "API key committed directly in source.",
                "what_is_needed": "Use SecretRedactor or environment variables.",
            }
        ],
        "positive_highlights": ["Clean type hints on new interfaces"],
        "general_recommendations": ["Add pytest tests in tests/unit/"],
    }

    markdown = build_review_markdown(sample_review, pr_title="Add new feature", pr_number=42)

    assert "## 🛸 Google Antigravity PR Review — Zymis Framework" in markdown
    assert "PR #42: Add new feature" in markdown
    assert "**65 / 100**" in markdown
    assert "`REQUEST_CHANGES`" in markdown
    assert "Gate 4: Enterprise Security & Secrets" in markdown
    assert "Hardcoded Secret" in markdown
    assert "**What is wrong:**" in markdown
    assert "**What is needed:**" in markdown
