"""OpenAI provider adapter (also handles OpenAI-compatible APIs)."""

from __future__ import annotations

import os
import time
from typing import Any

import structlog

try:
    from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError
except ImportError:
    AsyncOpenAI = None
    APIError = Exception
    RateLimitError = Exception
    APITimeoutError = Exception

from aiswarm.llm.adapter import BaseLLMAdapter, LLMMessage, LLMResponse

logger = structlog.get_logger(__name__)

# Cost per 1k tokens (USD) — used for budget tracking
_COST_TABLE: dict[str, tuple[float, float]] = {
    "gpt-4o": (0.005, 0.015),
    "gpt-4o-mini": (0.00015, 0.0006),
    "o1-preview": (0.015, 0.060),
    "o1-mini": (0.003, 0.012),
}


class OpenAIAdapter(BaseLLMAdapter):
    """Adapter for OpenAI and OpenAI-compatible APIs (e.g. Novita, DeepSeek)."""

    provider_name = "openai"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        provider_name: str = "openai",
        timeout: float = 120.0,
        cost_table: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self.provider_name = provider_name
        self._key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._base_url = base_url
        self._timeout = timeout
        self._cost_table = cost_table or _COST_TABLE
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            kwargs: dict[str, Any] = {
                "api_key": self._key or "placeholder",
                "timeout": self._timeout,
            }
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    def is_available(self) -> bool:
        return bool(self._key)

    def _cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        inp, out = self._cost_table.get(model, (0.0, 0.0))
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
        api_messages = [{"role": m.role, "content": m.content} for m in messages]

        t0 = time.monotonic()
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=api_messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
        except RateLimitError:
            logger.warning("llm.rate_limit", provider=self.provider_name, model=model)
            raise
        except APITimeoutError:
            logger.error("llm.timeout", provider=self.provider_name, model=model)
            raise
        except APIError as exc:
            logger.error("llm.api_error", provider=self.provider_name, model=model, error=str(exc))
            raise

        latency_ms = (time.monotonic() - t0) * 1000
        choice = response.choices[0]
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0

        cost = self._cost(model, prompt_tokens, completion_tokens)

        logger.debug(
            "llm.response",
            provider=self.provider_name,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=round(latency_ms, 1),
            cost_usd=round(cost, 6),
        )

        return LLMResponse(
            content=choice.message.content or "",
            model=model,
            provider=self.provider_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            finish_reason=choice.finish_reason or "stop",
            latency_ms=latency_ms,
            cost_usd=cost,
            raw=response,
        )
