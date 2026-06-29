from __future__ import annotations

import abc
import json
import logging
from typing import Any, Protocol, runtime_checkable

from forge.featureflags.exceptions import FlagStoreError
from forge.featureflags.models import FlagDefinition

logger = logging.getLogger(__name__)


@runtime_checkable
class FlagStore(Protocol):
    """Protocol for flag storage backends."""

    @abc.abstractmethod
    async def get_flag(self, name: str) -> FlagDefinition | None:
        """Retrieve a flag definition by name."""
        ...

    @abc.abstractmethod
    async def set_flag(self, flag: FlagDefinition) -> None:
        """Store or update a flag definition."""
        ...

    @abc.abstractmethod
    async def delete_flag(self, name: str) -> bool:
        """Delete a flag definition. Returns True if deleted."""
        ...

    @abc.abstractmethod
    async def list_flags(self) -> list[FlagDefinition]:
        """List all stored flag definitions."""
        ...

    @abc.abstractmethod
    async def close(self) -> None:
        """Release any held resources."""
        ...


class MemoryFlagStore:
    """In-memory flag store using a dict."""

    def __init__(self) -> None:
        self._flags: dict[str, FlagDefinition] = {}

    async def get_flag(self, name: str) -> FlagDefinition | None:
        return self._flags.get(name)

    async def set_flag(self, flag: FlagDefinition) -> None:
        self._flags[flag.name] = flag

    async def delete_flag(self, name: str) -> bool:
        if name in self._flags:
            del self._flags[name]
            return True
        return False

    async def list_flags(self) -> list[FlagDefinition]:
        return list(self._flags.values())

    async def close(self) -> None:
        self._flags.clear()


class RedisFlagStore:
    """Redis-backed flag store using redis.asyncio."""

    def __init__(
        self,
        redis_url: str,
        key_prefix: str = "forge:featureflags:",
        max_connections: int = 10,
    ) -> None:
        self._url = redis_url
        self._prefix = key_prefix
        self._max_connections = max_connections
        self._client: Any = None
        self._pool: Any = None

    @property
    def url(self) -> str:
        return self._url

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    async def connect(self) -> None:
        import redis.asyncio as aioredis

        try:
            self._pool = aioredis.ConnectionPool.from_url(
                self._url,
                max_connections=self._max_connections,
            )
            self._client = aioredis.Redis(connection_pool=self._pool)
            await self._client.ping()
        except Exception as exc:
            logger.warning("Failed to connect to Redis at %s: %s", self._url, exc)
            self._client = None
            self._pool = None
            raise FlagStoreError(f"Failed to connect to Redis: {exc}") from exc

    async def close(self) -> None:
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

    def _flag_key(self, name: str) -> str:
        return f"{self._prefix}{name}"

    def _flags_set_key(self) -> str:
        return f"{self._prefix}__flags__"

    def _serialize(self, flag: FlagDefinition) -> str:
        return flag.model_dump_json()

    def _deserialize(self, raw: str) -> FlagDefinition:
        data = json.loads(raw)
        return FlagDefinition.model_validate(data)

    async def get_flag(self, name: str) -> FlagDefinition | None:
        if not self._client:
            raise FlagStoreError("Redis store is not connected.")
        try:
            raw = await self._client.get(self._flag_key(name))
            if raw is None:
                return None
            return self._deserialize(raw.decode("utf-8"))
        except Exception as exc:
            logger.warning("Redis GET failed for flag %s: %s", name, exc)
            raise FlagStoreError(f"Redis GET failed: {exc}") from exc

    async def set_flag(self, flag: FlagDefinition) -> None:
        if not self._client:
            raise FlagStoreError("Redis store is not connected.")
        try:
            serialized = self._serialize(flag)
            await self._client.set(self._flag_key(flag.name), serialized)
            await self._client.sadd(self._flags_set_key(), flag.name)
        except Exception as exc:
            logger.warning("Redis SET failed for flag %s: %s", flag.name, exc)
            raise FlagStoreError(f"Redis SET failed: {exc}") from exc

    async def delete_flag(self, name: str) -> bool:
        if not self._client:
            raise FlagStoreError("Redis store is not connected.")
        try:
            deleted = await self._client.delete(self._flag_key(name))
            await self._client.srem(self._flags_set_key(), name)
            return bool(deleted and deleted > 0)
        except Exception as exc:
            logger.warning("Redis DELETE failed for flag %s: %s", name, exc)
            raise FlagStoreError(f"Redis DELETE failed: {exc}") from exc

    async def list_flags(self) -> list[FlagDefinition]:
        if not self._client:
            raise FlagStoreError("Redis store is not connected.")
        try:
            flag_names = await self._client.smembers(self._flags_set_key())
            if not flag_names:
                return []
            flags: list[FlagDefinition] = []
            for name_bytes in flag_names:
                name = name_bytes.decode("utf-8")
                raw = await self._client.get(self._flag_key(name))
                if raw is not None:
                    flags.append(self._deserialize(raw.decode("utf-8")))
            return flags
        except Exception as exc:
            logger.warning("Redis LIST failed: %s", exc)
            raise FlagStoreError(f"Redis LIST failed: {exc}") from exc
