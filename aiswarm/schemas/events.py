"""Event schemas for the internal event bus."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, ConfigDict



class EventType(str, Enum):
    # Task lifecycle
    TASK_CREATED = "TASK_CREATED"
    TASK_STARTED = "TASK_STARTED"
    TASK_STATE_CHANGED = "TASK_STATE_CHANGED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_ESCALATED = "TASK_ESCALATED"
    TASK_DEADLOCK = "TASK_DEADLOCK"
    TASK_MERGED = "TASK_MERGED"
    TASK_REJECTED = "TASK_REJECTED"
    TASK_CANCELLED = "TASK_CANCELLED"


    # Agent events
    AGENT_INVOKED = "AGENT_INVOKED"
    AGENT_RESPONDED = "AGENT_RESPONDED"
    AGENT_ERROR = "AGENT_ERROR"

    # Review events
    REVIEW_STARTED = "REVIEW_STARTED"
    REVIEW_COMPLETED = "REVIEW_COMPLETED"
    REVIEW_REJECTED = "REVIEW_REJECTED"

    # Worker events
    JOB_DISPATCHED = "JOB_DISPATCHED"
    JOB_STARTED = "JOB_STARTED"
    JOB_COMPLETED = "JOB_COMPLETED"
    JOB_FAILED = "JOB_FAILED"

    # Compiler / test events
    COMPILE_STARTED = "COMPILE_STARTED"
    COMPILE_COMPLETED = "COMPILE_COMPLETED"
    COMPILE_FAILED = "COMPILE_FAILED"
    TEST_STARTED = "TEST_STARTED"
    TEST_COMPLETED = "TEST_COMPLETED"
    TEST_FAILED = "TEST_FAILED"
    BENCHMARK_STARTED = "BENCHMARK_STARTED"
    BENCHMARK_COMPLETED = "BENCHMARK_COMPLETED"

    # System events
    SYSTEM_STARTED = "SYSTEM_STARTED"
    SYSTEM_SHUTDOWN = "SYSTEM_SHUTDOWN"
    DEADLOCK_DETECTED = "DEADLOCK_DETECTED"
    CHECKPOINT_SAVED = "CHECKPOINT_SAVED"
    CHECKPOINT_RESTORED = "CHECKPOINT_RESTORED"

    # Notification
    NOTIFICATION_SENT = "NOTIFICATION_SENT"


class Event(BaseModel):
    """Immutable, versioned, typed event flowing through the event bus."""
    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType
    version: str = "1.0"
    source: str          # Which agent/component emitted this
    task_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str | None = None  # group related events
    idempotency_key: str | None = None
