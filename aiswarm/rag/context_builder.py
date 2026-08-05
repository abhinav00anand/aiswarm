"""Context builder — assembles the final prompt context from retrieved files."""

from __future__ import annotations

from aiswarm.schemas.task import Task, FileContext


class ContextBuilder:
    """Assembles file contexts into a prompt-ready string."""

    def __init__(self, max_tokens: int = 8000) -> None:
        self._max_tokens = max_tokens

    def build(self, task: Task) -> str:
        """Return a formatted context block for the task's context files."""
        if not task.context_files:
            return "(no context files selected)"

        parts: list[str] = []
        token_count = 0

        for cf in task.context_files:
            if token_count + cf.token_count > self._max_tokens:
                parts.append(f"\n--- {cf.path} [TRUNCATED — token budget exceeded] ---\n")
                break
            parts.append(
                f"\n--- FILE: {cf.path} ---\n"
                f"# Reason: {cf.reason}\n"
                f"{cf.content}\n"
            )
            token_count += cf.token_count

        return "\n".join(parts)

    def token_budget_used(self, task: Task) -> int:
        return sum(cf.token_count for cf in task.context_files)
