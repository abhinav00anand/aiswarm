"""
Coder Agent — the primary code generator in AISwarm.

The Coder:
  - Receives the task, blueprint, and RAG-selected context files
  - Generates complete, production-ready code (no placeholders, no TODOs)
  - Incorporates rejection feedback from Critics and compiler errors
  - Respects the immutable environment policy (allowed imports, compiler versions)
  - Produces exactly the code for the target files — nothing more

The Coder is the most expensive agent and should only receive the
minimum necessary context as determined by the ContextSelector.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import structlog

from aiswarm.agents.base.agent import BaseAgent
from aiswarm.llm.adapter import LLMMessage
from aiswarm.schemas.task import Task

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are the Coder Agent of AISwarm.

You write high-quality, robust code. Every line you produce must satisfy:
✓ Correct — mathematically and logically accurate
✓ Fully typed — type hints on every function signature
✓ Fully documented — docstrings on every module, class, and public function
✓ No placeholders, TODOs, or mock implementations
✓ No dead code or unreachable branches
✓ Deterministic behavior
✓ Fail-fast: raise explicit exceptions, never silently return defaults
✓ SOLID, DRY, KISS principles throughout

Output format: Return ONLY the complete file content. No markdown fences.
No explanation. No comments outside the code itself. Just the code.

If you are revising rejected code:
- Read every rejection reason carefully
- Fix all identified flaws
- Do not introduce new issues while fixing old ones
"""

_REVISION_PREFIX = """\
The following code was REJECTED. You must fix ALL identified flaws.

Rejection reasons:
{reasons}

Compiler errors (if any):
{compiler_errors}

Test failures (if any):
{test_failures}

Boss directive (if any):
{boss_directive}

Previous code:
```
{previous_code}
```

Now write the corrected, fully-implemented version:
"""


class CoderAgent(BaseAgent):
    """Generates clean, robust code from plans and context."""

    role = "coder"

    async def run(self, task: Task) -> str:
        """
        Generate or revise code for the task.
        Stores result in task.generated_code and task.generated_code_hash.
        Returns the generated code string.
        """
        is_revision = task.retry_count > 0 and task.generated_code is not None
        logger.info(
            "coder.generating",
            task_id=task.task_id,
            revision=is_revision,
            retry=task.retry_count,
        )

        messages = self._build_messages(task)
        response = await self.call_llm(messages, task=task, temperature=self._temperature)
        task.prompt_ledger.append(self.build_ledger(messages, response, f"coder_v{task.retry_count + 1}"))

        code = self._clean_code(response.content)
        task.generated_code = code
        task.generated_code_hash = hashlib.sha256(code.encode()).hexdigest()
        # Clear previous review results for the new attempt
        task.reviews = []
        task.compiler_output = None
        task.test_output = None
        task.benchmark_output = None
        task.precheck_passed = None

        logger.info(
            "coder.generated",
            task_id=task.task_id,
            chars=len(code),
            hash=task.generated_code_hash[:12],
        )
        return code

    def _build_messages(self, task: Task) -> list[LLMMessage]:
        blueprint = task.metadata.get("blueprint", {})
        context_block = self._format_context(task)

        if task.retry_count > 0 and task.generated_code is not None:
            # Revision prompt
            revision_content = _REVISION_PREFIX.format(
                reasons="\n".join(f"  - {r}" for r in task.rejection_reasons()) or "(none)",
                compiler_errors=task.compiler_output.stderr[:2000] if task.compiler_output else "(none)",
                test_failures=task.test_output.stdout[:2000] if task.test_output else "(none)",
                boss_directive=task.boss_override or "(none)",
                previous_code=task.generated_code[:4000],
            )
            user_content = f"{revision_content}\n\n{context_block}"
        else:
            # First attempt
            plan_text = (
                blueprint.get("blueprint", "No plan available")
                if isinstance(blueprint, dict)
                else str(blueprint)
            )
            acceptance = "\n".join(
                f"  ✓ {c}" for c in task.acceptance_criteria
            ) or "  (none specified)"

            user_content = f"""
Implement the following task at production quality.

Task: {task.title}
Language: {task.target_language}
Target file(s): {", ".join(task.target_files)}

Implementation blueprint:
{plan_text}

Acceptance criteria:
{acceptance}

Context files (use only what you need):
{context_block}

Write the complete implementation now. No markdown fences. No placeholders.
"""

        return [
            LLMMessage(role="system", content=_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user_content),
        ]

    def _format_context(self, task: Task) -> str:
        if not task.context_files:
            return "(no context files)"
        parts = []
        for cf in task.context_files[:10]:  # max 10 context files
            parts.append(f"\n--- FILE: {cf.path} (reason: {cf.reason}) ---\n{cf.content}\n")
        return "\n".join(parts)

    def _clean_code(self, content: str) -> str:
        """Strip markdown fences if the model added them anyway."""
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            # Drop first line (```python or ```) and last line (```)
            inner = lines[1:] if lines[0].startswith("```") else lines
            if inner and inner[-1].strip() == "```":
                inner = inner[:-1]
            return "\n".join(inner)
        return text
