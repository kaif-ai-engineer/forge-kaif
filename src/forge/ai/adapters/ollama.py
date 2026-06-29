from __future__ import annotations

import json
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
    StreamInterruptedError,
)
from forge.ai.models import CompletionResponse, Message, StreamChunk, Usage

_logger = logging.getLogger(__name__)


class OllamaAdapter(BaseAdapter):
    """
    Adapter for local Ollama models via the Ollama HTTP API.

    Requires ``httpx`` to be installed.  Falls back to mock behaviour
    when the library is unavailable.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        timeout: float = 120.0,
        mock: bool = False,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._mock = mock
        self._client: Any = None
        if not mock:
            self._init_client()

    @property
    def provider(self) -> str:
        return "ollama"

    # ── BaseAdapter ────────────────────────────────────────────────

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        if self._client is None or self._mock:
            return _mock_complete(request)

        payload = self._build_payload(request)
        try:
            import httpx

            response = await self._client.post(
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=self._timeout,
            )
        except Exception as exc:
            _raise_ollama_error(exc)

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _raise_ollama_error(exc)

        try:
            data = response.json()
        except Exception as exc:
            raise AIProviderError(f"Ollama returned invalid JSON: {exc}") from exc

        content = data.get("message", {}).get("content", "")
        model = data.get("model", request.model)

        usage = Usage(
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
        )

        return CompletionResponse(
            model=model,
            message=Message(role="assistant", content=content),
            usage=usage,
            provider="ollama",
        )

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        if self._client is None or self._mock:
            async for chunk in _mock_stream(request):
                yield chunk
            return

        payload = self._build_payload(request)
        payload["stream"] = True

        try:
            import httpx

            async with self._client.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=self._timeout,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as exc:
                        _logger.warning("Skipping malformed Ollama stream line: %s", exc)
                        continue

                    delta_content = data.get("message", {}).get("content", "")
                    done = data.get("done", False)
                    finish_reason = "stop" if done else None

                    usage = None
                    if done and "prompt_eval_count" in data:
                        usage = Usage(
                            input_tokens=data.get("prompt_eval_count", 0),
                            output_tokens=data.get("eval_count", 0),
                        )

                    model = data.get("model", request.model)

                    if delta_content or finish_reason or usage:
                        yield StreamChunk(
                            delta=delta_content,
                            finish_reason=finish_reason,
                            usage=usage,
                            model=model,
                            provider="ollama",
                        )
        except httpx.HTTPStatusError as exc:
            _raise_ollama_error(exc)
        except Exception as exc:
            raise StreamInterruptedError(f"Ollama stream interrupted: {exc}") from exc

    def count_tokens(self, text: str) -> int:
        return TokenCounter.count_tokens(text)

    # ── Model Discovery ────────────────────────────────────────────

    async def list_models(self) -> list[str]:
        """Fetch available model names from Ollama's ``/api/tags`` endpoint."""
        if self._client is None or self._mock:
            return []

        try:
            response = await self._client.get(
                f"{self._base_url}/api/tags",
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.json()
            return [model["name"] for model in data.get("models", [])]
        except Exception as exc:
            _logger.warning("Failed to list Ollama models: %s", exc)
            return []

    # ── Internal ───────────────────────────────────────────────────

    def _init_client(self) -> None:
        try:
            import httpx

            self._client = httpx.AsyncClient()
        except ImportError:
            _logger.warning("httpx package not installed — using mock fallback")
            self._client = None

    def _build_payload(self, request: CompletionRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        }
        options: dict[str, Any] = {}
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if options:
            payload["options"] = options
        payload.update(request.extra)
        return payload


_HTTP_NOT_FOUND = 404


def _raise_ollama_error(exc: Exception) -> None:
    """Map HTTP/connection errors to the appropriate forge exception."""
    import httpx

    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        if status_code == _HTTP_NOT_FOUND:
            raise ModelNotFoundError(f"Ollama model not found: {exc}") from exc
        raise AIProviderError(f"Ollama API error (HTTP {status_code}): {exc}") from exc

    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        raise AIProviderError(
            f"Ollama connection failed — is Ollama running? {exc}",
        ) from exc

    if isinstance(exc, httpx.TimeoutException):
        raise AIProviderError(f"Ollama request timed out: {exc}") from exc

    if isinstance(exc, httpx.HTTPError):
        raise AIProviderError(f"Ollama HTTP error: {exc}") from exc

    raise AIProviderError(f"Ollama API error: {exc}") from exc


def _mock_complete(request: CompletionRequest) -> CompletionResponse:
    return CompletionResponse(
        model=request.model,
        message=Message(role="assistant", content="[mock ollama response]"),
        usage=Usage(
            input_tokens=TokenCounter.count_messages(request.messages),
            output_tokens=10,
        ),
        provider="ollama",
    )


async def _mock_stream(request: CompletionRequest) -> AsyncIterator[StreamChunk]:
    yield StreamChunk(
        delta="[mock ollama chunk]",
        finish_reason="stop",
        usage=Usage(
            input_tokens=TokenCounter.count_messages(request.messages),
            output_tokens=4,
        ),
        model=request.model,
        provider="ollama",
    )
