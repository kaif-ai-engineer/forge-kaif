<p align="center">
  <h1 align="center">forge</h1>
  <p align="center">The developer runtime for AI-era Python.</p>
  <p align="center">
    <a href="https://pypi.org/project/forge-kaif"><img src="https://img.shields.io/pypi/v/forge-kaif" alt="PyPI"></a>
    <a href="https://pypi.org/project/forge-kaif"><img src="https://img.shields.io/pypi/pyversions/forge-kaif" alt="Python versions"></a>
    <a href="https://github.com/kaif-ai-engineer/forge-kaif/actions"><img src="https://img.shields.io/github/actions/workflow/status/kaif-ai-engineer/forge-kaif/test.yml?branch=main" alt="CI"></a>
    <a href="LICENSE"><img src="https://img.shields.io/github/license/kaif-ai-engineer/forge-kaif" alt="MIT"></a>
  </p>
</p>

---

**Stop rebuilding your infrastructure. Start shipping.**

forge is a modular Python runtime that eliminates the undifferentiated heavy lifting
of backend development — config, logging, retries, AI model integration, health checks,
caching, and more — so you can focus on building what makes your product unique.

```python
from forge.ai import complete, Message

response = await complete(
    messages=[Message.user("What is 2+2?")],
    model="gpt-4o",
)
print(response.content)
```

## What is forge?

forge is **not** a web framework. It is the infrastructure layer that sits **below**
your web framework — the reusable runtime that every Python backend service needs.

- **Config** — typed, validated, layered configuration from env vars, `.env`, and TOML
- **Logging** — structured JSON logging with automatic trace context propagation
- **Retry** — exponential backoff, jitter, circuit breaker, and timeout management
- **AI** — unified interface across OpenAI, Anthropic, Gemini, and Ollama
- **Health** — Kubernetes-compatible `/health` and `/ready` endpoints
- **Cache** — decorator-based caching with in-memory and Redis backends
- **Validation** — Pydantic-integrated input validation with consistent error responses
- **CLI** — `forge init`, `forge check config`, `forge add module`

## Quick Start

```bash
pip install forge-kaif
```

```python
import asyncio
from forge.ai import complete, Message

async def main():
    response = await complete(
        messages=[Message.user("Hello, world")],
    )
    print(response.content)

asyncio.run(main())
```

## Documentation

Full documentation is available at [useforge.dev/docs](https://useforge.dev/docs).

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

## License

MIT — see [LICENSE](LICENSE) for details.
