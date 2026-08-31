"""Unit tests for the async event bus."""

from __future__ import annotations


import pytest

from aiswarm.core.event_bus import EventBus
from aiswarm.schemas.events import Event, EventType


@pytest.mark.asyncio
class TestEventBus:
    async def test_publish_and_receive(self) -> None:
        bus = EventBus()
        received: list[Event] = []

        @bus.subscribe(EventType.TASK_COMPLETED)
        async def handler(event: Event) -> None:
            received.append(event)

        ev = Event(event_type=EventType.TASK_COMPLETED, source="test")
        await bus.publish(ev)
        assert len(received) == 1
        assert received[0].event_id == ev.event_id

    async def test_multiple_handlers_same_type(self) -> None:
        bus = EventBus()
        calls: list[str] = []

        @bus.subscribe(EventType.TASK_STARTED)
        async def h1(event: Event) -> None:
            calls.append("h1")

        @bus.subscribe(EventType.TASK_STARTED)
        async def h2(event: Event) -> None:
            calls.append("h2")

        await bus.publish(Event(event_type=EventType.TASK_STARTED, source="test"))
        assert "h1" in calls
        assert "h2" in calls

    async def test_wildcard_handler_receives_all(self) -> None:
        bus = EventBus()
        all_events: list[EventType] = []

        async def wildcard(event: Event) -> None:
            all_events.append(event.event_type)

        bus.subscribe_all(wildcard)

        for et in (EventType.TASK_CREATED, EventType.TASK_COMPLETED, EventType.JOB_DISPATCHED):
            await bus.publish(Event(event_type=et, source="test"))

        assert len(all_events) == 3

    async def test_handler_error_doesnt_stop_others(self) -> None:
        bus = EventBus()
        second_called = [False]

        @bus.subscribe(EventType.TASK_FAILED)
        async def bad_handler(event: Event) -> None:
            raise RuntimeError("handler crashed")

        @bus.subscribe(EventType.TASK_FAILED)
        async def good_handler(event: Event) -> None:
            second_called[0] = True

        await bus.publish(Event(event_type=EventType.TASK_FAILED, source="test"))
        assert second_called[0]
        assert bus.stats["failed"] == 1

    async def test_no_handlers_doesnt_raise(self) -> None:
        bus = EventBus()
        # No exception expected
        await bus.publish(Event(event_type=EventType.CHECKPOINT_SAVED, source="test"))
        assert bus.stats["published"] == 1
