"""Shared utilities for Redis health checks across forge modules."""

from __future__ import annotations

import logging

from forge.core.module import HealthResult

logger = logging.getLogger(__name__)


def check_redis_health(url: str, *, label: str = "Redis") -> HealthResult:
    """
    Perform a synchronous Redis ping health check.

    Parameters
    ----------
    url:
        The Redis connection URL to probe.
    label:
        Human-readable label for log messages and health result messages.

    Returns
    -------
    HealthResult
        OK if the ping succeeds, ERROR otherwise.
    """
    try:
        import redis

        client = redis.from_url(url, socket_timeout=1.0)
        if client.ping():
            return HealthResult(HealthResult.OK, f"{label} is healthy")
        return HealthResult.error(f"{label} ping failed")
    except ImportError:
        return HealthResult.error(f"{label} health check unavailable: redis package not installed")
    except Exception as exc:
        return HealthResult.error(f"{label} unhealthy: {exc}")
