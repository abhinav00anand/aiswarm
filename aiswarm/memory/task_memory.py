"""Task Memory — persists task descriptions and outcomes for future reference."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_STORE_PATH = Path("./storage/task_memory.json")


@dataclass
class TaskRecord:
    task_id: str
    title: str
    description: str
    task_class: str
    final_state: str
    retry_count: int
    total_tokens: int
    cost_usd: float
    merged: bool
    created_at: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)


class TaskMemory:
    """Stores a searchable log of completed task outcomes."""

    def __init__(self) -> None:
        self._records: list[TaskRecord] = []
        self._load()

    def record(self, rec: TaskRecord) -> None:
        self._records.append(rec)
        self._save()

    def find_similar(self, title: str, top_k: int = 5) -> list[TaskRecord]:
        title_lower = title.lower()
        scored = [
            (sum(1 for w in title_lower.split() if w in r.title.lower()), r)
            for r in self._records
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:top_k] if _ > 0]

    def success_rate(self) -> float:
        if not self._records:
            return 0.0
        merged = sum(1 for r in self._records if r.merged)
        return merged / len(self._records)

    def _load(self) -> None:
        if not _STORE_PATH.exists():
            return
        try:
            data = json.loads(_STORE_PATH.read_text())
            self._records = [TaskRecord(**item) for item in data]
        except Exception:  # noqa: BLE001
            self._records = []

    def _save(self) -> None:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STORE_PATH.write_text(
            json.dumps([vars(r) for r in self._records], indent=2)
        )
