"""Testing Critic Agent — reviews code for testability and test coverage quality."""

from __future__ import annotations

import json
from typing import Any

import structlog

from aiswarm.agents.base.agent import BaseAgent
from aiswarm.llm.adapter import LLMMessage
from aiswarm.schemas.task import Task, CriticReview, ReviewDecision

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are the Testing Critic Agent of AISwarm.

You review code exclusively for testability and test quality.

Evaluation criteria:
1. Test coverage — critical paths must have unit tests
2. Test isolation — tests must not depend on external state
3. Assertions — tests must have meaningful, specific assertions
4. Edge cases — boundary conditions must be tested
5. Test naming — names must describe behavior, not implementation
6. Mocking — external dependencies must be properly mocked
7. Determinism — tests must produce identical results on every run
8. No test anti-patterns: no sleep(), no hardcoded ports, no file system side-effects

Rejection triggers:
- Zero tests for new public functions
- Tests that always pass (no assertions or trivial assertions)
- Tests that depend on network, filesystem, or external services without mocking
- Non-deterministic tests (time.sleep, random without seed)
- Tests that test implementation details rather than behavior

Output ONLY valid JSON:
{
  "decision": "APPROVE" | "REJECT" | "ESCALATE",
  "production_ready": true | false,
  "has_unit_tests": true | false,
  "has_edge_case_tests": true | false,
  "has_proper_mocking": true | false,
  "test_isolation": true | false,
  "estimated_coverage_pct": 0-100,
  "fatal_flaw": null or "description",
  "flaw_category": "MISSING_TESTS|BAD_ASSERTIONS|NON_DETERMINISTIC|NO_ISOLATION|ANTI_PATTERN",
  "flaw_explanation": "Why this fails production testing standards",
  "mandatory_fix": "Exact fix required",
  "suggestions": ["non-fatal improvements"],
  "overall_score": 0-100
}
"""


class TestingCritic(BaseAgent):
    """Reviews code testability and test suite quality."""

    role = "critic_testing"

    async def run(self, task: Task) -> CriticReview:
        code = task.generated_code or ""
        if not code.strip():
            review = CriticReview(
                critic_role="testing",
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
                content=f"""Review this code for testability and test quality.

Task: {task.title}
Language: {task.target_language}
Test plan from blueprint: {task.metadata.get("blueprint", {}).get("test_plan", []) if isinstance(task.metadata.get("blueprint"), dict) else ""}

Code:
```{task.target_language}
{code[:8000]}
```

Respond with ONLY the JSON review object.""",
            ),
        ]
        response = await self.call_llm(messages, task=task, temperature=0.1)
        task.prompt_ledger.append(self.build_ledger(messages, response, "test_critic_v1"))
        review = self._parse_review(response.content, response)
        task.reviews.append(review)
        logger.info("critic.testing", task_id=task.task_id, decision=review.decision.value, score=review.score)
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
                    critic_role="testing",
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
            critic_role="testing",
            decision=ReviewDecision.REJECT,
            production_ready=False,
            fatal_flaw="Failed to parse testing critic response",
            mandatory_fix="Retry",
        )
