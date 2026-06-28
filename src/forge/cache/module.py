from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, cast

from forge.cache._state import set_cache_module
from forge.cache.backends.base import CacheBackend
from forge.cache.exceptions import CacheError
from forge.core.module import ForgeModule, HealthResult

if TYPE_CHECKING:
    from forge.core.runtime import ForgeRuntime as Runtime


class CacheModule(ForgeModule):
    """
    Manages caching services and pluggable storage backends for the forge runtime.
    """

    name = "cache"
    dependencies: ClassVar[list[str]] = ["config"]

    def __init__(self) -> None:
        self._backend: CacheBackend | None = None
        self._runtime: Runtime | None = None

    @property
    def backend(self) -> CacheBackend:
        """Get the active cache backend."""
        if self._backend is None:
            raise CacheError("Cache backend is not initialized.")
        return self._backend

    async def setup(self, runtime: Runtime) -> None:
        """Initialize cache module and configure settings."""
        self._runtime = runtime
        set_cache_module(self)

        # Read cache configuration
        from forge.config.module import ConfigModule

        config_module = cast("ConfigModule", runtime.get(ConfigModule))
        config = getattr(config_module.config, "cache", None)

        backend_type = "memory"
        default_ttl = 300
        memory_max_size = 1000
        redis_url = None
        redis_key_prefix = "forge:"
        redis_max_connections = 10

        if config is not None:
            backend_type = getattr(config, "backend", "memory")
            default_ttl = getattr(config, "default_ttl", 300)
            memory_max_size = getattr(config, "memory_max_size", 1000)
            redis_config = getattr(config, "redis", None)
            if redis_config is not None:
                redis_url = getattr(redis_config, "url", None)
                redis_key_prefix = getattr(redis_config, "key_prefix", "forge:")
                redis_max_connections = getattr(redis_config, "max_connections", 10)

        if backend_type == "redis":
            from forge.cache.backends.redis import RedisBackend

            url = redis_url or "redis://localhost:6379/0"
            redis_backend = RedisBackend(
                redis_url=url,
                key_prefix=redis_key_prefix,
                max_connections=redis_max_connections,
                default_ttl=default_ttl,
            )
            await redis_backend.connect()
            self._backend = redis_backend
        else:
            from forge.cache.backends.memory import MemoryBackend

            self._backend = MemoryBackend(
                max_size=memory_max_size,
                default_ttl=default_ttl,
            )

    async def teardown(self) -> None:
        """Teardown the cache module."""
        set_cache_module(None)
        if self._backend:
            await self._backend.close()
            self._backend = None
        self._runtime = None

    async def get(self, key: str) -> Any | None:
        """Get a value from cache and emit hit/miss event."""
        if not self._backend:
            raise CacheError("Cache module is not initialized.")
        val = await self._backend.get(key)
        if self._runtime:
            if val is not None:
                await self._runtime._events.emit("cache.hit", key=key)
            else:
                await self._runtime._events.emit("cache.miss", key=key)
        return val

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set a cache value and emit set event."""
        if not self._backend:
            raise CacheError("Cache module is not initialized.")
        await self._backend.set(key, value, ttl)
        if self._runtime:
            await self._runtime._events.emit("cache.set", key=key, ttl=ttl)

    async def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        if not self._backend:
            raise CacheError("Cache module is not initialized.")
        return await self._backend.delete(key)

    async def has(self, key: str) -> bool:
        """Check if a key exists in cache."""
        if not self._backend:
            raise CacheError("Cache module is not initialized.")
        return await self._backend.has(key)

    async def clear(self) -> None:
        """Clear all cache values."""
        if not self._backend:
            raise CacheError("Cache module is not initialized.")
        await self._backend.clear()

    def health_check(self) -> HealthResult:
        """Check the health status of the caching backend."""
        if self._backend is None:
            return HealthResult.error("Cache backend not initialized")

        from forge.cache.backends.memory import MemoryBackend

        if isinstance(self._backend, MemoryBackend):
            return HealthResult(HealthResult.OK, "Memory cache active")

        from forge.cache.backends.redis import RedisBackend

        if isinstance(self._backend, RedisBackend):
            import redis

            try:
                # Use standard synchronous redis client for a quick sync ping
                client = redis.from_url(self._backend.url, socket_timeout=1.0)
                if client.ping():
                    return HealthResult(HealthResult.OK, "Redis backend is healthy")
                return HealthResult.error("Redis ping failed")
            except Exception as exc:
                return HealthResult.error(f"Redis backend unhealthy: {exc}")

        return HealthResult.ok()
