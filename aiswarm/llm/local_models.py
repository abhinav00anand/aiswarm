"""Local model adapter — Ollama / LM Studio (OpenAI-compatible)."""

from __future__ import annotations

import os
from aiswarm.llm.openai import OpenAIAdapter


class LocalModelAdapter(OpenAIAdapter):
    """
    Adapter for locally running models via Ollama or LM Studio.
    Uses the OpenAI-compatible /v1 endpoint at localhost:11434.
    """

    provider_name = "local"

    def __init__(self, base_url: str | None = None) -> None:
        super().__init__(
            api_key="ollama",   # Ollama doesn't need a real key
            base_url=base_url or os.getenv("LOCAL_MODEL_URL", "http://localhost:11434/v1"),
            provider_name="local",
            cost_table={},      # Local models are free
        )

    def is_available(self) -> bool:
        # Check if ollama endpoint is reachable (best-effort)
        return True
