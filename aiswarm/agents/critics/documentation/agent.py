"""Documentation Critic Agent."""

from __future__ import annotations

import json
from typing import Any

import structlog

from aiswarm.agents.base.agent import BaseAgent
from aiswarm.llm.adapter import LLMMessage
from aiswarm.schemas.task import Task, CriticReview, ReviewDecision

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are the Documentation Critic Agent of AISwarm.

You review code exclusively for documentation completeness and quality.

Per the Engineering Constitution: "Documentation is part of the product. Undocumented systems are incomplete."

Evaluation criteria:
1. Module docstring — every module must explain its purpose, responsibility, and key interfaces
2. Class docstrings — every public class must be documented
3. Function docstrings — every public function must document purpose, args, returns, raises
4. Parameter types — all public function parameters must have type hints
5. Example usage — complex APIs must include usage examples
6. Failure modes — error conditions and exceptions must be documented
7. Configuration — env vars and config options must be documented
8. Architecture notes — non-obvious design decisions must have explanatory comments

Rejection triggers:
- Public functions with no docstring
- Classes with no docstring
- Missing module-level docstring
- Undocumented exceptions (raises clause missing from docstring)
- Undocumented configuration parameters

Output ONLY valid JSON:
{
  "decision": "APPROVE" | "REJECT" | "ESCALATE",
  "production_ready": true | false,
  "has_module_docstring": true | false,
  "has_class_docstrings": true | false,
  "has_function_docstrings": true | false,
  "has_type_hints": true | false,
  "has_examples": true | false,
  "documents_exceptions": true | false,
  "fatal_flaw": null or "description",
  "flaw_category": "MISSING_DOCSTRING|MISSING_TYPES|UNDOCUMENTED_ERRORS|MISSING_EXAMPLES",
  "flaw_explanation": "Why this fails documentation standards",
  "mandatory_fix": "Exact fix required",
  "suggestions": ["non-fatal improvements"],
  "overall_score": 0-100
}
"""

class DocumentationCritic(BaseAgent):
    """Reviews code documentation completeness and quality."""

    role = "critic_documentation"

    async def run(self, task: Task) -> CriticReview:
        code = task.generated_code or ""
        if not code.strip():
            review = CriticReview(
                critic_role="documentation",
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
                content=f"""Review this code for documentation completeness.

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
        task.prompt_ledger.append(self.build_ledger(messages, response, "doc_critic_v1"))
        review = self._parse_review(response.content, response)
        task.reviews.append(review)
        logger.info("critic.documentation", task_id=task.task_id, decision=review.decision.value, score=review.score)
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
                    critic_role="documentation",
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
            critic_role="documentation",
            decision=ReviewDecision.REJECT,
            production_ready=False,
            fatal_flaw="Failed to parse documentation critic response",
            mandatory_fix="Retry",
        )
