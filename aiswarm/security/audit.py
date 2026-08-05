from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from aiswarm.utils.compat_log import get_logger

logger = get_logger(__name__)


class EventType(str, Enum):
    ROUTE_DECISION = "ROUTE_DECISION"
    TOOL_SPAWN = "TOOL_SPAWN"
    ESCALATION = "ESCALATION"
    MERGE = "MERGE"
    REJECTION = "REJECTION"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    HITL_REQUEST = "HITL_REQUEST"
    KEY_VERIFICATION = "KEY_VERIFICATION"


class AuditEvent(BaseModel):
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: EventType
    actor: str
    task_id: str | None = None
    action: str
    outcome: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditLedger:
    def __init__(self, persist_path: str | Path | None = None) -> None:
        self._events: list[AuditEvent] = []
        self._lock = asyncio.Lock()
        
        # Configure persistence path
        env_path = os.getenv("AISWARM_AUDIT_LOG_PATH")
        if persist_path:
            self._persist_path: Path | None = Path(persist_path)
        elif env_path:
            self._persist_path = Path(env_path)
        else:
            self._persist_path = Path.home() / ".aiswarm" / "audit.jsonl"
            
        self._load_persisted_events()

    def _load_persisted_events(self) -> None:
        """Load past audit events from disk on startup if present."""
        if not self._persist_path or not self._persist_path.exists():
            return
        try:
            with open(self._persist_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            event = AuditEvent.model_validate_json(line)
                            self._events.append(event)
                        except Exception:
                            pass
            logger.info("audit.persisted_events_loaded", path=str(self._persist_path), count=len(self._events))
        except Exception as exc:  # noqa: BLE001
            logger.warning("audit.load_error", error=str(exc))

    async def record(
        self,
        event_type: "EventType | str",
        actor: str,
        action: str,
        outcome: str,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        # Accept both string and EventType enum
        if isinstance(event_type, str):
            event_type = EventType(event_type)
        event = AuditEvent(
            event_type=event_type,
            actor=actor,
            action=action,
            outcome=outcome,
            task_id=task_id,
            metadata=metadata or {},
        )
        async with self._lock:
            self._events.append(event)
            if self._persist_path:
                try:
                    self._persist_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(self._persist_path, "a", encoding="utf-8") as f:
                        f.write(event.model_dump_json() + "\n")
                except Exception as exc:  # noqa: BLE001
                    logger.warning("audit.write_error", error=str(exc))
            logger.info(
                "audit.recorded",
                event_type=event.event_type.value,
                actor=event.actor,
                action=event.action,
                outcome=event.outcome,
            )
        return event



    async def get_events(
        self,
        task_id: str | None = None,
        event_type: EventType | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        async with self._lock:
            events = self._events.copy()

        filtered: list[AuditEvent] = []
        for e in reversed(events):
            if task_id and e.task_id != task_id:
                continue
            if event_type and e.event_type != event_type:
                continue
            filtered.append(e)
            if len(filtered) >= limit:
                break
        return filtered

    async def export_jsonl(self, path: str | Path) -> None:
        async with self._lock:
            events = self._events.copy()

        with open(path, "a", encoding="utf-8") as f:
            for event in events:
                f.write(event.model_dump_json() + "\n")
        logger.info("audit.exported", path=str(path), count=len(events))

    async def summary(self) -> dict[str, int]:
        async with self._lock:
            events = self._events.copy()

        counts: dict[str, int] = {}
        for event in events:
            counts[event.event_type.value] = counts.get(event.event_type.value, 0) + 1
        return counts


_LEDGER = AuditLedger()


def get_audit_ledger() -> AuditLedger:
    return _LEDGER
