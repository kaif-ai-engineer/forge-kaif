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


class AnthropicAdapter(BaseAdapter):
    """
    Thin wrapper around the Anthropic Python SDK.

    Requires ``anthropic`` to be installed.  Falls back to mock behaviour
    when the library is unavailable.
    """

    def __init__(self, api_key: str | None = None, timeout: float = 30.0) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._client: Any = None
        self._init_client()

    @property
    def provider(self) -> str:
        return "anthropic"

    # ── BaseAdapter ────────────────────────────────────────────────

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        if self._client is None or not self._api_key:
            return _mock_complete(request)

        payload = self._build_payload(request)
        try:
            response = await self._client.messages.create(**payload)
        except Exception as exc:
            import anthropic

            if isinstance(exc, anthropic.RateLimitError):
                raise RateLimitError(f"Anthropic API rate limit exceeded: {exc}") from exc
            if isinstance(exc, anthropic.AuthenticationError):
                raise AIProviderError(f"Anthropic API authentication failed: {exc}") from exc
            if isinstance(exc, anthropic.NotFoundError):
                raise ModelNotFoundError(f"Anthropic model not found: {exc}") from exc
            raise AIProviderError(f"Anthropic API error: {exc}") from exc

        return CompletionResponse(
            model=response.model or request.model,
            message=Message(
                role="assistant",
                content=response.content[0].text if response.content else "",
            ),
            usage=Usage(
                input_tokens=response.usage.input_tokens if response.usage else 0,
                output_tokens=response.usage.output_tokens if response.usage else 0,
            ),
            provider="anthropic",
        )

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        if self._client is None or not self._api_key:
            async for chunk in _mock_stream(request):
                yield chunk
            return

        payload = self._build_payload(request)
        payload["stream"] = True

        input_tokens = 0
        output_tokens = 0

        try:
            async with self._client.messages.create(**payload) as msg_stream:
                async for event in msg_stream:
                    delta_content = ""
                    finish_reason = None
                    usage = None

                    if event.type == "message_start":
                        if hasattr(event.message, "usage") and event.message.usage:
                            input_tokens = event.message.usage.input_tokens
                    elif event.type == "content_block_delta":
                        if hasattr(event.delta, "text") and event.delta.text:
                            delta_content = event.delta.text
                    elif event.type == "message_delta":
                        if hasattr(event, "usage") and event.usage:
                            output_tokens = event.usage.output_tokens
                        if hasattr(event.delta, "stop_reason") and event.delta.stop_reason:
                            finish_reason = event.delta.stop_reason
                    elif event.type == "message_stop":
                        usage = Usage(
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                        )

                    if delta_content or finish_reason or usage:
                        yield StreamChunk(
                            delta=delta_content,
                            finish_reason=finish_reason,
                            usage=usage,
                            model=request.model,
                            provider="anthropic",
                        )
        except Exception as exc:
            import anthropic

            if isinstance(exc, anthropic.RateLimitError):
                raise RateLimitError(f"Anthropic API rate limit exceeded: {exc}") from exc
            if isinstance(exc, anthropic.AuthenticationError):
                raise AIProviderError(f"Anthropic API authentication failed: {exc}") from exc
            if isinstance(exc, anthropic.NotFoundError):
                raise ModelNotFoundError(f"Anthropic model not found: {exc}") from exc
            raise StreamInterruptedError(f"Anthropic stream interrupted: {exc}") from exc

    def count_tokens(self, text: str) -> int:
        return TokenCounter.count_tokens(text)

    # ── Internal ───────────────────────────────────────────────────

    def _init_client(self) -> None:
        try:
            import anthropic

            if not self._api_key:
                self._client = None
            else:
                self._client = anthropic.AsyncAnthropic(
                    api_key=self._api_key, timeout=self._timeout
                )
        except (ImportError, Exception) as exc:
            _logger.warning("Failed to initialize Anthropic client: %s — using mock", exc)
            self._client = None

    def _build_payload(self, request: CompletionRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens or 1024,
            "messages": [
                {"role": m.role, "content": m.content}
                for m in request.messages
                if m.role != "system"
            ],
        }
        system_msgs = [m.content for m in request.messages if m.role == "system"]
        if system_msgs:
            payload["system"] = "\n".join(system_msgs)
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        payload.update(request.extra)
        return payload


def _mock_complete(request: CompletionRequest) -> CompletionResponse:
    return CompletionResponse(
        model=request.model,
        message=Message(role="assistant", content="[mock anthropic response]"),
        usage=Usage(
            input_tokens=TokenCounter.count_messages(request.messages),
            output_tokens=10,
        ),
        provider="anthropic",
    )


async def _mock_stream(request: CompletionRequest) -> AsyncIterator[StreamChunk]:
    yield StreamChunk(
        delta="[mock anthropic chunk]",
        finish_reason="stop",
        usage=Usage(
            input_tokens=TokenCounter.count_messages(request.messages),
            output_tokens=4,
        ),
        model=request.model,
        provider="anthropic",
    )
