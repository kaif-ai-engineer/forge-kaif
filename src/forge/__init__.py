"""
Forge framework — A modular runtime infrastructure library.
"""

from __future__ import annotations

from forge._version import __version__
from forge.ai.module import AIModule
from forge.config.module import ConfigModule
from forge.config.schema import ForgeConfig
from forge.core.module import ForgeModule
from forge.core.runtime import ForgeRuntime
from forge.log.module import LogModule
from forge.retry.module import RetryModule

Runtime = ForgeRuntime

__all__ = [
    "AIModule",
    "ConfigModule",
    "ForgeConfig",
    "ForgeModule",
    "ForgeRuntime",
    "LogModule",
    "RetryModule",
    "Runtime",
    "__version__",
]
