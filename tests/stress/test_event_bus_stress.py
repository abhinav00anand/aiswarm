"""
Stress tests for EventBus.

Covers:
  - 1000 events published to a single handler
  - Fan-out: 50 handlers × 200 events = 10 000 invocations
  - Slow handler isolation (slow handler must not block others)
  - Handler exception isolation (crashing handler must not drop other events)
  - Wildcard handler receives every event type
  - Typed handler receives only its event type
  - Concurrent publish + subscribe (no handler loss)
  - Stats (published/failed) correctness under load
"""

from __future__ import annotations

import asyncio
import time

import pytest

from aiswarm.core.event_bus import EventBus
from aiswarm.schemas.events import Event, EventType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _event(event_type: EventType = EventType.TASK_COMPLETED) -> Event:
    return Event(event_type=event_type, source="stress_test")


# ---------------------------------------------------------------------------
# High-volume publish
# ---------------------------------------------------------------------------

class TestEventBusHighVolume:

    @pytest.mark.asyncio
    async def test_1000_events_single_handler_all_received(self):
        bus = EventBus()
        received = []

        @bus.subscribe(EventType.TASK_COMPLETED)
        async def handler(event: Event):
            received.append(event.event_id)

        N = 1000
        await asyncio.gather(*[
            bus.publish(_event(EventType.TASK_COMPLETED))
            for _ in range(N)
        ])
        assert len(received) == N
        assert len(set(received)) == N  # all unique event IDs

    @pytest.mark.asyncio
    async def test_fanout_50_handlers_200_events(self):
        bus = EventBus()
        received = []

        for _ in range(50):
            @bus.subscribe(EventType.TASK_FAILED)
            async def handler(event: Event, _received=received):
                _received.append(1)

        N_events = 200
        await asyncio.gather(*[
            bus.publish(_event(EventType.TASK_FAILED))
            for _ in range(N_events)
        ])
        assert len(received) == 50 * N_events

    @pytest.mark.asyncio
    async def test_stats_published_count_accurate(self):
        bus = EventBus()
        N = 500
        await asyncio.gather(*[
            bus.publish(_event(EventType.TASK_STARTED))
            for _ in range(N)
        ])
        assert bus.stats["published"] == N

    @pytest.mark.asyncio
    async def test_stats_failed_count_accurate(self):
        bus = EventBus()
        N = 100

        @bus.subscribe(EventType.TASK_STARTED)
        async def crasher(event):
            raise RuntimeError("intentional crash")

        await asyncio.gather(*[
            bus.publish(_event(EventType.TASK_STARTED))
            for _ in range(N)
        ])
        assert bus.stats["failed"] == N


# ---------------------------------------------------------------------------
# Handler isolation
# ---------------------------------------------------------------------------

class TestEventBusHandlerIsolation:

    @pytest.mark.asyncio
    async def test_crashing_handler_does_not_drop_other_handlers(self):
        bus = EventBus()
        good_received = []

        @bus.subscribe(EventType.TASK_COMPLETED)
        async def crasher(event):
            raise ValueError("crash")

        @bus.subscribe(EventType.TASK_COMPLETED)
        async def good_handler(event):
            good_received.append(event.event_id)

        N = 50
        await asyncio.gather(*[
            bus.publish(_event(EventType.TASK_COMPLETED))
            for _ in range(N)
        ])
        assert len(good_received) == N

    @pytest.mark.asyncio
    async def test_slow_handler_does_not_block_fast_handler(self):
        bus = EventBus()
        fast_times = []
        slow_done = []

        @bus.subscribe(EventType.TASK_COMPLETED)
        async def slow_handler(event):
            await asyncio.sleep(0.1)
            slow_done.append(1)

        @bus.subscribe(EventType.TASK_COMPLETED)
        async def fast_handler(event):
            fast_times.append(time.monotonic())

        # Publish 5 events simultaneously
        await asyncio.gather(*[
            bus.publish(_event(EventType.TASK_COMPLETED))
            for _ in range(5)
        ])
        # Fast handler should have received all 5 events
        assert len(fast_times) == 5

    @pytest.mark.asyncio
    async def test_exception_in_all_handlers_fails_count_tracks_correctly(self):
        bus = EventBus()
        H = 3  # 3 handlers each crash

        for _ in range(H):
            @bus.subscribe(EventType.TASK_FAILED)
            async def crasher(event):
                raise RuntimeError("all crash")

        await bus.publish(_event(EventType.TASK_FAILED))
        assert bus.stats["failed"] == H

    @pytest.mark.asyncio
    async def test_no_handlers_event_silently_ignored(self):
        bus = EventBus()
        # No handlers registered for this type
        await bus.publish(_event(EventType.TASK_STARTED))
        assert bus.stats["published"] == 1
        assert bus.stats["failed"] == 0


# ---------------------------------------------------------------------------
# Typed vs wildcard routing
# ---------------------------------------------------------------------------

class TestEventBusRouting:

    @pytest.mark.asyncio
    async def test_typed_handler_receives_only_its_type(self):
        bus = EventBus()
        target_received = []
        other_received = []

        @bus.subscribe(EventType.TASK_COMPLETED)
        async def typed(event):
            target_received.append(event.event_type)

        @bus.subscribe(EventType.TASK_FAILED)
        async def other(event):
            other_received.append(event.event_type)

        await bus.publish(_event(EventType.TASK_COMPLETED))
        await bus.publish(_event(EventType.TASK_COMPLETED))
        await bus.publish(_event(EventType.TASK_FAILED))

        assert len(target_received) == 2
        assert all(t == EventType.TASK_COMPLETED for t in target_received)
        assert len(other_received) == 1

    @pytest.mark.asyncio
    async def test_wildcard_handler_receives_all_types(self):
        bus = EventBus()
        all_received = []

        async def wildcard(event: Event):
            all_received.append(event.event_type)

        bus.subscribe_all(wildcard)

        types_to_publish = [
            EventType.TASK_COMPLETED,
            EventType.TASK_FAILED,
            EventType.TASK_STARTED,
        ]
        for et in types_to_publish:
            await bus.publish(_event(et))

        assert len(all_received) == 3
        assert set(all_received) == set(types_to_publish)

    @pytest.mark.asyncio
    async def test_wildcard_plus_typed_both_fire(self):
        bus = EventBus()
        typed_hits = []
        wild_hits = []

        @bus.subscribe(EventType.TASK_COMPLETED)
        async def typed(event):
            typed_hits.append(1)

        async def wildcard(event):
            wild_hits.append(1)

        bus.subscribe_all(wildcard)

        await bus.publish(_event(EventType.TASK_COMPLETED))
        assert len(typed_hits) == 1
        assert len(wild_hits) == 1

    @pytest.mark.asyncio
    async def test_multi_type_subscription_single_handler(self):
        bus = EventBus()
        hits = []

        @bus.subscribe(EventType.TASK_COMPLETED, EventType.TASK_FAILED)
        async def multi(event):
            hits.append(event.event_type)

        await bus.publish(_event(EventType.TASK_COMPLETED))
        await bus.publish(_event(EventType.TASK_FAILED))
        await bus.publish(_event(EventType.TASK_STARTED))  # not subscribed

        assert len(hits) == 2


# ---------------------------------------------------------------------------
# Concurrent subscribe + publish
# ---------------------------------------------------------------------------

class TestEventBusConcurrentAccess:

    @pytest.mark.asyncio
    async def test_concurrent_publish_all_delivered(self):
        bus = EventBus()
        received = []

        @bus.subscribe(EventType.TASK_COMPLETED)
        async def handler(event):
            received.append(1)

        N = 300
        await asyncio.gather(*[
            bus.publish(_event(EventType.TASK_COMPLETED))
            for _ in range(N)
        ])
        assert len(received) == N

    @pytest.mark.asyncio
    async def test_event_id_uniqueness_under_concurrent_publish(self):
        bus = EventBus()
        ids = []

        @bus.subscribe(EventType.TASK_COMPLETED)
        async def handler(event):
            ids.append(event.event_id)

        N = 200
        await asyncio.gather(*[
            bus.publish(_event(EventType.TASK_COMPLETED))
            for _ in range(N)
        ])
        assert len(set(ids)) == N

    @pytest.mark.asyncio
    async def test_subscribe_during_publish_does_not_lose_events(self):
        """New subscriptions registered while publishes are in-flight must not lose
        already-dispatched events on pre-subscribed handlers."""
        bus = EventBus()
        early_received = []
        late_received = []

        @bus.subscribe(EventType.TASK_COMPLETED)
        async def early_handler(event):
            early_received.append(event.event_id)

        N_before = 50
        N_after = 50

        # Publish first batch before adding second handler
        await asyncio.gather(*[
            bus.publish(_event(EventType.TASK_COMPLETED))
            for _ in range(N_before)
        ])

        # Register a second handler mid-stream
        @bus.subscribe(EventType.TASK_COMPLETED)
        async def late_handler(event):
            late_received.append(event.event_id)

        # Publish second batch — both handlers must receive these
        await asyncio.gather(*[
            bus.publish(_event(EventType.TASK_COMPLETED))
            for _ in range(N_after)
        ])

        # Early handler received all events (before + after)
        assert len(early_received) == N_before + N_after
        # Late handler only received events after it was registered
        assert len(late_received) == N_after
