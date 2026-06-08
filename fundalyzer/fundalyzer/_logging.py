"""Structured logging configuration for fundalyzer.

Sets up the root logger with either:
  - human-readable format (default, for CLI use)
  - JSON-structured format (--log-format json, for log aggregation)

Usage in modules:  log = logging.getLogger(__name__)
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Literal

_STANDARD_LOG_ATTRS = frozenset({
    "args", "asctime", "created", "exc_info", "exc_text",
    "filename", "funcName", "levelname", "levelno", "lineno",
    "message", "module", "msecs", "msg", "name", "pathname",
    "process", "processName", "relativeCreated", "stack_info",
    "taskName", "thread", "threadName",
})


class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record, one per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),   # fully interpolated message
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Attach any non-standard fields the caller passed as extras
        for key, val in record.__dict__.items():
            if key not in _STANDARD_LOG_ATTRS and not key.startswith("_"):
                payload[key] = val
        return json.dumps(payload)


def configure_logging(
    level: str = "WARNING",
    fmt: Literal["text", "json"] = "text",
) -> None:
    """Configure the root logger.

    Args:
        level:  One of DEBUG / INFO / WARNING / ERROR.
        fmt:    'text' for human-readable, 'json' for structured JSON.
    """
    numeric = getattr(logging, level.upper(), logging.WARNING)
    handler = logging.StreamHandler(sys.stderr)

    if fmt == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    root = logging.getLogger()
    root.setLevel(numeric)

    # Avoid duplicate handlers when configure_logging is called more than once
    root.handlers.clear()
    root.addHandler(handler)
