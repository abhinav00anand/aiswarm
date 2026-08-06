"""
Boss Agent — the supreme authority in AISwarm.

Responsibilities:
  - Receives high-level goals and decomposes them into Manager-level assignments.
  - Oversees the entire system: reads logs, detects anomalies, intervenes.
  - Resolves deadlocks by reading the full deadlock packet and issuing corrective directives.
  - Can override any agent decision with a documented reason.
  - Has direct access to the main codebase (repo_root) for read/write operations.
  - Escalates critical failures to operators via notifications.

The Boss operates at the highest abstraction level and should never
be bogged down in implementation details.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from aiswarm.agents.base.agent import BaseAgent
from aiswarm.llm.adapter import LLMMessage
from aiswarm.schemas.task import Task, TaskState, TaskPriority, TaskClass
from aiswarm.core.state_machine import StateMachine
from aiswarm.agents.host2.manager import Host2CapabilityManager
from aiswarm.schemas.capabilities import CapabilityRequest

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are the Boss Agent of AISwarm — the highest authority in the system.

Your mandate:
1. Decompose high-level engineering goals into concrete tasks for the Manager.
2. Oversee the entire pipeline and intervene when agents are stuck.
3. Resolve deadlocks by diagnosing root causes and issuing precise corrective directives.
4. Override incorrect decisions with documented reasoning.
5. Protect system integrity: reject goals that are unsafe, ill-defined, or impossible.

Engineering Constitution you enforce:
- Correctness > Security > Reliability > Maintainability > Performance > Speed
- No code merges without passing: compilation + tests + numeric equivalence + critics
- Context stuffing is forbidden — only necessary files in prompts
- Every decision must be traceable and explainable

When resolving deadlocks, your output MUST be a JSON object:
{
  "action": "RETRY_WITH_DIRECTIVE" | "DECOMPOSE" | "REJECT" | "ESCALATE",
  "directive": "Precise instruction to the coder for the next attempt",
  "root_cause": "What caused the deadlock",
  "files_to_open": ["list of files to add to context"],
  "new_acceptance_criteria": ["updated criteria if needed"]
}
"""


class BossAgent(BaseAgent):
    """
    The Boss Agent — system administrator, deadlock resolver, goal decomposer.
    """

    role = "boss"

    def __init__(self, router: Any, model: str, repo_root: str = ".", **kwargs: Any) -> None:
        super().__init__(router, model, **kwargs)
        self._repo_root = Path(repo_root)

    async def run(self, task: Task) -> dict[str, Any]:
        """
        Boss reviews the task at a high level and validates it before the pipeline starts.
        Returns a directive dict.
        """
        logger.info("boss.reviewing_task", task_id=task.task_id, title=task.title)

        messages = [
            LLMMessage(role="system", content=_SYSTEM_PROMPT),
            LLMMessage(
                role="user",
                content=self._build_review_prompt(task),
            ),
        ]
        response = await self.call_llm(messages, task=task, temperature=0.1)
        task.prompt_ledger.append(self.build_ledger(messages, response, "boss_review_v1"))

        directive = self._parse_response(response.content)
        logger.info(
            "boss.review_complete",
            task_id=task.task_id,
            action=directive.get("action"),
        )
        return directive

    async def request_host2_capability(self, capability_name: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Request a specific capability from Host-2."""
        request = CapabilityRequest(
            capability_name=capability_name,
            requester_role="boss",
            parameters=parameters,
        )
        manager = Host2CapabilityManager()
        return await manager.execute_capability(request)

    async def execute_hybrid_task(self, task: Task) -> dict[str, Any]:
        """
        Execute a task in Hybrid Mode.
        Decomposes the task, delegates to Host-2, handles escalations, and merges results.
        """
        logger.info("boss.executing_hybrid", task_id=task.task_id)
        
        # 1. Decompose subtasks from task description
        prompt = f"""
Decompose the following task into lightweight subtasks for Host-2 execution:
Task: {task.description}

Output a JSON object with key "subtasks" as a list of subtask instruction strings:
{{
  "subtasks": ["subtask 1", "subtask 2"]
}}
"""
        messages = [
            LLMMessage(role="system", content=_SYSTEM_PROMPT),
            LLMMessage(role="user", content=prompt),
        ]
        response = await self.call_llm(messages, task=task, temperature=0.1)
        
        try:
            parsed = self._parse_response(response.content)
            subtasks = parsed.get("subtasks") or parsed.get("directive")
            if isinstance(subtasks, str):
                try:
                    subtasks = json.loads(subtasks)
                except Exception:
                    subtasks = [subtasks]
            if not isinstance(subtasks, list):
                subtasks = [task.description]
        except Exception:
            subtasks = [task.description]
            
        results = []
        for i, subtask in enumerate(subtasks):
            # 2. Delegate to Host-2
            logger.info("boss.hybrid_delegate", subtask=subtask)
            res = await self.request_host2_capability("lightweight_execution", {"instruction": str(subtask)})
            
            # 3. Handle EscalationPackets
            if res.get("status") in ["ESCALATED", "escalated"]:
                logger.warning("boss.hybrid_escalation", packet=res)
                res["resolution"] = "Boss logged escalation"
                
            results.append({"subtask": subtask, "result": res})
            
        # 4. Merge results and return
        return {
            "status": "success",
            "hybrid_execution": True,
            "subtasks_completed": len(results),
            "results": results
        }


    async def handle_deadlock(self, task: Task) -> dict[str, Any]:
        """
        Called by the orchestrator when a task enters DEADLOCK state.
        Boss reads the full deadlock packet and decides how to proceed.
        """
        logger.warning(
            "boss.handling_deadlock",
            task_id=task.task_id,
            retry_count=task.retry_count,
        )

        prompt = f"""
DEADLOCK RESOLUTION REQUEST

{task.deadlock_summary or 'No deadlock summary available.'}

Analyze the root cause and provide a precise resolution directive.
The system has exhausted {task.retry_count} retry attempts.
Every previous rejection reason is listed above.

Your JSON response must specify exactly what the coder should do differently.
"""
        messages = [
            LLMMessage(role="system", content=_SYSTEM_PROMPT),
            LLMMessage(role="user", content=prompt),
        ]
        response = await self.call_llm(messages, task=task, temperature=0.0)
        directive = self._parse_response(response.content)

        if directive.get("action") == "RETRY_WITH_DIRECTIVE":
            task.boss_override = directive.get("directive", "")
            task.retry_count = 0  # reset retry counter after boss intervention
            StateMachine.transition(
                task,
                TaskState.ESCALATED,
                reason=f"Boss override: {directive.get('root_cause', '')}",
                agent="boss",
                evidence={"directive": directive},
            )
            logger.info(
                "boss.deadlock_resolved",
                task_id=task.task_id,
                action=directive.get("action"),
            )
        elif directive.get("action") == "REJECT":
            StateMachine.transition(
                task,
                TaskState.REJECTED,
                reason=f"Boss rejected: {directive.get('root_cause', '')}",
                agent="boss",
            )

        return directive

    def _build_review_prompt(self, task: Task) -> str:
        criteria = "\n".join(f"  - {c}" for c in task.acceptance_criteria) or "  (none specified)"
        return f"""
Review this incoming task and confirm it is well-defined and achievable.

Title: {task.title}
Description: {task.description}
Target language: {task.target_language}
Target files: {task.target_files}
Priority: {task.priority.value}
Class: {task.task_class.value}

Acceptance criteria:
{criteria}

Respond with a JSON directive. If the task is valid, use action=RETRY_WITH_DIRECTIVE
with directive="PROCEED". If the task needs clarification, use action=DECOMPOSE.
"""

    def _parse_response(self, content: str) -> dict[str, Any]:
        """Extract JSON from the response, tolerating markdown fences."""
        text = content.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        # Find first { ... }
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return {"action": "RETRY_WITH_DIRECTIVE", "directive": content}

    async def read_log(self, log_path: str, tail_lines: int = 100) -> str:
        """Boss can read any log file for diagnosis."""
        path = self._repo_root / log_path
        if not path.exists():
            return f"Log not found: {log_path}"
        lines = path.read_text(encoding="utf-8").splitlines()
        return "\n".join(lines[-tail_lines:])

    async def read_file(self, file_path: str) -> str:
        """Boss has direct read access to the codebase."""
        path = self._repo_root / file_path
        if not path.exists():
            return f"File not found: {file_path}"
        return path.read_text(encoding="utf-8")

    async def write_file(self, file_path: str, content: str, reason: str) -> None:
        """Boss can directly write files when escalation requires it."""
        path = self._repo_root / file_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.warning(
            "boss.direct_write",
            file=str(path),
            reason=reason,
        )
