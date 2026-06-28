from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, ClassVar

from forge.ai.adapters.anthropic import AnthropicAdapter
from forge.ai.adapters.mock import MockAdapter
from forge.ai.adapters.openai import OpenAIAdapter
from forge.ai.router import ModelRouter
from forge.core.module import ForgeModule, HealthResult

if TYPE_CHECKING:
    from forge.ai.models import CompletionRequest, CompletionResponse

if TYPE_CHECKING:
    from forge.core.runtime import ForgeRuntime


class AIModule(ForgeModule):
    name = "ai"
    dependencies: ClassVar[list[str]] = ["config"]

    def __init__(self) -> None:
        self._router: ModelRouter | None = None
        self._config_ai: Any = None

    # ── Public API ─────────────────────────────────────────────────

    @property
    def router(self) -> ModelRouter:
        if self._router is None:
            raise RuntimeError("AIModule not initialised")
        return self._router

    async def complete(
        self,
        request: CompletionRequest,
        fallback_models: list[str] | None = None,
    ) -> CompletionResponse:
        return await self.router.complete(request, fallback_models)

    async def stream(
        self, request: CompletionRequest
    ) -> AsyncIterator[str]:
        async for chunk in self.router.stream(request):
            yield chunk

    # ── ForgeModule ────────────────────────────────────────────────

    async def setup(self, runtime: ForgeRuntime) -> None:
        from forge.config.module import ConfigModule

        config_module: ConfigModule = runtime.get(ConfigModule)  # type: ignore[assignment]
        self._config_ai = config_module.config.ai

        self._router = ModelRouter(max_tokens_limit=self._config_ai.max_tokens)

        # Register adapters
        openai_adapter = OpenAIAdapter(
            api_key=self._get_openai_key(),
            timeout=self._config_ai.timeout,
        )
        self._router.register("gpt-4o*", openai_adapter)
        self._router.register("gpt-4*", openai_adapter)
        self._router.register("gpt-3.5*", openai_adapter)

        anthropic_adapter = AnthropicAdapter(
            api_key=self._get_anthropic_key(),
            timeout=self._config_ai.timeout,
        )
        self._router.register("claude*", anthropic_adapter)

        mock_adapter = MockAdapter()
        self._router.register("*", mock_adapter)

        # Fallback chain (tried in order)
        for fb_model in self._config_ai.fallback_models:
            adapter_for_fallback = self._router.resolve(fb_model)
            if adapter_for_fallback is not None:
                self._router.register(fb_model, adapter_for_fallback, is_fallback=True)

    async def teardown(self) -> None:
        self._router = None
        self._config_ai = None

    def health_check(self) -> HealthResult:
        if self._router is None:
            return HealthResult.error("AI module not initialised")
        return HealthResult.ok()

    # ── Internal ───────────────────────────────────────────────────

    def _get_openai_key(self) -> str | None:
        if self._config_ai is None:
            return None
        val = self._config_ai.openai_api_key
        return val.get_secret_value() if val is not None else None

    def _get_anthropic_key(self) -> str | None:
        if self._config_ai is None:
            return None
        val = self._config_ai.anthropic_api_key
        return val.get_secret_value() if val is not None else None
