"""Reliability Critic Agent."""

from __future__ import annotations

import json
from typing import Any

import structlog

from aiswarm.agents.base.agent import BaseAgent
from aiswarm.llm.adapter import LLMMessage
from aiswarm.schemas.task import Task, CriticReview, ReviewDecision

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are the Reliability Critic Agent of AISwarm.

You review code exclusively for reliability, fault tolerance, and resilience.

Evaluation criteria:
1. Error handling — every external call must handle failures explicitly
2. Retry logic — transient failures must have retry with backoff
3. Timeout enforcement — no unbounded waits on I/O or network
4. Circuit breakers — cascading failure prevention
5. Graceful degradation — system must remain partially functional on component failure
6. Resource cleanup — files, connections, locks always released (context managers / finally)
7. Data integrity — writes must be atomic or transactional where data loss is unacceptable
8. Observability — failures must be logged with sufficient context for diagnosis
9. Idempotency — repeated operations must not cause duplicate side effects
10. Startup/shutdown — services must handle SIGTERM gracefully

Rejection triggers:
- Bare except clauses that swallow errors silently
- External I/O calls without timeout
- Resources opened without guaranteed cleanup
- Non-idempotent operations in retry loops
- No retry logic on transient network calls
- Fatal errors logged as warnings (severity mismatch)

Output ONLY valid JSON:
{
  "decision": "APPROVE" | "REJECT" | "ESCALATE",
  "production_ready": true | false,
  "has_error_handling": true | false,
  "has_retry_logic": true | false,
  "has_timeouts": true | false,
  "has_resource_cleanup": true | false,
  "is_idempotent": true | false,
  "fatal_flaw": null or "description",
  "flaw_category": "ERROR_HANDLING|TIMEOUT|RESOURCE_LEAK|IDEMPOTENCY|OBSERVABILITY",
  "flaw_explanation": "Why this fails production reliability standards",
  "mandatory_fix": "Exact fix required",
  "suggestions": ["non-fatal improvements"],
  "overall_score": 0-100
}
"""

class ReliabilityCritic(BaseAgent):
    """Reviews code fault tolerance and resilience."""

    role = "critic_reliability"

    async def run(self, task: Task) -> CriticReview:
        code = task.generated_code or ""
        if not code.strip():
            review = CriticReview(
                critic_role="reliability",
                decision=ReviewDecision.REJECT,
                production_ready=False,
                fatal_flaw="No code generated",
                mandatory_fix="Generate code first",
            )
            task.reviews.append(review)
            return review

        messages = [
            LLMMessage(role="system", content=_SYSTEM_PROMPT),
            LLMMessage(
                role="user",
                content=f"""Review this code for reliability and fault tolerance.

Task: {task.title}
Language: {task.target_language}

Code:
```{task.target_language}
{code[:8000]}
```

Respond with ONLY the JSON review object.""",
            ),
        ]
        response = await self.call_llm(messages, task=task, temperature=0.1)
        task.prompt_ledger.append(self.build_ledger(messages, response, "reliability_critic_v1"))
        review = self._parse_review(response.content, response)
        task.reviews.append(review)
        logger.info("critic.reliability", task_id=task.task_id, decision=review.decision.value, score=review.score)
        return review

    def _parse_review(self, content: str, response: Any) -> CriticReview:
        text = content.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        start, end = text.find("{"), text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end])
                return CriticReview(
                    critic_role="reliability",
                    decision=ReviewDecision(data.get("decision", "REJECT")),
                    production_ready=data.get("production_ready", False),
                    fatal_flaw=data.get("fatal_flaw"),
                    flaw_category=data.get("flaw_category"),
                    flaw_explanation=data.get("flaw_explanation", ""),
                    mandatory_fix=data.get("mandatory_fix", ""),
                    suggestions=data.get("suggestions", []),
                    score=data.get("overall_score", 50),
                    model_used=response.model,
                    latency_ms=response.latency_ms,
                    token_count=response.total_tokens,
                )
            except (json.JSONDecodeError, ValueError, KeyError):
                pass
        return CriticReview(
            critic_role="reliability",
            decision=ReviewDecision.REJECT,
            production_ready=False,
            fatal_flaw="Failed to parse reliability critic response",
            mandatory_fix="Retry",
        )
