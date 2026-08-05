"""Repository Memory — tracks file ownership, change history, and impact."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_STORE_PATH = Path("./storage/repository_memory.json")


@dataclass
class FileOwnership:
    path: str
    primary_agent_role: str = "coder"
    last_modified_by_task: str = ""
    change_count: int = 0
    known_dependencies: list[str] = field(default_factory=list)


class RepositoryMemory:
    """Tracks which files were modified by which tasks."""

    def __init__(self) -> None:
        self._files: dict[str, FileOwnership] = {}
        self._load()

    def record_change(self, path: str, task_id: str, agent_role: str = "coder") -> None:
        rec = self._files.get(path) or FileOwnership(path=path)
        rec.last_modified_by_task = task_id
        rec.primary_agent_role = agent_role
        rec.change_count += 1
        self._files[path] = rec
        self._save()

    def get_owner(self, path: str) -> FileOwnership | None:
        return self._files.get(path)

    def frequently_changed(self, top_k: int = 10) -> list[FileOwnership]:
        sorted_files = sorted(self._files.values(), key=lambda f: f.change_count, reverse=True)
        return sorted_files[:top_k]

    def _load(self) -> None:
        if not _STORE_PATH.exists():
            return
        try:
            data = json.loads(_STORE_PATH.read_text())
            self._files = {k: FileOwnership(**v) for k, v in data.items()}
        except Exception:  # noqa: BLE001
            self._files = {}

    def _save(self) -> None:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STORE_PATH.write_text(json.dumps({k: vars(v) for k, v in self._files.items()}, indent=2))
