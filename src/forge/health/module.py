from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar, cast

from forge.core.module import ForgeModule
from forge.health._state import set_health_module
from forge.health.checks import (
    HealthCheckFn,
    HealthRegistry,
    HealthResult,
    _decorator_registered_checks,
)

if TYPE_CHECKING:
    from forge.core.runtime import ForgeRuntime as Runtime


class HealthModule(ForgeModule):
    """
    Manages health and readiness checks for the forge runtime.

    Integrates with K8s probes and coordinates module-level checks.
    """

    name = "health"
    dependencies: ClassVar[list[str]] = ["config"]

    def __init__(self) -> None:
        super().__init__()
        self._registry = HealthRegistry()
        self._runtime: Runtime | None = None

    @property
    def registry(self) -> HealthRegistry:
        """Get the health registry instance."""
        return self._registry

    @property
    def _config(self) -> Any:
        """Dynamically fetch the health configuration section."""
        if self._runtime:
            from forge.config.module import ConfigModule

            try:
                config_module = cast("ConfigModule", self._runtime.get(ConfigModule))
                return getattr(config_module.config, "health", None)
            except Exception:
                return None
        return None

    @property
    def include_details(self) -> bool:
        """Dynamically determine if check details should be included in responses."""
        config = self._config
        if config is None:
            return True
        if isinstance(config, dict):
            return bool(config.get("include_details", True))
        return bool(getattr(config, "include_details", True))

    @property
    def health_path(self) -> str:
        """Get the configured liveness check path."""
        config = self._config
        if config is None:
            return "/health"
        if isinstance(config, dict):
            return str(config.get("health_path", "/health"))
        return str(getattr(config, "health_path", "/health"))

    @property
    def ready_path(self) -> str:
        """Get the configured readiness check path."""
        config = self._config
        if config is None:
            return "/ready"
        if isinstance(config, dict):
            return str(config.get("ready_path", "/ready"))
        return str(getattr(config, "ready_path", "/ready"))

    @property
    def check_timeout(self) -> float:
        """Get the health check execution timeout."""
        config = self._config
        if config is None:
            return 5.0
        if isinstance(config, dict):
            return float(config.get("check_timeout", 5.0))
        return float(getattr(config, "check_timeout", 5.0))

    async def setup(self, runtime: Runtime) -> None:
        """Initialize the health module and configure settings."""
        self._runtime = runtime
        set_health_module(self)

        # Register default critical "runtime" check
        async def check_runtime() -> HealthResult:
            if runtime.is_initialized:
                return HealthResult.ok()
            return HealthResult.error("Runtime not initialized")

        self._registry.register("runtime", check_runtime, critical=True)

        # Register any pending decorator-registered checks
        for name, fn, critical in _decorator_registered_checks:
            self._registry.register(name, fn, critical=critical)
        _decorator_registered_checks.clear()

        # Configurable paths: update router paths dynamically
        from forge.health.router import health_router, liveness, readiness

        health_path = self.health_path
        ready_path = self.ready_path

        from fastapi.routing import APIRoute

        for route in health_router.routes:
            endpoint = getattr(route, "endpoint", None)
            if isinstance(route, APIRoute):
                if endpoint == liveness:
                    route.path = health_path
                elif endpoint == readiness:
                    route.path = ready_path

    async def teardown(self) -> None:
        """Teardown the health module."""
        set_health_module(None)
        self._runtime = None

    def register(self, name: str, check: HealthCheckFn, critical: bool = False) -> None:
        """Register a custom health check."""
        self._registry.register(name, check, critical=critical)

    def check(self, name: str, critical: bool = False) -> Callable[[HealthCheckFn], HealthCheckFn]:
        """Decorator to register a custom health check function."""

        def decorator(fn: HealthCheckFn) -> HealthCheckFn:
            self._registry.register(name, fn, critical=critical)
            return fn

        return decorator

    async def check_all(self) -> dict[str, dict[str, Any]]:
        """
        Run all registered checks and return results.

        Returns dict of check_name -> {status, message, latency_ms}
        """
        timeout = self.check_timeout

        # 1. Run custom registered checks
        custom_results = await self._registry.run_all(timeout=timeout)

        results: dict[str, dict[str, Any]] = {}
        for name, res in custom_results.items():
            results[name] = {
                "status": res.status,
                "message": res.message,
                "latency_ms": res.latency_ms,
            }

        # 2. Collect module health checks (synchronous)
        if self._runtime:
            import time

            for module in self._runtime._container.initialization_order():
                if module.name == self.name:
                    continue
                start = time.monotonic()
                try:
                    core_res = module.health_check()
                    latency_ms = (time.monotonic() - start) * 1000.0
                    status: str = getattr(core_res, "status", "ok")
                    if hasattr(status, "value"):
                        status = status.value

                    message: str | None = None
                    if status not in ("ok", "degraded", "error"):
                        status = "error"
                        message = f"Invalid health status returned: {status}"
                    else:
                        message = getattr(core_res, "message", None)
                except Exception as exc:
                    latency_ms = (time.monotonic() - start) * 1000.0
                    status = "error"
                    message = f"Check raised: {exc}"

                results[module.name] = {
                    "status": status,
                    "message": message,
                    "latency_ms": round(latency_ms, 2),
                }

        return results

    def is_ready(self, check_results: dict[str, dict[str, Any]]) -> bool:
        """
        Determine overall readiness.

        Returns False if any critical check fails (status is error).
        """
        # Check custom registry checks
        for name, (_, critical) in self._registry._checks.items():
            if critical:
                res = check_results.get(name)
                if res and res.get("status") == "error":
                    return False

        # Check module checks (considered critical if error status returned)
        if self._runtime:
            for module in self._runtime._container.initialization_order():
                if module.name == self.name:
                    continue
                res = check_results.get(module.name)
                if res and res.get("status") == "error":
                    return False

        return True
