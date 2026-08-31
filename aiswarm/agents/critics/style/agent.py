"""Style Critic Agent."""

from __future__ import annotations

import json
from typing import Any

import structlog

from aiswarm.agents.base.agent import BaseAgent
from aiswarm.llm.adapter import LLMMessage
from aiswarm.schemas.task import Task, CriticReview, ReviewDecision

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are the Style Critic Agent of AISwarm.

You review code exclusively for style, formatting, and language convention compliance.

Evaluation criteria (Python-focused, adapt for other languages):
1. PEP 8 compliance — line length, indentation, spacing
2. Import ordering — stdlib, third-party, local; alphabetical within groups
3. Naming conventions — snake_case for functions/variables, PascalCase for classes
4. String formatting — f-strings preferred over % or .format()
5. List/dict comprehensions — used where appropriate, not abused
6. Context managers — used for resource management (with statements)
7. Exception specificity — specific exceptions, not bare Exception
8. Constant naming — UPPER_SNAKE_CASE for module-level constants
9. Blank lines — 2 between top-level, 1 between methods
10. No trailing whitespace, consistent line endings

Rejection triggers:
- Inconsistent indentation (mixed tabs and spaces)
- Lines over 120 characters
- Wildcard imports (from x import *)
- Mutable default arguments (def f(x=[]))
- Comparison to None with == instead of is

Output ONLY valid JSON:
{
  "decision": "APPROVE" | "REJECT" | "ESCALATE",
  "production_ready": true | false,
  "pep8_compliant": true | false,
  "imports_ordered": true | false,
  "naming_consistent": true | false,
  "has_wildcard_imports": true | false,
  "has_mutable_defaults": true | false,
  "line_length_ok": true | false,
  "fatal_flaw": null or "description",
  "flaw_category": "FORMATTING|NAMING|IMPORTS|ANTI_PATTERN",
  "flaw_explanation": "Why this violates style standards",
  "mandatory_fix": "Exact fix required",
  "suggestions": ["non-fatal style improvements"],
  "overall_score": 0-100
}
"""


class StyleCritic(BaseAgent):
    """Reviews code style and formatting convention compliance."""

    role = "critic_style"

    async def run(self, task: Task) -> CriticReview:
        code = task.generated_code or ""
        if not code.strip():
            review = CriticReview(
                critic_role="style",
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
                content=f"""Review this code for style and convention compliance.

Task: {task.title}
Language: {task.target_language}

Code:
```{task.target_language}
{code[:8000]}
```

Respond with ONLY the JSON review object.""",
            ),
        ]
        response = await self.call_llm(messages, task=task, temperature=0.0)
        task.prompt_ledger.append(self.build_ledger(messages, response, "style_critic_v1"))
        review = self._parse_review(response.content, response)
        task.reviews.append(review)
        logger.info(
            "critic.style", task_id=task.task_id, decision=review.decision.value, score=review.score
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
                    critic_role="style",
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
            critic_role="style",
            decision=ReviewDecision.REJECT,
            production_ready=False,
            fatal_flaw="Failed to parse style critic response",
            mandatory_fix="Retry",
        )
