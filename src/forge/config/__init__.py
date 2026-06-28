"""
Config module — layered configuration with pydantic-settings and TOML support.

Provides the ForgeConfig model with automatic environment-variable binding
via pydantic-settings, the ConfigModule lifecycle wrapper, and utilities for
loading TOML files, dotenv files, and deep merging.
"""

from forge.config.loaders import deep_merge, load_dotenv, load_toml, merge_config
from forge.config.module import ConfigModule
from forge.config.schema import (
    AIConfig,
    CacheConfig,
    CircuitBreakerConfig,
    ConfigModuleConfig,
    ForgeConfig,
    HealthConfig,
    LogConfig,
    RedisCacheConfig,
    RetryConfig,
)
from forge.config.secrets import (
    field_is_sensitive,
    is_secret,
    mask_value,
    str_from_secret,
)

__all__ = [
    "AIConfig",
    "CacheConfig",
    "CircuitBreakerConfig",
    "ConfigModule",
    "ConfigModuleConfig",
    "ForgeConfig",
    "HealthConfig",
    "LogConfig",
    "RedisCacheConfig",
    "RetryConfig",
    "deep_merge",
    "field_is_sensitive",
    "is_secret",
    "load_dotenv",
    "load_toml",
    "mask_value",
    "merge_config",
    "str_from_secret",
]
