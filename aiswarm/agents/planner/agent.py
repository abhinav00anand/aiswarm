"""
Task Planner Agent — turns a Manager-assigned task into a precise deliverable.

The planner:
  - Analyzes the task description and target files
  - Identifies which existing code is relevant
  - Writes an implementation blueprint (NOT code — that's the Coder's job)
  - Determines what tests need to be written alongside the implementation
  - Classifies the task for the right critic rubric
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from aiswarm.agents.base.agent import BaseAgent
from aiswarm.llm.adapter import LLMMessage
from aiswarm.schemas.task import Task

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are the Task Planner Agent of AISwarm.

You receive a file-level task and produce a precise implementation blueprint.
You do NOT write code. You plan what the code must do.

Output JSON:
{
  "blueprint": "Step-by-step implementation plan (no code)",
  "interface_contract": "What public API this code must expose",
  "test_plan": ["Test case 1 description", "Test case 2 description"],
  "performance_targets": {"metric": "target value"},
  "security_considerations": ["consideration 1"],
  "dependencies_needed": ["library or module"],
  "rejection_risks": ["what critics will likely reject"],
  "complexity_estimate": "LOW|MEDIUM|HIGH",
  "suggested_approach": "High-level algorithmic approach"
}

Be precise. Do not invent requirements not in the task description.
"""


class PlannerAgent(BaseAgent):
    """Produces implementation blueprints before the coder writes code."""

    role = "planner"

    async def run(self, task: Task) -> dict[str, Any]:
        """
        Plan the task. Stores the blueprint in task.metadata['blueprint'].
        """
        logger.info("planner.planning", task_id=task.task_id)

        context_summary = self._summarize_context(task)
        messages = [
            LLMMessage(role="system", content=_SYSTEM_PROMPT),
            LLMMessage(
                role="user",
                content=f"""
Task: {task.title}
Description: {task.description}
Target files: {task.target_files}
Language: {task.target_language}
Acceptance criteria:
{chr(10).join(f'  - {c}' for c in task.acceptance_criteria)}

Existing context:
{context_summary}
""",
            ),
        ]
        response = await self.call_llm(messages, task=task, temperature=0.1)
        task.prompt_ledger.append(self.build_ledger(messages, response, "planner_v1"))

        plan = self._parse_plan(response.content)
        task.metadata["blueprint"] = plan
        logger.info(
            "planner.planned",
            task_id=task.task_id,
            complexity=plan.get("complexity_estimate", "?"),
        )
        return plan

    def _summarize_context(self, task: Task) -> str:
        if not task.context_files:
            return "(no context files selected yet)"
        lines = []
        for cf in task.context_files[:5]:
            lines.append(f"--- {cf.path} ({cf.token_count} tokens) ---")
            lines.append(cf.content[:500])
            lines.append("...")
        return "\n".join(lines)

    def _parse_plan(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return {"blueprint": content, "complexity_estimate": "MEDIUM"}
