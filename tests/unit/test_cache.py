from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from forge.cache._state import set_cache_module
from forge.cache.backends.memory import MemoryBackend
from forge.cache.backends.redis import RedisBackend
from forge.cache.decorators import cached
from forge.cache.exceptions import CacheBackendError, CacheError
from forge.cache.module import CacheModule
from forge.config.module import ConfigModule
from forge.core.runtime import ForgeRuntime
from forge.core.module import HealthResult


class CustomObj:
    """Helper test class for pickle serialization."""

    def __init__(self, val: int) -> None:
        self.val = val

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, CustomObj) and self.val == other.val


@pytest.mark.asyncio
async def test_memory_backend_ops() -> None:
    """Test basic operations on MemoryBackend."""
    backend = MemoryBackend(max_size=3, default_ttl=300)

    # Initially empty
    assert await backend.get("foo") is None
    assert not await backend.has("foo")

    # Set value
    await backend.set("foo", "bar")
    assert await backend.get("foo") == "bar"
    assert await backend.has("foo")

    # Delete value
    assert await backend.delete("foo") is True
    assert await backend.get("foo") is None
    assert await backend.delete("foo") is False

    # Clear
    await backend.set("foo", 1)
    await backend.set("baz", 2)
    assert await backend.has("foo")
    assert await backend.has("baz")
    await backend.clear()
    assert not await backend.has("foo")
    assert not await backend.has("baz")


@pytest.mark.asyncio
async def test_memory_backend_lru_eviction() -> None:
    """Test that LRU eviction removes the least recently used item."""
    backend = MemoryBackend(max_size=3, default_ttl=300)

    await backend.set("k1", 1)
    await backend.set("k2", 2)
    await backend.set("k3", 3)

    # k1, k2, k3 are in cache. k1 is LRU, k3 is MRU.
    # Access k1 to make it MRU
    assert await backend.get("k1") == 1

    # Now k2 is LRU, k1 is MRU.
    # Set k4 (triggers eviction of k2)
    await backend.set("k4", 4)

    assert await backend.has("k1")
    assert not await backend.has("k2")
    assert await backend.has("k3")
    assert await backend.has("k4")


@pytest.mark.asyncio
async def test_memory_backend_ttl() -> None:
    """Test that lazy TTL expiration works."""
    backend = MemoryBackend(max_size=5, default_ttl=300)

    # Set with short TTL
    await backend.set("k1", "val", ttl=1)
    assert await backend.get("k1") == "val"

    # Set with 0 TTL (no expiry)
    await backend.set("k2", "val2", ttl=0)

    # Fast forward or wait
    await asyncio.sleep(1.05)

    assert await backend.get("k1") is None
    assert await backend.get("k2") == "val2"


@pytest.mark.asyncio
async def test_cache_module_events() -> None:
    """Test that CacheModule emits hit, miss, and set events."""
    runtime = ForgeRuntime()
    runtime.register(ConfigModule())
    cm = CacheModule()
    runtime.register(cm)

    await runtime.init()

    events_received: list[tuple[str, dict[str, Any]]] = []

    async def on_event(name: str, **payload: Any) -> None:
        events_received.append((name, payload))

    runtime._events.on("cache.hit", lambda **p: on_event("cache.hit", **p))
    runtime._events.on("cache.miss", lambda **p: on_event("cache.miss", **p))
    runtime._events.on("cache.set", lambda **p: on_event("cache.set", **p))

    try:
        await cm.set("test_key", "value", ttl=10)
        assert await cm.get("test_key") == "value"
        assert await cm.get("missing_key") is None

        # Allow event delivery to propagate
        await asyncio.sleep(0.01)

        assert len(events_received) == 3
        assert events_received[0] == ("cache.set", {"key": "test_key", "ttl": 10})
        assert events_received[1] == ("cache.hit", {"key": "test_key"})
        assert events_received[2] == ("cache.miss", {"key": "missing_key"})
    finally:
        await runtime.teardown()


@pytest.mark.asyncio
async def test_cached_decorator_basic() -> None:
    """Test the basic behavior of the @cached decorator."""
    runtime = ForgeRuntime()
    runtime.register(ConfigModule())
    cm = CacheModule()
    runtime.register(cm)

    await runtime.init()

    call_count = 0

    @cached(ttl=60, key="val:{x}")
    async def compute(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x * 10

    try:
        # First call: miss
        res1 = await compute(5)
        assert res1 == 50
        assert call_count == 1

        # Second call: hit
        res2 = await compute(5)
        assert res2 == 50
        assert call_count == 1

        # Different arg: miss
        res3 = await compute(6)
        assert res3 == 60
        assert call_count == 2
    finally:
        await runtime.teardown()


@pytest.mark.asyncio
async def test_cached_decorator_auto_key() -> None:
    """Test the auto key generation logic of @cached decorator."""
    runtime = ForgeRuntime()
    runtime.register(ConfigModule())
    cm = CacheModule()
    runtime.register(cm)

    await runtime.init()

    call_count = 0

    @cached()
    async def compute_auto(x: int, y: str) -> str:
        nonlocal call_count
        call_count += 1
        return f"{x}:{y}"

    try:
        res1 = await compute_auto(10, "hello")
        assert res1 == "10:hello"
        assert call_count == 1

        res2 = await compute_auto(10, "hello")
        assert res2 == "10:hello"
        assert call_count == 1

        res3 = await compute_auto(10, "world")
        assert res3 == "10:world"
        assert call_count == 2
    finally:
        await runtime.teardown()


@pytest.mark.asyncio
async def test_cached_decorator_namespace() -> None:
    """Test the namespace parameter prefixing of @cached decorator."""
    runtime = ForgeRuntime()
    runtime.register(ConfigModule())
    cm = CacheModule()
    runtime.register(cm)

    await runtime.init()

    @cached(namespace="custom_ns")
    async def namespaced_fn() -> str:
        return "ok"

    try:
        await namespaced_fn()
        # Verify it was cached under the namespace
        backend = cm.backend
        assert hasattr(backend, "_cache")
        cache_keys = list(getattr(backend, "_cache").keys())
        assert any(k.startswith("custom_ns:") for k in cache_keys)
    finally:
        await runtime.teardown()


@pytest.mark.asyncio
async def test_cached_decorator_invalidate() -> None:
    """Test the invalidation helper attached to decorated functions."""
    runtime = ForgeRuntime()
    runtime.register(ConfigModule())
    cm = CacheModule()
    runtime.register(cm)

    await runtime.init()

    call_count = 0

    @cached(key="item:{item_id}")
    async def fetch_item(item_id: int) -> int:
        nonlocal call_count
        call_count += 1
        return item_id

    try:
        await fetch_item(42)
        assert call_count == 1

        # Call again (hit)
        await fetch_item(42)
        assert call_count == 1

        # Invalidate specific entry
        # Mypy warning workaround for dynamically attached attribute
        invalidate_fn = getattr(fetch_item, "invalidate")
        await invalidate_fn(42)

        # Call again (miss)
        await fetch_item(42)
        assert call_count == 2
    finally:
        await runtime.teardown()


@pytest.mark.asyncio
async def test_global_invalidate() -> None:
    """Test the global invalidate helper function."""
    runtime = ForgeRuntime()
    runtime.register(ConfigModule())
    cm = CacheModule()
    runtime.register(cm)

    await runtime.init()

    from forge.cache import invalidate

    try:
        await cm.set("test_key", "test_val")
        assert await cm.has("test_key")

        # Global invalidate
        deleted = await invalidate("test_key")
        assert deleted is True
        assert not await cm.has("test_key")

        # Invalidating missing key
        deleted_missing = await invalidate("missing_key")
        assert deleted_missing is False
    finally:
        await runtime.teardown()


@pytest.mark.asyncio
async def test_cached_decorator_no_runtime() -> None:
    """Decorator should work transparently if no runtime is active."""
    set_cache_module(None)

    call_count = 0

    @cached()
    async def simple_fn(val: int) -> int:
        nonlocal call_count
        call_count += 1
        return val

    # Since no cache is setup, should bypass and call directly every time
    assert await simple_fn(10) == 10
    assert call_count == 1

    assert await simple_fn(10) == 10
    assert call_count == 2

    # Invalidate should return False when no runtime/backend is configured
    invalidate_fn = getattr(simple_fn, "invalidate")
    assert await invalidate_fn(10) is False


def test_cache_module_health_check() -> None:
    """Test health check output of CacheModule."""
    cm = CacheModule()

    # Before initialized
    res = cm.health_check()
    assert res.status == HealthResult.ERROR
    assert "not initialized" in (res.message or "")

    # MemoryBackend initialized
    from forge.cache.backends.memory import MemoryBackend

    cm._backend = MemoryBackend()
    res_mem = cm.health_check()
    assert res_mem.status == HealthResult.OK
    assert "Memory cache active" in (res_mem.message or "")


@pytest.mark.asyncio
async def test_redis_backend_operations() -> None:
    """Test RedisBackend operations against a running Redis instance."""
    # We will attempt connection to local Redis
    backend = RedisBackend(redis_url="redis://127.0.0.1:6379/1")
    try:
        await backend.connect()
    except CacheBackendError:
        pytest.skip("Local Redis instance is not available or connection refused.")

    try:
        # Operations
        await backend.clear()
        assert await backend.get("foo") is None
        assert not await backend.has("foo")

        # Simple json serializable type
        await backend.set("foo", {"hello": "world"}, ttl=10)
        assert await backend.has("foo")
        assert await backend.get("foo") == {"hello": "world"}

        # Complex pickle fallback type (like a complex number or user-defined class)
        obj = CustomObj(42)
        await backend.set("obj", obj)
        assert await backend.get("obj") == obj

        # Delete
        assert await backend.delete("foo") is True
        assert await backend.get("foo") is None
        assert await backend.delete("foo") is False

        # Clear prefix test
        await backend.set("prefix_test_1", 100)
        await backend.set("prefix_test_2", 200)
        await backend.clear()
        assert await backend.get("prefix_test_1") is None
        assert await backend.get("prefix_test_2") is None
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_redis_backend_health_check() -> None:
    """Test health check output when Redis backend is active."""
    cm = CacheModule()
    redis_backend = RedisBackend(redis_url="redis://127.0.0.1:6379/1")

    # If connection fails, health check should return error
    # Connect to invalid port/host to test failure mode
    bad_backend = RedisBackend(redis_url="redis://127.0.0.1:12345")
    cm._backend = bad_backend
    res_bad = cm.health_check()
    assert res_bad.status == HealthResult.ERROR

    # Try connecting to the valid local Redis
    try:
        await redis_backend.connect()
        cm._backend = redis_backend
        res_good = cm.health_check()
        assert res_good.status == HealthResult.OK
        assert "Redis backend is healthy" in (res_good.message or "")
    except CacheBackendError:
        # Skip if local Redis not available
        pass
    finally:
        await redis_backend.close()
