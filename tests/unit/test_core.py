from __future__ import annotations

import asyncio
from typing import Any, ClassVar

import pytest

from forge import (
    ConfigModule,
    ForgeConfig,
    ForgeModule,
    ForgeRuntime,
    LogModule,
    log,
)
from forge.core.context import (
    TraceContext,
    get_baggage,
    get_baggage_item,
    get_trace_id,
)
from forge.core.exceptions import (
    CircularDependencyError,
    ModuleRegistrationError,
)
from forge.retry import CircuitBreaker, CircuitBreakerOpenError, retry


# ── Mock Modules for Dependency Injection Tests ────────────────────
class ModuleA(ForgeModule):
    name = "module_a"


class ModuleB(ForgeModule):
    name = "module_b"
    dependencies: ClassVar[list[str]] = ["module_a"]


class ModuleC(ForgeModule):
    name = "module_c"
    dependencies: ClassVar[list[str]] = ["module_b"]


class CircularModule1(ForgeModule):
    name = "circ_1"
    dependencies: ClassVar[list[str]] = ["circ_2"]


class CircularModule2(ForgeModule):
    name = "circ_2"
    dependencies: ClassVar[list[str]] = ["circ_1"]


# ── 1. Core Runtime & DI Container Tests ───────────────────────────


@pytest.mark.asyncio
async def test_runtime_topological_initialization() -> None:
    runtime = ForgeRuntime()
    # Register out of order
    runtime.register(ModuleC())
    runtime.register(ModuleB())
    runtime.register(ModuleA())

    await runtime.init()

    # Get modules and check setup states
    a = runtime.get(ModuleA)
    b = runtime.get(ModuleB)
    c = runtime.get(ModuleC)

    assert a._lifecycle_state.name == "READY"
    assert b._lifecycle_state.name == "READY"
    assert c._lifecycle_state.name == "READY"

    await runtime.teardown()


@pytest.mark.asyncio
async def test_runtime_circular_dependency() -> None:
    runtime = ForgeRuntime()
    runtime.register(CircularModule1())
    runtime.register(CircularModule2())

    with pytest.raises(CircularDependencyError):
        await runtime.init()


@pytest.mark.asyncio
async def test_runtime_duplicate_registration() -> None:
    runtime = ForgeRuntime()
    runtime.register(ModuleA())
    with pytest.raises(ModuleRegistrationError):
        runtime.register(ModuleA(), replace=False)


# ── 2. Event Bus Tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_event_bus_publish_subscribe() -> None:
    runtime = ForgeRuntime()
    await runtime.init()

    received: list[dict[str, Any]] = []

    async def handler(**kwargs: Any) -> None:
        received.append(kwargs)

    runtime.events.on("test.topic", handler)
    await runtime.events.emit("test.topic", foo="bar")

    await asyncio.sleep(0.01)
    assert len(received) == 1
    assert received[0] == {"foo": "bar"}

    # Unsubscribe
    runtime.events.off("test.topic", handler)
    await runtime.events.emit("test.topic", baz="qux")
    await asyncio.sleep(0.01)
    assert len(received) == 1

    await runtime.teardown()


# ── 3. Trace Context & Baggage Tests ───────────────────────────────


def test_trace_context_propagation() -> None:
    # Test using context manager
    with TraceContext(trace_id="my-trace-id", baggage={"user_id": "123"}):
        assert get_trace_id() == "my-trace-id"
        assert get_baggage_item("user_id") == "123"
        assert get_baggage() == {"user_id": "123"}

    assert get_trace_id() == ""
    assert get_baggage() == {}


# ── 4. Configuration Module Tests ──────────────────────────────────


@pytest.mark.asyncio
async def test_config_module_override_and_sensitive() -> None:
    runtime = ForgeRuntime()
    runtime.register(ConfigModule())
    await runtime.init()

    config_mod = runtime.get(ConfigModule)
    assert isinstance(config_mod.config, ForgeConfig)

    # Override test
    original_env = config_mod.config.environment
    with config_mod.override({"environment": "testing-override"}):
        assert config_mod.config.environment == "testing-override"

    assert config_mod.config.environment == original_env

    # Secret masking / sensitive fields checks
    from forge.config.secrets import field_is_sensitive, mask_value

    assert field_is_sensitive("api_key") is True
    assert field_is_sensitive("password") is True
    assert field_is_sensitive("normal_field") is False
    assert mask_value("my-secret-key") == "********"

    await runtime.teardown()


# ── 5. Logging Module & LoggerProxy Tests ──────────────────────────


@pytest.mark.asyncio
async def test_logging_proxy_and_context() -> None:
    runtime = ForgeRuntime()
    runtime.register(ConfigModule())
    runtime.register(LogModule())
    await runtime.init()

    # Get a logger from log.get
    logger = log.get("test_module")
    # Logging with keyword args should not crash
    logger.info("Test message", key1="val1", key2=123)

    # Test context manager
    with log.context(request_id="req-abc"):
        logger.debug("Inside context")

    await runtime.teardown()


# ── 6. Retry & Circuit Breaker Tests ───────────────────────────────


@pytest.mark.asyncio
async def test_retry_decorator_success() -> None:
    calls = 0

    @retry(attempts=3, base_delay=0.01)
    async def fast_func() -> str:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise ValueError("transient failure")
        return "success"

    result = await fast_func()
    assert result == "success"
    assert calls == 2


@pytest.mark.asyncio
async def test_circuit_breaker_states() -> None:
    breaker = CircuitBreaker(failure_threshold=2, recovery_time=0.05)

    # Initially CLOSED
    assert breaker.state.value == "CLOSED"

    # Record failures to trip
    breaker._on_failure()
    assert breaker.state.value == "CLOSED"

    breaker._on_failure()
    assert breaker.state.value == "OPEN"

    # In open state, attempting to run breaker raises
    with pytest.raises(CircuitBreakerOpenError):
        async with breaker:
            pass

    # Wait for recovery time
    await asyncio.sleep(0.07)
    # Check state updates
    breaker._check_state()
    assert breaker.state.value == "HALF_OPEN"

    # Record success to close again
    breaker._on_success()
    assert breaker.state.value == "CLOSED"
