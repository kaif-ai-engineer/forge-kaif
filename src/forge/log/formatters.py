from __future__ import annotations

import datetime
import json
import logging
import traceback
from typing import Any

from forge.core.context import get_trace_id

_MAX_STR_LEN = 10_000

# ── ANSI colour codes ──────────────────────────────────────────────
_GREY = "\x1b[38;20m"
_BLUE = "\x1b[34;20m"
_YELLOW = "\x1b[33;20m"
_RED = "\x1b[31;20m"
_BOLD_RED = "\x1b[31;1m"
_RESET = "\x1b[0m"

_COLOUR_MAP: dict[int, str] = {
    logging.DEBUG: _GREY,
    logging.INFO: _BLUE,
    logging.WARNING: _YELLOW,
    logging.ERROR: _RED,
    logging.CRITICAL: _BOLD_RED,
}

_LEVEL_LABELS: dict[int, str] = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARN",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "FATAL",
}


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    """Return extra fields attached to *record* via LogContext, minus std keys."""
    extras: dict[str, Any] = {}
    for key in dir(record):
        if key.startswith("_"):
            continue
        if key in (
            "args",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "message",
            "module",
            "msecs",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "thread",
            "threadName",
        ):
            continue
        extras[key] = getattr(record, key)
    return extras


# ── Safe JSON serialiser ───────────────────────────────────────────


def _convert_for_json(obj: Any, seen: set[int] | None = None) -> Any:
    """Recursively convert *obj* into a JSON-safe structure."""
    if seen is None:
        seen = set()
    obj_id = id(obj)
    if obj_id in seen:
        return "<circular>"
    seen.add(obj_id)
    result: Any
    try:
        if isinstance(obj, (str, int, float, bool, type(None))):
            result = obj
        elif isinstance(obj, bytes):
            result = obj.decode("utf-8", errors="replace")
        elif isinstance(obj, datetime.datetime):
            result = obj.isoformat()
        elif isinstance(obj, dict):
            result = {str(k): _convert_for_json(v, seen) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            result = [_convert_for_json(v, seen) for v in obj]
        elif isinstance(obj, Exception):
            result = str(obj)
        elif hasattr(obj, "__dict__"):
            result = _convert_for_json(obj.__dict__, seen)
        else:
            result = str(obj)
        return result
    finally:
        seen.discard(obj_id)


def _truncate(obj: Any) -> Any:
    """Truncate strings longer than ``_MAX_STR_LEN``."""
    if isinstance(obj, str):
        return obj[:_MAX_STR_LEN] + "..." if len(obj) > _MAX_STR_LEN else obj
    if isinstance(obj, dict):
        return {k: _truncate(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_truncate(v) for v in obj]
    return obj


# ── Formatters ─────────────────────────────────────────────────────


class JSONFormatter(logging.Formatter):
    """
    Outputs structured JSON log lines for production use.

    Every record produces: ``timestamp``, ``level``, ``module``,
    ``message``, and optionally ``trace_id`` (if one is active).
    Extra fields bound via ``LogContext`` are included at the top level.
    Circular references are replaced with ``"<circular>"`` and strings
    longer than 10 000 characters are truncated.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.datetime.fromtimestamp(
                record.created, tz=datetime.UTC
            ).isoformat(),
            "level": _LEVEL_LABELS.get(record.levelno, record.levelname),
            "module": record.name,
            "message": record.getMessage(),
        }

        trace_id = get_trace_id()
        if trace_id:
            payload["trace_id"] = trace_id

        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = "".join(
                traceback.format_exception(*record.exc_info)
            )

        extras = _extra_fields(record)
        payload.update(extras)

        safe = _truncate(_convert_for_json(payload))
        return json.dumps(safe, default=str)


class DevFormatter(logging.Formatter):
    """
    Colorized human-readable log output for development.

    Format::

        [2026-06-28 12:00:00] module.name  INFO   message here
    """

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.datetime.fromtimestamp(
            record.created, tz=datetime.UTC
        ).strftime("%Y-%m-%d %H:%M:%S")
        level = _LEVEL_LABELS.get(record.levelno, record.levelname)
        colour = _COLOUR_MAP.get(record.levelno, _GREY)

        message = record.getMessage()
        trace_id = get_trace_id()
        parts: list[str] = [
            f"{colour}[{timestamp}]{_RESET}",
            f"{record.name:<25}",
            f"{colour}{level:>5}{_RESET}",
            message,
        ]
        if trace_id:
            parts.insert(2, f"{_GREY}[{trace_id[:8]}]{_RESET}")

        if record.exc_info and record.exc_info[0] is not None:
            exc = "".join(traceback.format_exception(*record.exc_info))
            parts.append(f"\n{_RED}{exc}{_RESET}")

        return "  ".join(parts)
