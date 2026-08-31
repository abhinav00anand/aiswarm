"""OpenTelemetry tracing — distributed trace instrumentation."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Generator

import structlog

logger = structlog.get_logger(__name__)

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider

    _OT_AVAILABLE = True
except ImportError:
    _OT_AVAILABLE = False


class ZymisTracer:
    """Wraps OpenTelemetry tracing for AISwarm pipeline stages."""

    def __init__(self, service_name: str = "zymis") -> None:
        self._enabled = _OT_AVAILABLE and os.getenv("TRACING_ENABLED", "false").lower() == "true"
        self._tracer: Any = None
        if self._enabled:
            self._setup(service_name)

    def _setup(self, service_name: str) -> None:
        try:
            provider = TracerProvider()
            trace.set_tracer_provider(provider)
            self._tracer = trace.get_tracer(service_name)
            logger.info("tracing.initialized", service=service_name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("tracing.setup_failed", error=str(exc))
            self._enabled = False

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Generator[Any, None, None]:
        """Context manager that creates a trace span if tracing is enabled."""
        if not self._enabled or self._tracer is None:
            yield None
            return
        with self._tracer.start_as_current_span(name) as span:
            for key, value in attrs.items():
                span.set_attribute(key, str(value))
            yield span


# Singleton
tracer = ZymisTracer()
