"""
Shared utility for running async health checks from sync methods.

Health checks are called synchronously by the framework, but some backends
(like Redis, cloud storage) require async I/O. This module provides a safe
bridge that avoids the pitfalls of spawning new event loops in threads.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import Any

logger = logging.getLogger(__name__)

_health_check_executor: concurrent.futures.ThreadPoolExecutor | None = None


def _get_executor() -> concurrent.futures.ThreadPoolExecutor:
    """Return a shared thread pool executor for health check bridges."""
    global _health_check_executor  # noqa: PLW0603
    if _health_check_executor is None:
        _health_check_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="forge-health",
        )
    return _health_check_executor


def run_async_health_check(coro: Any) -> Any:
    """
    Run an async coroutine from a synchronous health check method.

    If an event loop is already running, delegates to a background thread
    to avoid deadlocks. If no loop is running, uses ``asyncio.run``.

    Parameters
    ----------
    coro:
        The async coroutine to execute.

    Returns
    -------
    The result of the coroutine.

    Raises
    ------
    RuntimeError
        If the health check fails or times out.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    future: concurrent.futures.Future[Any] = concurrent.futures.Future()

    def _run_in_thread() -> None:
        try:
            result = asyncio.run(coro)
            future.set_result(result)
        except Exception as exc:
            future.set_exception(exc)

    executor = _get_executor()
    executor.submit(_run_in_thread)
    return future.result(timeout=10.0)
