"""AWS Bedrock provider adapter."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import structlog

from aiswarm.llm.adapter import BaseLLMAdapter, LLMMessage, LLMResponse

logger = structlog.get_logger(__name__)


class BedrockAdapter(BaseLLMAdapter):
    """Adapter for AWS Bedrock — supports Claude on Bedrock."""

    provider_name = "bedrock"

    def __init__(
        self,
        region: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
    ) -> None:
        self._region = region or os.getenv("AWS_REGION", "us-east-1")
        self._access_key = access_key or os.getenv("AWS_ACCESS_KEY_ID", "")
        self._secret_key = secret_key or os.getenv("AWS_SECRET_ACCESS_KEY", "")
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import boto3

                self._client = boto3.client(
                    "bedrock-runtime",
                    region_name=self._region,
                    aws_access_key_id=self._access_key or None,
                    aws_secret_access_key=self._secret_key or None,
                )
            except ImportError as exc:
                raise ImportError("boto3 is required for Bedrock support") from exc
        return self._client

    def is_available(self) -> bool:
        return bool(self._access_key and self._secret_key)

    async def chat(
        self,
        messages: list[LLMMessage],
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        import asyncio

        client = self._get_client()
        system_parts = [m.content for m in messages if m.role == "system"]
        api_messages = [
            {"role": m.role, "content": m.content} for m in messages if m.role != "system"
        ]
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": "\n".join(system_parts),
                "messages": api_messages,
            }
        )

        t0 = time.monotonic()
        try:
            # boto3 is synchronous — run in thread pool
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.invoke_model(modelId=model, body=body),
            )
        except Exception as exc:
            logger.error("llm.api_error", provider="bedrock", model=model, error=str(exc))
            raise

        latency_ms = (time.monotonic() - t0) * 1000
        body_json = json.loads(response["body"].read())
        content = body_json.get("content", [{}])[0].get("text", "")
        usage = body_json.get("usage", {})
        prompt_tokens = usage.get("input_tokens", 0)
        completion_tokens = usage.get("output_tokens", 0)

        return LLMResponse(
            content=content,
            model=model,
            provider="bedrock",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            finish_reason=body_json.get("stop_reason", "stop"),
            latency_ms=latency_ms,
            raw=body_json,
        )
