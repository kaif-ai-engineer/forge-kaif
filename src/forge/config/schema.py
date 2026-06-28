from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings


class LogConfig(BaseModel):
    level: str = Field(default="INFO", description="Log level")
    format: str = Field(default="dev", description="Output format: json or dev")
    levels: dict[str, str] = Field(default_factory=dict, description="Per-module overrides")


class CircuitBreakerConfig(BaseModel):
    failure_threshold: int = Field(default=5, ge=1)
    recovery_time: float = Field(default=60.0, ge=0)


class RetryConfig(BaseModel):
    default_attempts: int = Field(default=3, ge=1)
    default_backoff: str = Field(default="exponential", pattern=r"^(exponential|linear|constant)$")
    default_base_delay: float = Field(default=1.0, ge=0)
    default_max_delay: float = Field(default=60.0, ge=0)
    default_jitter: bool = Field(default=True)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)


class RedisCacheConfig(BaseModel):
    url: str | None = Field(default=None, description="Redis connection URL")
    key_prefix: str = Field(default="forge:")
    max_connections: int = Field(default=10, ge=1)


class CacheConfig(BaseModel):
    backend: str = Field(default="memory", pattern=r"^(memory|redis)$")
    default_ttl: int = Field(default=300, ge=0)
    memory_max_size: int = Field(default=1000, ge=1)
    redis: RedisCacheConfig = Field(default_factory=RedisCacheConfig)


class AIConfig(BaseModel):
    default_model: str = Field(default="gpt-4o")
    timeout: int = Field(default=30, ge=1)
    max_tokens: int = Field(default=4096, ge=1)
    fallback_models: list[str] = Field(default_factory=lambda: ["gpt-4o-mini"])
    structured_output_retries: int = Field(default=3, ge=0)
    openai_api_key: SecretStr | None = Field(default=None)
    anthropic_api_key: SecretStr | None = Field(default=None)


class HealthConfig(BaseModel):
    health_path: str = Field(default="/health")
    ready_path: str = Field(default="/ready")
    check_timeout: float = Field(default=5.0, ge=0)
    include_details: bool = Field(default=True)


class ConfigModuleConfig(BaseModel):
    extra_env_files: list[str] = Field(default_factory=list)


class ForgeConfig(BaseSettings):
    model_config = {
        "env_prefix": "FORGE_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    environment: str = Field(default="development", pattern=r"^(development|staging|production)$")
    debug: bool = Field(default=False)

    config: ConfigModuleConfig = Field(default_factory=ConfigModuleConfig)
    log: LogConfig = Field(default_factory=LogConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    health: HealthConfig = Field(default_factory=HealthConfig)
