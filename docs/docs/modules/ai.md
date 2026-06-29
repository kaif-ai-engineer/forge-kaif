# AI Module

`forge.ai` — Unified AI model interface across OpenAI, Anthropic, Gemini, and Ollama.

## Overview

The AI module provides a single, consistent API for completions and streaming across
all major LLM providers. It handles provider-specific differences internally, so you
write code once and switch providers by changing a config value.

## Installation

```bash
pip install forge-runtime[openai]     # OpenAI support
pip install forge-runtime[anthropic]  # Anthropic support
pip install forge-runtime[all]        # All providers
```

## Quick Start

```python
import asyncio
from forge.ai import complete, Message

async def main():
    response = await complete(
        messages=[Message.user("What is the capital of France?")],
        model="gpt-4o",
    )
    print(response.content)

asyncio.run(main())
```

## Key Features

### Structured Output

```python
from pydantic import BaseModel
from forge.ai import complete, Message

class SentimentResult(BaseModel):
    sentiment: str
    confidence: float

result = await complete(
    messages=[Message.user("Analyze: I love this product!")],
    output_schema=SentimentResult,
)
# result is a SentimentResult instance with validated fields
```

### Streaming

```python
from forge.ai import stream, Message

async for chunk in stream(
    messages=[Message.user("Tell me a story")],
    model="gpt-4o",
):
    print(chunk.delta, end="")
```

### Multi-Provider Fallback

```python
response = await complete(
    messages=[Message.user("Hello")],
    model="gpt-4o",
    fallback_models=["claude-3-5-sonnet", "gemini-1.5-pro"],
)
```

### Token Counting & Cost Estimation

```python
from forge.ai import TokenCounter

counter = TokenCounter()
tokens = counter.count("Hello, world")
cost = counter.estimate_cost(tokens, model="gpt-4o")
```

### Adapter Architecture

The module uses an adapter pattern to abstract provider differences:

- `OpenAIAdapter` — OpenAI GPT-4, GPT-4o, GPT-3.5
- `AnthropicAdapter` — Claude 3.5 Sonnet, Claude 3 Opus
- `GeminiAdapter` — Gemini 1.5 Pro, Gemini 1.5 Flash
- `OllamaAdapter` — Local models via Ollama
- `MockAdapter` — Fully offline for testing

## API Reference

::: forge.ai
    options:
      show_root_heading: false
      show_bases: false
      show_source: false
