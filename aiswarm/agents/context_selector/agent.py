"""
Context Selector Agent — RAG-powered context retrieval.

Policy engine (not just search):
  - Knows the difference between public API files, implementation internals,
    test fixtures, and generated artifacts.
  - Selects the smallest useful set of files.
  - Never sends the entire repository unless Boss explicitly approves it.
  - Records every selection decision in the prompt ledger.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import structlog

from aiswarm.agents.base.agent import BaseAgent
from aiswarm.llm.adapter import LLMMessage
from aiswarm.schemas.task import Task, FileContext

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are the Context Selector Agent of AISwarm.

You select the minimum set of files a coder needs to complete a task.
You never include entire repositories. You think like a senior engineer
who knows which file to open first.

Rules:
1. Public API headers / interface files → always include if the task touches them
2. Direct implementation files → include if being modified
3. Test fixtures → include only if the task involves fixing test regressions
4. Generated files → never include (they are derived, not authoritative)
5. Configuration files → include only if the task touches config
6. Maximum 15 files, maximum 8000 total tokens

Output a JSON array:
[
  {
    "path": "relative/file/path.py",
    "reason": "Why this file is needed",
    "lines": null or [start_line, end_line]
  }
]

If you need only specific functions from a large file, specify the line range.
"""


class ContextSelectorAgent(BaseAgent):
    """Selects the minimum necessary context files for a task."""

    role = "context_selector"

    def __init__(self, router: Any, model: str, repo_root: str = ".", **kwargs: Any) -> None:
        super().__init__(router, model, **kwargs)
        self._repo_root = Path(repo_root)
        self._max_files = kwargs.get("config", {}).get("max_files", 15)
        self._max_tokens = kwargs.get("config", {}).get("max_tokens", 8000)

    async def run(self, task: Task) -> list[FileContext]:
        """
        Select context files for the task.
        Populates task.context_files.
        """
        logger.info("context_selector.selecting", task_id=task.task_id)

        # First: check if RAG index is available
        context_files: list[FileContext] = []

        # LLM-assisted selection based on task description + available files
        available = self._list_available_files()
        messages = [
            LLMMessage(role="system", content=_SYSTEM_PROMPT),
            LLMMessage(
                role="user",
                content=self._build_prompt(task, available),
            ),
        ]
        response = await self.call_llm(messages, task=task, temperature=0.0)
        selections = self._parse_selections(response.content)

        for sel in selections[: self._max_files]:
            content = self._read_file(sel["path"], sel.get("lines"))
            if content is not None:
                ctx = FileContext(
                    path=sel["path"],
                    content=content,
                    reason=sel.get("reason", "context"),
                    token_count=len(content.split()) * 4 // 3,  # rough estimate
                    relevance_score=1.0,
                )
                context_files.append(ctx)

        task.context_files = context_files
        task.prompt_ledger.append(
            self.build_ledger(messages, response, "ctx_selector_v1")
        )

        logger.info(
            "context_selector.selected",
            task_id=task.task_id,
            file_count=len(context_files),
        )
        return context_files

    def _list_available_files(self) -> list[str]:
        """Walk the repo and return relative paths of source files."""
        extensions = {".py", ".ts", ".js", ".cpp", ".rs", ".h", ".hpp", ".md"}
        skip_dirs = {
            ".git", "__pycache__", "node_modules", ".venv", "venv",
            "dist", "build", ".mypy_cache", ".ruff_cache",
        }
        files: list[str] = []
        for path in self._repo_root.rglob("*"):
            if any(part in skip_dirs for part in path.parts):
                continue
            if path.is_file() and path.suffix in extensions:
                try:
                    rel = str(path.relative_to(self._repo_root))
                    files.append(rel)
                except ValueError:
                    pass
        return sorted(files)[:200]  # cap at 200 for prompt size

    def _build_prompt(self, task: Task, available: list[str]) -> str:
        file_list = "\n".join(f"  {f}" for f in available[:100])
        return f"""
Select the minimum files needed for this task.

Task: {task.title}
Description: {task.description}
Target files: {task.target_files}
Language: {task.target_language}
Context hints from manager: {task.metadata.get("context_hints", [])}

Available files in repository:
{file_list}

Select only the files the coder genuinely needs. Output JSON array only.
"""

    def _parse_selections(self, content: str) -> list[dict[str, Any]]:
        import json
        text = content.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        start, end = text.find("["), text.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return []

    def _read_file(
        self, path: str, lines: list[int] | None = None
    ) -> str | None:
        full_path = self._repo_root / path
        if not full_path.exists() or not full_path.is_file():
            return None
        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
            if lines and len(lines) == 2:
                all_lines = content.splitlines()
                start, end = max(0, lines[0] - 1), min(len(all_lines), lines[1])
                content = "\n".join(all_lines[start:end])
            # Truncate very large files
            return content[:12000]
        except OSError:
            return None
