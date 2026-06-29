from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from forge.cache.module import CacheModule

_active_cache_module: CacheModule | None = None


def get_cache_module() -> CacheModule | None:
    """Get the active cache module instance."""
    return _active_cache_module


def set_cache_module(module: CacheModule | None) -> None:
    """Set the active cache module instance."""
    global _active_cache_module  # noqa: PLW0603
    _active_cache_module = module
