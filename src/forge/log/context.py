from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from typing import Self

from forge.core.otel import get_current_span_context
from forge.core.otel import is_otel_available as _otel_available

_log_context: ContextVar[dict[str, Any]] = ContextVar("_log_context")


class LogContext:
    """
    Async-safe context manager that binds extra fields to log entries.

    Usage::

        with LogContext(request_id="abc-123", user="alice"):
            logger.info("processing request")
            # → log entry includes request_id="abc-123", user="alice"
    """

    def __init__(self, **kwargs: Any) -> None:
        self._extra = kwargs
        self._token: Token[dict[str, Any]] | None = None

    def __enter__(self) -> Self:
        current = dict(_log_context.get({}))
        current.update(self._extra)
        self._token = _log_context.set(current)
        return self

    def __exit__(self, *args: object) -> None:
        if self._token is not None:
            _log_context.reset(self._token)

    @staticmethod
    def get_current() -> dict[str, Any]:
        """Return a copy of the currently bound extra fields."""
        current = _log_context.get({})
        return dict(current)


class LogContextFilter(logging.Filter):
    """
    Logging filter that injects ``LogContext`` fields into every record.

    Attach this filter to the root logger or handler to automatically
    propagate contextvars-based extra fields to all log entries::

        root_logger.addFilter(LogContextFilter())
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if _otel_available():
            ctx = get_current_span_context()
            if ctx:
                record.otel_trace_id = ctx["trace_id"]
                record.otel_span_id = ctx["span_id"]

        fields = _log_context.get({})
        for key, value in fields.items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True
