# FAQ

## General

### Is forge a web framework?

**No.** forge is not a web framework. It is the infrastructure layer that sits
*below* your web framework. You use forge inside FastAPI, Django, Flask, or any
other Python web framework to handle config, logging, retries, AI model integration,
health checks, and caching.

### Can I use just one module?

**Yes.** Each module is independently usable. You can use only `forge.config` without
any other module, or only `forge.ai` without the runtime. There are no mandatory
dependencies between modules at the code level.

### How do I install forge?

```bash
pip install forge-kaif
```

See the [Getting Started guide](getting-started/index.md) for provider-specific extras.

### Do I need a runtime to use forge modules?

No, but the runtime provides lifecycle management, dependency injection, and
cross-module integration. For simple use cases, you can use individual modules
directly:

```python
from forge.ai import complete, Message
```

For production applications with multiple modules, using the [ForgeRuntime](api/core.md)
is recommended.

## Comparisons

### How does forge compare to LangChain?

**Positioning:** forge is *not* an AI agent framework. LangChain is an AI orchestration
framework for chains, agents, and tools. forge is an infrastructure runtime that
happens to include a clean AI model abstraction layer.

**Key differences:**

| Aspect | LangChain | forge |
|--------|-----------|-------|
| Focus | AI orchestration, agents, tools | General infrastructure (config, logging, retries, AI, health, cache) |
| Complexity | High — many abstractions | Low — one module per concern |
| Config | Not provided | First-class, typed, validated |
| Logging | Not provided | Structured JSON with trace propagation |
| Retries | Via LangChain-specific APIs | Generic decorator, works with anything |
| Dependencies | Heavy | Minimal (Pydantic v2 only in core) |
| AI scope | Orchestration (chains, agents, RAG) | Completion + streaming + structured output |

**Can they be used together?** Yes. forge can provide the infrastructure (config,
logging, retries) while LangChain handles AI orchestration.

### How does forge compare to PydanticAI?

**Positioning:** PydanticAI is an AI agent framework focused on type-safe agent
development. forge is a general infrastructure runtime with an AI module.

| Aspect | PydanticAI | forge |
|--------|-----------|-------|
| Focus | AI agents with structured outputs | General infrastructure + AI module |
| Config | Not provided | First-class, typed, validated |
| Logging | Not provided | Structured JSON |
| Retries | Basic | Full circuit breaker + strategies |
| Health | Not provided | K8s-compatible endpoints |
| Caching | Not provided | Decorator-based with backends |
| Validation | Core feature (Pydantic) | Pydantic-integrated decorator |

**Can they be used together?** Yes. forge provides the infrastructure that PydanticAI
agents need — config, logging, retries, health checks.

### How does forge compare to FastAPI?

**They are complementary, not competing.** FastAPI is a web framework. forge is an
infrastructure runtime that you use *inside* FastAPI. See the [Using with FastAPI
guide](guides/fastapi.md) for details.

### How does forge compare to Spring Boot?

Spring Boot is the closest analogy to forge — but for Java. forge brings Spring
Boot-style autoconfiguration and module management to Python, with an AI-first
design, minimal dependencies, and async-native APIs.

### How does forge compare to rolling my own?

If you enjoy writing config loaders, logger setup, retry logic, and AI provider
wrappers for every project, forge is not for you. If you'd rather write business
logic, forge gives you production-grade infrastructure in one `pip install`.

## Technical

### What Python versions are supported?

Python 3.11 and later.

### What are forge's dependencies?

The core forge runtime has only one required dependency: **Pydantic v2**.
Provider-specific dependencies (OpenAI, Anthropic, etc.) are optional extras.

### Is forge async-only?

forge's public APIs are async-native (using `asyncio`). However, you can use
individual modules in synchronous code where appropriate.

### Does forge support OpenTelemetry?

forge's logging module outputs structured JSON that integrates with any log
aggregator. OpenTelemetry integration is planned for a future release.

### Can I contribute?

Yes! See [CONTRIBUTING.md](https://github.com/forge-kaif/forge/blob/main/CONTRIBUTING.md)
for guidelines. All contributions are welcome — bug fixes, features, docs, examples.

### How do I report a bug?

Open an issue on [GitHub](https://github.com/forge-kaif/forge/issues) with:
- A minimal reproduction
- Expected vs. actual behavior
- Python version and forge version
- Any relevant error messages or logs

### What is forge's license?

MIT — free for all use cases, including commercial.
