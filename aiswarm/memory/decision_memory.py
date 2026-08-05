"""Decision Memory — records architectural decisions for consistency."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

_STORE_PATH = Path("./storage/decision_memory.json")


@dataclass
class DecisionRecord:
    decision_id: str
    context: str
    decision: str
    rationale: str
    made_by: str  # boss | manager | human
    alternatives: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    superseded_by: str | None = None


class DecisionMemory:
    """Records and retrieves past architectural decisions."""

    def __init__(self) -> None:
        self._records: list[DecisionRecord] = []
        self._load()

    def record(self, rec: DecisionRecord) -> None:
        self._records.append(rec)
        self._save()

    def find(self, context_keyword: str) -> list[DecisionRecord]:
        kw = context_keyword.lower()
        return [r for r in self._records if kw in r.context.lower() and not r.superseded_by]

    def _load(self) -> None:
        if not _STORE_PATH.exists():
            return
        try:
            data = json.loads(_STORE_PATH.read_text())
            self._records = [DecisionRecord(**item) for item in data]
        except Exception:  # noqa: BLE001
            self._records = []

    def _save(self) -> None:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STORE_PATH.write_text(json.dumps([vars(r) for r in self._records], indent=2))
