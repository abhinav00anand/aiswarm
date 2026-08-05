"""
Unit Tests for API Key Enforcement & Security Authentication.
"""

from aiswarm.security.auth import APIKeyValidator, SecurityAuthError


def test_verify_api_key_explicit():
    """Explicitly provided API key should pass validation."""
    assert APIKeyValidator.verify_api_keys(explicit_key="test-api-key-12345") is True


def test_verify_api_key_environment(monkeypatch):
    """Setting environment variable should pass validation."""
    monkeypatch.setenv("AISWARM_API_KEY", "aiswarm_secret_key_9999")
    assert APIKeyValidator.verify_api_keys() is True


def test_verify_api_key_missing(monkeypatch):
    """Missing all API keys should raise SecurityAuthError."""
    for key in ["AISWARM_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "NOVITA_API_KEY", "DEEPSEEK_API_KEY"]:
        monkeypatch.delenv(key, raising=False)

    raised = False
    try:
        APIKeyValidator.verify_api_keys()
    except SecurityAuthError:
        raised = True
    assert raised is True

