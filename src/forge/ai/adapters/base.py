from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from forge.ai.tokens import TokenCounter

if TYPE_CHECKING:
    from forge.ai.models import CompletionRequest, CompletionResponse, StreamChunk, Usage


class BaseAdapter(ABC):
    """Interface that every provider adapter must implement."""

    @property
    @abstractmethod
    def provider(self) -> str:
        """Short label such as ``"openai"`` or ``"anthropic"``."""

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Synchronous (non-streaming) completion."""

    async def stream(self, _request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        """Yield content chunks as they arrive."""
        # Subclasses override; the ``if False: yield`` makes type
        # checkers recognise this as an async generator.
        if False:  # pragma: no cover
            yield
        raise NotImplementedError

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Return an estimated token count for *text*."""

    def estimate_cost(self, usage: Usage, model: str) -> float:
        """Return the estimated USD cost for the given usage."""
        return TokenCounter.estimate_cost(usage, model)
