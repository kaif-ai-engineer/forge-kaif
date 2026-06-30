"""
Developer-facing event publication API for the forge runtime.

Wraps the core :class:`forge.core.events.EventBus` with wildcard pattern
subscription, an event history buffer for late-joining subscribers, and
a decorator-friendly registration API.

Usage::

    from forge.events import EventsModule

    runtime.register(EventsModule())
    await runtime.init()

    # Exact-match subscription
    runtime.events.on("cache.hit", my_handler)

    # Wildcard subscription (all ai.* events)
    runtime.events.on("ai.*", my_handler)

    # Decorator-style registration
    @runtime.events.on("runtime.ready")
    async def on_ready(**kwargs):
        ...

    # Late-joining subscriber with history replay
    runtime.events.subscribe("ai.*", late_handler, replay=True)

    # Emitting events
    await runtime.events.emit("my.event", key="value")
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from forge.core.module import ForgeModule, HealthResult

if TYPE_CHECKING:
    from forge.core.events import EventBus
    from forge.core.runtime import ForgeRuntime as Runtime

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public type aliases
# ---------------------------------------------------------------------------

Handler = Callable[..., Awaitable[Any]]
"""Signature that every event handler must satisfy."""

# ---------------------------------------------------------------------------
# Event record stored in the history buffer
# ---------------------------------------------------------------------------


@dataclass
class EventRecord:
    """A single entry in the event history buffer."""

    event: str
    payload: dict[str, Any]
    timestamp: float


# ---------------------------------------------------------------------------
# Enhanced event bus wrapper
# ---------------------------------------------------------------------------


class EventBusWrapper:
    """
    Wraps the core :class:`~forge.core.events.EventBus` with wildcard
    pattern support and an event history buffer.

    Every method is compatible with the core ``EventBus`` interface so
    this class acts as a drop-in replacement for ``runtime._events``.
    """

    def __init__(self, core_bus: EventBus, history_size: int = 200) -> None:
        self._core: EventBus = core_bus
        self._history: deque[EventRecord] = deque(maxlen=history_size)
        self._wildcard_handlers: dict[str, set[Handler]] = {}

    # -- Public registration / unregistration ---------------------------------

    def on(
        self,
        event: str,
        handler: Handler | None = None,
    ) -> Handler | Callable[[Handler], Handler]:
        """
        Register an async handler for *event*.

        Supports three calling conventions:

        * Direct: ``bus.on("event.name", handler)``
        * Decorator: ``@bus.on("event.name")``
        * Wildcard: ``bus.on("ai.*", handler)`` or ``@bus.on("*")``

        Wildcard patterns use shell-style globbing (``fnmatch``).
        """

        def _register(h: Handler) -> Handler:
            if _is_wildcard(event):
                self._wildcard_handlers.setdefault(event, set()).add(h)
            else:
                self._core.on(event, h)
            return h

        if handler is not None:
            return _register(handler)
        return _register

    def off(self, event: str, handler: Handler) -> None:
        """
        Unregister a previously registered handler.

        Raises ``KeyError`` if the handler is not registered for the
        given *event* (or wildcard pattern).
        """
        if _is_wildcard(event):
            handlers = self._wildcard_handlers.get(event)
            if handlers is None or handler not in handlers:
                msg = f"Handler {handler!r} is not registered for pattern {event!r}."
                raise KeyError(msg)
            handlers.discard(handler)
            if not handlers:
                del self._wildcard_handlers[event]
        else:
            self._core.off(event, handler)

    # -- Subscription with optional history replay ----------------------------

    def subscribe(
        self,
        event: str,
        handler: Handler,
        *,
        replay: bool = False,
    ) -> Handler:
        """
        Register *handler* for *event*, optionally replaying matching
        history entries to the handler immediately.

        This is the primary API for late-joining subscribers::

            @runtime.events.subscribe("ai.*", replay=True)
            async def track_ai(**kwargs):
                ...
        """
        self.on(event, handler)
        if replay:
            self.replay(event, handler)
        return handler

    def replay(self, event: str, handler: Handler) -> None:
        """Fire *handler* for every history entry that matches *event*."""
        _tasks: list[asyncio.Task[None]] = [
            asyncio.ensure_future(handler(**record.payload))
            for record in self._history
            if fnmatch.fnmatch(record.event, event)
        ]

    # -- Emission -------------------------------------------------------------

    async def emit(self, event: str, **kwargs: Any) -> None:
        """
        Emit *event* and await all registered handlers concurrently.

        Stores the event in the history buffer, dispatches exact-match
        handlers via the core bus, and then dispatches wildcard handlers
        that match *event*.

        Exceptions from individual handlers are caught and logged so
        that a failing handler never blocks other subscribers.
        """
        record = EventRecord(
            event=event,
            payload=kwargs,
            timestamp=time.monotonic(),
        )
        self._history.append(record)

        await self._core.emit(event, **kwargs)

        wildcard_tasks: list[asyncio.Task[None]] = []
        for pattern, handlers in self._wildcard_handlers.items():
            if fnmatch.fnmatch(event, pattern):
                wildcard_tasks.extend(
                    asyncio.create_task(
                        self._safe_dispatch(handler, event, kwargs),
                    )
                    for handler in handlers
                )

        if wildcard_tasks:
            results = await asyncio.gather(*wildcard_tasks, return_exceptions=True)
            for exc in results:
                if isinstance(exc, BaseException):
                    _log.warning(
                        "Wildcard handler for '%s' raised %s: %s",
                        event,
                        type(exc).__name__,
                        exc,
                    )

    # -- Introspection --------------------------------------------------------

    def has_listeners(self, event: str) -> bool:
        """Return ``True`` if at least one handler is registered for *event*."""
        if self._core.has_listeners(event):
            return True
        return any(fnmatch.fnmatch(event, p) for p in self._wildcard_handlers)

    @property
    def history(self) -> tuple[EventRecord, ...]:
        """Immutable snapshot of the event history buffer."""
        return tuple(self._history)

    def clear_history(self) -> None:
        """Discard all stored events from the history buffer."""
        self._history.clear()

    # -- Internal helpers -----------------------------------------------------

    async def _safe_dispatch(
        self,
        handler: Handler,
        event: str,
        payload: dict[str, Any],
    ) -> None:
        try:
            await handler(**payload)
        except Exception:
            _log.exception("Unhandled exception in wildcard handler for '%s'", event)
            raise


# ---------------------------------------------------------------------------
# Module implementation
# ---------------------------------------------------------------------------


class EventsModule(ForgeModule):
    """
    Forge module that upgrades the core ``EventBus`` with wildcard
    subscriptions, history buffering, and late-joiner replay.

    Register this module with the runtime early so that every other
    module can benefit from the enhanced event API::

        runtime.register(EventsModule(history_size=500))
    """

    name = "events"
    dependencies: ClassVar[list[str]] = []

    def __init__(self, history_size: int = 200) -> None:
        super().__init__()
        self._wrapper: EventBusWrapper | None = None
        self._runtime: Runtime | None = None
        self._core_bus: EventBus | None = None
        self._history_size = history_size

    # -- Public accessor ------------------------------------------------------

    @property
    def bus(self) -> EventBusWrapper:
        """The :class:`EventBusWrapper` instance installed on the runtime."""
        if self._wrapper is None:
            raise RuntimeError(
                "EventsModule is not initialized. "
                "Register it with the runtime and call await runtime.init().",
            )
        return self._wrapper

    # -- Lifecycle ------------------------------------------------------------

    async def setup(self, runtime: Runtime) -> None:
        self._runtime = runtime
        self._core_bus = runtime._events
        if self._core_bus is None:
            from forge.core.exceptions import ForgeError

            raise ForgeError("Runtime does not have an _events attribute.")

        self._wrapper = EventBusWrapper(
            core_bus=self._core_bus,
            history_size=self._history_size,
        )
        runtime._events = self._wrapper  # type: ignore[assignment]

    async def teardown(self) -> None:
        if self._wrapper is not None:
            self._wrapper.clear_history()
        self._wrapper = None
        self._runtime = None

    # -- Health ---------------------------------------------------------------

    def health_check(self) -> HealthResult:
        if self._wrapper is None:
            return HealthResult.error("EventsModule is not initialized.")
        return HealthResult.ok()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_wildcard(pattern: str) -> bool:
    """Return ``True`` if *pattern* contains a glob metacharacter."""
    return "*" in pattern or "?" in pattern or "[" in pattern
