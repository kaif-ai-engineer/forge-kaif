from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from forge.ai.adapters.base import BaseAdapter
from forge.ai.tokens import TokenCounter

if TYPE_CHECKING:
    from forge.ai.models import CompletionRequest

from forge.ai.exceptions import (
    AIProviderError,
    ModelNotFoundError,
    RateLimitError,
    StreamInterruptedError,
)
from forge.ai.models import CompletionResponse, Message, StreamChunk, Usage

_logger = logging.getLogger(__name__)


class OpenAIAdapter(BaseAdapter):
    """
    Thin wrapper around the OpenAI Python SDK.

    Requires ``openai`` to be installed.  Falls back to mock behaviour
    when the library is unavailable.
    """

    def __init__(self, api_key: str | None = None, timeout: float = 30.0) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._client: Any = None
        self._init_client()

    @property
    def provider(self) -> str:
        return "openai"

    # ── BaseAdapter ────────────────────────────────────────────────

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        if self._client is None or not self._api_key:
            return _mock_complete(request)

        payload = self._build_payload(request)
        try:
            response = await self._client.chat.completions.create(**payload)
        except Exception as exc:
            import openai

            if isinstance(exc, openai.RateLimitError):
                raise RateLimitError(f"OpenAI API rate limit exceeded: {exc}") from exc
            if isinstance(exc, openai.AuthenticationError):
                raise AIProviderError(f"OpenAI API authentication failed: {exc}") from exc
            if isinstance(exc, openai.NotFoundError):
                raise ModelNotFoundError(f"OpenAI model not found: {exc}") from exc
            raise AIProviderError(f"OpenAI API error: {exc}") from exc

        return CompletionResponse(
            model=response.model or request.model,
            message=Message(
                role="assistant",
                content=response.choices[0].message.content or "",
            ),
            usage=Usage(
                input_tokens=response.usage.prompt_tokens if response.usage else 0,
                output_tokens=response.usage.completion_tokens if response.usage else 0,
            ),
            provider="openai",
        )

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        if self._client is None or not self._api_key:
            async for chunk in _mock_stream(request):
                yield chunk
            return

        payload = self._build_payload(request)
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}
        try:
            response = await self._client.chat.completions.create(**payload)
        except Exception as exc:
            import openai

            if isinstance(exc, openai.RateLimitError):
                raise RateLimitError(f"OpenAI API rate limit exceeded: {exc}") from exc
            if isinstance(exc, openai.AuthenticationError):
                raise AIProviderError(f"OpenAI API authentication failed: {exc}") from exc
            if isinstance(exc, openai.NotFoundError):
                raise ModelNotFoundError(f"OpenAI model not found: {exc}") from exc
            raise AIProviderError(f"OpenAI API error: {exc}") from exc

        try:
            async for event in response:
                delta_content = ""
                finish_reason = None
                usage = None

                if event.choices:
                    choice = event.choices[0]
                    if choice.delta and choice.delta.content:
                        delta_content = choice.delta.content
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason

                if hasattr(event, "usage") and event.usage is not None:
                    usage = Usage(
                        input_tokens=event.usage.prompt_tokens,
                        output_tokens=event.usage.completion_tokens,
                    )

                if delta_content or finish_reason or usage:
                    yield StreamChunk(
                        delta=delta_content,
                        finish_reason=finish_reason,
                        usage=usage,
                        model=event.model or request.model,
                        provider="openai",
                    )
        except Exception as exc:
            raise StreamInterruptedError(f"OpenAI stream interrupted: {exc}") from exc

    def count_tokens(self, text: str) -> int:
        return TokenCounter.count_tokens(text)

    # ── Internal ───────────────────────────────────────────────────

    def _init_client(self) -> None:
        try:
            import openai

            if not self._api_key:
                self._client = None
            else:
                self._client = openai.AsyncOpenAI(api_key=self._api_key, timeout=self._timeout)
        except (ImportError, Exception) as exc:
            _logger.warning("Failed to initialize OpenAI client: %s — using mock", exc)
            self._client = None

    def _build_payload(self, request: CompletionRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        payload.update(request.extra)
        return payload


def _mock_complete(request: CompletionRequest) -> CompletionResponse:
    return CompletionResponse(
        model=request.model,
        message=Message(role="assistant", content="[mock openai response]"),
        usage=Usage(
            input_tokens=TokenCounter.count_messages(request.messages),
            output_tokens=10,
        ),
        provider="openai",
    )


async def _mock_stream(request: CompletionRequest) -> AsyncIterator[StreamChunk]:
    yield StreamChunk(
        delta="[mock openai chunk]",
        finish_reason="stop",
        usage=Usage(
            input_tokens=TokenCounter.count_messages(request.messages),
            output_tokens=4,
        ),
        model=request.model,
        provider="openai",
    )
