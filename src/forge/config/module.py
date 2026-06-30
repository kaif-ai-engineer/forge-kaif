from __future__ import annotations

import os
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from forge.config.loaders import load_dotenv, load_toml
from forge.config.schema import ForgeConfig
from forge.core.exceptions import ConfigurationError
from forge.core.module import ForgeModule, HealthResult

if TYPE_CHECKING:
    from collections.abc import Generator

    from forge.core.runtime import ForgeRuntime


_CONFIG_PATH = "forge.config.toml"
_DOTENV_FILES = [".env", ".env.local"]


def _unwrap_toml(raw: dict[str, Any]) -> dict[str, Any]:
    if "forge" in raw and isinstance(raw["forge"], dict):
        return raw["forge"]
    return raw


class ConfigModule(ForgeModule):
    name = "config"

    def __init__(self) -> None:
        super().__init__()
        self._config: ForgeConfig | None = None

    @property
    def config(self) -> ForgeConfig:
        if self._config is None:
            raise ConfigurationError(
                "Configuration has not been loaded yet. "
                "Ensure ``await runtime.init()`` has been called."
            )
        return self._config

    # ------------------------------------------------------------------
    # Override context manager
    # ------------------------------------------------------------------

    @contextmanager
    def override(self, values: dict[str, Any]) -> Generator[None, None, None]:
        if self._config is None:
            raise ConfigurationError("Cannot override config before initialisation.")

        snapshot = self._config.model_dump()
        try:
            for dotted_path, raw_value in values.items():
                _apply_override(self._config, dotted_path, raw_value)
            yield
        finally:
            self._config = ForgeConfig.model_validate(snapshot)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def require(self, keys: list[str]) -> None:
        missing: list[str] = []
        for key in keys:
            value = os.environ.get(key)
            if not value:
                missing.append(key)

        if missing:
            lines = ["Missing required environment variable(s):"]
            lines.extend(f"  - {key}" for key in missing)
            lines.append("")
            lines.append("To fix this, set them in your .env file:")
            lines.extend(f"    {key}=your-value-here" for key in missing)
            lines.append("")
            lines.append("Or export them in your shell:")
            lines.extend(f"    export {key}=your-value-here" for key in missing)
            raise ConfigurationError("\n".join(lines))

    # ------------------------------------------------------------------
    # ForgeModule
    # ------------------------------------------------------------------

    async def setup(self, _runtime: ForgeRuntime) -> None:
        self._config = self._build_config()

    async def teardown(self) -> None:
        self._config = None

    def health_check(self) -> HealthResult:
        if self._config is None:
            return HealthResult.error("Config not initialised")
        return HealthResult.ok()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_config(self) -> ForgeConfig:
        toml_raw = load_toml(_CONFIG_PATH)
        toml_data = _unwrap_toml(toml_raw)

        # Save actual env vars before dotenv manipulation.
        actual_env: dict[str, str] = {}
        for key in list(os.environ):
            actual_env[key] = os.environ[key]

        # Phase 1: load .env into environment to determine $ENVIRONMENT.
        for k, v in load_dotenv(".env").items():
            os.environ[k] = v

        # Determine environment: actual env var > TOML > .env > "development".
        env = actual_env.get("FORGE_ENVIRONMENT", "")
        if not env:
            env = str(toml_data.get("environment", ""))
        if not env:
            env = os.environ.get("FORGE_ENVIRONMENT", "development")

        # Phase 2: load remaining dotenv files in ascending priority.
        for dotenv_path in _DOTENV_FILES[1:]:  # .env.local
            for k, v in load_dotenv(dotenv_path).items():
                os.environ[k] = v

        for k, v in load_dotenv(f".env.{env}").items():
            os.environ[k] = v

        # Restore actual env vars so they always win over dotenv files.
        os.environ.update(actual_env)

        # Build config: TOML values as constructor args (lowest priority
        # among env sources), then .env files (now in os.environ), then
        # actual env vars on top.
        return ForgeConfig(**toml_data)


def _apply_override(config: ForgeConfig, dotted_path: str, value: Any) -> None:
    parts = dotted_path.split(".")
    target: Any = config
    for part in parts[:-1]:
        target = getattr(target, part)
    setattr(target, parts[-1], value)
