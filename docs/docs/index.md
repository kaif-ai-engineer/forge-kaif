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

## Next Steps

- [Getting Started](getting-started/) — 5-minute guide
- [Modules](modules/) — explore each module
- [API Reference](api/) — comprehensive API docs
