from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from forge.ai.adapters.base import BaseAdapter
from forge.ai.tokens import TokenCounter

if TYPE_CHECKING:
    from forge.ai.models import CompletionRequest

from forge.ai.models import CompletionResponse, Message, Usage

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
        if self._client is None:
            return _mock_complete(request)

        payload = self._build_payload(request)
        response = await self._client.chat.completions.create(**payload)

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
        )

    async def stream(
        self, request: CompletionRequest
    ) -> AsyncIterator[str]:
        if self._client is None:
            async for chunk in _mock_stream():
                yield chunk
            return

        payload = self._build_payload(request)
        payload["stream"] = True
        response = await self._client.chat.completions.create(**payload)

        async for event in response:
            if event.choices and event.choices[0].delta.content:
                yield event.choices[0].delta.content

    def count_tokens(self, text: str) -> int:
        return TokenCounter.count_tokens(text)

    # ── Internal ───────────────────────────────────────────────────

    def _init_client(self) -> None:
        try:
            import openai

            self._client = openai.AsyncOpenAI(
                api_key=self._api_key, timeout=self._timeout
            )
        except ImportError:
            _logger.warning("openai package not installed — using mock")
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
    )


async def _mock_stream() -> AsyncIterator[str]:
    yield "[mock openai chunk]"
