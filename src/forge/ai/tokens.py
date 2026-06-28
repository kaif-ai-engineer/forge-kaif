from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from forge.ai.models import CompletionRequest, Message, Usage

# ── Hardcoded pricing table (USD per 1M tokens) ────────────────────
# Source: published pricing as of 2026-06

_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.150, "output": 0.600},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku": {"input": 0.80, "output": 4.00},
    "claude-3-opus": {"input": 15.00, "output": 75.00},
}


def _chars_per_token(text: str) -> int:
    """Rough token estimate: ~4 characters per token for English text."""
    return max(1, len(text) // 4)


class TokenCounter:
    """Estimates token usage and enforces pre-request budget limits."""

    @staticmethod
    def count_tokens(text: str) -> int:
        """Estimate the number of tokens in *text*."""
        return _chars_per_token(text)

    @staticmethod
    def count_messages(messages: list[Message]) -> int:
        """Estimate total tokens across a list of messages."""
        overhead = len(messages) * 4  # ~4 tokens per message for role markers
        content = sum(_chars_per_token(m.content) for m in messages)
        return overhead + content

    @staticmethod
    def estimate_cost(usage: Usage, model: str) -> float:
        """
        Calculate cost in USD from token counts using the pricing table.

        Returns 0.0 for unknown models.
        """
        prices = _PRICING.get(model)
        if prices is None:
            return 0.0
        input_cost = (usage.input_tokens / 1_000_000) * prices["input"]
        output_cost = (usage.output_tokens / 1_000_000) * prices["output"]
        return round(input_cost + output_cost, 6)

    @staticmethod
    def check_budget(
        request: CompletionRequest,
        max_tokens_limit: int,
    ) -> None:
        """
        Raise :class:`ValueError` if the estimated request exceeds *max_tokens_limit*.

        Catches runaway prompts before calling the adapter.
        """
        estimated = TokenCounter.count_messages(request.messages)
        if estimated > max_tokens_limit:
            raise BudgetExceededError(
                f"Estimated {estimated} input tokens exceeds "
                f"limit of {max_tokens_limit}"
            )


class BudgetExceededError(ValueError):
    """Raised when the estimated token count exceeds the configured limit."""



