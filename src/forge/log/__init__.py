"""
Structured logging module — JSON and human-readable log output with context propagation.

Provides a module-aware logger factory, automatic trace ID propagation via
contextvars, and configurable output formats for development and production
environments.
"""

from __future__ import annotations

import logging
from typing import Any

from forge.log.context import LogContext, LogContextFilter
from forge.log.formatters import DevFormatter, JSONFormatter
from forge.log.module import LogModule
from forge.log.proxy import LoggerProxy


def get(name: str) -> LoggerProxy:
    """
    Get a module logger wrapped in LoggerProxy.

    Delegates to the active runtime's LogModule if initialized,
    otherwise returns a default LoggerProxy.
    """
    try:
        from forge.core.runtime import ForgeRuntime

        runtime = ForgeRuntime.get_active()
        log_module: LogModule = runtime.get(LogModule)  # type: ignore[assignment]
        return log_module.get(name)
    except Exception:
        # Before runtime init
        return LoggerProxy(logging.getLogger(name))


def context(**kwargs: Any) -> LogContext:
    """Context manager for binding key-value pairs to all log entries within the context."""
    return LogContext(**kwargs)


__all__ = [
    "DevFormatter",
    "JSONFormatter",
    "LogContext",
    "LogContextFilter",
    "LogModule",
    "LoggerProxy",
    "context",
    "get",
]
