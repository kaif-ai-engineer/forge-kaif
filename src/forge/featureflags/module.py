from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, cast

from forge.core.module import ForgeModule, HealthResult
from forge.featureflags._state import set_featureflags_module
from forge.featureflags.evaluator import FlagEvaluator
from forge.featureflags.exceptions import FeatureFlagError
from forge.featureflags.models import EvaluationContext, EvaluationResult, FlagDefinition
from forge.featureflags.store import FlagStore, MemoryFlagStore

if TYPE_CHECKING:
    from forge.core.runtime import ForgeRuntime as Runtime


class FeatureFlagsModule(ForgeModule):
    """
    Manages feature flag definitions, storage, and evaluation.

    Supports boolean, percentage rollout, and user-segment based flag
    evaluation with in-memory and optional Redis backends.
    """

    name = "featureflags"
    dependencies: ClassVar[list[str]] = ["config"]

    def __init__(self) -> None:
        super().__init__()
        self._store: FlagStore | None = None
        self._evaluator: FlagEvaluator | None = None
        self._runtime: Runtime | None = None

    @property
    def store(self) -> FlagStore:
        if self._store is None:
            raise FeatureFlagError("Feature flag store is not initialized.")
        return self._store

    @property
    def evaluator(self) -> FlagEvaluator:
        if self._evaluator is None:
            raise FeatureFlagError("Feature flag evaluator is not initialized.")
        return self._evaluator

    async def setup(self, runtime: Runtime) -> None:
        """Initialize the feature flags module."""
        self._runtime = runtime
        set_featureflags_module(self)

        from forge.config.module import ConfigModule

        config_module = cast("ConfigModule", runtime.get(ConfigModule))
        config = getattr(config_module.config, "featureflags", None)

        backend_type = "memory"
        redis_url = None
        redis_key_prefix = "forge:featureflags:"
        redis_max_connections = 10
        flags_config: list[dict[str, Any]] | None = None

        if config is not None:
            backend_type = getattr(config, "backend", "memory")
            flags_config = getattr(config, "flags", None)
            redis_config = getattr(config, "redis", None)
            if redis_config is not None:
                redis_url = getattr(redis_config, "url", None)
                redis_key_prefix = getattr(redis_config, "key_prefix", "forge:featureflags:")
                redis_max_connections = getattr(redis_config, "max_connections", 10)

        if backend_type == "redis":
            from forge.featureflags.store import RedisFlagStore

            url = redis_url or "redis://localhost:6379/0"
            redis_store = RedisFlagStore(
                redis_url=url,
                key_prefix=redis_key_prefix,
                max_connections=redis_max_connections,
            )
            await redis_store.connect()
            self._store = redis_store
        else:
            self._store = MemoryFlagStore()

        self._evaluator = FlagEvaluator(self._store)

        # Pre-load flags from config if provided
        if flags_config:
            for flag_data in flags_config:
                flag = FlagDefinition.model_validate(flag_data)
                await self._store.set_flag(flag)

    async def teardown(self) -> None:
        """Teardown the feature flags module."""
        set_featureflags_module(None)
        if self._store:
            try:
                await self._store.close()
            except Exception as exc:
                import logging

                logging.getLogger(__name__).warning("Error closing flag store: %s", exc)
        self._store = None
        self._evaluator = None
        self._runtime = None

    async def evaluate(
        self,
        flag_name: str,
        context: EvaluationContext,
    ) -> EvaluationResult:
        """Evaluate a single flag for the given context."""
        return await self.evaluator.evaluate(flag_name, context)

    async def evaluate_bulk(
        self,
        flag_names: list[str],
        context: EvaluationContext,
    ) -> dict[str, EvaluationResult]:
        """Evaluate multiple flags for the given context."""
        return await self.evaluator.evaluate_bulk(flag_names, context)

    async def evaluate_all(
        self,
        context: EvaluationContext,
    ) -> dict[str, EvaluationResult]:
        """Evaluate all flags for the given context."""
        return await self.evaluator.evaluate_all(context)

    async def get_flag(self, name: str) -> FlagDefinition | None:
        """Get a flag definition by name."""
        return await self.store.get_flag(name)

    async def set_flag(self, flag: FlagDefinition) -> None:
        """Store or update a flag definition."""
        await self.store.set_flag(flag)

    async def delete_flag(self, name: str) -> bool:
        """Delete a flag definition by name."""
        return await self.store.delete_flag(name)

    async def list_flags(self) -> list[FlagDefinition]:
        """List all stored flag definitions."""
        return await self.store.list_flags()

    def _health_check_redis(self, store: Any) -> HealthResult:
        """Check health of Redis-backed flag store."""
        if not store.is_connected:
            return HealthResult.error("Redis flag store not connected")
        from forge.core.redis_health import check_redis_health

        return check_redis_health(store.url, label="Redis flag store")

    def health_check(self) -> HealthResult:
        """Check the health status of the feature flags backend."""
        if self._store is None:
            return HealthResult.error("Feature flag store not initialized")

        if isinstance(self._store, MemoryFlagStore):
            return HealthResult(HealthResult.OK, "Memory flag store active")

        from forge.featureflags.store import RedisFlagStore

        if isinstance(self._store, RedisFlagStore):
            return self._health_check_redis(self._store)

        return HealthResult.ok()
