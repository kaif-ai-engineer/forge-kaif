from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from forge.core.exceptions import EventError

_log = logging.getLogger(__name__)

Handler = Callable[..., Awaitable[Any]]


class EventBus:
    """
    In-process async event bus for decoupled module communication.

    Supports subscribing with :meth:`on` / :meth:`off` and emitting
    events with :meth:`emit`.  All handlers are awaited concurrently
    and exceptions are caught and logged so a single failing handler
    never blocks other subscribers.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, set[Handler]] = {}

    def on(self, event: str, handler: Handler) -> None:
        """
        Register an async handler for *event*.

        Parameters
        ----------
        event:
            Dot-delimited event name (e.g. ``"runtime.ready"``).
        handler:
            An async callable that will receive the event payload.
        """
        self._handlers.setdefault(event, set()).add(handler)

    def off(self, event: str, handler: Handler) -> None:
        """
        Unregister a previously registered handler.

        Raises
        ------
        EventError
            If the handler was not registered for *event*.
        """
        handlers = self._handlers.get(event)
        if handlers is None or handler not in handlers:
            raise EventError(f"Handler {handler!r} is not registered for event '{event}'.")
        handlers.discard(handler)
        if not handlers:
            del self._handlers[event]

    async def emit(self, event: str, **kwargs: Any) -> None:
        """
        Emit *event* and await all registered handlers concurrently.

        Parameters
        ----------
        event:
            Dot-delimited event name.
        **kwargs:
            Payload passed as keyword arguments to each handler.
        """
        handlers = self._handlers.get(event, set())
        if not handlers:
            return

        results = await asyncio.gather(
            *(self._safe_dispatch(handler, event, kwargs) for handler in handlers),
            return_exceptions=True,
        )
        for exc in results:
            if isinstance(exc, BaseException):
                _log.warning(
                    "Handler for '%s' raised %s: %s",
                    event,
                    type(exc).__name__,
                    exc,
                )

    async def _safe_dispatch(
        self,
        handler: Handler,
        event: str,
        kwargs: dict[str, Any],
    ) -> None:
        try:
            await handler(**kwargs)
        except Exception:
            _log.exception("Unhandled exception in handler for '%s'", event)
            raise

    def has_listeners(self, event: str) -> bool:
        """Return ``True`` if at least one handler is registered for *event*."""
        return event in self._handlers and bool(self._handlers[event])
