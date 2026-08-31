"""DeepSeek provider adapter (OpenAI-compatible)."""

from __future__ import annotations

import os

from aiswarm.llm.openai import OpenAIAdapter

_DEEPSEEK_COSTS: dict[str, tuple[float, float]] = {
    "deepseek-coder": (0.00014, 0.00028),
    "deepseek-chat": (0.00014, 0.00028),
    "deepseek-reasoner": (0.00055, 0.00219),
}


class DeepSeekAdapter(OpenAIAdapter):
    """DeepSeek — uses the OpenAI-compatible endpoint."""

    provider_name = "deepseek"

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(
            api_key=api_key or os.getenv("DEEPSEEK_API_KEY", ""),
            base_url="https://api.deepseek.com/v1",
            provider_name="deepseek",
            cost_table=_DEEPSEEK_COSTS,
        )

    def is_available(self) -> bool:
        return bool(self._key)
