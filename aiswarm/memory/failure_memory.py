"""Failure Memory."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_STORE_PATH = Path("./storage/failure_memory.json")


@dataclass
class FailureRecord:
    task_id: str
    task_title: str
    error_pattern: str  # e.g. "circular import", "numpy not available"
    error_source: str  # "compiler" | "security_critic" | "test"
    resolution: str  # what fixed it
    resolved_at: float = field(default_factory=time.time)
    retry_count_at_resolution: int = 0
    tags: list[str] = field(default_factory=list)


class FailureMemory:
    """
    Stores and retrieves past failure patterns for proactive resolution.
    """

    def __init__(self) -> None:
        self._records: list[FailureRecord] = []
        self._load()

    def record(self, record: FailureRecord) -> None:
        self._records.append(record)
        self._save()
        logger.info(
            "failure_memory.recorded",
            task_id=record.task_id,
            pattern=record.error_pattern,
        )

    def find_similar(self, error_text: str, top_k: int = 3) -> list[FailureRecord]:
        """Return past failure records whose pattern appears in the error text."""
        matches = [r for r in self._records if r.error_pattern.lower() in error_text.lower()]
        return sorted(matches, key=lambda r: r.resolved_at, reverse=True)[:top_k]

    def resolution_hint(self, error_text: str) -> str | None:
        """Return the most recent resolution hint for an error pattern."""
        matches = self.find_similar(error_text, top_k=1)
        if matches:
            return f"[Past fix for '{matches[0].error_pattern}']: {matches[0].resolution}"
        return None

    def _load(self) -> None:
        if not _STORE_PATH.exists():
            return
        try:
            data = json.loads(_STORE_PATH.read_text())
            self._records = [FailureRecord(**item) for item in data]
        except Exception:  # noqa: BLE001
            self._records = []

    def _save(self) -> None:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STORE_PATH.write_text(json.dumps([vars(r) for r in self._records], indent=2, default=str))
