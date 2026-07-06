# Using forge with FastAPI

This guide shows how to integrate forge into a FastAPI application. forge provides
the infrastructure layer — config, logging, retries, health checks — while FastAPI
handles HTTP routing.

## Complete Example

```python
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from forge import ForgeRuntime, ConfigModule, LogModule, AIModule, HealthModule
from forge.log import get as get_logger

logger = get_logger("my_app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize forge runtime on startup
    runtime = ForgeRuntime()
    runtime.register(ConfigModule())
    runtime.register(LogModule())
    runtime.register(HealthModule())
    runtime.use_defaults()
    await runtime.init()

    # Mount health check endpoints
    from forge.health import health_router
    app.mount("/health", health_router)

    logger.info("Application started")
    yield

    # Graceful shutdown
    await runtime.teardown()
    logger.info("Application stopped")


app = FastAPI(
    title="My AI App",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    logger.info("Root endpoint called")
    return {"message": "Hello from forge + FastAPI!"}


@app.post("/chat")
async def chat(request: Request):
    from forge.ai import complete, Message

    body = await request.json()
    response = await complete(
        messages=[Message.user(body["message"])],
        model="gpt-4o",
    )
    return {"response": response.content}
```

## Key Integration Points

### Lifespan Management

Use FastAPI's lifespan context manager to initialize and teardown the forge runtime
alongside your application lifecycle:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime = ForgeRuntime()
    runtime.use_defaults()   # Register all default modules
    await runtime.init()
    yield
    await runtime.teardown()
```

### Health Checks

Mount the forge health router to get Kubernetes-compatible `/health` and `/ready`
endpoints:

```python
from forge.health import health_router
app.mount("/health", health_router)
```

### Structured Logging

Use forge loggers throughout your FastAPI app for consistent structured output:

```python
from forge.log import get as get_logger

logger = get_logger("my_app")

@app.get("/users")
async def get_users():
    logger.info("Fetching users", page=1)
    ...
```

### Environment Configuration

Set up your `.env` file with forge and FastAPI configuration:

```bash
# forge config
FORGE_ENVIRONMENT=production
FORGE_AI__DEFAULT_MODEL=gpt-4o

# FastAPI
HOST=0.0.0.0
PORT=8000
```

## Running the App

```bash
pip install forge-kaif[openai] fastapi uvicorn
uvicorn main:app --reload
```
