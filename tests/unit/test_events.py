"""Unit tests for the Event schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aiswarm.schemas.events import Event, EventType


class TestEvent:
    def test_event_id_auto_generated_and_unique(self) -> None:
        e1 = Event(event_type=EventType.TASK_CREATED, source="test")
        e2 = Event(event_type=EventType.TASK_CREATED, source="test")
        assert e1.event_id != e2.event_id

    def test_default_version_is_1_0(self) -> None:
        e = Event(event_type=EventType.TASK_CREATED, source="test")
        assert e.version == "1.0"

    def test_task_id_optional_defaults_none(self) -> None:
        e = Event(event_type=EventType.SYSTEM_STARTED, source="boot")
        assert e.task_id is None

    def test_payload_defaults_to_empty_dict(self) -> None:
        e = Event(event_type=EventType.TASK_CREATED, source="test")
        assert e.payload == {}

    def test_payload_accepts_arbitrary_data(self) -> None:
        e = Event(
            event_type=EventType.TASK_FAILED,
            source="worker",
            payload={"reason": "timeout", "retries": 3},
        )
        assert e.payload["reason"] == "timeout"
        assert e.payload["retries"] == 3

    def test_event_is_frozen_after_creation(self) -> None:
        e = Event(event_type=EventType.TASK_CREATED, source="test")
        with pytest.raises(ValidationError):
            e.source = "mutated"

    def test_missing_required_fields_raises(self) -> None:
        with pytest.raises(ValidationError):
            Event()  # type: ignore[call-arg]

    def test_timestamp_is_set_automatically(self) -> None:
        e = Event(event_type=EventType.TASK_CREATED, source="test")
        assert e.timestamp is not None

    def test_correlation_id_optional(self) -> None:
        e = Event(event_type=EventType.TASK_CREATED, source="test", correlation_id="corr-1")
        assert e.correlation_id == "corr-1"

    def test_all_event_types_are_strings(self) -> None:
        for member in EventType:
            assert isinstance(member.value, str)
