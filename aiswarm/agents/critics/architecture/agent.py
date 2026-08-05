"""
Architecture Critic Agent — reviews code for structural correctness.

Evaluates: SOLID, DRY, KISS, YAGNI, separation of concerns, coupling,
cohesion, abstraction quality, dependency direction, and module design.
Emits a structured JSON review with veto power on architectural violations.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from aiswarm.agents.base.agent import BaseAgent
from aiswarm.llm.adapter import LLMMessage
from aiswarm.schemas.task import Task, CriticReview, ReviewDecision

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are the Architecture Critic Agent of AISwarm.

You review code exclusively for architectural quality. You do NOT review
for security or performance — those have dedicated critics.

Your evaluation criteria:
1. SOLID principles (Single Responsibility, Open/Closed, Liskov, Interface Segregation, Dependency Inversion)
2. DRY — no duplicated logic
3. KISS — no unnecessary complexity
4. YAGNI — no speculative generality
5. Separation of concerns — each module has one reason to change
6. Coupling — low coupling between modules
7. Cohesion — high cohesion within modules
8. Abstraction quality — abstractions reduce complexity, not add it
9. Dependency direction — dependencies point inward (no circular imports)
10. Module boundaries — each module has a clear public API

Rejection criteria (any one is sufficient to reject):
- God objects or god functions (>300 lines doing multiple things)
- Circular dependencies
- Business logic in infrastructure layer
- Direct framework dependency inside domain objects
- Unwarranted inheritance instead of composition
- Hidden global state or singleton abuse
- Missing interfaces where polymorphism is needed

Output ONLY valid JSON:
{
  "decision": "APPROVE" | "REJECT" | "ESCALATE",
  "production_ready": true | false,
  "solid_compliance": true | false,
  "separation_of_concerns": true | false,
  "coupling_score": 0-10,
  "cohesion_score": 0-10,
  "abstraction_quality": 0-10,
  "fatal_flaw": "null or one-sentence description of the worst violation",
  "flaw_category": "null or category name",
  "flaw_explanation": "Why this flaw fails production standards",
  "mandatory_fix": "Exactly what the coder must do to fix the fatal flaw",
  "suggestions": ["non-fatal improvement suggestions"],
  "overall_score": 0-100
}

Be strict. A score below 70 should be REJECT.
"""


class ArchitectureCritic(BaseAgent):
    """Reviews code structural and architectural quality."""

    role = "critic_architecture"

    async def run(self, task: Task) -> CriticReview:
        code = task.generated_code or ""
        if not code.strip():
            review = CriticReview(
                critic_role="architecture",
                decision=ReviewDecision.REJECT,
                production_ready=False,
                fatal_flaw="No code generated",
                mandatory_fix="Coder must generate non-empty code",
            )
            task.reviews.append(review)
            return review

        messages = [
            LLMMessage(role="system", content=_SYSTEM_PROMPT),
            LLMMessage(
                role="user",
                content=self._build_prompt(task, code),
            ),
        ]
        response = await self.call_llm(messages, task=task, temperature=0.1)
        task.prompt_ledger.append(self.build_ledger(messages, response, "arch_critic_v1"))

        review = self._parse_review(response.content, response)
        task.reviews.append(review)

        logger.info(
            "critic.architecture",
            task_id=task.task_id,
            decision=review.decision.value,
            score=review.score,
            fatal_flaw=review.fatal_flaw,
        )
        return review

    def _build_prompt(self, task: Task, code: str) -> str:
        blueprint = task.metadata.get("blueprint", {})
        bp_text = (
            blueprint.get("blueprint", "")
            if isinstance(blueprint, dict)
            else str(blueprint)
        )
        return f"""
Review this code for architectural quality.

Task: {task.title}
Language: {task.target_language}
Implementation blueprint for reference:
{bp_text[:500]}

Code to review:
```{task.target_language}
{code[:8000]}
```

Respond with ONLY the JSON review object.
"""

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
                    critic_role="architecture",
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
            critic_role="architecture",
            decision=ReviewDecision.REJECT,
            production_ready=False,
            fatal_flaw="Failed to parse critic response",
            mandatory_fix="Coder should retry; critic parsing error occurred",
        )
