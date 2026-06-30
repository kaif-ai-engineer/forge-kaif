"""
Shared test fixtures for all forge module tests.

Provides runtime fixtures, mock modules, and configuration helpers
for writing unit and integration tests.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any, ClassVar, Self

import pytest

from forge import ForgeModule, ForgeRuntime
from forge.config.schema import ForgeConfig

# ---------------------------------------------------------------------------
# Mock modules for dependency injection tests
# ---------------------------------------------------------------------------


class MockModuleA(ForgeModule):
    name = "mock_module_a"
    setup_called = False
    teardown_called = False

    async def setup(self, runtime: Any) -> None:
        self.setup_called = True

    async def teardown(self) -> None:
        self.teardown_called = True


class MockModuleB(ForgeModule):
    name = "mock_module_b"
    dependencies: ClassVar[list[str]] = ["mock_module_a"]


class MockModuleC(ForgeModule):
    name = "mock_module_c"
    dependencies: ClassVar[list[str]] = ["mock_module_b"]


# ---------------------------------------------------------------------------
# Runtime fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def runtime() -> AsyncIterator[ForgeRuntime]:
    """Provide a fresh ForgeRuntime that is torn down after the test."""
    rt = ForgeRuntime()
    yield rt
    if rt.is_initialized:
        await rt.teardown()


@pytest.fixture
async def initialized_runtime() -> AsyncIterator[ForgeRuntime]:
    """Provide a fully initialized ForgeRuntime with default modules."""
    rt = ForgeRuntime()
    rt.register(MockModuleA())
    rt.register(MockModuleB())
    rt.register(MockModuleC())
    await rt.init()
    yield rt
    await rt.teardown()


@pytest.fixture
async def config_runtime() -> AsyncIterator[ForgeRuntime]:
    """Provide a runtime with ConfigModule registered and initialized."""
    from forge.config.module import ConfigModule

    rt = ForgeRuntime()
    rt.register(ConfigModule())
    await rt.init()
    yield rt
    await rt.teardown()


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def env_vars() -> Any:
    """Context manager for temporarily setting environment variables."""

    class EnvGuard:
        def __init__(self) -> None:
            self._original: dict[str, str | None] = {}
            self._updates: dict[str, str] = {}

        def set(self, key: str, value: str) -> Self:
            self._updates[key] = value
            return self

        def __enter__(self) -> Self:
            for key, value in self._updates.items():
                self._original[key] = os.environ.get(key)
                os.environ[key] = value
            return self

        def __exit__(self, *args: object) -> None:
            for key, original in self._original.items():
                if original is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = original

    return EnvGuard


# ---------------------------------------------------------------------------
# Common data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_config() -> ForgeConfig:
    """Return a default ForgeConfig instance."""
    return ForgeConfig()
