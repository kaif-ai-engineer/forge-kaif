from __future__ import annotations

from forge.core.exceptions import ForgeError


class AIError(ForgeError):
    """Base exception for all AI module errors."""


class AIProviderError(AIError):
    """Raised when the provider API returns an error (auth, billing, bad request)."""


class TokenLimitError(AIError):
    """Raised when the requested prompt exceeds the model's budget or maximum context."""


class StructuredOutputError(AIError):
    """
    Raised when the model fails to produce output conforming to the Pydantic schema
    after the maximum retry attempts have been exhausted.
    """

    def __init__(
        self,
        schema_name: str,
        attempts: int,
        last_response: str,
        last_error: str,
    ) -> None:
        self.schema_name = schema_name
        self.attempts = attempts
        self.last_response = last_response
        self.last_error = last_error
        super().__init__(
            f"Failed to produce structured output conforming to '{schema_name}' "
            f"after {attempts} attempt(s). Last error: {last_error}. "
            f"Last raw response: {last_response!r}"
        )


class StreamInterruptedError(AIError):
    """Raised when an active stream is cut short or disconnected."""


class RateLimitError(AIProviderError):
    """Raised when the provider rate-limits the client."""


class ModelNotFoundError(AIProviderError):
    """Raised when the requested model is not available or registered."""


class AllModelsFailedError(AIError):
    """Raised when all models in the fallback chain have failed to execute."""
