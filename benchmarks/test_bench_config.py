from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from forge import ConfigModule, ForgeRuntime


def test_config_load_time(benchmark: pytest.BenchmarkFixture) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "forge.config.toml"
        config_path.write_text("""\
[forge]
environment = "development"

[forge.log]
level = "INFO"
format = "json"

[forge.retry]
default_attempts = 5
""")

        old_cwd = os.getcwd()
        os.chdir(tmpdir)
        try:

            async def _load() -> None:
                rt = ForgeRuntime()
                rt.register(ConfigModule())
                await rt.init()
                await rt.teardown()

            benchmark(lambda: asyncio.run(_load()))
        finally:
            os.chdir(old_cwd)

    mean = benchmark.stats["mean"]
    assert mean < 0.05, f"Config load took {mean * 1000:.1f}ms (threshold 50ms)"
