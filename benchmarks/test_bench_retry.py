from __future__ import annotations

import asyncio

import pytest

from forge.retry.module import retry

_CALLS = 5_000


def test_retry_overhead(benchmark: pytest.BenchmarkFixture) -> None:
    @retry(attempts=2, backoff="constant", base_delay=0.0, jitter=False)
    async def _always_ok() -> int:
        return 42

    async def _run() -> None:
        for _ in range(_CALLS):
            await _always_ok()

    benchmark(lambda: asyncio.run(_run()))

    mean = benchmark.stats["mean"]
    per_call_ms = (mean / _CALLS) * 1000
    assert per_call_ms < 1, f"Retry overhead {per_call_ms:.3f}ms per call (threshold 1ms)"
