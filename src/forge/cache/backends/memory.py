from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any


class MemoryBackend:
    """
    LRU cache with TTL support. Pure Python, no external dependencies.

    Implementation: OrderedDict as LRU queue.
    - get(): moves key to end (most recently used)
    - set(): adds to end, evicts from front if over capacity
    - TTL is checked on read (lazy expiration)
    """

    def __init__(self, max_size: int = 1000, default_ttl: int = 300) -> None:
        self._cache: OrderedDict[str, tuple[Any, float | None]] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl

    async def get(self, key: str) -> Any | None:
        if key not in self._cache:
            return None

        value, expires_at = self._cache[key]

        # Lazy TTL expiration
        if expires_at is not None and time.monotonic() > expires_at:
            del self._cache[key]
            return None

        # Move to end (LRU update)
        self._cache.move_to_end(key)
        return value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        effective_ttl = ttl if ttl is not None else self._default_ttl
        expires_at = time.monotonic() + effective_ttl if effective_ttl > 0 else None

        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (value, expires_at)

        # Evict LRU if over capacity
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)  # Remove from front (least recently used)

    async def delete(self, key: str) -> bool:
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    async def has(self, key: str) -> bool:
        return await self.get(key) is not None

    async def clear(self) -> None:
        self._cache.clear()

    async def close(self) -> None:
        pass
