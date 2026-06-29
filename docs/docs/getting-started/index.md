# Getting Started

This guide will take you from zero to a working forge application in under 5 minutes.

## Prerequisites

- Python 3.11 or later
- An OpenAI API key (or any supported provider)

## Step 1: Install

```bash
pip install forge-runtime
```

??? tip "Optional extras"
    Install provider-specific extras as needed:

    ```bash
    pip install forge-runtime[openai]      # OpenAI support
    pip install forge-runtime[anthropic]   # Anthropic support
    pip install forge-runtime[ollama]      # Local Ollama support
    pip install forge-runtime[all]         # All providers
    ```

## Step 2: Set your API key

```bash
export OPENAI_API_KEY=sk-your-key-here
```

Or create a `.env` file:

```bash
echo "OPENAI_API_KEY=sk-your-key-here" > .env
```

## Step 3: Create your app

Create a file called `main.py`:

```python
import asyncio
from forge.ai import complete, Message

async def main():
    response = await complete(
        messages=[Message.user("What is 2+2?")],
        model="gpt-4o",
    )
    print(response.content)

asyncio.run(main())
```

## Step 4: Run it

```bash
python main.py
```

You should see:

```
4
```

That's it. You just made your first AI call with forge — with structured logging,
retry handling, and token counting built in, all without any additional configuration.

## What just happened?

Behind the scenes, forge automatically:

1. **Loaded configuration** from your environment (no config files needed for simple usage)
2. **Initialized the runtime** with default modules (AI, Config, Log, Retry)
3. **Created a logger** with trace context propagation
4. **Sent the request** to OpenAI with automatic retry on transient failures
5. **Returned the response** with token usage metadata

## Next Steps

- [Explore all modules](../modules/config.md) — deep-dive into each component
- [Use with FastAPI](../guides/fastapi.md) — integrate forge into your web app
- [Write a custom module](../guides/custom-module.md) — extend forge for your needs
- [Browse recipes](../recipes/structured-outputs.md) — common patterns and solutions
