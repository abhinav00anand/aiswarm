"""Google Gemini provider adapter."""

from __future__ import annotations

import os
import time
from typing import Any

import structlog

from aiswarm.llm.adapter import BaseLLMAdapter, LLMMessage, LLMResponse

logger = structlog.get_logger(__name__)

_COST_TABLE: dict[str, tuple[float, float]] = {
    "gemini-1.5-pro-002": (0.00125, 0.005),
    "gemini-1.5-flash-002": (0.000075, 0.0003),
    "gemini-1.5-pro": (0.00125, 0.005),
    "gemini-1.5-flash": (0.000075, 0.0003),
}


class GeminiAdapter(BaseLLMAdapter):
    """Adapter for Google Gemini models via google-generativeai SDK."""

    provider_name = "gemini"

    def __init__(self, api_key: str | None = None) -> None:
        self._key = api_key or os.getenv("GOOGLE_API_KEY", "")

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
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise ImportError("google-generativeai is required for Gemini support") from exc

        genai.configure(api_key=self._key)
        gen_model = genai.GenerativeModel(model_name=model)

        system_parts = [m.content for m in messages if m.role == "system"]
        history = []
        last_user = ""
        for m in messages:
            if m.role == "system":
                continue
            if m.role == "user":
                last_user = m.content
            elif m.role == "assistant":
                history.append({"role": "model", "parts": m.content})

        generation_config = genai.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        t0 = time.monotonic()
        try:
            response = await gen_model.generate_content_async(
                contents=last_user,
                generation_config=generation_config,
            )
        except Exception as exc:
            logger.error("llm.api_error", provider="gemini", model=model, error=str(exc))
            raise

        latency_ms = (time.monotonic() - t0) * 1000
        content = response.text or ""
        prompt_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
        completion_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
        cost = self._cost(model, prompt_tokens, completion_tokens)

        return LLMResponse(
            content=content,
            model=model,
            provider="gemini",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            finish_reason="stop",
            latency_ms=latency_ms,
            cost_usd=cost,
            raw=response,
        )
