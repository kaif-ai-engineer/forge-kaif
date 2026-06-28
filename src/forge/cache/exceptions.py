from __future__ import annotations

from forge.core.exceptions import ForgeError


class CacheError(ForgeError):
    """Base exception for all cache-related errors."""


class CacheBackendError(CacheError):
    """Raised when a cache backend operation fails or is unavailable."""
