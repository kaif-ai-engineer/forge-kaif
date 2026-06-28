"""
Health check module — standardized /health and /ready endpoints.

Provides a health check registry, built-in checks for module dependencies,
and FastAPI routers for /health (liveness) and /ready (readiness) endpoints
compatible with Kubernetes probes.
"""

from __future__ import annotations

from forge.health.checks import HealthRegistry, HealthResult, check
from forge.health.module import HealthModule
from forge.health.router import health_router

__all__ = [
    "HealthModule",
    "HealthRegistry",
    "HealthResult",
    "check",
    "health_router",
]
