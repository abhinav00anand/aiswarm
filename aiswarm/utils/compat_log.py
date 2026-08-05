"""
Compatibility Logger Wrapper — Gracefully handles structlog or stdlib logging fallback.
"""

from __future__ import annotations

import logging
from typing import Any


class StdlibLoggerWrapper:
    """Wrapper mapping structlog keyword log calls to stdlib logging."""

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def _fmt(self, event: str, kwargs: dict[str, Any]) -> str:
        if not kwargs:
            return event
        pairs = " ".join(f"{k}={v!r}" for k, v in kwargs.items())
        return f"{event} | {pairs}"

    def info(self, event: str, **kwargs: Any) -> None:
        self._logger.info(self._fmt(event, kwargs))

    def warning(self, event: str, **kwargs: Any) -> None:
        self._logger.warning(self._fmt(event, kwargs))

    def error(self, event: str, **kwargs: Any) -> None:
        self._logger.error(self._fmt(event, kwargs))

    def critical(self, event: str, **kwargs: Any) -> None:
        self._logger.critical(self._fmt(event, kwargs))

    def debug(self, event: str, **kwargs: Any) -> None:
        self._logger.debug(self._fmt(event, kwargs))


def get_logger(name: str = __name__) -> Any:
    """Return a structlog BoundLogger if structlog is installed, else return StdlibLoggerWrapper."""
    try:
        import structlog
        return structlog.get_logger(name)
    except ImportError:
        return StdlibLoggerWrapper(name)
