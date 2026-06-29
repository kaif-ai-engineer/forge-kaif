from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response

# APIRouter created at import time (stateless)
health_router = APIRouter(tags=["health"])


@health_router.get("/health", summary="Liveness probe")
async def liveness(response: Response) -> dict[str, str]:
    """
    Kubernetes liveness probe.

    Returns 200 if process is alive. Returns 503 if not initialized.
    """
    from forge.health._state import get_health_module
    health_module = get_health_module()
    if health_module is None:
        response.status_code = 503
        return {"status": "unhealthy", "message": "Health module not initialized"}
    return {"status": "healthy"}


@health_router.get("/ready", summary="Readiness probe")
async def readiness(response: Response) -> dict[str, Any]:
    """
    Kubernetes readiness probe.

    Runs critical health checks. Returns 200 if all pass, 503 otherwise.
    """
    from forge.health._state import get_health_module
    health_module = get_health_module()
    if health_module is None:
        response.status_code = 503
        return {"status": "unhealthy", "message": "Health module not initialized"}

    checks = await health_module.check_all()
    is_ready = health_module.is_ready(checks)

    if not is_ready:
        response.status_code = 503

    status_str = "healthy" if is_ready else "unhealthy"
    include_details = health_module.include_details

    res: dict[str, Any] = {"status": status_str}
    if include_details:
        res["checks"] = checks

    return res
