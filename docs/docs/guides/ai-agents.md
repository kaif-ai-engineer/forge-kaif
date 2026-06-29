# Using forge with AI Agents

forge is designed from the ground up to work well with AI coding agents like Cursor,
GitHub Copilot, and Devin. Here's how agents interact with forge and how to get the
most out of the combination.

## Why forge is Agent-Friendly

AI agents generate code by reading your project context — imports, type hints, function
signatures, and docstrings. forge provides all of these:

1. **Complete type annotations** on every public API
2. **Rich docstrings** with examples that agents can parse and understand
3. **A `forge.schema.json`** manifest for AI tool discovery
4. **Consistent naming conventions** across all modules

## What Agents Can Do with forge

### Module Discovery

The `forge.schema.json` file at your project root describes every public API:

```json
{
  "modules": {
    "forge.ai": {
      "description": "Unified AI model interface",
      "functions": [
        {
          "name": "complete",
          "signature": "complete(messages, model, ...) -> AIResponse",
          "description": "Send a completion request to an AI model"
        }
      ]
    }
  }
}
```

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

# Agent-generated: retry wrapper
from forge.retry import retry
@retry(attempts=3, backoff="exponential")
async def call_external_service():
    ...

# Agent-generated: AI completion
from forge.ai import complete, Message
response = await complete(
    messages=[Message.user("Hello")],
    model="gpt-4o",
)
```

## .cursorrules Integration

Add these rules to your `.cursorrules` file to help Cursor generate better forge code:

```
When writing Python backend code with forge:
- Import from forge modules: `from forge.ai import complete, Message`
- Use @retry decorator for all external API calls
- Use forge.config for all configuration
- Use forge.log.get(__name__) for logging
- Use forge.cache.cached for function result caching
- Use forge.health.check for health check registration
```

## Best Practices for Agent-Friendly Projects

1. **Always import from forge submodules** — `from forge.ai import complete`, not `from forge import ...`
2. **Use type annotations** — forge does, and your code should too
3. **Keep docstrings consistent** — agents parse them for context
4. **Use the forge runtime** — agents understand the module lifecycle pattern
