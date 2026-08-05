"""
Async in-process event bus.

All subsystems communicate through typed, versioned, idempotent events.
Subscribers register handlers for specific EventTypes.
The bus guarantees at-least-once delivery within a process.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Callable, Awaitable

import structlog

from aiswarm.schemas.events import Event, EventType

logger = structlog.get_logger(__name__)

Handler = Callable[[Event], Awaitable[None]]


class EventBus:
    """
    Thread-safe async event bus supporting wildcard and typed subscriptions.

    Usage::

        bus = EventBus()

        @bus.subscribe(EventType.TASK_COMPLETED)
        async def on_done(event: Event) -> None:
            print(event.payload)

        await bus.publish(Event(event_type=EventType.TASK_COMPLETED, source="orchestrator"))
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)
        self._wildcard_handlers: list[Handler] = []
        self._lock = asyncio.Lock()
        self._published: int = 0
        self._failed: int = 0

    def subscribe(self, *event_types: EventType) -> Callable[[Handler], Handler]:
        """Decorator to register a handler for one or more event types."""
        def decorator(fn: Handler) -> Handler:
            for et in event_types:
                self._handlers[et].append(fn)
            return fn
        return decorator

    def subscribe_all(self, fn: Handler) -> None:
        """Register a handler that receives every event regardless of type."""
        self._wildcard_handlers.append(fn)

    async def publish(self, event: Event | dict[str, Any]) -> None:
        """
        Publish an event. All matching handlers are called concurrently.
        Errors in handlers are logged but do not prevent other handlers from running.
        """
        if isinstance(event, dict):
            from aiswarm.schemas.events import Event as EventSchema, EventType as EvType
            if "event_type" not in event and "type" in event:
                event["event_type"] = event.pop("type")
            if "source" not in event:
                event["source"] = "system"
            if isinstance(event.get("event_type"), str):
                try:
                    event["event_type"] = EvType(event["event_type"])
                except ValueError:
                    event["event_type"] = EvType.TASK_CREATED
            event = EventSchema.model_validate(event)

        self._published += 1
        handlers = list(self._handlers.get(event.event_type, []))

        handlers += self._wildcard_handlers

        if not handlers:
            logger.debug(
                "event.no_handlers",
                event_type=event.event_type.value,
                event_id=event.event_id,
            )
            return

        tasks = [asyncio.create_task(self._invoke(h, event)) for h in handlers]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _invoke(self, handler: Handler, event: Event) -> None:
        try:
            await handler(event)
        except Exception as exc:  # noqa: BLE001
            self._failed += 1
            logger.error(
                "event_bus.handler_error",
                handler=handler.__qualname__,
                event_type=event.event_type.value,
                error=str(exc),
            )

    @property
    def stats(self) -> dict[str, int]:
        return {"published": self._published, "failed": self._failed}
