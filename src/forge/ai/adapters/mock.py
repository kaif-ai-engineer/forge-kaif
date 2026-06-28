from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from forge.ai.adapters.base import BaseAdapter
from forge.ai.tokens import TokenCounter

if TYPE_CHECKING:
    from forge.ai.models import CompletionRequest

from forge.ai.models import CompletionResponse, Message, Usage

_logger = logging.getLogger(__name__)


class MockAdapter(BaseAdapter):
    """
    Fully offline adapter for testing — no external API calls.

    Returns a canned response and never raises rate-limit or auth errors.
    """

    def __init__(self, response_text: str = "[mock response]") -> None:
        self._response_text = response_text

    @property
    def provider(self) -> str:
        return "mock"

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        return CompletionResponse(
            model=request.model,
            message=Message(role="assistant", content=self._response_text),
            usage=Usage(
                input_tokens=TokenCounter.count_messages(request.messages),
                output_tokens=self.count_tokens(self._response_text),
            ),
        )

    async def stream(
        self, _request: CompletionRequest
    ) -> AsyncIterator[str]:
        yield self._response_text

    def count_tokens(self, text: str) -> int:
        return TokenCounter.count_tokens(text)
