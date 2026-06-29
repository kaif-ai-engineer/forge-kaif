from __future__ import annotations

import abc
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CacheBackend(Protocol):
    """
    Protocol for cache storage backends.

    All methods are async. Implementations must handle serialization
    of arbitrary Python objects.
    """

    @abc.abstractmethod
    async def get(self, key: str) -> Any | None:
        """Return value for key, or None if not found / expired."""
        ...

    @abc.abstractmethod
    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store value. ttl=None means no expiry."""
        ...

    @abc.abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a key. Returns True if deleted, False otherwise."""
        ...

    @abc.abstractmethod
    async def has(self, key: str) -> bool:
        """Return True if key exists and has not expired."""
        ...

    @abc.abstractmethod
    async def clear(self) -> None:
        """Clear all keys in this cache."""
        ...

    @abc.abstractmethod
    async def close(self) -> None:
        """Clean up resources. Called during module teardown."""
        ...
