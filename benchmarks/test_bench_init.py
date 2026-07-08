from __future__ import annotations

import asyncio

import pytest

from forge import ForgeRuntime
from forge.core.module import ForgeModule


class _BenchBenchA(ForgeModule):
    name = "bench_a"


class _BenchBenchB(ForgeModule):
    name = "bench_b"


class _BenchBenchC(ForgeModule):
    name = "bench_c"


class _BenchBenchD(ForgeModule):
    name = "bench_d"


class _BenchBenchE(ForgeModule):
    name = "bench_e"


_MODULES = 5


def test_runtime_init_time(benchmark: pytest.BenchmarkFixture) -> None:
    async def _init_and_teardown() -> None:
        rt = ForgeRuntime()
        rt.register(_BenchBenchA())
        rt.register(_BenchBenchB())
        rt.register(_BenchBenchC())
        rt.register(_BenchBenchD())
        rt.register(_BenchBenchE())
        await rt.init()
        await rt.teardown()

    benchmark(lambda: asyncio.run(_init_and_teardown()))
    mean = benchmark.stats["mean"]
    assert mean < 0.2, (
        f"Runtime init with {_MODULES} modules took {mean * 1000:.1f}ms (threshold 200ms)"
    )
