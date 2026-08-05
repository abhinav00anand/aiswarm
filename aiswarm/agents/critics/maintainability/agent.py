"""Maintainability Critic Agent — reviews code for long-term maintenance quality."""

from __future__ import annotations

import json
from typing import Any

import structlog

from aiswarm.agents.base.agent import BaseAgent
from aiswarm.llm.adapter import LLMMessage
from aiswarm.schemas.task import Task, CriticReview, ReviewDecision

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are the Maintainability Critic Agent of AISwarm.

You review code exclusively for long-term maintainability and readability.

Evaluation criteria:
1. Naming — variables, functions, classes must have clear, intention-revealing names
2. Function length — functions over 50 lines must be decomposed
3. Complexity — cyclomatic complexity must be low (no deeply nested conditionals)
4. Comments — complex logic must have explanatory comments; obvious code must NOT be over-commented
5. Magic numbers/strings — all literals must be named constants
6. Dead code — no unreachable, commented-out, or unused code
7. TODO/FIXME — no unresolved placeholders in production code
8. Configuration — hardcoded values must be configurable
9. Logging — sufficient logging for operational diagnosis
10. Type hints — all public functions must be fully type-annotated

Rejection triggers:
- Functions longer than 100 lines without clear justification
- Single-letter variable names outside mathematical/loop contexts
- Magic numbers used more than once without a named constant
- TODO or FIXME comments in production code paths
- Commented-out blocks of old code

Output ONLY valid JSON:
{
  "decision": "APPROVE" | "REJECT" | "ESCALATE",
  "production_ready": true | false,
  "naming_quality": 0-10,
  "function_length_ok": true | false,
  "complexity_ok": true | false,
  "has_magic_numbers": true | false,
  "has_dead_code": true | false,
  "has_todo_fixme": true | false,
  "type_hints_complete": true | false,
  "fatal_flaw": null or "description",
  "flaw_category": "NAMING|COMPLEXITY|DEAD_CODE|MAGIC_VALUES|MISSING_TYPES",
  "flaw_explanation": "Why this fails maintainability standards",
  "mandatory_fix": "Exact fix required",
  "suggestions": ["non-fatal improvements"],
  "overall_score": 0-100
}
"""


class MaintainabilityCritic(BaseAgent):
    """Reviews code readability and long-term maintainability."""

    role = "critic_maintainability"

    async def run(self, task: Task) -> CriticReview:
        code = task.generated_code or ""
        if not code.strip():
            review = CriticReview(
                critic_role="maintainability",
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
                content=f"""Review this code for maintainability and readability.

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
        task.prompt_ledger.append(self.build_ledger(messages, response, "maintain_critic_v1"))
        review = self._parse_review(response.content, response)
        task.reviews.append(review)
        logger.info("critic.maintainability", task_id=task.task_id, decision=review.decision.value, score=review.score)
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
                    critic_role="maintainability",
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
            critic_role="maintainability",
            decision=ReviewDecision.REJECT,
            production_ready=False,
            fatal_flaw="Failed to parse maintainability critic response",
            mandatory_fix="Retry",
        )
