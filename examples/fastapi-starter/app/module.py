from __future__ import annotations

from typing import ClassVar

from forge import ConfigModule, ForgeModule, ForgeRuntime, log
from forge.core.module import HealthResult


class AppModule(ForgeModule):
    name = "app"
    dependencies: ClassVar[list[str]] = ["config", "cache"]

    async def setup(self, runtime: ForgeRuntime) -> None:
        self.logger = log.get("app")
        config = runtime.get(ConfigModule).config
        self.logger.info("AppModule initialized", environment=config.environment)

    async def teardown(self) -> None:
        self.logger.info("AppModule torn down")

    def health_check(self) -> HealthResult:
        return HealthResult.ok()
