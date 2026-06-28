from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, cast


@dataclass
class HealthResult:
    """Result of a single health check."""

    status: Literal["ok", "degraded", "error"]
    message: str | None = None
    latency_ms: float = 0.0

    @classmethod
    def ok(cls, message: str | None = None) -> HealthResult:
        """Create a successful health check result."""
        return cls(status="ok", message=message)

    @classmethod
    def degraded(cls, message: str) -> HealthResult:
        """Create a degraded health check result."""
        return cls(status="degraded", message=message)

    @classmethod
    def error(cls, message: str) -> HealthResult:
        """Create a failing health check result."""
        return cls(status="error", message=message)


HealthCheckFn = Callable[[], Awaitable[Any]]


class HealthRegistry:
    """Registry managing custom registered health check functions."""

    def __init__(self) -> None:
        self._checks: dict[str, tuple[HealthCheckFn, bool]] = {}

    def register(self, name: str, check_fn: HealthCheckFn, critical: bool = False) -> None:  # noqa: FBT001, FBT002
        """Register a health check function."""
        self._checks[name] = (check_fn, critical)

    def unregister(self, name: str) -> None:
        """Unregister a health check function by name."""
        self._checks.pop(name, None)

    async def _run_single(self, name: str, check_fn: HealthCheckFn, timeout: float) -> HealthResult:  # noqa: ASYNC109
        """Run a single check function, enforcing a timeout and catching errors."""
        start_time = time.monotonic()
        try:
            # Run the check function and enforce timeout
            res = await asyncio.wait_for(check_fn(), timeout=timeout)
            latency_ms = (time.monotonic() - start_time) * 1000.0

            # Extract status and message from result (supports core or local HealthResult)
            status: Literal["ok", "degraded", "error"] = "ok"
            message: str | None = None

            if res is not None:
                raw_status = getattr(res, "status", "ok")
                if hasattr(raw_status, "value"):
                    raw_status = raw_status.value
                if raw_status in ("ok", "degraded", "error"):
                    status = cast("Literal['ok', 'degraded', 'error']", raw_status)
                else:
                    status = "error"
                    message = f"Invalid health status returned: {raw_status}"

                message = getattr(res, "message", message)

            return HealthResult(
                status=status,
                message=message,
                latency_ms=round(latency_ms, 2)
            )
        except TimeoutError:
            latency_ms = (time.monotonic() - start_time) * 1000.0
            return HealthResult(
                status="error",
                message=f"Check timed out after {timeout}s",
                latency_ms=round(latency_ms, 2)
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - start_time) * 1000.0
            return HealthResult(
                status="error",
                message=str(exc),
                latency_ms=round(latency_ms, 2)
            )

    async def run_all(self, timeout: float = 5.0) -> dict[str, HealthResult]:  # noqa: ASYNC109
        """Run all registered checks concurrently."""
        if not self._checks:
            return {}

        names = list(self._checks.keys())
        tasks = [self._run_single(name, fn, timeout) for name, (fn, _) in self._checks.items()]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        dict_results: dict[str, HealthResult] = {}
        for name, res in zip(names, results, strict=True):
            if isinstance(res, HealthResult):
                dict_results[name] = res
            else:
                dict_results[name] = HealthResult(
                    status="error",
                    message=str(res)
                )
        return dict_results

    async def run_critical(self, timeout: float = 5.0) -> dict[str, HealthResult]:  # noqa: ASYNC109
        """Run only critical registered checks concurrently."""
        critical_checks = {name: (fn, crit) for name, (fn, crit) in self._checks.items() if crit}
        if not critical_checks:
            return {}

        names = list(critical_checks.keys())
        tasks = [self._run_single(name, fn, timeout) for name, (fn, _) in critical_checks.items()]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        dict_results: dict[str, HealthResult] = {}
        for name, res in zip(names, results, strict=True):
            if isinstance(res, HealthResult):
                dict_results[name] = res
            else:
                dict_results[name] = HealthResult(
                    status="error",
                    message=str(res)
                )
        return dict_results


# Temporary store for checks registered via decorator before setup is called
_decorator_registered_checks: list[tuple[str, HealthCheckFn, bool]] = []


def check(name: str, critical: bool = False) -> Callable[[HealthCheckFn], HealthCheckFn]:  # noqa: FBT001, FBT002
    """Decorator to register a custom health check."""
    def decorator(fn: HealthCheckFn) -> HealthCheckFn:
        from forge.health._state import get_health_module
        hm = get_health_module()
        if hm is not None:
            hm.registry.register(name, fn, critical=critical)
        else:
            _decorator_registered_checks.append((name, fn, critical))
        return fn
    return decorator
