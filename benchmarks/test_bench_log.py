"""
Log throughput benchmark.

Measures the emit-side throughput of the LogModule's QueueHandler pipeline
(application-facing, non-blocking logging). The QueueListener is stopped during
measurement to avoid GIL contention with the formatting thread.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys

import pytest

from forge import ConfigModule, ForgeRuntime, LogModule

_LOG_COUNT = 100_000


def test_log_throughput(benchmark: pytest.BenchmarkFixture) -> None:
    orig_stderr_fd = os.dup(sys.stderr.fileno())
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull_fd, sys.stderr.fileno())
    os.close(devnull_fd)

    rt: ForgeRuntime | None = None
    lm: LogModule | None = None
    try:

        async def _setup() -> tuple[ForgeRuntime, logging.Logger, LogModule]:
            rt = ForgeRuntime()
            rt.register(ConfigModule())
            rt.register(LogModule())
            await rt.init()
            lm: LogModule = rt.get(LogModule)
            return rt, lm.get_logger("bench"), lm

        rt, logger, lm = asyncio.run(_setup())

        if lm._listener is not None:
            lm._listener.stop()

        def _log() -> None:
            for _ in range(_LOG_COUNT):
                logger.info("benchmark log message")

        benchmark.pedantic(_log, rounds=5, iterations=1, warmup_rounds=2)

        mean = benchmark.stats["mean"]
        throughput = _LOG_COUNT / mean
        assert throughput > 25_000, f"Log throughput {throughput:,.0f} logs/sec < 25,000"
    finally:
        if lm is not None and lm._listener is not None:
            with contextlib.suppress(AssertionError):
                lm._listener.start()
        if rt is not None:
            asyncio.run(rt.teardown())
        os.dup2(orig_stderr_fd, sys.stderr.fileno())
        os.close(orig_stderr_fd)
