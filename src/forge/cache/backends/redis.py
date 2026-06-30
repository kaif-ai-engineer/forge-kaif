from __future__ import annotations

import json
import logging
import pickle
from typing import Any

import redis.asyncio as aioredis

from forge.cache.exceptions import CacheBackendError

logger = logging.getLogger(__name__)


class RedisBackend:
    """
    Redis cache backend using redis.asyncio.

    Supports connection pooling, key prefixes, and json/pickle serialization.
    """

    def __init__(
        self,
        redis_url: str,
        key_prefix: str = "forge:",
        max_connections: int = 10,
        default_ttl: int = 300,
    ) -> None:
        self._url = redis_url
        self._prefix = key_prefix
        self._max_connections = max_connections
        self._default_ttl = default_ttl
        self._pool: aioredis.ConnectionPool | None = None
        self._client: aioredis.Redis | None = None

    @property
    def url(self) -> str:
        """Get the Redis URL."""
        return self._url

    @property
    def is_connected(self) -> bool:
        """Check if connected to Redis."""
        return self._client is not None

    async def connect(self) -> None:
        """Initialize the connection pool and client."""
        try:
            self._pool = aioredis.ConnectionPool.from_url(
                self._url,
                max_connections=self._max_connections,
            )
            self._client = aioredis.Redis(connection_pool=self._pool)
            # Verify connectivity
            await self._client.ping()  # type: ignore[misc]
        except Exception as exc:
            logger.warning("Failed to connect to Redis at %s: %s", self._url, exc)
            self._client = None
            self._pool = None
            raise CacheBackendError(f"Failed to connect to Redis: {exc}") from exc

    async def disconnect(self) -> None:
        """Close connection pool and release resources."""
        if self._client:
            try:
                await self._client.aclose()
            except Exception as exc:
                logger.warning("Error closing Redis client: %s", exc)
        if self._pool:
            try:
                await self._pool.disconnect()
            except Exception as exc:
                logger.warning("Error disconnecting Redis pool: %s", exc)
        self._client = None
        self._pool = None

    async def close(self) -> None:
        """Close connections. Conforms to base backend protocol."""
        await self.disconnect()

    def _prefixed_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def _serialize(self, value: Any) -> bytes:
        try:
            # Attempt JSON serialization
            serialized = json.dumps(value)
            return b"j" + serialized.encode("utf-8")
        except (TypeError, ValueError):
            # Fall back to pickle serialization
            serialized_pickle = pickle.dumps(value)
            return b"p" + serialized_pickle

    def _deserialize(self, data: bytes) -> Any:
        if not data:
            return None
        header = data[0:1]
        payload = data[1:]
        if header == b"j":
            return json.loads(payload.decode("utf-8"))
        if header == b"p":
            return pickle.loads(payload)  # noqa: S301
        raise ValueError(f"Unknown serialization header: {header!r}")

    async def get(self, key: str) -> Any | None:
        if not self._client:
            raise CacheBackendError("Redis backend is not connected.")
        try:
            raw = await self._client.get(self._prefixed_key(key))
            if raw is None:
                return None
            return self._deserialize(bytes(raw))
        except Exception as exc:
            logger.warning("Redis GET failed for key %s: %s", key, exc)
            raise CacheBackendError(f"Redis GET failed: {exc}") from exc

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        if not self._client:
            raise CacheBackendError("Redis backend is not connected.")
        try:
            serialized = self._serialize(value)
            effective_ttl = ttl if ttl is not None else self._default_ttl
            prefixed = self._prefixed_key(key)
            if effective_ttl > 0:
                await self._client.set(prefixed, serialized, ex=effective_ttl)
            else:
                await self._client.set(prefixed, serialized)
        except Exception as exc:
            logger.warning("Redis SET failed for key %s: %s", key, exc)
            raise CacheBackendError(f"Redis SET failed: {exc}") from exc

    async def delete(self, key: str) -> bool:
        if not self._client:
            raise CacheBackendError("Redis backend is not connected.")
        try:
            result = await self._client.delete(self._prefixed_key(key))
            return bool(result and result > 0)
        except Exception as exc:
            logger.warning("Redis DELETE failed for key %s: %s", key, exc)
            raise CacheBackendError(f"Redis DELETE failed: {exc}") from exc

    async def has(self, key: str) -> bool:
        if not self._client:
            raise CacheBackendError("Redis backend is not connected.")
        try:
            result = await self._client.exists(self._prefixed_key(key))
            return bool(result and result > 0)
        except Exception as exc:
            logger.warning("Redis EXISTS failed for key %s: %s", key, exc)
            raise CacheBackendError(f"Redis EXISTS failed: {exc}") from exc

    async def clear(self) -> None:
        if not self._client:
            raise CacheBackendError("Redis backend is not connected.")
        try:
            # Find all keys matching the prefix
            pattern = f"{self._prefix}*"
            keys = await self._client.keys(pattern)
            if keys:
                await self._client.delete(*keys)
        except Exception as exc:
            logger.warning("Redis CLEAR failed: %s", exc)
            raise CacheBackendError(f"Redis CLEAR failed: {exc}") from exc
