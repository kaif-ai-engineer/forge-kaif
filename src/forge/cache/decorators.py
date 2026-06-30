from __future__ import annotations

import functools
import hashlib
import inspect
import json
from collections.abc import Callable
from typing import Any, TypeVar, cast

from forge.cache._state import get_cache_module
from forge.cache.backends.base import CacheBackend

F = TypeVar("F", bound=Callable[..., Any])


def cached(
    ttl: int | None = None,
    key: str | None = None,
    namespace: str | None = None,
    backend: CacheBackend | None = None,
) -> Callable[[F], F]:
    """
    Decorator for caching async function results.

    Args:
        ttl: Time-to-live in seconds. Defaults to cache module default_ttl.
        key: Cache key template. Supports {arg_name} interpolation from function args.
        namespace: Optional namespace prefix for the cache key.
        backend: Optional custom backend to use instead of the active module.
    """

    def decorator(func: F) -> F:
        if not inspect.iscoroutinefunction(func):
            raise TypeError(
                f"@cached requires an async function. {func.__qualname__} is synchronous."
            )

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # 1. Resolve cache client/backend
            b = backend
            cm = None
            if b is None:
                cm = get_cache_module()

            # 2. If no cache available, call the function transparently
            if b is None and cm is None:
                return await func(*args, **kwargs)

            # 3. Resolve key
            cache_key = _resolve_key(func, key, namespace, args, kwargs)

            # 4. Check cache
            if cm is not None:
                cached_value = await cm.get(cache_key)
            else:
                assert b is not None  # noqa: S101
                cached_value = await b.get(cache_key)

            if cached_value is not None:
                return cached_value

            # 5. Call function and cache result
            result = await func(*args, **kwargs)

            if cm is not None:
                await cm.set(cache_key, result, ttl=ttl)
            else:
                assert b is not None  # noqa: S101
                await b.set(cache_key, result, ttl=ttl)

            return result

        # Attach invalidation helper to the wrapped function
        async def invalidate(*args: Any, **kwargs: Any) -> bool:
            b = backend
            cm = None
            if b is None:
                cm = get_cache_module()

            if b is None and cm is None:
                return False

            cache_key = _resolve_key(func, key, namespace, args, kwargs)

            if cm is not None:
                return await cm.delete(cache_key)
            assert b is not None  # noqa: S101
            return await b.delete(cache_key)

        setattr(wrapper, "invalidate", invalidate)  # noqa: B010
        return cast("F", wrapper)

    return decorator


def _resolve_key(
    func: Callable[..., Any],
    key_template: str | None,
    namespace: str | None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> str:
    if key_template is not None:
        # Bind args to parameter names for template substitution
        sig = inspect.signature(func)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        formatted = key_template.format(**bound.arguments)
        if namespace:
            return f"{namespace}:{formatted}"
        return formatted

    # Auto-generate key from function identity + args hash
    try:
        args_hash = hashlib.sha256(
            json.dumps([args, kwargs], default=str, sort_keys=True).encode()
        ).hexdigest()[:16]
    except (TypeError, ValueError):
        args_hash = hashlib.sha256(str(args).encode()).hexdigest()[:16]

    ns = namespace or "forge:cache"
    return f"{ns}:{func.__module__}.{func.__qualname__}:{args_hash}"
