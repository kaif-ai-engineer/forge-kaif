"""
Integration tests for critical forge runtime paths.

These tests exercise end-to-end flows that span multiple modules,
verifying that the runtime lifecycle, DI, events, and module
interactions work correctly in realistic scenarios.
"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar

import pytest

from forge import ForgeModule, ForgeRuntime
from forge.core.exceptions import (
    ForgeError,
    ModuleStateError,
)

# ---------------------------------------------------------------------------
# Modules for integration testing
# ---------------------------------------------------------------------------


class SetupOrderTracker(ForgeModule):
    """Tracks the order in which modules are set up."""

    name = "tracker"
    setup_order: ClassVar[list[str]] = []

    async def setup(self, runtime: Any) -> None:
        self.setup_order.append(self.name)


class DepA(ForgeModule):
    name = "dep_a"

    async def setup(self, runtime: Any) -> None:
        SetupOrderTracker.setup_order.append(self.name)


class DepB(ForgeModule):
    name = "dep_b"
    dependencies: ClassVar[list[str]] = ["dep_a"]

    async def setup(self, runtime: Any) -> None:
        SetupOrderTracker.setup_order.append(self.name)


class DepC(ForgeModule):
    name = "dep_c"
    dependencies: ClassVar[list[str]] = ["dep_b"]

    async def setup(self, runtime: Any) -> None:
        SetupOrderTracker.setup_order.append(self.name)


class FailingModule(ForgeModule):
    """Module whose setup always fails."""

    name = "failing"

    async def setup(self, runtime: Any) -> None:
        raise RuntimeError("Intentional setup failure")


class TeardownTracker(ForgeModule):
    """Module that records teardown calls."""

    name = "teardown_tracker"
    teardown_called: ClassVar[bool] = False

    async def teardown(self) -> None:
        TeardownTracker.teardown_called = True


# ---------------------------------------------------------------------------
# Runtime lifecycle integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_lifecycle() -> None:
    """Verify complete runtime lifecycle: register → init → use → teardown."""
    SetupOrderTracker.setup_order.clear()

    runtime = ForgeRuntime()
    runtime.register(DepC())
    runtime.register(DepA())
    runtime.register(DepB())
    runtime.register(SetupOrderTracker())

    await runtime.init()

    # Verify topological order: dep_a and tracker have no deps (both in_degree=0),
    # dep_b depends on dep_a, dep_c depends on dep_b.
    # Exact order among same-level nodes depends on insertion order.
    assert SetupOrderTracker.setup_order[0] == "dep_a"
    assert "tracker" in SetupOrderTracker.setup_order
    assert SetupOrderTracker.setup_order.index("dep_a") < SetupOrderTracker.setup_order.index(
        "dep_b"
    )
    assert SetupOrderTracker.setup_order.index("dep_b") < SetupOrderTracker.setup_order.index(
        "dep_c"
    )
    assert runtime.is_initialized
    assert not runtime.is_shutting_down

    await runtime.teardown()
    assert not runtime.is_initialized


@pytest.mark.asyncio
async def test_teardown_is_idempotent() -> None:
    """Verify teardown can be called multiple times safely."""
    TeardownTracker.teardown_called = False

    runtime = ForgeRuntime()
    runtime.register(TeardownTracker())
    await runtime.init()

    await runtime.teardown()
    assert TeardownTracker.teardown_called

    # Second teardown should be a no-op
    await runtime.teardown()


@pytest.mark.asyncio
async def test_double_init_raises() -> None:
    """Verify init cannot be called twice."""
    runtime = ForgeRuntime()
    await runtime.init()

    with pytest.raises(ForgeError, match="cannot be initialised"):
        await runtime.init()

    await runtime.teardown()


@pytest.mark.asyncio
async def test_setup_failure_propagates() -> None:
    """Verify module setup failures are properly reported."""
    runtime = ForgeRuntime()
    runtime.register(FailingModule())

    with pytest.raises(ForgeError, match="Failed to initialise module 'failing'"):
        await runtime.init()


@pytest.mark.asyncio
async def test_invalid_lifecycle_transition() -> None:
    """Verify invalid state transitions raise ModuleStateError."""
    runtime = ForgeRuntime()
    runtime.register(DepA())
    await runtime.init()

    module = runtime.get(DepA)
    # Module is READY; trying to go back to REGISTERED should fail
    from forge.core.module import ModuleLifecycleState

    with pytest.raises(ModuleStateError):
        module._transition(ModuleLifecycleState.REGISTERED)

    await runtime.teardown()


# ---------------------------------------------------------------------------
# Event bus integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_bus_end_to_end() -> None:
    """Verify events are emitted and received across module boundaries."""
    runtime = ForgeRuntime()
    await runtime.init()

    received: list[dict[str, Any]] = []

    async def handler(**kwargs: Any) -> None:
        received.append(kwargs)

    runtime.events.on("test.end_to_end", handler)
    await runtime.events.emit("test.end_to_end", value=42)
    await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0] == {"value": 42}

    await runtime.teardown()


@pytest.mark.asyncio
async def test_event_unsubscribe() -> None:
    """Verify handlers can be unsubscribed."""
    runtime = ForgeRuntime()
    await runtime.init()

    call_count = 0

    async def counter(**kwargs: Any) -> None:
        nonlocal call_count
        call_count += 1

    runtime.events.on("test.count", counter)
    await runtime.events.emit("test.count")
    await asyncio.sleep(0.01)
    assert call_count == 1

    runtime.events.off("test.count", counter)
    await runtime.events.emit("test.count")
    await asyncio.sleep(0.01)
    assert call_count == 1

    await runtime.teardown()


@pytest.mark.asyncio
async def test_failing_handler_does_not_block_others() -> None:
    """Verify a failing event handler doesn't prevent other handlers from running."""
    runtime = ForgeRuntime()
    await runtime.init()

    results: list[str] = []

    async def good_handler(**kwargs: Any) -> None:
        results.append("good")

    async def bad_handler(**kwargs: Any) -> None:
        raise RuntimeError("Handler failure")

    runtime.events.on("test.mixed", bad_handler)
    runtime.events.on("test.mixed", good_handler)
    await runtime.events.emit("test.mixed")
    await asyncio.sleep(0.05)

    assert "good" in results

    await runtime.teardown()


# ---------------------------------------------------------------------------
# Trace context integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trace_context_through_event_handler() -> None:
    """Verify trace context propagates through event handlers."""
    from forge.core.context import TraceContext, get_trace_id

    runtime = ForgeRuntime()
    await runtime.init()

    captured_trace_id: list[str] = []

    async def tracer(**kwargs: Any) -> None:
        captured_trace_id.append(get_trace_id())

    runtime.events.on("test.traced", tracer)

    with TraceContext(trace_id="integration-trace-123"):
        await runtime.events.emit("test.traced")
        await asyncio.sleep(0.05)

    assert captured_trace_id == ["integration-trace-123"]

    await runtime.teardown()


# ---------------------------------------------------------------------------
# DI container integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_module_access_after_init() -> None:
    """Verify modules can be accessed after initialization."""
    runtime = ForgeRuntime()
    runtime.register(DepA())
    await runtime.init()

    module = runtime.get(DepA)
    assert module.name == "dep_a"
    assert module._lifecycle_state.value == "READY"

    await runtime.teardown()


@pytest.mark.asyncio
async def test_get_nonexistent_module_raises() -> None:
    """Verify accessing a non-registered module raises."""
    runtime = ForgeRuntime()
    await runtime.init()

    from forge.core.exceptions import ModuleNotFoundError

    with pytest.raises(ModuleNotFoundError):
        runtime.get(DepA)

    await runtime.teardown()
