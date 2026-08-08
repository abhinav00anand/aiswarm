"""Working Memory."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

@dataclass
class WorkingMemory:
    """Ephemeral memory for a single task execution."""
    task_id: str
    created_at: float = field(default_factory=time.time)
    current_prompt: str = ""
    last_response: str = ""
    active_context_paths: list[str] = field(default_factory=list)
    intermediate_results: dict[str, Any] = field(default_factory=dict)
    token_budget_remaining: int = 100_000

    def store(self, key: str, value: Any) -> None:
        self.intermediate_results[key] = value

    def retrieve(self, key: str, default: Any = None) -> Any:
        return self.intermediate_results.get(key, default)

    def clear(self) -> None:
        self.intermediate_results.clear()
        self.current_prompt = ""
        self.last_response = ""
        self.active_context_paths = []

class WorkingMemoryStore:
    """Registry of per-task working memory instances."""

    def __init__(self) -> None:
        self._store: dict[str, WorkingMemory] = {}

    def get_or_create(self, task_id: str) -> WorkingMemory:
        if task_id not in self._store:
            self._store[task_id] = WorkingMemory(task_id=task_id)
        return self._store[task_id]

    def clear(self, task_id: str) -> None:
        mem = self._store.get(task_id)
        if mem:
            mem.clear()

    def evict(self, task_id: str) -> None:
        self._store.pop(task_id, None)
