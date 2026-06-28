from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from forge.ai.adapters.base import BaseAdapter
from forge.ai.exceptions import AIProviderError, ModelNotFoundError, RateLimitError
from forge.ai.models import CompletionRequest, CompletionResponse, Message, StreamChunk, Usage
from forge.ai.tokens import TokenCounter

_logger = logging.getLogger(__name__)


class GeminiAdapter(BaseAdapter):
    """Adapter for Google Gemini models via google-generativeai."""

    def __init__(self, api_key: str | None = None, timeout: float = 30.0) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._client: Any = None
        self._init_client()

    @property
    def provider(self) -> str:
        return "gemini"

    def _init_client(self) -> None:
        try:
            import google.generativeai as genai

            if self._api_key:
                genai.configure(api_key=self._api_key)
            self._client = genai
        except ImportError:
            _logger.warning("google-generativeai package not installed — using mock fallback")
            self._client = None

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        if self._client is None or not self._api_key:
            return self._mock_complete(request)

        # Prepare messages in Gemini format
        system_instruction = None
        gemini_messages = []
        for msg in request.messages:
            if msg.role == "system":
                if system_instruction is None:
                    system_instruction = msg.content
                else:
                    system_instruction += "\n" + msg.content
            elif msg.role == "user":
                gemini_messages.append({"role": "user", "parts": [msg.content]})
            elif msg.role in ("assistant", "model"):
                gemini_messages.append({"role": "model", "parts": [msg.content]})

        # Initialize the generative model
        try:
            model = self._client.GenerativeModel(
                model_name=request.model,
                system_instruction=system_instruction,
            )
        except Exception as exc:
            raise AIProviderError(
                f"Failed to initialize Gemini model '{request.model}': {exc}"
            ) from exc

        # Set up generation config
        generation_config: dict[str, Any] = {}
        if request.max_tokens is not None:
            generation_config["max_output_tokens"] = request.max_tokens
        if request.temperature is not None:
            generation_config["temperature"] = request.temperature

        # Call the Gemini API
        try:
            response = await model.generate_content_async(
                contents=gemini_messages,
                generation_config=self._client.types.GenerationConfig(**generation_config),
                request_options={"timeout": self._timeout},
            )
        except Exception as exc:
            err_msg = str(exc)
            if "429" in err_msg or "resource exhausted" in err_msg.lower():
                raise RateLimitError(f"Gemini API rate limit exceeded: {exc}") from exc
            if "403" in err_msg or "api key not valid" in err_msg.lower() or "401" in err_msg:
                raise AIProviderError(f"Gemini API authentication failed: {exc}") from exc
            if "404" in err_msg or "model not found" in err_msg.lower():
                raise ModelNotFoundError(f"Gemini model not found: {exc}") from exc
            raise AIProviderError(f"Gemini API error: {exc}") from exc

        # Parse output and usage
        content = response.text or ""
        prompt_tokens = 0
        completion_tokens = 0
        if response.usage_metadata:
            prompt_tokens = response.usage_metadata.prompt_token_count
            completion_tokens = response.usage_metadata.candidates_token_count

        return CompletionResponse(
            model=request.model,
            message=Message(role="assistant", content=content),
            usage=Usage(input_tokens=prompt_tokens, output_tokens=completion_tokens),
            provider="gemini",
        )

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        """Streaming is not supported for Gemini in MVP."""
        if False:  # pragma: no cover
            yield
        raise NotImplementedError(
            "Streaming is not supported for the Gemini adapter in this MVP version."
        )

    def count_tokens(self, text: str) -> int:
        return TokenCounter.count_tokens(text)

    def _mock_complete(self, request: CompletionRequest) -> CompletionResponse:
        return CompletionResponse(
            model=request.model,
            message=Message(role="assistant", content="[mock gemini response]"),
            usage=Usage(
                input_tokens=TokenCounter.count_messages(request.messages),
                output_tokens=10,
            ),
            provider="gemini",
        )
