"""Local model adapter."""

from __future__ import annotations

import os
from typing import Any

from aiswarm.llm.adapter import LLMMessage, LLMResponse
from aiswarm.llm.ollama_manager import OllamaManager
from aiswarm.llm.openai import OpenAIAdapter
from aiswarm.security.audit import get_audit_ledger
from aiswarm.security.redaction import scrub
from aiswarm.utils.compat_log import get_logger

logger = get_logger(__name__)


class LocalModelAdapter(OpenAIAdapter):
    """
    Adapter for locally running models via Ollama or LM Studio.
    Enforces secret redaction on all input/output and records audit events.
    """

    provider_name = "local"

    def __init__(self, base_url: str | None = None, default_model: str | None = None) -> None:
        raw_url = base_url or os.getenv("LOCAL_MODEL_URL", "http://localhost:11434/v1")
        if not raw_url.endswith("/v1") and not raw_url.endswith("/v1/"):
            raw_url = f"{raw_url.rstrip('/')}/v1"

        super().__init__(
            api_key="ollama",  # Ollama does not require an API key
            base_url=raw_url,
            provider_name="local",
            cost_table={},  # Local execution is 0 cost
        )
        self.manager = OllamaManager(base_url=raw_url)
        self.default_model = default_model or os.getenv("OLLAMA_DEFAULT_MODEL", "llama3.2:3b")

    def is_available(self) -> bool:
        """Check if the local Ollama service is reachable and responsive."""
        return self.manager.is_service_running()

    async def chat(
        self,
        messages: list[LLMMessage],
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Send a chat request to local Ollama with secret scrubbing and audit logging.
        """
        target_model = model or self.default_model

        # 1. Scrub input messages for sensitive credentials
        sanitized_messages = [LLMMessage(role=m.role, content=scrub(m.content)) for m in messages]

        logger.info("local_adapter.chat_start", model=target_model, message_count=len(messages))

        try:
            response = await super().chat(
                messages=sanitized_messages,
                model=target_model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )

            # 2. Scrub response content
            sanitized_content = scrub(response.content)
            response.content = sanitized_content

            # 3. Log audit event
            audit = get_audit_ledger()
            await audit.record(
                event_type="OLLAMA_MODEL_EXECUTION",
                actor="local_model_adapter",
                action="chat_completion",
                outcome="SUCCESS",
                metadata={
                    "model": target_model,
                    "prompt_tokens": response.prompt_tokens,
                    "completion_tokens": response.completion_tokens,
                    "total_tokens": response.total_tokens,
                    "provider": self.provider_name,
                },
            )

            return response

        except Exception as exc:
            logger.error("local_adapter.chat_failed", model=target_model, error=str(exc))
            audit = get_audit_ledger()
            await audit.record(
                event_type="OLLAMA_MODEL_EXECUTION",
                actor="local_model_adapter",
                action="chat_completion",
                outcome="FAILED",
                metadata={"model": target_model, "error": str(exc)},
            )
            raise
