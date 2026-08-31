"""Lifecycle manager."""

from __future__ import annotations

import asyncio
import signal
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class LifecycleManager:
    """
    Manages ordered startup and shutdown of async services.

    Usage::

        lm = LifecycleManager()
        lm.register("redis", redis_client, priority=10)
        lm.register("orchestrator", orc, priority=20)
        await lm.startup()
        # ... run ...
        await lm.shutdown()
    """

    def __init__(self) -> None:
        self._services: list[tuple[int, str, Any]] = []  # (priority, name, service)
        self._started: list[str] = []

    def register(self, name: str, service: Any, priority: int = 50) -> None:
        """Register a service. Lower priority numbers start first."""
        self._services.append((priority, name, service))
        self._services.sort(key=lambda x: x[0])

    async def startup(self) -> None:
        logger.info("lifecycle.startup_begin", service_count=len(self._services))
        for priority, name, service in self._services:
            logger.info("lifecycle.starting_service", name=name, priority=priority)
            try:
                if hasattr(service, "start"):
                    await service.start()
                elif hasattr(service, "startup"):
                    await service.startup()
                self._started.append(name)
            except Exception as exc:  # noqa: BLE001
                logger.error("lifecycle.startup_error", name=name, error=str(exc))
                raise
        logger.info("lifecycle.startup_complete")

    async def shutdown(self) -> None:
        # Shut down in reverse order
        logger.info("lifecycle.shutdown_begin")
        for name in reversed(self._started):
            service = next((s for _, n, s in self._services if n == name), None)
            if service is None:
                continue
            logger.info("lifecycle.stopping_service", name=name)
            try:
                if hasattr(service, "shutdown"):
                    await service.shutdown()
                elif hasattr(service, "stop"):
                    service.stop()
                elif hasattr(service, "close"):
                    await service.close()
            except Exception as exc:  # noqa: BLE001
                logger.error("lifecycle.shutdown_error", name=name, error=str(exc))
        logger.info("lifecycle.shutdown_complete")

    def install_signal_handlers(self) -> None:
        """Register SIGTERM/SIGINT handlers to trigger graceful shutdown."""
        loop = asyncio.get_event_loop()

        async def _shutdown() -> None:
            logger.info("lifecycle.signal_received")
            await self.shutdown()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(_shutdown()))
