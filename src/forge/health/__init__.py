"""
Health check module — standardized /health and /ready endpoints.

Provides a health check registry, built-in checks for module dependencies,
and FastAPI routers for /health (liveness) and /ready (readiness) endpoints
compatible with Kubernetes probes.
"""
