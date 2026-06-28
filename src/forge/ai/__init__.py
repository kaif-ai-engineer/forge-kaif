"""
AI model abstraction module — unified interface across LLM providers.

Provides a single API surface for completions and streaming across OpenAI,
Anthropic, and a fully offline MockAdapter for testing.  Includes token
estimation, cost calculation, fallback routing, and pre-request budget
checking.
"""

from forge.ai.adapters.anthropic import AnthropicAdapter
from forge.ai.adapters.base import BaseAdapter
from forge.ai.adapters.mock import MockAdapter
from forge.ai.adapters.openai import OpenAIAdapter
from forge.ai.models import CompletionRequest, CompletionResponse, Message, Usage
from forge.ai.module import AIModule
from forge.ai.router import CompletionError, ModelNotFoundError, ModelRouter
from forge.ai.tokens import BudgetExceededError, TokenCounter

__all__ = [
    "AIModule",
    "AnthropicAdapter",
    "BaseAdapter",
    "BudgetExceededError",
    "CompletionError",
    "CompletionRequest",
    "CompletionResponse",
    "Message",
    "MockAdapter",
    "ModelNotFoundError",
    "ModelRouter",
    "OpenAIAdapter",
    "TokenCounter",
    "Usage",
]
