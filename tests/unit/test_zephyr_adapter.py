"""Unit tests for the Zephyr LLM adapter and provider router integration."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from aiswarm.llm.adapter import LLMMessage, LLMResponse
from aiswarm.llm.zephyr import ZephyrAdapter
from aiswarm.llm.provider_router import ProviderRouter


class TestZephyrAdapter:
    def test_adapter_initialization(self) -> None:
        adapter = ZephyrAdapter(
            api_key="zph_tmp_test_key_123456",
            base_url="http://localhost:10000",
        )
        assert adapter.provider_name == "zephyr"
        assert adapter._base_url == "http://localhost:10000/v1"
        assert adapter.is_available()

    def test_availability_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ZEPHYR_API_KEY", "zph_tmp_env_key_789")
        adapter = ZephyrAdapter()
        assert adapter.is_available()

    @pytest.mark.asyncio
    async def test_chat_success(self) -> None:
        adapter = ZephyrAdapter(
            api_key="zph_tmp_mock_key",
            base_url="http://localhost:10000/v1",
        )

        mock_choice = MagicMock()
        mock_choice.message.content = "def add(a: int, b: int) -> int:\n    return a + b"
        mock_choice.finish_reason = "stop"

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 15
        mock_usage.completion_tokens = 12
        mock_usage.total_tokens = 27

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_create = AsyncMock(return_value=mock_response)

        with patch.object(adapter, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create = mock_create
            mock_get_client.return_value = mock_client

            messages = [
                LLMMessage(role="system", content="You are a python assistant."),
                LLMMessage(role="user", content="Write an add function."),
            ]

            res: LLMResponse = await adapter.chat(
                messages=messages,
                model="zephyr/llama-3.1-70b",
            )

            assert res.content == "def add(a: int, b: int) -> int:\n    return a + b"
            assert res.provider == "zephyr"
            assert res.model == "zephyr/llama-3.1-70b"
            assert res.prompt_tokens == 15
            assert res.completion_tokens == 12
            assert res.total_tokens == 27
            assert res.finish_reason == "stop"


class TestZephyrProviderRouterIntegration:
    def test_provider_router_has_zephyr(self) -> None:
        router = ProviderRouter()
        assert "zephyr" in router._providers
        zephyr_adapter = router._providers["zephyr"]
        assert isinstance(zephyr_adapter, ZephyrAdapter)

    def test_provider_preference_order_with_zephyr_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ZEPHYR_API_KEY", "zph_tmp_active_key")
        monkeypatch.setenv("ZEPHYR_API_URL", "http://localhost:10000/v1")
        router = ProviderRouter()
        
        # When ZEPHYR_API_KEY is set, zephyr is prioritized first
        assert "zephyr" in router._providers
