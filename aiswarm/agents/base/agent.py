"""BaseAgent."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import structlog

from aiswarm.llm.provider_router import ProviderRouter
from aiswarm.llm.adapter import LLMMessage, LLMResponse
from aiswarm.schemas.task import Task, PromptLedger

logger = structlog.get_logger(__name__)


class BaseAgent(ABC):
    """Abstract base class for all AISwarm agents."""

    role: str = "base"

    def __init__(
        self,
        router: ProviderRouter,
        model: str,
        provider_preference: list[str] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._router = router
        self._model = model
        self._provider_pref = provider_preference or ["novita", "openai", "anthropic"]
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._config = config or {}

    async def call_llm(
        self,
        messages: list[LLMMessage],
        task: Task | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send messages to the LLM and record metrics on the task."""
        t0 = time.monotonic()
        response = await self._router.chat(
            messages=messages,
            model=self._model,
            provider_preference=self._provider_pref,
            temperature=temperature if temperature is not None else self._temperature,
            max_tokens=max_tokens if max_tokens is not None else self._max_tokens,
        )
        latency_ms = (time.monotonic() - t0) * 1000

        if task is not None:
            task.total_tokens_used += response.total_tokens
            task.total_llm_calls += 1
            task.estimated_cost_usd += response.cost_usd

        logger.debug(
            "agent.llm_call",
            role=self.role,
            model=self._model,
            tokens=response.total_tokens,
            latency_ms=round(latency_ms, 1),
        )
        return response

    def build_ledger(
        self,
        messages: list[LLMMessage],
        response: LLMResponse,
        prompt_version: str = "1.0",
    ) -> PromptLedger:
        return PromptLedger(
            prompt_version=prompt_version,
            total_tokens=response.total_tokens,
            model_used=response.model,
            provider_used=response.provider,
            system_prompt_tokens=sum(
                len(m.content.split()) for m in messages if m.role == "system"
            ),
            user_prompt_tokens=sum(len(m.content.split()) for m in messages if m.role == "user"),
        )

    @abstractmethod
    async def run(self, task: Task) -> Any:
        """Execute the agent's primary action on the given task."""

    def __repr__(self) -> str:
        return f"<{type(self).__name__} role={self.role!r} model={self._model!r}>"
