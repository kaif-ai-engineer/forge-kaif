from __future__ import annotations

import asyncio

import pytest

from forge import AIModule, ConfigModule, ForgeRuntime
from forge.ai.models import CompletionRequest, Message
from forge.retry.module import RetryModule


def test_ai_overhead(benchmark: pytest.BenchmarkFixture) -> None:
    async def _setup() -> tuple[ForgeRuntime, AIModule]:
        rt = ForgeRuntime()
        rt.register(ConfigModule())
        rt.register(RetryModule())
        rt.register(AIModule())
        await rt.init()
        am: AIModule = rt.get(AIModule)
        return rt, am

    rt, am = asyncio.run(_setup())

    request = CompletionRequest(
        model="mock",
        messages=[Message(role="user", content="hello")],
        max_tokens=10,
    )

    async def _complete() -> object:
        return await am.complete(request)

    benchmark(lambda: asyncio.run(_complete()))

    mean = benchmark.stats["mean"]
    assert mean < 0.005, f"AI module overhead {mean * 1000:.1f}ms (threshold 5ms)"

    asyncio.run(rt.teardown())
