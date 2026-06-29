# forge

The developer runtime for AI-era Python.

forge is a modular Python runtime that eliminates the undifferentiated heavy lifting
of backend development — config, logging, retries, AI model integration, health checks,
caching, and more.

## Quick Install

```bash
pip install forge-runtime
```

## Your First AI Call

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

## Why forge?

forge sits **below** your web framework. It is not a replacement for FastAPI, Django, or Flask.
It is the infrastructure layer that every Python backend needs — unified, modular, and
production-ready from `pip install`.

[Read the full positioning →](why-forge.md)

## What's Included

| Module | Description |
|--------|-------------|
| [Config](modules/config.md) | Typed, validated, layered configuration from env vars, `.env`, and TOML |
| [Logging](modules/log.md) | Structured JSON logging with automatic trace context propagation |
| [Retry](modules/retry.md) | Exponential backoff, jitter, and circuit breaker for resilience |
| [AI](modules/ai.md) | Unified interface across OpenAI, Anthropic, Gemini, and Ollama |
| [Health](modules/health.md) | Kubernetes-compatible `/health` and `/ready` endpoints |
| [Cache](modules/cache.md) | Decorator-based caching with in-memory LRU and Redis backends |
| [Validation](modules/validation.md) | Pydantic-integrated input validation with consistent error responses |

## Next Steps

- [Getting Started](getting-started/index.md) — 5-minute guide
- [Modules](modules/config.md) — explore each module
- [API Reference](api/config.md) — comprehensive API docs
- [FAQ](faq.md) — common questions and comparisons
