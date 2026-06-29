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
            _raise_gemini_error(exc)

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
        if self._client is None or not self._api_key:
            async for chunk in _mock_stream(request):
                yield chunk
            return

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

        # Initiate the streaming request
        try:
            stream_resp = await model.generate_content_async(
                contents=gemini_messages,
                generation_config=self._client.types.GenerationConfig(**generation_config),
                stream=True,
                request_options={"timeout": self._timeout},
            )
        except Exception as exc:
            _raise_gemini_error(exc, "starting Gemini stream")

        try:
            async for chunk in stream_resp:
                delta_content = ""
                finish_reason = None
                usage = None

                # Check for content blocked by safety filters
                if hasattr(chunk, "prompt_feedback") and chunk.prompt_feedback:
                    block_reason = chunk.prompt_feedback.block_reason
                    if block_reason:
                        yield StreamChunk(
                            delta="",
                            finish_reason="content_filter",
                            usage=None,
                            model=request.model,
                            provider="gemini",
                        )
                        return

                # Extract text from candidates
                if chunk.candidates:
                    candidate = chunk.candidates[0]

                    if candidate.content and candidate.content.parts:
                        parts_text = "".join(
                            p.text for p in candidate.content.parts if hasattr(p, "text") and p.text
                        )
                        if parts_text:
                            delta_content = parts_text

                    if candidate.finish_reason:
                        finish_reason = _map_gemini_finish_reason(candidate.finish_reason)

                # Extract usage metadata (typically available on the last chunk)
                if chunk.usage_metadata:
                    usage = Usage(
                        input_tokens=getattr(chunk.usage_metadata, "prompt_token_count", 0),
                        output_tokens=getattr(chunk.usage_metadata, "candidates_token_count", 0),
                    )

                if delta_content or finish_reason or usage:
                    yield StreamChunk(
                        delta=delta_content,
                        finish_reason=finish_reason,
                        usage=usage,
                        model=request.model,
                        provider="gemini",
                    )
        except Exception as exc:
            _raise_gemini_stream_error(exc)

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


_finish_reason_map: dict[str, str] = {
    "STOP": "stop",
    "MAX_TOKENS": "length",
    "SAFETY": "content_filter",
    "RECITATION": "content_filter",
    "OTHER": "error",
}


def _map_gemini_finish_reason(reason: Any) -> str:
    """Map Gemini's finish reason enum to a standard string."""
    reason_str = reason.name if hasattr(reason, "name") else str(reason).upper()
    return _finish_reason_map.get(reason_str, reason_str.lower())


def _raise_gemini_error(exc: Exception, context: str = "Gemini API") -> None:
    """Raise the appropriate exception based on the Gemini error."""
    err_msg = str(exc)
    if "429" in err_msg or "resource exhausted" in err_msg.lower():
        raise RateLimitError(f"Gemini API rate limit exceeded: {exc}") from exc
    if "403" in err_msg or "api key not valid" in err_msg.lower() or "401" in err_msg:
        raise AIProviderError(f"Gemini API authentication failed: {exc}") from exc
    if "404" in err_msg or "model not found" in err_msg.lower():
        raise ModelNotFoundError(f"Gemini model not found: {exc}") from exc
    if "safety" in err_msg.lower() or "blocked" in err_msg.lower():
        raise AIProviderError(f"Gemini content blocked by safety filters: {exc}") from exc
    raise AIProviderError(f"{context} error: {exc}") from exc


def _raise_gemini_stream_error(exc: Exception) -> None:
    """Raise stream-specific or general Gemini error."""
    err_msg = str(exc)
    if "429" in err_msg or "resource exhausted" in err_msg.lower():
        raise RateLimitError(f"Gemini API rate limit exceeded: {exc}") from exc
    if "403" in err_msg or "api key not valid" in err_msg.lower() or "401" in err_msg:
        raise AIProviderError(f"Gemini API authentication failed: {exc}") from exc
    if "404" in err_msg or "model not found" in err_msg.lower():
        raise ModelNotFoundError(f"Gemini model not found: {exc}") from exc
    if "safety" in err_msg.lower() or "blocked" in err_msg.lower():
        raise AIProviderError(f"Gemini content blocked by safety filters: {exc}") from exc
    raise StreamInterruptedError(f"Gemini stream interrupted: {exc}") from exc


async def _mock_stream(request: CompletionRequest) -> AsyncIterator[StreamChunk]:
    yield StreamChunk(
        delta="[mock gemini chunk]",
        finish_reason="stop",
        usage=Usage(
            input_tokens=TokenCounter.count_messages(request.messages),
            output_tokens=4,
        ),
        model=request.model,
        provider="gemini",
    )
