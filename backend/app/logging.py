"""Yapılandırılmış loglama (structlog).

`configure_logging()` uygulama başlarken bir kez çağrılır. Geliştirmede renkli
konsol, production'da (LOG_JSON=true) tek satır JSON üretir. `request_id` gibi
bağlam değişkenleri contextvar üzerinden tüm loglara otomatik eklenir.
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.config import Settings
from app.log_stream import capture_log_event


def configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level, logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        capture_log_event,
    ]

    renderer = (
        structlog.processors.JSONRenderer()
        if settings.log_json
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
