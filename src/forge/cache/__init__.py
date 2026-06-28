from __future__ import annotations

from forge.cache.decorators import cached
from forge.cache.exceptions import CacheBackendError, CacheError
from forge.cache.module import CacheModule


async def invalidate(key: str) -> bool:
    """Convenience helper to invalidate a cache key in the active cache module."""
    from forge.cache._state import get_cache_module

    cm = get_cache_module()
    if cm is not None:
        return await cm.delete(key)
    return False


__all__ = ["CacheBackendError", "CacheError", "CacheModule", "cached", "invalidate"]
