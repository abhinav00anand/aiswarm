"""
Provider router — selects, initializes, and fails over between LLM providers.

Every agent uses the router; never a provider directly.
The router applies:
  1. Role-specific provider preference order from config.
  2. Automatic fallback if the primary provider fails or is unavailable.
  3. Per-provider rate limiting (token bucket + concurrency cap).
  4. Cost guard circuit breaker — halts on budget breach.
  5. Cost and token tracking aggregated per session.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import structlog

from aiswarm.llm.adapter import BaseLLMAdapter, LLMMessage, LLMResponse
from aiswarm.llm.openai import OpenAIAdapter
from aiswarm.llm.anthropic import AnthropicAdapter
from aiswarm.llm.gemini import GeminiAdapter
from aiswarm.llm.deepseek import DeepSeekAdapter
from aiswarm.llm.bedrock import BedrockAdapter
from aiswarm.llm.local_models import LocalModelAdapter
from aiswarm.core.cost_guard import CostGuard, CostLimitExceeded
from aiswarm.core.rate_limiter import ProviderRateLimiter

logger = structlog.get_logger(__name__)

# ── Per-provider model ID mapping ─────────────────────────────────────────────
# When the router falls back from Novita→OpenAI→Anthropic, the Novita model ID
# (e.g. "meta-llama/llama-3.1-70b-instruct") is invalid on OpenAI or Anthropic.
# This table maps a Novita model ID to an equivalent model on each provider.
# If no mapping exists the provider is skipped during fallback.
_MODEL_FALLBACK: dict[str, dict[str, str]] = {
    # novita model id → {provider: equivalent_model}
    "meta-llama/llama-3.1-405b-instruct": {
        "openai": "gpt-4o",
        "anthropic": "claude-3-5-sonnet-20241022",
        "gemini": "gemini-2.0-flash",
        "deepseek": "deepseek-chat",
        "local": os.getenv("OLLAMA_SELECTED_MODEL", "llama3.1:8b"),
    },
    "meta-llama/llama-3.1-70b-instruct": {
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-5-haiku-20241022",
        "gemini": "gemini-2.0-flash",
        "deepseek": "deepseek-chat",
        "local": os.getenv("OLLAMA_SELECTED_MODEL", "llama3.1:8b"),
    },
    "meta-llama/llama-3.1-8b-instruct": {
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-5-haiku-20241022",
        "gemini": "gemini-2.0-flash",
        "deepseek": "deepseek-chat",
        "local": "llama3",
    },
    "deepseek/deepseek-r1": {
        "openai": "gpt-4o",
        "anthropic": "claude-3-5-sonnet-20241022",
        "deepseek": "deepseek-reasoner",
        "local": os.getenv("OLLAMA_SELECTED_MODEL", "llama3.1:8b"),
    },
}


_KNOWN_PROVIDER_MODELS: dict[str, set[str]] = {
    "openai": {"gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo", "o1", "o1-mini", "o3-mini"},
    "anthropic": {"claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"},
    "gemini": {"gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"},
    "deepseek": {"deepseek-chat", "deepseek-reasoner"},
    "local": {
        "llama3.1:8b", "llama3.2:3b", "llama3.2:1b", "llama3.1:70b", "llama3.1:latest",
        "llama3.2:latest", "llama3:latest", "llama3", "llama3:70b", "codestral:latest",
        "codestral", "mistral", "mistral:latest", "qwen", "qwen:latest", "phi3:latest",
        "gemma2:latest", "distilgpt2"
    },
}

_PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o",
    "anthropic": "claude-3-5-sonnet-20241022",
    "gemini": "gemini-2.0-flash",
    "deepseek": "deepseek-chat",
    "local": os.getenv("OLLAMA_SELECTED_MODEL", "llama3.2:3b"),
}


_ADAPTER_MODEL_CACHE: str | None = None


def get_adapter_model() -> str:
    """Retrieve the advertised model ID from the adapter's /v1/models endpoint."""
    global _ADAPTER_MODEL_CACHE
    if _ADAPTER_MODEL_CACHE is not None:
        return _ADAPTER_MODEL_CACHE
    
    url = os.getenv("OPENAI_API_ADAPTER_URL")
    if not url:
        _ADAPTER_MODEL_CACHE = "adapter-default"
        return _ADAPTER_MODEL_CACHE
        
    import urllib.request
    import json
    base_url = url.rstrip('/')
    try:
        req = urllib.request.Request(f"{base_url}/v1/models", method="GET")
        with urllib.request.urlopen(req, timeout=3.0) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                if "data" in data and len(data["data"]) > 0:
                    _ADAPTER_MODEL_CACHE = data["data"][0]["id"]
                    return _ADAPTER_MODEL_CACHE
    except Exception:
        pass
        
    _ADAPTER_MODEL_CACHE = "adapter-default"
    return _ADAPTER_MODEL_CACHE


def _resolve_model(requested_model: str, provider_name: str) -> str | None:
    """
    Resolve the correct model ID for a given provider.

    - For "adapter": use advertised model ID or requested model.
    - For "novita": use requested model ID directly.
    - For "local": check explicit mapping or allow direct pass-through for local models.
    """
    if provider_name == "adapter":
        adv = get_adapter_model()
        if adv and adv != "adapter-default":
            return adv
        return requested_model

    if provider_name in ("novita", "local"):
        mapping = _MODEL_FALLBACK.get(requested_model, {})
        if provider_name in mapping:
            return mapping[provider_name]
        return requested_model

    # Check explicit mapping table
    mapping = _MODEL_FALLBACK.get(requested_model, {})
    if provider_name in mapping:
        return mapping[provider_name]

    # Check if requested_model is natively supported by this provider
    known_models = _KNOWN_PROVIDER_MODELS.get(provider_name, set())
    if requested_model in known_models:
        return requested_model

    # If provider is not a known provider with limited model list, allow the requested model to be used directly
    if provider_name not in _KNOWN_PROVIDER_MODELS:
        logger.debug(
            "router.allowing_unknown_provider_model",
            requested=requested_model,
            provider=provider_name,
        )
        return requested_model

    # Fallback default model for provider to avoid invalid model ID errors
    fallback_default = _PROVIDER_DEFAULT_MODELS.get(provider_name)
    if fallback_default:
        logger.info(
            "router.resolved_fallback_default",
            requested=requested_model,
            provider=provider_name,
            resolved=fallback_default,
        )
        return fallback_default

    logger.debug(
        "router.no_model_mapping",
        requested=requested_model,
        provider=provider_name,
    )
    return None



# Novita uses the OpenAI-compatible adapter
_NOVITA_COSTS: dict[str, tuple[float, float]] = {
    "meta-llama/llama-3.1-405b-instruct": (0.0028, 0.0028),
    "meta-llama/llama-3.1-70b-instruct": (0.0009, 0.0009),
    "meta-llama/llama-3.1-8b-instruct": (0.0001, 0.0001),
    "deepseek/deepseek-r1": (0.0014, 0.0019),
    "mistralai/mistral-nemo": (0.0001, 0.0001),
}


def _build_providers() -> dict[str, BaseLLMAdapter]:
    """Construct all provider adapters from environment configuration."""
    novita_key = os.getenv("NOVITA_API_KEY") or os.getenv("NOVITA_TOKEN", "")
    novita_base = os.getenv("NOVITA_BASE_URL", "https://api.novita.ai/v3/openai")

    providers = {
        "novita": OpenAIAdapter(
            api_key=novita_key,
            base_url=novita_base,
            provider_name="novita",
            cost_table=_NOVITA_COSTS,
        ),
        "openai": OpenAIAdapter(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            base_url=os.getenv("OPENAI_API_BASE"),
            provider_name="openai",
        ),
        "anthropic": AnthropicAdapter(
            api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        ),
        "gemini": GeminiAdapter(
            api_key=os.getenv("GOOGLE_API_KEY", ""),
        ),
        "deepseek": DeepSeekAdapter(
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        ),
        "bedrock": BedrockAdapter(),
        "local": LocalModelAdapter(),
    }

    adapter_url = os.getenv("OPENAI_API_ADAPTER_URL")
    if adapter_url:
        providers["adapter"] = OpenAIAdapter(
            api_key=os.getenv("OPENAI_API_KEY", "dummy"),
            base_url=adapter_url,
            provider_name="adapter",
            cost_table={},
        )

    return providers


class ProviderRouter:
    """
    Intelligent router with fallback, cost tracking, rate limiting, and budget guard.

    Usage::

        router = ProviderRouter()
        response = await router.chat(
            messages=messages,
            model="meta-llama/llama-3.1-70b-instruct",
            provider_preference=["novita", "openai", "anthropic"],
        )
    """

    def __init__(
        self,
        providers: dict[str, BaseLLMAdapter] | None = None,
        cost_guard: CostGuard | None = None,
        rate_limiter: ProviderRateLimiter | None = None,
    ) -> None:
        self._providers = providers or _build_providers()
        self._cost_guard = cost_guard or CostGuard()
        self._rate_limiter = rate_limiter or ProviderRateLimiter()
        self._total_tokens: int = 0
        self._total_cost: float = 0.0
        self._call_count: int = 0
        self._failures: dict[str, int] = {}

    async def chat(
        self,
        messages: list[LLMMessage],
        model: str,
        provider_preference: list[str] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        task_id: str = "",
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Attempt providers in preference order, falling back on error.

        Applies per-provider rate limiting and cost-guard checks on every call.

        Args:
            messages: Conversation history in LLMMessage format.
            model: Preferred model ID (Novita/canonical).
            provider_preference: Ordered list of provider names to try.
            temperature: Sampling temperature.
            max_tokens: Maximum completion tokens.
            task_id: Optional task ID for cost-guard attribution.

        Raises:
            CostLimitExceeded: When daily/session budget is exhausted.
            RuntimeError: When all providers fail.
        """
        order = list(provider_preference) if provider_preference else ["novita", "openai", "anthropic", "deepseek", "local"]
        if os.getenv("OPENAI_API_ADAPTER_URL") and "adapter" not in order:
            order = ["adapter"] + order
        if "local" not in order:
            order.append("local")

        last_exc: Exception | None = None
        is_notebook = os.getenv("BLYNX_NOTEBOOK_MODE") in ("1", "true", "True")

        for provider_name in order:
            provider = self._providers.get(provider_name)
            if provider is None:
                logger.warning("router.unknown_provider", name=provider_name)
                continue
            if not provider.is_available():
                logger.debug("router.provider_unavailable", name=provider_name)
                continue

            resolved_model = _resolve_model(model, provider_name)
            if resolved_model is None:
                logger.debug(
                    "router.skipping_no_model",
                    provider=provider_name,
                    requested_model=model,
                )
                continue

            try:
                logger.debug(
                    "router.attempting",
                    provider=provider_name,
                    model=resolved_model,
                    temperature=temperature,
                )

                # Cap tokens if using adapter or in notebook mode
                target_max_tokens = max_tokens
                if provider_name == "adapter" or is_notebook:
                    if target_max_tokens > 1024:
                        target_max_tokens = 1024
                    if "do_sample" not in kwargs:
                        kwargs["do_sample"] = False

                # ── Rate limit: acquire slot before calling provider ───────
                async with self._rate_limiter.acquire(provider_name):
                    response = await provider.chat(
                        messages=messages,
                        model=resolved_model,
                        temperature=temperature,
                        max_tokens=target_max_tokens,
                        **kwargs,
                    )

                self._total_tokens += response.total_tokens
                self._total_cost += response.cost_usd
                self._call_count += 1
                self._failures.pop(provider_name, None)

                # ── Cost guard: record spend after every successful call ───
                await self._cost_guard.record(
                    provider=provider_name,
                    tokens=response.total_tokens,
                    cost_usd=response.cost_usd,
                    task_id=task_id,
                )

                return response

            except CostLimitExceeded:
                # Budget exhausted — do NOT fall back, re-raise immediately
                raise

            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                err_str = str(exc)
                self._failures[provider_name] = self._failures.get(provider_name, 0) + 1

                # Notify rate limiter if we received HTTP 429
                if "429" in err_str or "rate limit" in err_str.lower():
                    self._rate_limiter.notify_rate_limited(provider_name)

                logger.warning(
                    "router.provider_failed",
                    provider=provider_name,
                    error=err_str,
                    failures=self._failures[provider_name],
                )
                # Brief back-off before trying next provider
                await asyncio.sleep(0.5)

        raise RuntimeError(
            f"All providers exhausted for model={model!r}. "
            f"Last error: {last_exc}"
        ) from last_exc

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "total_calls": self._call_count,
            "total_tokens": self._total_tokens,
            "total_cost_usd": round(self._total_cost, 6),
            "provider_failures": dict(self._failures),
            "cost_guard": self._cost_guard.check_budget_remaining(),
            "rate_limiter": self._rate_limiter.stats(),
        }

    @property
    def cost_guard(self) -> CostGuard:
        return self._cost_guard

    def list_available(self) -> list[str]:
        return [name for name, p in self._providers.items() if p.is_available()]
