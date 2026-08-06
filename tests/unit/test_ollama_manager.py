"""
Unit tests for the Ollama Auto-Provisioning & Security Fallback Subsystem.
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock

from aiswarm.llm.ollama_manager import OllamaManager, MODEL_LARGE, MODEL_MEDIUM, MODEL_SMALL
from aiswarm.llm.local_models import LocalModelAdapter
from aiswarm.llm.adapter import LLMMessage
from aiswarm.security.auth import APIKeyValidator, SecurityAuthError
from aiswarm.security.audit import get_audit_ledger


class TestOllamaManager:
    def test_disk_space_model_selection(self) -> None:
        """Test model selection based on disk space thresholds."""
        assert OllamaManager.select_model_for_space(20.0) == MODEL_LARGE
        assert OllamaManager.select_model_for_space(16.0) == MODEL_LARGE
        assert OllamaManager.select_model_for_space(12.0) == MODEL_MEDIUM
        assert OllamaManager.select_model_for_space(8.0) == MODEL_MEDIUM
        assert OllamaManager.select_model_for_space(4.0) == MODEL_SMALL
        assert OllamaManager.select_model_for_space(0.5) == MODEL_SMALL

    def test_get_free_disk_gb_returns_positive_float(self) -> None:
        free_gb = OllamaManager.get_free_disk_gb(".")
        assert isinstance(free_gb, float)
        assert free_gb >= 0.0

    @patch.object(OllamaManager, "is_service_running", return_value=True)
    @patch.object(OllamaManager, "pull_model", return_value=True)
    def test_ensure_ollama_provisioned_success(self, mock_pull: MagicMock, mock_running: MagicMock) -> None:
        manager = OllamaManager()
        ok, model = manager.ensure_ollama_provisioned()
        assert ok is True
        assert model in [MODEL_LARGE, MODEL_MEDIUM, MODEL_SMALL]


@pytest.mark.asyncio
class TestLocalModelAdapterSecurity:
    async def test_chat_scrubs_secrets_and_records_audit(self) -> None:
        adapter = LocalModelAdapter()
        # Mock underlying OpenAIAdapter chat completion
        mock_response = MagicMock()
        mock_response.content = "Here is secret sk-ant-123456789012345678901234567890"
        mock_response.prompt_tokens = 10
        mock_response.completion_tokens = 20
        mock_response.total_tokens = 30

        with patch("aiswarm.llm.openai.OpenAIAdapter.chat", return_value=mock_response):
            msg = LLMMessage(role="user", content="My secret is sk-12345678901234567890123456789012")
            res = await adapter.chat(messages=[msg], model="llama3.2:3b")

            # Verify response was scrubbed
            assert "sk-ant" not in res.content
            assert "***" in res.content

        # Verify audit ledger recorded the event
        ledger = get_audit_ledger()
        events = await ledger.get_events(limit=10)
        ollama_events = [e for e in events if e.event_type == "OLLAMA_MODEL_EXECUTION"]
        assert len(ollama_events) > 0
        assert ollama_events[-1].metadata["model"] == "llama3.2:3b"


class TestAPIKeyValidatorOllamaFallback:
    def test_auth_fallback_to_ollama_when_no_cloud_keys(self) -> None:
        # Clear cloud keys from environment
        keys_to_clear = [
            "AISWARM_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
            "GOOGLE_API_KEY", "GEMINI_API_KEY", "NOVITA_API_KEY", "DEEPSEEK_API_KEY"
        ]
        with patch.dict(os.environ, {k: "" for k in keys_to_clear}, clear=False):
            with patch("aiswarm.llm.ollama_manager.OllamaManager.ensure_ollama_provisioned", return_value=(True, "llama3.2:3b")):
                result = APIKeyValidator.verify_api_keys()
                assert result is True
                assert os.environ.get("OLLAMA_FALLBACK_ACTIVE") == "true"
                assert os.environ.get("OLLAMA_SELECTED_MODEL") == "llama3.2:3b"

    def test_auth_raises_error_if_ollama_also_fails(self) -> None:
        keys_to_clear = [
            "AISWARM_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
            "GOOGLE_API_KEY", "GEMINI_API_KEY", "NOVITA_API_KEY", "DEEPSEEK_API_KEY"
        ]
        with patch.dict(os.environ, {k: "" for k in keys_to_clear}, clear=False):
            with patch("aiswarm.llm.ollama_manager.OllamaManager.ensure_ollama_provisioned", return_value=(False, "llama3.2:1b")):
                with pytest.raises(SecurityAuthError, match="CRITICAL SECURITY ERROR"):
                    APIKeyValidator.verify_api_keys()
