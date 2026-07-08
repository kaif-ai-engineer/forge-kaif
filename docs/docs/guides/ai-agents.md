# Using forge with AI Agents

forge is designed from the ground up to work well with AI coding agents like Cursor,
GitHub Copilot, and Devin. Here's how agents interact with forge and how to get the
most out of the combination.

## Why forge is Agent-Friendly

AI agents generate code by reading your project context — imports, type hints, function
signatures, and docstrings. forge provides all of these:

1. **Complete type annotations** on every public API
2. **Rich docstrings** with examples that agents can parse and understand
3. **A `forge.schema.json`** manifest for AI tool discovery covering all 12 modules
4. **Consistent naming conventions** across all modules
5. **Machine-parseable error messages** — every exception follows the same format
6. **An auto-generated `.cursorrules`** file in every `forge init` project

## What Agents Can Do with forge

### Module Discovery via Schema

The `forge.schema.json` file at your project root describes every public API in the
entire framework — including signatures, return types, error types, and examples:

```json
{
  "modules": {
    "forge.ai": {
      "description": "Unified AI model interface across OpenAI, Anthropic, Gemini, and Ollama.",
      "error_types": [
        {"name": "RateLimitError", "description": "Raised when the provider rate-limits..."},
        {"name": "StructuredOutputError", "description": "Raised when structured output fails..."}
      ],
      "functions": [
        {
          "name": "complete",
          "signature": "complete(messages: list[Message], model: str | None = None, output_schema: type[BaseModel] | None = None, ...) -> CompletionResponse | BaseModel",
          "description": "Send a completion request to an AI model."
        }
      ],
      "classes": [
        {
          "name": "Message",
          "signature": "Message(role: Literal['system','user','assistant'], content: str)",
          "description": "An immutable chat message."
        }
      ]
    }
  }
}
```

### .cursorrules Integration

Every `forge init` project includes a `.cursorrules` file that tells AI agents exactly
how to write forge-compatible code. The file covers:

- **Import conventions** — correct module paths and banned patterns
- **Retry usage** — `@retry` decorator patterns with and without circuit breakers
- **Config access** — runtime config via `get_config()`, test overrides
- **Logging conventions** — structured fields, context binding, secret masking
- **Structured output** — Pydantic schema with auto-retry on validation failure
- **Error handling** — all errors use a parseable format
- **Cache usage** — `@cached` and `invalidate` patterns
- **AI streaming** — `async for chunk in stream()`
- **Module patterns** — `ForgeModule` subclass template

### Code Generation Examples

Agents can reliably generate forge code because the API is predictable:

```python
# Agent-generated: config access
from forge.config import ForgeConfig
config = ForgeConfig()

# Agent-generated: structured logging
from forge.log import get
logger = get("my_module")
logger.info("Operation completed", duration_ms=42)

# Agent-generated: retry wrapper with circuit breaker
from forge.retry import retry, CircuitBreaker
breaker = CircuitBreaker(failure_threshold=5, recovery_time=60.0)

@retry(attempts=3, backoff="exponential", circuit_breaker=breaker)
async def call_external_service():
    ...

# Agent-generated: AI completion with structured output
from pydantic import BaseModel
from forge.ai import complete, Message

class SentimentResult(BaseModel):
    sentiment: str
    confidence: float

result = await complete(
    messages=[Message.user("Analyze: I love this!")],
    output_schema=SentimentResult,
)

# Agent-generated: cached function
from forge.cache import cached

@cached(ttl=300, key="user:{user_id}")
async def get_user(user_id: int) -> dict:
    return await db.fetch_user(user_id)

# Agent-generated: health check registration
from forge.health import check, HealthResult

@check("database")
async def check_database() -> HealthResult:
    ...
```

### Error Message Parsing

All forge exceptions follow a consistent parseable format that agents can understand:

```
{ExceptionClass}: {what happened — one sentence, specific}

  {why it happened — context}

  To fix this:
    {step 1}
    {step 2}

  Docs: {url}
```

Example:

```
ConfigurationError: Missing required environment variable: OPENAI_API_KEY

  This key is required by the forge.ai module.

  To fix this:
    1. Set the variable in your .env file:
       OPENAI_API_KEY=sk-your-key-here

    2. Or set it in your environment:
       export OPENAI_API_KEY=sk-your-key-here

  Get an API key at: https://platform.openai.com/api-keys
```

## Best Practices for Agent-Friendly Projects

1. **Always import from forge submodules** — `from forge.ai import complete`, not `from forge import ...`
2. **Use type annotations** — forge does, and your code should too
3. **Keep docstrings consistent** — agents parse them for context
4. **Use the forge runtime** — agents understand the module lifecycle pattern
5. **Keep the `.cursorrules` file** — it ships with `forge init` and helps agents write consistent code
6. **Reference `forge.schema.json`** — point your agent to it for API discovery
