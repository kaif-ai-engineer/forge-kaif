from __future__ import annotations

import asyncio

import pytest

from forge import ConfigModule, ForgeRuntime, HealthModule


def test_health_check_response(benchmark: pytest.BenchmarkFixture) -> None:
    async def _setup() -> tuple[ForgeRuntime, HealthModule]:
        rt = ForgeRuntime()
        rt.register(ConfigModule())
        hm = HealthModule()
        rt.register(hm)
        await rt.init()
        return rt, hm

    rt, hm = asyncio.run(_setup())

    for i in range(10):

        async def _check() -> dict[str, str]:
            return {"status": "ok"}

        hm.register(f"bench_check_{i}", _check)

    async def _run_check() -> dict[str, dict[str, object]]:
        return await hm.check_all()

    benchmark(lambda: asyncio.run(_run_check()))

    mean = benchmark.stats["mean"]
    assert mean < 0.1, f"Health check took {mean * 1000:.1f}ms (threshold 100ms)"

    asyncio.run(rt.teardown())
