"""
Forge framework — A modular runtime infrastructure library.
"""

from __future__ import annotations

from forge import cache, crud, events, featureflags, health, jobs, storage, validation
from forge._version import __version__
from forge.ai.module import AIModule
from forge.cache.module import CacheModule
from forge.config.module import ConfigModule
from forge.config.schema import ForgeConfig
from forge.core.module import ForgeModule
from forge.core.runtime import ForgeRuntime
from forge.crud.module import CrudModule
from forge.events.module import EventsModule
from forge.featureflags.module import FeatureFlagsModule
from forge.health.module import HealthModule
from forge.jobs.module import JobsModule
from forge.log.module import LogModule
from forge.retry.module import RetryModule
from forge.storage.module import StorageModule
from forge.validation.module import ValidationModule

Runtime = ForgeRuntime

__all__ = [
    "AIModule",
    "CacheModule",
    "ConfigModule",
    "CrudModule",
    "EventsModule",
    "FeatureFlagsModule",
    "ForgeConfig",
    "ForgeModule",
    "ForgeRuntime",
    "HealthModule",
    "JobsModule",
    "LogModule",
    "RetryModule",
    "Runtime",
    "StorageModule",
    "ValidationModule",
    "__version__",
    "cache",
    "crud",
    "events",
    "featureflags",
    "health",
    "jobs",
    "storage",
    "validation",
]
