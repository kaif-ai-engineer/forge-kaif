from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from forge.ai.exceptions import AllModelsFailedError, ModelNotFoundError
from forge.ai.tokens import TokenCounter

if TYPE_CHECKING:
    from typing import Any

    from forge.ai.adapters.base import BaseAdapter
    from forge.ai.models import CompletionRequest, CompletionResponse, StreamChunk

_logger = logging.getLogger(__name__)


class ModelRouter:
    """
    Selects an adapter based on model name and supports fallback chains.

    Usage::

        router = ModelRouter()
        router.register("gpt-4o*", openai_adapter)
        router.register("claude*", anthropic_adapter)
        router.register("*", mock_adapter)

        resp = await router.complete(request)
    """

    def __init__(
        self,
        max_tokens_limit: int = 128_000,
        retry_module: Any | None = None,
    ) -> None:
        self._patterns: list[tuple[re.Pattern[str], BaseAdapter]] = []
        self._fallback: list[tuple[str, BaseAdapter]] = []
        self._max_tokens_limit = max_tokens_limit
        self._retry_module = retry_module

    # ── Registration ───────────────────────────────────────────────

    def register(
        self,
        model_pattern: str,
        adapter: BaseAdapter,
        *,
        is_fallback: bool = False,
    ) -> None:
        """
        Register *adapter* for models matching *model_pattern* (glob-style).

        Use ``"*"`` as the pattern to match all models.  When
        ``is_fallback=True`` the adapter is added to the fallback chain.
        """
        regex = _glob_to_regex(model_pattern)
        compiled = re.compile(regex)
        if is_fallback:
            self._fallback.append((model_pattern, adapter))
        else:
            self._patterns.append((compiled, adapter))

    # ── Resolution ─────────────────────────────────────────────────

    def resolve(self, model: str) -> BaseAdapter | None:
        """Return the first adapter whose pattern matches *model*, or ``None``."""
        for pattern, adapter in self._patterns:
            if pattern.match(model):
                return adapter
        return None

    # ── Public API ─────────────────────────────────────────────────

    async def complete(
        self,
        request: CompletionRequest,
        fallback_models: list[str] | None = None,
    ) -> CompletionResponse:
        """
        Execute the request with automatic fallback on failure.

        *fallback_models* lists model names to try in order after the
        primary model fails.  If ``None``, uses the router's internal
        fallback adapter list.
        """
        adapter = self.resolve(request.model)
        if adapter is None:
            raise ModelNotFoundError(f"No adapter registered for model {request.model!r}")

        # Pre-request budget check
        TokenCounter.check_budget(request, self._max_tokens_limit)

        # Attempt primary adapter
        last_error: Exception | None = None
        try:
            return await self._call_adapter(adapter, request)
        except Exception as exc:
            last_error = exc
            _logger.warning(
                "Model %r via %s failed: %s — trying fallback",
                request.model,
                adapter.provider,
                exc,
            )

        # Fallback chain
        fallback_adapters = self._build_fallback_chain(fallback_models)
        for fb_model, fb_adapter in fallback_adapters:
            try:
                fb_request = request.model_copy(update={"model": fb_model})
                return await self._call_adapter(fb_adapter, fb_request)
            except Exception as exc:
                last_error = exc
                _logger.warning("Fallback %s also failed: %s", fb_adapter.provider, exc)

        raise AllModelsFailedError(
            f"All {1 + len(fallback_adapters)} adapter(s) failed for model {request.model!r}"
        ) from last_error

    async def stream(
        self,
        request: CompletionRequest,
    ) -> AsyncIterator[StreamChunk]:
        adapter = self.resolve(request.model)
        if adapter is None:
            raise ModelNotFoundError(f"No adapter registered for model {request.model!r}")
        TokenCounter.check_budget(request, self._max_tokens_limit)
        async for chunk in adapter.stream(request):
            yield chunk

    async def _call_adapter(
        self, adapter: BaseAdapter, request: CompletionRequest
    ) -> CompletionResponse:
        if self._retry_module is not None:
            from typing import cast

            from forge.ai.exceptions import RateLimitError

            res = await self._retry_module.retry(
                adapter.complete,
                retryable_exceptions=(RateLimitError,),
            )(request)
            return cast("CompletionResponse", res)
        return await adapter.complete(request)

    # ── Internal ───────────────────────────────────────────────────

    def _build_fallback_chain(
        self,
        fallback_models: list[str] | None,
    ) -> list[tuple[str, BaseAdapter]]:
        if fallback_models:
            adapters: list[tuple[str, BaseAdapter]] = []
            for model in fallback_models:
                a = self.resolve(model)
                if a is not None:
                    adapters.append((model, a))
            return adapters

        chain: list[tuple[str, BaseAdapter]] = []
        for pat, adapter in self._fallback:
            model_name = pat.replace("*", "").replace("?", "")
            chain.append((model_name, adapter))
        return chain


# Alias for backward compatibility
CompletionError = AllModelsFailedError


def _glob_to_regex(pattern: str) -> str:
    """Convert a simple glob pattern to a regex anchored at both ends."""
    parts: list[str] = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            parts.append(".*")
        elif ch == "?":
            parts.append(".")
        else:
            parts.append(re.escape(ch))
        i += 1
    return "^(?:" + "".join(parts) + ")$"
