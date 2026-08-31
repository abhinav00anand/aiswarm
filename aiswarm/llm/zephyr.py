"""
Zephyr provider adapter — connects Zymis swarms to Zephyr zero-trust distributed edge GPU mesh.

Enables Zymis agents (Coder, Planner, Critics, Boss) to route prompt workloads
directly to remote GPUs (vLLM, Ollama, llama.cpp) connected via Zephyr WebSockets.
"""

from __future__ import annotations

import asyncio
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

# Default cost table for Zephyr remote GPU edge inference (effectively zero or low cost)
_ZEPHYR_COST_TABLE: dict[str, tuple[float, float]] = {
    "zephyr/llama-3.1-70b": (0.0, 0.0),
    "zephyr/qwen2.5-coder-32b": (0.0, 0.0),
    "zephyr/codestral": (0.0, 0.0),
}


class ZephyrAdapter(BaseLLMAdapter):
    """
    Adapter for Zephyr Zero-Trust Edge Inference Mesh.

    Routes Zymis agent requests to remote GPU nodes tunneled through Zephyr Cloud Control Plane.
    """

    provider_name = "zephyr"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 120.0,
        cost_table: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self.provider_name = "zephyr"
        self._key = (
            api_key
            or os.getenv("ZEPHYR_API_KEY")
            or os.getenv("ZEPHYR_BOOTSTRAP_KEY")
            or "zph_tmp_default_key"
        )
        self._base_url = (
            base_url
            or os.getenv("ZEPHYR_API_URL")
            or "http://localhost:10000/v1"
        )
        if not self._base_url.endswith("/v1"):
            self._base_url = self._base_url.rstrip("/") + "/v1"

        self._timeout = timeout
        self._cost_table = cost_table or _ZEPHYR_COST_TABLE
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            if AsyncOpenAI is None:
                raise RuntimeError("openai package is required for ZephyrAdapter. Run `pip install openai`.")
            self._client = AsyncOpenAI(
                api_key=self._key,
                base_url=self._base_url,
                timeout=self._timeout,
            )
        return self._client

    def is_available(self) -> bool:
        """Return True if Zephyr API URL or key is configured."""
        return bool(os.getenv("ZEPHYR_API_KEY") or os.getenv("ZEPHYR_BOOTSTRAP_KEY") or os.getenv("ZEPHYR_API_URL") or self._key)

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
        """Dispatch chat completion to remote Zephyr edge GPU node."""
        client = self._get_client()
        api_messages = [{"role": m.role, "content": m.content} for m in messages]

        t0 = time.monotonic()
        max_attempts = 4
        response = None
        for attempt in range(max_attempts):
            try:
                response = await client.chat.completions.create(
                    model=model,
                    messages=api_messages,  # type: ignore[arg-type]
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
                break
            except RateLimitError as exc:
                if attempt == max_attempts - 1:
                    logger.warning("zephyr.rate_limit", provider=self.provider_name, model=model)
                    raise
                await asyncio.sleep(2.0 * (attempt + 1))
            except APITimeoutError as exc:
                if attempt == max_attempts - 1:
                    logger.error("zephyr.timeout", provider=self.provider_name, model=model)
                    raise
                await asyncio.sleep(2.0 * (attempt + 1))
            except APIError as exc:
                if "at capacity" in str(exc).lower() and attempt < max_attempts - 1:
                    logger.warning("zephyr.node_capacity_retry", attempt=attempt + 1, wait_s=2.0 * (attempt + 1))
                    await asyncio.sleep(2.0 * (attempt + 1))
                    continue
                logger.error("zephyr.api_error", provider=self.provider_name, model=model, error=str(exc))
                raise

        if response is None:
            raise RuntimeError(f"Zephyr completions returned no response for model {model}")

        latency_ms = (time.monotonic() - t0) * 1000
        choice = response.choices[0]
        usage = response.usage

        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else 0

        content = choice.message.content or ""
        cost = self._cost(model, prompt_tokens, completion_tokens)

        logger.info(
            "zephyr.completion_success",
            model=model,
            latency_ms=round(latency_ms, 2),
            tokens=total_tokens,
        )

        return LLMResponse(
            content=content,
            model=model,
            provider=self.provider_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            finish_reason=choice.finish_reason or "stop",
            latency_ms=latency_ms,
            cost_usd=cost,
            raw=response,
        )
