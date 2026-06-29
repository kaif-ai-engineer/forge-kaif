# Multi-Provider AI Fallback

Configure automatic fallback chains across AI providers for resilience.

## The Problem

Single-provider AI apps have a single point of failure. If OpenAI is down, your
app is down. You want to fallback to Anthropic, then Gemini, then Ollama.

## The Solution

forge's AI module supports built-in fallback routing. Define a list of models and
forge tries them in order until one succeeds.

## Basic Fallback

```python
from forge.ai import complete, Message

response = await complete(
    messages=[Message.user("Hello")],
    model="gpt-4o",
    fallback_models=[
        "claude-3-5-sonnet",
        "gemini-1.5-pro",
    ],
)
```

## Complete Fallback Chain

```python
response = await complete(
    messages=[Message.user("Write a poem about Python")],
    model="gpt-4o",
    fallback_models=[
        "gpt-4o-mini",        # Cheaper fallback
        "claude-3-5-sonnet",   # Anthropic
        "claude-3-haiku",      # Cheaper Anthropic
        "gemini-1.5-pro",      # Google
        "gemini-1.5-flash",    # Cheaper Google
    ],
    max_retries=2,            # Retries per model before fallback
)
```

## Configuration-Driven Fallback

```python
# forge.config.toml
[ai]
default_model = "gpt-4o"
fallback_models = [
    "claude-3-5-sonnet",
    "gemini-1.5-pro",
    "ollama/mistral",         # Local fallback
]
```

Then your code is provider-agnostic:

```python
response = await complete(
    messages=[Message.user("Hello")],
)
# Automatically uses configured model + fallbacks
```
