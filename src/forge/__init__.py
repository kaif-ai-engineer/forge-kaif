"""
Forge framework — A modular runtime infrastructure library.
"""

from __future__ import annotations

from forge import cache, health, validation
from forge._version import __version__
from forge.ai.module import AIModule
from forge.cache.module import CacheModule
from forge.config.module import ConfigModule
from forge.config.schema import ForgeConfig
from forge.core.module import ForgeModule
from forge.core.runtime import ForgeRuntime
from forge.health.module import HealthModule
from forge.log.module import LogModule
from forge.retry.module import RetryModule
from forge.validation.module import ValidationModule

Runtime = ForgeRuntime

__all__ = [
    "AIModule",
    "CacheModule",
    "ConfigModule",
    "ForgeConfig",
    "ForgeModule",
    "ForgeRuntime",
    "HealthModule",
    "LogModule",
    "RetryModule",
    "Runtime",
    "ValidationModule",
    "__version__",
    "cache",
    "health",
    "validation",
]
