from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from forge import ConfigModule, ForgeRuntime, HealthModule
from forge.health import HealthResult, check, health_router
from forge.health.router import liveness, readiness


@pytest.fixture
def app() -> FastAPI:
    """Create a FastAPI test application with the health router."""
    fastapi_app = FastAPI()
    fastapi_app.include_router(health_router)
    return fastapi_app


@pytest.mark.asyncio
async def test_health_not_initialized(app: FastAPI) -> None:
    """Liveness and readiness return 503 before runtime initialization."""
    # Ensure health module is not set (clean state)
    from forge.health._state import set_health_module

    set_health_module(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res_health = await ac.get("/health")
        assert res_health.status_code == 503
        assert res_health.json() == {
            "status": "unhealthy",
            "message": "Health module not initialized",
        }

        res_ready = await ac.get("/ready")
        assert res_ready.status_code == 503
        assert res_ready.json() == {
            "status": "unhealthy",
            "message": "Health module not initialized",
        }


@pytest.mark.asyncio
async def test_health_and_readiness_basic(app: FastAPI) -> None:
    """Standard /health and /ready behavior when runtime is healthy."""
    runtime = ForgeRuntime()
    runtime.register(ConfigModule())
    runtime.register(HealthModule())

    await runtime.init()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # 1. Liveness probe (/health)
            res_health = await ac.get("/health")
            assert res_health.status_code == 200
            assert res_health.json() == {"status": "healthy"}

            # 2. Readiness probe (/ready)
            res_ready = await ac.get("/ready")
            assert res_ready.status_code == 200

            data = res_ready.json()
            assert data["status"] == "healthy"
            assert "checks" in data
            assert "runtime" in data["checks"]
            assert data["checks"]["runtime"]["status"] == "ok"
            assert isinstance(data["checks"]["runtime"]["latency_ms"], float)
    finally:
        await runtime.teardown()


@pytest.mark.asyncio
async def test_custom_check_decorator(app: FastAPI) -> None:
    """A custom check registered via decorator is run during readiness."""

    # Register decorator check
    @check("custom_decorated", critical=True)
    async def dummy_check() -> HealthResult:
        return HealthResult.ok("All good here")

    runtime = ForgeRuntime()
    runtime.register(ConfigModule())
    runtime.register(HealthModule())

    await runtime.init()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/ready")
            assert res.status_code == 200
            data = res.json()
            assert "custom_decorated" in data["checks"]
            assert data["checks"]["custom_decorated"]["status"] == "ok"
            assert data["checks"]["custom_decorated"]["message"] == "All good here"
    finally:
        await runtime.teardown()


@pytest.mark.asyncio
async def test_critical_check_failure(app: FastAPI) -> None:
    """A failing critical check returns HTTP 503 and makes service unhealthy."""
    runtime = ForgeRuntime()
    runtime.register(ConfigModule())
    hm = HealthModule()
    runtime.register(hm)

    # Register critical check that fails
    async def fail_check() -> HealthResult:
        return HealthResult.error("Database connection refused")

    hm.register("database", fail_check, critical=True)

    await runtime.init()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/ready")
            assert res.status_code == 503
            data = res.json()
            assert data["status"] == "unhealthy"
            assert data["checks"]["database"]["status"] == "error"
            assert data["checks"]["database"]["message"] == "Database connection refused"
    finally:
        await runtime.teardown()


@pytest.mark.asyncio
async def test_non_critical_check_failure(app: FastAPI) -> None:
    """A failing non-critical check does not cause 503 and returns HTTP 200."""
    runtime = ForgeRuntime()
    runtime.register(ConfigModule())
    hm = HealthModule()
    runtime.register(hm)

    # Register non-critical check that fails
    async def fail_check() -> HealthResult:
        return HealthResult.error("Cache capacity full")

    hm.register("cache", fail_check, critical=False)

    await runtime.init()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/ready")
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "healthy"
            assert data["checks"]["cache"]["status"] == "error"
    finally:
        await runtime.teardown()


@pytest.mark.asyncio
async def test_check_timeout(app: FastAPI) -> None:
    """A check that exceeds timeout is cancelled and returns error status."""
    runtime = ForgeRuntime()
    config_mod = ConfigModule()
    runtime.register(config_mod)
    hm = HealthModule()
    runtime.register(hm)

    async def slow_check() -> HealthResult:
        await asyncio.sleep(1.0)
        return HealthResult.ok()

    hm.register("slow_dep", slow_check, critical=True)

    # Override timeout to be very low
    await runtime.init()
    try:
        with config_mod.override({"health": {"check_timeout": 0.02}}):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.get("/ready")
                assert res.status_code == 503
                data = res.json()
                assert data["status"] == "unhealthy"
                assert data["checks"]["slow_dep"]["status"] == "error"
                assert "timed out" in data["checks"]["slow_dep"]["message"].lower()
    finally:
        await runtime.teardown()


@pytest.mark.asyncio
async def test_check_exception(app: FastAPI) -> None:
    """An exception raised inside a check is caught and returned as an error."""
    runtime = ForgeRuntime()
    runtime.register(ConfigModule())
    hm = HealthModule()
    runtime.register(hm)

    async def crash_check() -> HealthResult:
        raise ValueError("Unexpected database crash")

    hm.register("crashing_dep", crash_check, critical=True)

    await runtime.init()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/ready")
            assert res.status_code == 503
            data = res.json()
            assert data["status"] == "unhealthy"
            assert data["checks"]["crashing_dep"]["status"] == "error"
            assert "Unexpected database crash" in data["checks"]["crashing_dep"]["message"]
    finally:
        await runtime.teardown()


@pytest.mark.asyncio
async def test_include_details_false(app: FastAPI) -> None:
    """When include_details config flag is False, checks are omitted from /ready response."""
    runtime = ForgeRuntime()
    config_mod = ConfigModule()
    runtime.register(config_mod)
    runtime.register(HealthModule())

    await runtime.init()

    try:
        with config_mod.override({"health": {"include_details": False}}):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.get("/ready")
                assert res.status_code == 200
                data = res.json()
                assert data == {"status": "healthy"}
    finally:
        await runtime.teardown()


@pytest.mark.asyncio
async def test_configurable_paths() -> None:
    """Health paths can be configured dynamically via configuration."""
    runtime = ForgeRuntime()
    config_mod = ConfigModule()
    runtime.register(config_mod)
    runtime.register(HealthModule())

    await runtime.init()

    try:
        with config_mod.override(
            {"health": {"health_path": "/my-liveness", "ready_path": "/my-readiness"}}
        ):
            from forge.health.module import HealthModule as HMClass

            health_module = runtime.get(HMClass)

            # Update paths on health_router before including it in the app
            for route in health_router.routes:
                endpoint = getattr(route, "endpoint", None)
                if endpoint == liveness:
                    route.path = health_module.health_path
                elif endpoint == readiness:
                    route.path = health_module.ready_path

            custom_app = FastAPI()
            custom_app.include_router(health_router)

            async with AsyncClient(
                transport=ASGITransport(app=custom_app), base_url="http://test"
            ) as ac:
                res_liveness = await ac.get("/my-liveness")
                assert res_liveness.status_code == 200
                assert res_liveness.json() == {"status": "healthy"}

                res_readiness = await ac.get("/my-readiness")
                assert res_readiness.status_code == 200
                assert res_readiness.json()["status"] == "healthy"
    finally:
        # Reset route paths back to defaults for subsequent tests
        for route in health_router.routes:
            endpoint = getattr(route, "endpoint", None)
            if endpoint == liveness:
                route.path = "/health"
            elif endpoint == readiness:
                route.path = "/ready"
        await runtime.teardown()


@pytest.mark.asyncio
async def test_module_health_checks_integration(app: FastAPI) -> None:
    """Verify other modules' health checks are automatically collected and run."""
    from forge.core.module import ForgeModule
    from forge.core.module import HealthResult as CoreHealthResult

    class DummyModule(ForgeModule):
        name = "dummy_module"

        def health_check(self) -> CoreHealthResult:
            return CoreHealthResult.degraded("Impaired database connections")

    runtime = ForgeRuntime()
    runtime.register(ConfigModule())
    runtime.register(HealthModule())
    runtime.register(DummyModule())

    await runtime.init()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/ready")
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "healthy"
            assert "dummy_module" in data["checks"]
            assert data["checks"]["dummy_module"]["status"] == "degraded"
            assert data["checks"]["dummy_module"]["message"] == "Impaired database connections"
    finally:
        await runtime.teardown()
