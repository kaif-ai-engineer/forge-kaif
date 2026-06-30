"""
Shared fixtures and configuration for forge performance benchmarks.

Benchmarks measure runtime init time, config load time, log throughput,
retry overhead, health check response time, and AI module overhead.
"""

from __future__ import annotations

import pytest

from forge import ForgeRuntime
from forge.core.module import ForgeModule

# ---------------------------------------------------------------------------
# Lightweight benchmark modules (no I/O, no external deps)
# ---------------------------------------------------------------------------


class _BenchModuleA(ForgeModule):
    name = "bench_a"


class _BenchModuleB(ForgeModule):
    name = "bench_b"


class _BenchModuleC(ForgeModule):
    name = "bench_c"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bench_runtime() -> ForgeRuntime:
    """Return a fresh, uninitialized runtime for benchmarking."""
    return ForgeRuntime()


@pytest.fixture
def bench_runtime_with_modules() -> ForgeRuntime:
    """Return a runtime pre-loaded with lightweight modules."""
    rt = ForgeRuntime()
    rt.register(_BenchModuleA())
    rt.register(_BenchModuleB())
    rt.register(_BenchModuleC())
    return rt
