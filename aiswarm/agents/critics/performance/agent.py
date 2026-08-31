"""Performance Critic Agent."""

from __future__ import annotations

import json
from typing import Any

import structlog

from aiswarm.agents.base.agent import BaseAgent
from aiswarm.llm.adapter import LLMMessage
from aiswarm.schemas.task import Task, CriticReview, ReviewDecision

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are the Performance Critic Agent of AISwarm.

You review code exclusively for performance and efficiency. You do NOT review
for security or architecture — those have dedicated critics.

Your evaluation criteria:
1. Algorithmic complexity — reject O(n²) or worse where O(n log n) or O(n) is achievable
2. Memory allocation — reject unbounded allocations in hot paths
3. Cache locality — reject patterns that cause cache thrashing
4. I/O efficiency — reject unnecessary disk/network calls inside loops
5. Concurrency — reject blocking calls in async contexts, unguarded shared state
6. Vectorization — reject scalar loops where SIMD/vectorized operations are available
7. Zero-copy — reject unnecessary data copies for large buffers
8. Lazy evaluation — reject eager computation when lazy is correct
9. Profiling hotspots — identify functions that will dominate runtime
10. Memory leaks — reject patterns that accumulate without bounds

Rejection triggers (any one sufficient):
- Nested loops with O(n²) that has an obvious O(n log n) alternative
- Unbounded list/dict growth inside a loop without eviction
- Blocking synchronous I/O in an async function (without asyncio.run_in_executor)
- Memory copies larger than 64KB that could be zero-copy
- String concatenation in a loop (use join or buffer)
- Repeated identical DB queries inside a loop (N+1 problem)

Output ONLY valid JSON:
{
  "decision": "APPROVE" | "REJECT" | "ESCALATE",
  "production_ready": true | false,
  "has_algorithmic_issues": true | false,
  "has_memory_issues": true | false,
  "has_io_bottlenecks": true | false,
  "has_concurrency_issues": true | false,
  "time_complexity": "O(n) or description",
  "space_complexity": "O(n) or description",
  "fatal_flaw": null or "description",
  "flaw_category": null or "ALGORITHM|MEMORY|IO|CONCURRENCY|VECTORIZATION",
  "flaw_explanation": "Why this fails production performance standards",
  "mandatory_fix": "Exact fix the coder must implement",
  "optimization_suggestions": ["non-fatal suggestions"],
  "overall_score": 0-100
}
"""


class PerformanceCritic(BaseAgent):
    """Reviews code efficiency and performance characteristics."""

    role = "critic_performance"

    async def run(self, task: Task) -> CriticReview:
        code = task.generated_code or ""
        if not code.strip():
            review = CriticReview(
                critic_role="performance",
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
                content=f"""
Review this code for performance and efficiency.

Task: {task.title}
Language: {task.target_language}
Performance targets from plan: {task.metadata.get("blueprint", {}).get("performance_targets", {}) if isinstance(task.metadata.get("blueprint"), dict) else ""}

Code:
```{task.target_language}
{code[:8000]}
```

Respond with ONLY the JSON review object.
""",
            ),
        ]
        response = await self.call_llm(messages, task=task, temperature=0.1)
        task.prompt_ledger.append(self.build_ledger(messages, response, "perf_critic_v1"))
        review = self._parse_review(response.content, response)
        task.reviews.append(review)

        logger.info(
            "critic.performance",
            task_id=task.task_id,
            decision=review.decision.value,
            score=review.score,
        )
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
                    critic_role="performance",
                    decision=ReviewDecision(data.get("decision", "REJECT")),
                    production_ready=data.get("production_ready", False),
                    fatal_flaw=data.get("fatal_flaw"),
                    flaw_category=data.get("flaw_category"),
                    flaw_explanation=data.get("flaw_explanation", ""),
                    mandatory_fix=data.get("mandatory_fix", ""),
                    suggestions=data.get("optimization_suggestions", []),
                    score=data.get("overall_score", 50),
                    model_used=response.model,
                    latency_ms=response.latency_ms,
                    token_count=response.total_tokens,
                )
            except (json.JSONDecodeError, ValueError, KeyError):
                pass
        return CriticReview(
            critic_role="performance",
            decision=ReviewDecision.REJECT,
            production_ready=False,
            fatal_flaw="Failed to parse performance critic response",
            mandatory_fix="Retry",
        )
