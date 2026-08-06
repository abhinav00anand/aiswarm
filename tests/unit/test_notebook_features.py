"""
Unit Tests for Ephemeral Notebook & Kaggle support features.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from aiswarm.security.auth import APIKeyValidator, SecurityAuthError
from aiswarm.llm.provider_router import ProviderRouter, _resolve_model
from aiswarm.bootstrap.startup import build_orchestrator


def test_validate_adapter_url_success():
    """Test validate_adapter_url returns True when mock endpoints respond successfully."""
    from aiswarm.security.auth import validate_adapter_url

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response

        assert validate_adapter_url("http://127.0.0.1:8000") is True


def test_validate_adapter_url_failure():
    """Test validate_adapter_url returns False when connection is refused."""
    from aiswarm.security.auth import validate_adapter_url

    with patch("urllib.request.urlopen", side_effect=Exception("Connection Refused")):
        assert validate_adapter_url("http://127.0.0.1:9999") is False


def test_verify_api_keys_selection_priority(monkeypatch):
    """Test selection priority for api keys, local-adapter, and Ollama."""
    # 1. Cloud keys override
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    assert APIKeyValidator.verify_api_keys() is True

    # 2. Adapter override takes precedence if cloud keys are missing but adapter is set and validated
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.setenv("OPENAI_API_ADAPTER_URL", "http://127.0.0.1:8000")
    
    with patch("aiswarm.security.auth.validate_adapter_url", return_value=True):
        assert APIKeyValidator.verify_api_keys() is True

    # 3. If validation fails and AISWARM_NO_OLLAMA is set, raises SecurityAuthError
    monkeypatch.setenv("AISWARM_NO_OLLAMA", "1")
    with patch("aiswarm.security.auth.validate_adapter_url", return_value=False):
        with pytest.raises(SecurityAuthError):
            APIKeyValidator.verify_api_keys()


def test_provider_router_adapter_override(monkeypatch):
    """Test that ProviderRouter creates, prioritizes, and configures the adapter provider."""
    monkeypatch.setenv("OPENAI_API_ADAPTER_URL", "http://127.0.0.1:8000")
    
    # Mock validation and get_adapter_model
    with patch("aiswarm.llm.provider_router.get_adapter_model", return_value="distilgpt2"):
        router = ProviderRouter()
        assert "adapter" in router._providers
        
        # Test model resolution
        resolved = _resolve_model("some-large-model", "adapter")
        assert resolved == "distilgpt2"


def test_notebook_mode_environment_and_model_overrides(monkeypatch):
    """Test build_orchestrator configurations when AISWARM_NOTEBOOK_MODE=1 is set."""
    monkeypatch.setenv("AISWARM_NOTEBOOK_MODE", "1")
    monkeypatch.setenv("OPENAI_API_ADAPTER_URL", "http://127.0.0.1:8000")
    
    # Prevent real authentication checks failing
    with patch("aiswarm.security.auth.APIKeyValidator.verify_api_keys", return_value=True), \
         patch("aiswarm.llm.provider_router.get_adapter_model", return_value="distilgpt2"):
         
        orc, lifecycle = build_orchestrator(repo_root=".")
        
        # Verify CPU threads variables are set to 1
        assert os.environ.get("OMP_NUM_THREADS") == "1"
        assert os.environ.get("MKL_NUM_THREADS") == "1"
        
        # Verify agents default to the adapter/distilgpt2 model
        boss = orc._agents.get("boss")
        assert boss._model == "distilgpt2"
        assert "adapter" in boss._provider_pref
