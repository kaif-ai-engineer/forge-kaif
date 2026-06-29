from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from forge import ForgeRuntime
from forge.events import EventBusWrapper, EventsModule
from forge.events.event_types import (
    CACHE_HIT,
    CACHE_MISS,
    CACHE_SET,
    RUNTIME_READY,
    RUNTIME_SHUTDOWN,
    AIRequestCompletedPayload,
)

# ── Helpers ──────────────────────────────────────────────────────────


async def noop_handler(**kwargs: Any) -> None:
    """Handler that does nothing."""


def make_recorder() -> tuple[list[dict[str, Any]], Any]:
    """Return a (events_list, handler) pair for capturing emissions."""
    received: list[dict[str, Any]] = []

    async def handler(**kwargs: Any) -> None:
        received.append(kwargs)

    return received, handler


def _bus(runtime: ForgeRuntime) -> EventBusWrapper:
    """Cast ``runtime.events`` to ``EventBusWrapper`` for tests."""
    return cast("EventBusWrapper", runtime.events)


# ── EventBusWrapper (unit tests, no runtime) ─────────────────────────


class TestEventBusWrapper:
    """Direct tests of EventBusWrapper without a full runtime."""

    def test_is_wildcard_detection(self) -> None:
        from forge.events.module import _is_wildcard

        assert _is_wildcard("*")
        assert _is_wildcard("ai.*")
        assert _is_wildcard("?.event")
        assert _is_wildcard("[abc].event")
        assert not _is_wildcard("ai.request.completed")
        assert not _is_wildcard("runtime.ready")
        assert not _is_wildcard("plain")

    @pytest.mark.asyncio
    async def test_exact_match_subscription(self) -> None:
        """Exact-match handlers receive events via the core bus."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        received, handler = make_recorder()
        runtime.events.on("test.event", handler)
        await runtime.events.emit("test.event", foo=1, bar=2)
        await asyncio.sleep(0.01)

        assert len(received) == 1
        assert received[0] == {"foo": 1, "bar": 2}

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_wildcard_subscription(self) -> None:
        """Wildcard subscriptions receive matching events."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        received, handler = make_recorder()
        runtime.events.on("test.*", handler)

        await runtime.events.emit("test.one", a=1)
        await runtime.events.emit("test.two", b=2)
        await runtime.events.emit("other.event", c=3)
        await asyncio.sleep(0.01)

        assert len(received) == 2
        assert received[0] == {"a": 1}
        assert received[1] == {"b": 2}

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_global_wildcard(self) -> None:
        """The ``*`` pattern receives every event."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        received, handler = make_recorder()
        runtime.events.on("*", handler)

        await runtime.events.emit("first", x=1)
        await runtime.events.emit("second", y=2)
        await asyncio.sleep(0.01)

        assert len(received) == 2

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_handler_called_exactly_once(self) -> None:
        """A handler registered for both exact and wildcard is called once."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        count = 0

        async def counter(**kwargs: Any) -> None:
            nonlocal count
            count += 1

        # Same handler, both exact and wildcard — called once per matching emit
        runtime.events.on("exact.only", counter)
        await runtime.events.emit("exact.only")
        await asyncio.sleep(0.01)
        assert count == 1

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_unsubscribe_exact(self) -> None:
        """Exact-match handlers can be unsubscribed."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        received, handler = make_recorder()
        runtime.events.on("test.topic", handler)
        runtime.events.off("test.topic", handler)

        await runtime.events.emit("test.topic", val=1)
        await asyncio.sleep(0.01)
        assert len(received) == 0

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_unsubscribe_wildcard(self) -> None:
        """Wildcard handlers can be unsubscribed."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        received, handler = make_recorder()
        runtime.events.on("wild.*", handler)
        runtime.events.off("wild.*", handler)

        await runtime.events.emit("wild.card")
        await asyncio.sleep(0.01)
        assert len(received) == 0

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_unsubscribe_wildcard_not_found(self) -> None:
        """Unsubscribing a non-existent wildcard handler raises KeyError."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        _, handler = make_recorder()
        with pytest.raises(KeyError, match="not registered"):
            runtime.events.off("nonexistent.*", handler)

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_multiple_wildcard_patterns(self) -> None:
        """Multiple wildcard patterns can match the same event."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        received_a, handler_a = make_recorder()
        received_b, handler_b = make_recorder()

        runtime.events.on("data.*", handler_a)
        runtime.events.on("*.update", handler_b)

        await runtime.events.emit("data.update", val=42)
        await asyncio.sleep(0.01)

        assert len(received_a) == 1
        assert len(received_b) == 1

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_concurrent_handler_execution(self) -> None:
        """Handlers are executed concurrently (not sequentially)."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        started = 0

        async def make_slow() -> Any:
            async def slow(**kwargs: Any) -> None:
                nonlocal started
                started += 1
                await asyncio.sleep(0.05)
            return slow

        handlers = [await make_slow() for _ in range(5)]
        for h in handlers:
            runtime.events.on("concurrent.test", h)

        await runtime.events.emit("concurrent.test")
        await asyncio.sleep(0.01)

        assert started == 5

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_block(self) -> None:
        """A handler that raises does not prevent other handlers from running."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        ok_received: list[str] = []

        async def failing_handler(**kwargs: Any) -> None:
            raise ValueError("oops")

        async def ok_handler(**kwargs: Any) -> None:
            ok_received.append("ok")

        runtime.events.on("resilient.test", failing_handler)
        runtime.events.on("resilient.test", ok_handler)

        await runtime.events.emit("resilient.test")
        await asyncio.sleep(0.01)

        assert len(ok_received) == 1

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_decorator_syntax(self) -> None:
        """The ``on()`` method can be used as a decorator."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        received: list[dict[str, Any]] = []

        bus = _bus(runtime)

        @bus.on("decorator.test")  # type: ignore[untyped-decorator]
        async def decorated(**kwargs: Any) -> None:
            received.append(kwargs)

        assert decorated is not None

        await bus.emit("decorator.test", msg="hello")
        await asyncio.sleep(0.01)

        assert len(received) == 1
        assert received[0] == {"msg": "hello"}

        await runtime.teardown()


# ── EventHistoryBuffer Tests ─────────────────────────────────────────


class TestEventHistoryBuffer:
    """Tests for the event history buffer feature."""

    @pytest.mark.asyncio
    async def test_history_stores_recent_events(self) -> None:
        """Emitted events are stored in the history buffer."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        await runtime.events.emit("evt.a", x=1)
        await runtime.events.emit("evt.b", y=2)

        bus = _bus(runtime)
        assert len(bus.history) >= 2
        assert bus.history[-2].event == "evt.a"
        assert bus.history[-2].payload == {"x": 1}
        assert bus.history[-1].event == "evt.b"
        assert bus.history[-1].payload == {"y": 2}

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_history_bounded_size(self) -> None:
        """History buffer does not exceed its configured maxlen."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=3)
        runtime.register(events_mod)
        await runtime.init()

        for i in range(5):
            await runtime.events.emit(f"evt.{i}", n=i)

        hist = _bus(runtime).history
        assert len(hist) == 3
        assert hist[0].event == "evt.2"
        assert hist[1].event == "evt.3"
        assert hist[2].event == "evt.4"

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_clear_history(self) -> None:
        """clear_history() discards all stored events."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        bus = _bus(runtime)
        before = len(bus.history)
        await bus.emit("some.event")
        assert len(bus.history) == before + 1

        bus.clear_history()
        assert len(bus.history) == 0

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_subscribe_replays_history(self) -> None:
        """Late-joining subscribers receive matching history events."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        await runtime.events.emit("ai.request.started", model="gpt-4")
        await runtime.events.emit("ai.request.completed", model="gpt-4", tokens=100)
        await runtime.events.emit("other.event", val=1)

        bus = _bus(runtime)
        received: list[dict[str, Any]] = []

        async def late_handler(**kwargs: Any) -> None:
            received.append(kwargs)

        bus.subscribe("ai.*", late_handler, replay=True)
        await asyncio.sleep(0.01)

        assert len(received) == 2
        assert received[0] == {"model": "gpt-4"}
        assert received[1] == {"model": "gpt-4", "tokens": 100}

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_subscribe_no_replay(self) -> None:
        """Subscribing without replay does not replay history."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        await runtime.events.emit("ai.started")

        received, handler = make_recorder()
        _bus(runtime).subscribe("ai.*", handler, replay=False)
        await asyncio.sleep(0.01)

        assert len(received) == 0

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_history_immutable_tuple(self) -> None:
        """The ``history`` property returns an immutable tuple."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        await runtime.events.emit("test.event")
        hist = _bus(runtime).history

        with pytest.raises(AttributeError):
            hist.append(1)  # type: ignore[attr-defined]

        await runtime.teardown()


# ── has_listeners Tests ──────────────────────────────────────────────


class TestHasListeners:
    """Tests for has_listeners."""

    @pytest.mark.asyncio
    async def test_has_listeners_exact(self) -> None:
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        assert not runtime.events.has_listeners("my.event")
        runtime.events.on("my.event", noop_handler)
        assert runtime.events.has_listeners("my.event")

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_has_listeners_wildcard(self) -> None:
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        assert not runtime.events.has_listeners("prefix.alpha")
        runtime.events.on("prefix.*", noop_handler)
        assert runtime.events.has_listeners("prefix.alpha")

        await runtime.teardown()


# ── Event Types (event_types.py) ─────────────────────────────────────


class TestEventTypes:
    """Verify that event_types are correctly defined and importable."""

    def test_event_name_constants(self) -> None:
        assert RUNTIME_READY == "runtime.ready"
        assert RUNTIME_SHUTDOWN == "runtime.shutdown"
        assert CACHE_HIT == "cache.hit"
        assert CACHE_MISS == "cache.miss"
        assert CACHE_SET == "cache.set"

    def test_typeddict_usage(self) -> None:
        payload: AIRequestCompletedPayload = {
            "model": "gpt-4o",
            "provider": "openai",
            "input_tokens": 150,
            "output_tokens": 320,
            "latency_ms": 412.5,
            "trace_id": "abc123",
        }
        assert payload["model"] == "gpt-4o"
        assert payload["trace_id"] == "abc123"


# ── EventsModule Integration ─────────────────────────────────────────


class TestEventsModule:
    """Tests for EventsModule as a ForgeModule."""

    @pytest.mark.asyncio
    async def test_module_health_check(self) -> None:
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        result = events_mod.health_check()
        assert result.status == "ok"

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_module_health_not_initialized(self) -> None:
        events_mod = EventsModule()
        result = events_mod.health_check()
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_bus_property_uninitialized(self) -> None:
        events_mod = EventsModule()
        with pytest.raises(RuntimeError, match="not initialized"):
            _ = events_mod.bus

    @pytest.mark.asyncio
    async def test_runtime_events_drop_in_replacement(self) -> None:
        """EventsModule can be used as a drop-in for the core EventBus."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        received: list[dict[str, Any]] = []

        async def handler(**kwargs: Any) -> None:
            received.append(kwargs)

        # Exact same API as core EventBus
        runtime.events.on("dropin.test", handler)
        await runtime.events.emit("dropin.test", msg="works")
        await asyncio.sleep(0.01)

        assert len(received) == 1
        assert received[0] == {"msg": "works"}

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_core_runtime_events_still_work(self) -> None:
        """Existing events emitted by the runtime (ready/shutdown) still work."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)

        received_ready: list[dict[str, Any]] = []
        received_shutdown: list[dict[str, Any]] = []

        async def on_ready(**kwargs: Any) -> None:
            received_ready.append(kwargs)

        async def on_shutdown(**kwargs: Any) -> None:
            received_shutdown.append(kwargs)

        runtime.events.on("runtime.ready", on_ready)
        runtime.events.on("runtime.shutdown", on_shutdown)

        await runtime.init()
        await runtime.teardown()

        assert len(received_ready) == 1
        assert len(received_shutdown) == 1

    @pytest.mark.asyncio
    async def test_wildcard_receives_runtime_events(self) -> None:
        """Wildcard handlers receive runtime.ready/runtime.shutdown."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)

        async def catch_all(**kwargs: Any) -> None:
            pass

        runtime.events.on("*", catch_all)

        await runtime.init()

        # Capture before teardown clears history
        hist_after_init = _bus(runtime).history
        assert any(r.event == "runtime.ready" for r in hist_after_init)

        await runtime.teardown()

        hist_after_shutdown = _bus(runtime).history
        # After teardown, history is cleared — no events expected
        assert len(hist_after_shutdown) == 0


# ── Edge Cases ───────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge case and error handling tests."""

    @pytest.mark.asyncio
    async def test_emit_with_no_handlers(self) -> None:
        """Emitting an event with no handlers should not error."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        await runtime.events.emit("orphan.event")
        # No assertion — just should not raise

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_empty_string_event_name(self) -> None:
        """Empty string event names should not crash (edge case)."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        received, handler = make_recorder()
        runtime.events.on("", handler)
        await runtime.events.emit("", data=1)
        await asyncio.sleep(0.01)

        assert len(received) == 1
        assert received[0] == {"data": 1}

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_dot_in_wildcard_pattern(self) -> None:
        """Wildcard patterns with dots match correctly."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        received, handler = make_recorder()
        runtime.events.on("a.b.*", handler)

        await runtime.events.emit("a.b.c", val=1)
        await runtime.events.emit("a.b.c.d", val=2)
        await runtime.events.emit("x.y.z", val=3)
        await asyncio.sleep(0.01)

        assert len(received) == 2

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_handler_removed_after_unsubscribe(self) -> None:
        """After unsubscribing, handler should not be called."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        call_count = 0

        async def counter(**kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1

        runtime.events.on("count.me", counter)
        await runtime.events.emit("count.me")
        await asyncio.sleep(0.01)
        assert call_count == 1

        runtime.events.off("count.me", counter)
        await runtime.events.emit("count.me")
        await asyncio.sleep(0.01)
        assert call_count == 1

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_duplicate_handler_not_called_twice(self) -> None:
        """Registering the same handler twice on the same event does not call it twice."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        call_count = 0

        async def counter(**kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1

        runtime.events.on("dedup.test", counter)
        runtime.events.on("dedup.test", counter)
        runtime.events.off("dedup.test", counter)

        await runtime.events.emit("dedup.test")
        await asyncio.sleep(0.01)
        assert call_count == 0

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_multiple_events_same_handler(self) -> None:
        """A single handler can subscribe to multiple events."""
        runtime = ForgeRuntime()
        events_mod = EventsModule(history_size=10)
        runtime.register(events_mod)
        await runtime.init()

        received: list[str] = []

        async def multi_handler(**kwargs: Any) -> None:
            received.append(kwargs.get("src", ""))

        runtime.events.on("source.a", multi_handler)
        runtime.events.on("source.b", multi_handler)
        runtime.events.on("source.c", multi_handler)

        await runtime.events.emit("source.a", src="a")
        await runtime.events.emit("source.b", src="b")
        await runtime.events.emit("source.c", src="c")
        await asyncio.sleep(0.01)

        assert received == ["a", "b", "c"]

        await runtime.teardown()
