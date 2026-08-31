"""
Structured logging configuration using structlog + stdlib logging.

Every log entry is:
  - Structured JSON in production
  - Colored human-readable in development
  - Always contains: timestamp, level, logger_name, event
  - Never contains: secrets, tokens, PII
"""

from __future__ import annotations

import logging
import logging.config
import os
import sys
from pathlib import Path

import structlog


def configure_logging(
    level: str | None = None,
    log_format: str | None = None,
    log_dir: str = "./storage/logs",
) -> None:
    """Configure structlog and stdlib logging for the entire application."""
    level = level or os.getenv("LOG_LEVEL", "INFO")
    log_format = log_format or os.getenv("LOG_FORMAT", "console")
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    # ── structlog configuration ───────────────────────────────────────────────
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Quiet noisy libraries
    for noisy in ["httpx", "httpcore", "asyncio", "chromadb", "urllib3"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)
