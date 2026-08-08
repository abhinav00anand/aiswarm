"""Prompt ledger store."""

from __future__ import annotations

import json
from pathlib import Path

from aiswarm.schemas.task import PromptLedger

_LEDGER_DIR = Path("./storage/prompts")

def save_ledger(task_id: str, ledger: PromptLedger) -> None:
    """Append a ledger entry to the task's prompt history file."""
    _LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    path = _LEDGER_DIR / f"{task_id}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(ledger.model_dump_json() + "\n")

def load_ledgers(task_id: str) -> list[PromptLedger]:
    """Load all prompt ledger entries for a task."""
    path = _LEDGER_DIR / f"{task_id}.jsonl"
    if not path.exists():
        return []
    entries: list[PromptLedger] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(PromptLedger.model_validate_json(line))
            except Exception:  # noqa: BLE001
                pass
    return entries
