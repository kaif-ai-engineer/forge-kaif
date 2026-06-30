from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel

from forge.ai.adapters.anthropic import AnthropicAdapter
from forge.ai.adapters.gemini import GeminiAdapter
from forge.ai.adapters.mock import MockAdapter
from forge.ai.adapters.ollama import OllamaAdapter
from forge.ai.adapters.openai import OpenAIAdapter
from forge.ai.router import ModelRouter
from forge.core.module import ForgeModule, HealthResult
from forge.retry.module import RetryModule

if TYPE_CHECKING:
    from forge.ai.models import CompletionRequest, CompletionResponse, Message, StreamChunk
    from forge.core.runtime import ForgeRuntime


class AIModule(ForgeModule):
    name = "ai"
    dependencies: ClassVar[list[str]] = ["config", "retry"]

    def __init__(self) -> None:
        super().__init__()
        self._router: ModelRouter | None = None
        self._config_ai: Any = None

        # Metrics
        self._request_count = 0
        self._latency_ms_history: list[float] = []
        self._input_tokens = 0
        self._output_tokens = 0
        self._total_cost = 0.0

    # ── Public API ─────────────────────────────────────────────────

    @property
    def router(self) -> ModelRouter:
        if self._router is None:
            raise RuntimeError("AIModule not initialised")
        return self._router

    async def complete(
        self,
        request: CompletionRequest,
        output_schema: type[BaseModel] | None = None,
        fallback_models: list[str] | None = None,
        max_retries: int | None = None,
    ) -> CompletionResponse | BaseModel:
        import time

        start_time = time.monotonic()

        if output_schema is not None:
            from forge.ai.structured import StructuredOutputEnforcer

            retries = (
                max_retries
                if max_retries is not None
                else (self._config_ai.structured_output_retries if self._config_ai else 3)
            )
            enforcer = StructuredOutputEnforcer(max_retries=retries)

            async def _complete_fn(msgs: list[Message]) -> CompletionResponse:
                req = request.model_copy(update={"messages": msgs})
                res = await self.router.complete(req, fallback_models)

                if res.usage is not None:
                    try:
                        adapter = self.router.resolve(res.model)
                        if adapter is not None:
                            res.cost = adapter.estimate_cost(res.usage, res.model)
                    except Exception:
                        from forge.ai.tokens import TokenCounter

                        res.cost = TokenCounter.estimate_cost(res.usage, res.model)

                    self._input_tokens += res.usage.input_tokens
                    self._output_tokens += res.usage.output_tokens
                    self._total_cost += res.cost
                return res

            try:
                validated = await enforcer.enforce(request.messages, output_schema, _complete_fn)
                latency_ms = (time.monotonic() - start_time) * 1000.0
                self._request_count += 1
                self._latency_ms_history.append(latency_ms)
                return validated
            except Exception:
                latency_ms = (time.monotonic() - start_time) * 1000.0
                self._request_count += 1
                self._latency_ms_history.append(latency_ms)
                raise
        else:
            try:
                response = await self.router.complete(request, fallback_models)
                latency_ms = (time.monotonic() - start_time) * 1000.0
                response.latency_ms = latency_ms

                # Update metrics
                self._request_count += 1
                self._latency_ms_history.append(latency_ms)
                if response.usage is not None:
                    try:
                        adapter = self.router.resolve(response.model)
                        if adapter is not None:
                            response.cost = adapter.estimate_cost(response.usage, response.model)
                    except Exception:
                        from forge.ai.tokens import TokenCounter

                        response.cost = TokenCounter.estimate_cost(response.usage, response.model)

                    self._input_tokens += response.usage.input_tokens
                    self._output_tokens += response.usage.output_tokens
                    self._total_cost += response.cost
                return response
            except Exception:
                latency_ms = (time.monotonic() - start_time) * 1000.0
                self._request_count += 1
                self._latency_ms_history.append(latency_ms)
                raise

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        import time

        from forge.ai.tokens import TokenCounter

        start_time = time.monotonic()
        input_tokens = TokenCounter.count_messages(request.messages)
        output_tokens = 0

        model_used = request.model

        try:
            async for chunk in self.router.stream(request):
                if chunk.delta:
                    output_tokens += TokenCounter.count_tokens(chunk.delta)
                if chunk.model:
                    model_used = chunk.model
                if chunk.usage and chunk.usage.output_tokens > 0:
                    output_tokens = chunk.usage.output_tokens
                yield chunk

            latency_ms = (time.monotonic() - start_time) * 1000.0

            from forge.ai.models import Usage

            usage = Usage(input_tokens=input_tokens, output_tokens=output_tokens)
            cost = 0.0
            try:
                adapter = self.router.resolve(model_used)
                if adapter is not None:
                    cost = adapter.estimate_cost(usage, model_used)
            except Exception:
                cost = TokenCounter.estimate_cost(usage, model_used)

            self._request_count += 1
            self._latency_ms_history.append(latency_ms)
            self._input_tokens += input_tokens
            self._output_tokens += output_tokens
            self._total_cost += cost

        except Exception:
            latency_ms = (time.monotonic() - start_time) * 1000.0
            self._request_count += 1
            self._latency_ms_history.append(latency_ms)
            raise

    def get_metrics(self) -> dict[str, Any]:
        """Return the collected observability metrics."""
        return {
            "request_count": self._request_count,
            "total_latency_ms": sum(self._latency_ms_history),
            "latency_history": list(self._latency_ms_history),
            "token_count": {
                "input": self._input_tokens,
                "output": self._output_tokens,
                "total": self._input_tokens + self._output_tokens,
            },
            "cost_estimate": round(self._total_cost, 6),
        }

    # ── ForgeModule ────────────────────────────────────────────────

    async def setup(self, runtime: ForgeRuntime) -> None:
        from forge.config.module import ConfigModule

        config_module: ConfigModule = runtime.get(ConfigModule)  # type: ignore[assignment]
        self._config_ai = config_module.config.ai

        self._router = ModelRouter(
            max_tokens_limit=self._config_ai.max_tokens,
            retry_module=runtime.get(RetryModule),
        )

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

        gemini_adapter = GeminiAdapter(
            api_key=self._get_gemini_key(),
            timeout=self._config_ai.timeout,
        )
        self._router.register("gemini*", gemini_adapter)

        ollama_adapter = OllamaAdapter(
            timeout=self._config_ai.timeout,
        )
        self._router.register("ollama*", ollama_adapter)

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

        default_model = self._config_ai.default_model
        try:
            adapter = self._router.resolve(default_model)
            if adapter is None:
                return HealthResult.error(
                    f"No adapter registered for default model '{default_model}'"
                )

            if adapter.provider == "mock":
                return HealthResult.ok()

            from forge.ai.models import CompletionRequest, Message
            from forge.core.async_bridge import run_async_health_check

            async def _ping() -> None:
                req = CompletionRequest(
                    model=default_model,
                    messages=[Message(role="user", content="ping")],
                    max_tokens=1,
                )
                await asyncio.wait_for(adapter.complete(req), timeout=5.0)

            run_async_health_check(_ping())
            return HealthResult.ok()
        except Exception as e:
            provider_name = adapter.provider if "adapter" in locals() and adapter else "unknown"
            return HealthResult.error(f"Health check failed for provider '{provider_name}': {e}")

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

    def _get_gemini_key(self) -> str | None:
        if self._config_ai is None:
            return None
        val = getattr(self._config_ai, "gemini_api_key", None)
        return val.get_secret_value() if val is not None else None
