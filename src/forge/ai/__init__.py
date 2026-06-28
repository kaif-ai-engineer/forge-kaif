"""
AI model abstraction module — unified interface across LLM providers.

Provides a single API surface for completions and streaming across OpenAI,
Anthropic, Gemini, and Ollama. Supports structured output enforcement via
Pydantic, automatic retry and fallback, token counting, and cost estimation.
"""
