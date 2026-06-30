from __future__ import annotations

import uuid
from contextvars import ContextVar, Token
from typing import Any, Self

_current_trace_id: ContextVar[str] = ContextVar("_current_trace_id", default="")
_current_span_id: ContextVar[str] = ContextVar("_current_span_id", default="")
_empty_baggage: dict[str, Any] = {}
_baggage: ContextVar[dict[str, Any]] = ContextVar("_baggage", default=_empty_baggage)


def generate_trace_id() -> str:
    """Generate a new trace ID (UUID4 hex string)."""
    return uuid.uuid4().hex


def generate_span_id() -> str:
    """Generate a new span ID (UUID4 hex string)."""
    return uuid.uuid4().hex[:16]


def get_trace_id() -> str:
    """Return the current trace ID, or ``""`` if none is set."""
    return _current_trace_id.get()


def set_trace_id(trace_id: str | None = None) -> Token[str]:
    """
    Set the current trace ID.

    Parameters
    ----------
    trace_id:
        The trace ID to use.  If ``None``, a new one is generated.

    Returns
    -------
    Token[str]
        A token that can be used with ``reset_trace_id`` to restore
        the previous value.
    """
    return _current_trace_id.set(trace_id or generate_trace_id())


def reset_trace_id(token: Token[str]) -> None:
    """Restore the trace ID to the value it had before *token* was created."""
    _current_trace_id.reset(token)


def get_span_id() -> str:
    """Return the current span ID, or ``""`` if none is set."""
    return _current_span_id.get()


def set_span_id(span_id: str | None = None) -> Token[str]:
    """
    Set the current span ID.

    Parameters
    ----------
    span_id:
        The span ID to use.  If ``None``, a new one is generated.
    """
    return _current_span_id.set(span_id or generate_span_id())


def reset_span_id(token: Token[str]) -> None:
    """Restore the span ID to the value it had before *token* was created."""
    _current_span_id.reset(token)


def get_baggage() -> dict[str, Any]:
    """Return a copy of the current baggage (mutable key-value context)."""
    return dict(_baggage.get())


def set_baggage(key: str, value: Any) -> None:
    """Set a baggage key for the current async context."""
    current = dict(_baggage.get())
    current[key] = value
    _baggage.set(current)


def get_baggage_item(key: str, default: Any = None) -> Any:
    """Return a single baggage item, or *default* if missing."""
    return _baggage.get().get(key, default)


def reset_baggage(token: Token[dict[str, Any]]) -> None:
    """Restore baggage to the value it had before *token* was created."""
    _baggage.reset(token)


class TraceContext:
    """
    Async context manager that sets trace ID, span ID, and baggage.

    Usage::

        async with TraceContext(trace_id="abc") as ctx:
            print(ctx.trace_id)
    """

    def __init__(
        self,
        trace_id: str | None = None,
        span_id: str | None = None,
        baggage: dict[str, Any] | None = None,
    ) -> None:
        self._trace_id = trace_id
        self._span_id = span_id
        self._baggage = baggage or {}
        self._trace_token: Token[str] | None = None
        self._span_token: Token[str] | None = None
        self._baggage_token: Token[dict[str, Any]] | None = None

    def __enter__(self) -> Self:
        self._trace_token = set_trace_id(self._trace_id)
        self._span_token = set_span_id(self._span_id)
        merged = dict(_baggage.get())
        merged.update(self._baggage)
        self._baggage_token = _baggage.set(merged)
        return self

    def __exit__(self, *args: object) -> None:
        if self._trace_token is not None:
            reset_trace_id(self._trace_token)
        if self._span_token is not None:
            reset_span_id(self._span_token)
        if self._baggage_token is not None:
            reset_baggage(self._baggage_token)

    @property
    def trace_id(self) -> str:
        return get_trace_id()

    @property
    def span_id(self) -> str:
        return get_span_id()
