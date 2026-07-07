# Why forge?

## The problem

Every Python backend project reinvents the same infrastructure. You write:

- Config loading from `.env` files
- Structured logging setup
- Retry logic for external API calls
- AI provider wrappers (OpenAI, Anthropic, Gemini)
- Health check endpoints for Kubernetes
- Caching layer with TTL
- Input validation with error formatting

This is not business logic. It is **undifferentiated heavy lifting** — and every team
solves it slightly differently, which means every team solves it slightly wrong.

## The solution

forge is a **unified, modular, AI-first developer infrastructure runtime** that solves
all of these problems in one `pip install`. It is designed from day one to be used by
both human developers and AI coding agents.

## How is forge different?

### forge is not a web framework

| Product | Layer |
|---------|-------|
| **forge** | Infrastructure runtime — config, logging, retries, AI, health, caching |
| FastAPI | Web framework — HTTP routing, request handling, OpenAPI |
| Django | Full-stack framework — ORM, admin, auth, templates |
| LangChain | AI orchestration — chains, agents, tools |

forge sits **below** your web framework. You use forge *inside* your FastAPI routes,
your CLI commands, your background workers. It is the layer that handles everything
except your business logic.

### forge is modular, not monolithic

Use one module, some modules, or all of them — forge is fully modular:

```python
# Use only config
from forge.config import ForgeConfig, load_toml

# Use only AI
from forge.ai import complete, Message

# Use everything
from forge import ForgeRuntime, ConfigModule, LogModule, AIModule
```

Each module has zero required dependencies on other modules at the code level.
They integrate through the runtime but can be used independently.

### forge is agent-ready

AI coding agents (Cursor, GitHub Copilot, Devin) need predictable, well-documented,
fully-typed APIs to generate reliable code. forge provides:

- **Complete type annotations** on all public APIs
- **Agent-readable docstrings** with descriptions, parameter types, and examples
- **`forge.schema.json`** — a machine-readable API manifest
- **Consistent error messages** that agents can parse and respond to

### The five-minute guarantee

Every design decision is evaluated against one question: *Does this make the first
five minutes better or worse?*

```mermaid
flowchart LR
    A["pip install forge-kaif"] --> B["Set API key"]
    B --> C["Write 5 lines of code"]
    C --> D["First AI call works"]
    D --> E["Developer is impressed"]
```

## Compared to alternatives

| Need | Rolling your own | LangChain | forge |
|------|-----------------|-----------|-------|
| Config loading | 50 lines of `os.getenv` | Not provided | 1 line |
| AI completions | 100 lines per provider | 10 lines (complex) | 5 lines |
| Retry logic | 30 lines of backoff | Via LangChain | 1 decorator |
| Health checks | 20 lines per endpoint | Not provided | 0 lines (auto) |
| Caching | 40 lines per backend | Via LangChain | 1 decorator |
| Logging | 20 lines of `logging.basicConfig` | Not provided | 1 line |
| **Total code** | ~300 lines per project | ~100 lines + complexity tax | **~10 lines** |

## Design philosophy

- **Explicit over implicit** — no magic auto-discovery. You register what you use.
- **Fail fast** — configuration errors surface at startup with actionable messages.
- **Zero external deps in core** — Pydantic v2 is the only required dependency.
- **Async by default** — all public APIs are async-native.
- **Types are not optional** — mypy `--strict` passes on the entire codebase.
- **Public APIs are contracts** — breaking changes are MAJOR version bumps.

## When should you NOT use forge?

forge might not be right for you if:

- You need a full web framework (use FastAPI, Django, or Flask — then add forge *underneath*)
- You need an AI agent framework (use PydanticAI or LangChain — forge can complement them)
- You prefer copy-pasting the same 300 lines of boilerplate into every project
- Your project is a 50-line script that will never grow

For everything else — from AI-powered APIs to microservices to background workers —
forge gives you back the time you'd spend on infrastructure.
