"""
AI model abstraction module — unified interface across LLM providers.

Provides a single API surface for completions and streaming across OpenAI,
Anthropic, and a fully offline MockAdapter for testing.  Includes token
estimation, cost calculation, fallback routing, and pre-request budget
checking.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel

from forge.ai.adapters.anthropic import AnthropicAdapter
from forge.ai.adapters.base import BaseAdapter
from forge.ai.adapters.gemini import GeminiAdapter
from forge.ai.adapters.mock import MockAdapter
from forge.ai.adapters.ollama import OllamaAdapter
from forge.ai.adapters.openai import OpenAIAdapter
from forge.ai.exceptions import (
    AIError,
    AIProviderError,
    AllModelsFailedError,
    ModelNotFoundError,
    RateLimitError,
    StreamInterruptedError,
    StructuredOutputError,
    TokenLimitError,
)
from forge.ai.models import (
    AIResponse,
    CompletionRequest,
    CompletionResponse,
    Message,
    StreamChunk,
    TokenUsage,
    Usage,
)
from forge.ai.module import AIModule
from forge.ai.router import CompletionError, ModelRouter
from forge.ai.tokens import BudgetExceededError, TokenCounter
from forge.core.runtime import ForgeRuntime


async def complete(
    messages: list[Message],
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    output_schema: type[BaseModel] | None = None,
    fallback_models: list[str] | None = None,
    max_retries: int | None = None,
    **kwargs: Any,
) -> CompletionResponse | BaseModel:
    """
    Convenience function to perform an AI completion request.

    Uses the active ForgeRuntime context.
    """
    runtime = ForgeRuntime.get_active()
    ai_module: AIModule = runtime.get(AIModule)  # type: ignore[assignment]

    model_name = model or ai_module._config_ai.default_model
    request = CompletionRequest(
        model=model_name,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        extra=kwargs,
    )
    return await ai_module.complete(
        request=request,
        output_schema=output_schema,
        fallback_models=fallback_models,
        max_retries=max_retries,
    )


async def stream(
    messages: list[Message],
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    **kwargs: Any,
) -> AsyncIterator[StreamChunk]:
    """
    Convenience function to perform an AI streaming completion request.

    Uses the active ForgeRuntime context.
    """
    runtime = ForgeRuntime.get_active()
    ai_module: AIModule = runtime.get(AIModule)  # type: ignore[assignment]

    model_name = model or ai_module._config_ai.default_model
    request = CompletionRequest(
        model=model_name,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        extra=kwargs,
    )
    async for chunk in ai_module.stream(request):
        yield chunk


__all__ = [
    "AIError",
    "AIModule",
    "AIProviderError",
    "AIResponse",
    "AllModelsFailedError",
    "AnthropicAdapter",
    "BaseAdapter",
    "BudgetExceededError",
    "CompletionError",
    "CompletionRequest",
    "CompletionResponse",
    "GeminiAdapter",
    "Message",
    "MockAdapter",
    "ModelNotFoundError",
    "OllamaAdapter",
    "ModelRouter",
    "OpenAIAdapter",
    "RateLimitError",
    "StreamChunk",
    "StreamInterruptedError",
    "StructuredOutputError",
    "TokenCounter",
    "TokenLimitError",
    "TokenUsage",
    "Usage",
    "complete",
    "stream",
]
