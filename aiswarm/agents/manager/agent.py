"""
Manager Agent — the engineering manager of AISwarm.

Responsibilities:
  - Receives a high-level goal from the Boss.
  - Decomposes it into file-level tasks with precise deliverables.
  - Assigns tasks to the workflow engine queue.
  - Monitors task progress and reassigns stuck tasks.
  - Defines target file structure and folder conventions.
  - Provides explicit acceptance criteria for each sub-task.

The Manager never writes code. It decomposes, assigns, and tracks.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog

from aiswarm.agents.base.agent import BaseAgent
from aiswarm.llm.adapter import LLMMessage
from aiswarm.schemas.task import Task, TaskPriority, TaskClass

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are the Manager Agent of AISwarm.

Your job is to decompose a high-level engineering goal into concrete, file-level tasks.
Each task must be:
- Scoped to one or two source files maximum
- Have clear, verifiable acceptance criteria
- Specify the target programming language
- Identify which existing files provide context

Output a JSON array of task objects:
[
  {
    "title": "Short task title",
    "description": "What exactly needs to be implemented or changed",
    "target_files": ["path/to/file.py"],
    "target_language": "python",
    "task_class": "FEATURE|BUGFIX|REFACTOR|PERFORMANCE|SECURITY|TEST",
    "priority": "CRITICAL|HIGH|NORMAL|LOW",
    "acceptance_criteria": ["criterion 1", "criterion 2"],
    "context_hints": ["files that provide relevant context"],
    "dependencies": ["task_title of prerequisite tasks"]
  }
]

Rules:
- Maximum 20 tasks per decomposition
- Each task must be independently testable
- Do not create tasks that span the entire codebase
- Performance tasks must specify measurable targets
- Security tasks must name the specific threat model
"""


@dataclass
class TaskSpec:
    """A raw task specification before it becomes a Task object."""
    title: str
    description: str
    target_files: list[str]
    target_language: str = "python"
    task_class: str = "FEATURE"
    priority: str = "NORMAL"
    acceptance_criteria: list[str] = None  # type: ignore[assignment]
    context_hints: list[str] = None  # type: ignore[assignment]
    dependencies: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.acceptance_criteria = self.acceptance_criteria or []
        self.context_hints = self.context_hints or []
        self.dependencies = self.dependencies or []


class ManagerAgent(BaseAgent):
    """
    Decomposes high-level goals into file-level task specifications.
    """

    role = "manager"

    async def run(self, task: Task) -> list[TaskSpec]:
        """
        The task here is the high-level goal (e.g. Boss created it).
        Returns a list of TaskSpec objects ready for the scheduler.
        """
        logger.info(
            "manager.decomposing",
            task_id=task.task_id,
            title=task.title,
        )
        messages = [
            LLMMessage(role="system", content=_SYSTEM_PROMPT),
            LLMMessage(
                role="user",
                content=self._build_decomposition_prompt(task),
            ),
        ]
        response = await self.call_llm(messages, task=task, temperature=0.2)
        task.prompt_ledger.append(self.build_ledger(messages, response, "manager_decompose_v1"))

        specs = self._parse_specs(response.content)
        logger.info(
            "manager.decomposed",
            task_id=task.task_id,
            subtask_count=len(specs),
        )
        return specs

    async def define_folder_structure(self, goal: str) -> str:
        """
        Ask the manager to suggest an optimal folder structure for a goal.
        Returns a markdown code block with the proposed tree.
        """
        messages = [
            LLMMessage(role="system", content=_SYSTEM_PROMPT),
            LLMMessage(
                role="user",
                content=(
                    f"Suggest the best folder structure for this project:\n\n{goal}\n\n"
                    "Return only a markdown code block with the directory tree. "
                    "Be precise and opinionated. Follow production conventions."
                ),
            ),
        ]
        response = await self.call_llm(messages, temperature=0.1)
        return response.content

    def _build_decomposition_prompt(self, task: Task) -> str:
        return f"""
Goal: {task.title}

Details:
{task.description}

Target language: {task.target_language}
Priority: {task.priority.value}

Break this into the minimum set of precise file-level tasks needed
to fully implement the goal at production quality.
Each task should be independently completable and testable.
"""

    def _parse_specs(self, content: str) -> list[TaskSpec]:
        text = content.strip()
        # Strip markdown fences
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        # Find JSON array
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                items = json.loads(text[start:end])
                return [
                    TaskSpec(
                        title=item.get("title", "Untitled"),
                        description=item.get("description", ""),
                        target_files=item.get("target_files", []),
                        target_language=item.get("target_language", "python"),
                        task_class=item.get("task_class", "FEATURE"),
                        priority=item.get("priority", "NORMAL"),
                        acceptance_criteria=item.get("acceptance_criteria", []),
                        context_hints=item.get("context_hints", []),
                        dependencies=item.get("dependencies", []),
                    )
                    for item in items
                ]
            except (json.JSONDecodeError, KeyError):
                pass
        logger.error("manager.parse_failed", content_preview=content[:200])
        return []
