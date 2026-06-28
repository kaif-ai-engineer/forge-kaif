"""
Provider adapters for the AI model abstraction module.

Each adapter wraps a third-party LLM provider SDK behind the BaseAdapter
protocol, enabling unified completion and streaming semantics across OpenAI,
Anthropic, Gemini, Ollama, and a MockAdapter for testing.
"""
