"""Anthropic Claude provider adapter."""

from __future__ import annotations

import os
import time
from typing import Any

import structlog

try:
    from anthropic import AsyncAnthropic, APIError, RateLimitError
except ImportError:
    AsyncAnthropic = None
    APIError = Exception
    RateLimitError = Exception

from aiswarm.llm.adapter import BaseLLMAdapter, LLMMessage, LLMResponse

logger = structlog.get_logger(__name__)

_COST_TABLE: dict[str, tuple[float, float]] = {
    "claude-3-5-sonnet-20241022": (0.003, 0.015),
    "claude-3-5-haiku-20241022": (0.001, 0.005),
    "claude-3-opus-20240229": (0.015, 0.075),
}


class AnthropicAdapter(BaseLLMAdapter):
    """Adapter for Anthropic Claude models."""

    provider_name = "anthropic"

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self._timeout = timeout
        self._client: AsyncAnthropic | None = None

    def _get_client(self) -> AsyncAnthropic:
        if self._client is None:
            self._client = AsyncAnthropic(
                api_key=self._key,
                timeout=self._timeout,
            )
        return self._client

    def is_available(self) -> bool:
        return bool(self._key)

    def _cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        inp, out = _COST_TABLE.get(model, (0.0, 0.0))
        return (prompt_tokens * inp + completion_tokens * out) / 1000.0

    async def chat(
        self,
        messages: list[LLMMessage],
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        client = self._get_client()

        # Anthropic separates system from user/assistant messages
        system_parts = [m.content for m in messages if m.role == "system"]
        system_prompt = "\n\n".join(system_parts)
        api_messages = [
            {"role": m.role, "content": m.content} for m in messages if m.role != "system"
        ]

        t0 = time.monotonic()
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=api_messages,  # type: ignore[arg-type]
                **kwargs,
            )
        except RateLimitError:
            logger.warning("llm.rate_limit", provider="anthropic", model=model)
            raise
        except APIError as exc:
            logger.error("llm.api_error", provider="anthropic", model=model, error=str(exc))
            raise

        latency_ms = (time.monotonic() - t0) * 1000
        content = response.content[0].text if response.content else ""
        prompt_tokens = response.usage.input_tokens
        completion_tokens = response.usage.output_tokens
        cost = self._cost(model, prompt_tokens, completion_tokens)

        return LLMResponse(
            content=content,
            model=model,
            provider="anthropic",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            finish_reason=response.stop_reason or "stop",
            latency_ms=latency_ms,
            cost_usd=cost,
            raw=response,
        )
