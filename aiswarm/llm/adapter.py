"""
LLM Adapter — unified interface over all provider implementations.

Every provider must implement BaseLLMAdapter. Callers always use the
adapter interface and never touch provider SDKs directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMMessage:
    role: str   # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    finish_reason: str
    latency_ms: float
    cost_usd: float = 0.0
    raw: Any = None


class BaseLLMAdapter(ABC):
    """Abstract base for all LLM provider adapters."""

    provider_name: str = "base"

    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a chat completion request and return a structured response."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider is configured and reachable."""

    async def health_check(self) -> bool:
        """Lightweight liveness check — override for richer checks."""
        return self.is_available()
