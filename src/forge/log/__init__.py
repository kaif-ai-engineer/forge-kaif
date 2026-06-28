"""
Structured logging module — JSON and human-readable log output with context propagation.

Provides a module-aware logger factory, automatic trace ID propagation via
contextvars, and configurable output formats for development and production
environments.
"""

from forge.log.context import LogContext, LogContextFilter
from forge.log.formatters import DevFormatter, JSONFormatter
from forge.log.module import LogModule

__all__ = [
    "DevFormatter",
    "JSONFormatter",
    "LogContext",
    "LogContextFilter",
    "LogModule",
]
