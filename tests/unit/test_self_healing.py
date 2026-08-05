"""
Unit Tests for Self-Healing Engine.
"""

from aiswarm.core.self_healing import FailureCategory, SelfHealingEngine


def test_classify_missing_import():
    """ModuleNotFoundError should be classified as MISSING_IMPORT."""
    stderr = "Traceback:\nModuleNotFoundError: No module named 'requests'"
    classified = SelfHealingEngine.classify_failure(stderr)
    assert classified["category"] == FailureCategory.MISSING_IMPORT
    assert classified["missing_package"] == "requests"
    assert classified["auto_fixable"] is True


def test_classify_syntax_error():
    """SyntaxError should be classified as SYNTAX_ERROR."""
    stderr = "SyntaxError: invalid syntax line 4"
    classified = SelfHealingEngine.classify_failure(stderr)
    assert classified["category"] == FailureCategory.SYNTAX_ERROR
    assert classified["auto_fixable"] is True


def test_auto_repair_missing_import():
    """Missing import should generate an auto-repair patch."""
    engine = SelfHealingEngine()
    failure = {"category": FailureCategory.MISSING_IMPORT, "missing_package": "json"}
    code = "data = json.loads('{}')"
    repaired = engine.attempt_auto_repair(code, failure)
    assert repaired["repaired"] is True
    assert "import json" in repaired["code"]
