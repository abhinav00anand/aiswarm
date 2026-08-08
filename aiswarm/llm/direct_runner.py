"""Direct Model Coordinator for Blynx."""

from __future__ import annotations

import time
from typing import Any

from aiswarm.llm.adapter import BaseLLMAdapter, LLMMessage, LLMResponse
from aiswarm.security.audit import get_audit_ledger
from aiswarm.security.governor import EngineeringGovernor
from aiswarm.security.redaction import scrub
from aiswarm.utils.compat_log import get_logger

logger = get_logger(__name__)

class DirectModelCoordinator:
    """
    Direct Model Execution Engine coordinated with Zymis security & audit infrastructure.
    """

    def __init__(
        self,
        governor: EngineeringGovernor | None = None,
        llm_adapter: BaseLLMAdapter | None = None,
    ) -> None:
        self.governor = governor or EngineeringGovernor()
        self.adapter = llm_adapter  # Must be injected — BaseLLMAdapter has no direct constructor
        self.audit_ledger = get_audit_ledger()

    async def run_direct(
        self,
        prompt: str,
        model: str = "gpt-4o",
        system_prompt: str = "You are a helpful AI assistant coordinated by Zymis.",
        temperature: float = 0.7,
        user_role: str = "user",
    ) -> dict[str, Any]:
        """
        Directly run a prompt through the specified model while AISwarm coordinates
        real-time secret scrubbing, governance spend checks, and immutable audit logging.
        """
        start_time = time.time()
        logger.info("direct_model.start", model=model, role=user_role)

        # 1. Scrub prompt for sensitive credentials before sending
        scrubbed_prompt = scrub(prompt)

        # 2. Check governance token / cost budget
        self.governor.check_capability_spawn_policy("direct_model_exec", user_role)

        # 3. Construct messages and call model via LLMAdapter
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=scrubbed_prompt),
        ]

        if self.adapter is None:
            raise RuntimeError(
                "DirectModelCoordinator requires an llm_adapter to be injected. "
                "Use ProviderRouter or a concrete BaseLLMAdapter implementation."
            )
        try:
            response: LLMResponse = await self.adapter.chat(
                messages=messages,
                model=model,
                temperature=temperature,
            )

            # 4. Scrub output response
            sanitized_content = scrub(response.content)
            duration = time.time() - start_time

            # 5. Record event in immutable Audit Ledger
            await self.audit_ledger.record(
                event_type="DIRECT_MODEL_EXECUTION",
                actor=user_role,
                action="direct_prompt_run",
                outcome="SUCCESS",
                metadata={
                    "model": model,
                    "prompt_tokens": response.prompt_tokens,
                    "completion_tokens": response.completion_tokens,
                    "cost_usd": response.cost_usd,
                    "duration_seconds": round(duration, 3),
                },
            )

            logger.info("direct_model.success", model=model, duration=round(duration, 3), cost_usd=response.cost_usd)

            return {
                "status": "SUCCESS",
                "model": model,
                "content": sanitized_content,
                "usage": {
                    "prompt_tokens": response.prompt_tokens,
                    "completion_tokens": response.completion_tokens,
                    "total_tokens": response.total_tokens,
                    "cost_usd": response.cost_usd,
                },
                "duration_seconds": round(duration, 3),
            }

        except Exception as exc:
            duration = time.time() - start_time
            logger.error("direct_model.failed", model=model, error=str(exc))
            
            await self.audit_ledger.record(
                event_type="DIRECT_MODEL_EXECUTION",
                actor=user_role,
                action="direct_prompt_run",
                outcome="FAILED",
                metadata={"model": model, "error": str(exc)},
            )

            return {
                "status": "FAILED",
                "model": model,
                "error": scrub(str(exc)),
                "duration_seconds": round(duration, 3),
            }
