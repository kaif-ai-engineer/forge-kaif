# FastAPI Starter

A production-ready FastAPI application built on top of the **Forge** runtime framework. Demonstrates configuration loading, structured logging, health checks, and caching.

## Features

- **Configuration** — Loaded from `forge.config.toml`, `.env`, and environment variables via `ForgeConfig`
- **Structured Logging** — JSON or human-readable output with automatic field injection
- **Health Checks** — Built-in `/health` (liveness) and `/ready` (readiness) endpoints; custom check registration via decorators
- **Caching** — In-memory (default) or Redis-backed caching with the `@cached` decorator
- **Custom Modules** — Example `AppModule` with lifecycle hooks and its own health check

## Prerequisites

- Python 3.11+
- `pip`

## Installation

```bash
# Clone the repository (if you haven't already)
git clone <repo-url> && cd forge-kaif

# Install forge (editable, from project root)
pip install -e .

# Install example dependencies
cd examples/fastapi-starter
pip install -r requirements.txt
```

## Configuration

Copy the example env file and adjust as needed:

```bash
cp .env.example .env
```

Key environment variables:

| Variable | Default | Description |
|---|---|---|
| `FORGE_ENVIRONMENT` | `development` | Runtime environment |
| `FORGE_DEBUG` | `true` | Enable debug mode |
| `FORGE_LOG_LEVEL` | `INFO` | Log level |
| `FORGE_LOG_FORMAT` | `dev` | `dev` (colorized) or `json` |
| `FORGE_CACHE_BACKEND` | `memory` | `memory` or `redis` |
| `FORGE_CACHE_REDIS_URL` | — | Redis URL (required with `redis` backend) |

You can also edit `forge.config.toml` for static configuration.

## Running

```bash
# From examples/fastapi-starter
uvicorn app.main:app --reload
```

The server starts at `http://localhost:8000`.

## Testing the Endpoints

```bash
# Root
curl http://localhost:8000/

# Liveness probe
curl http://localhost:8000/health

# Readiness probe (runs all health checks)
curl http://localhost:8000/ready

# Get an item
curl http://localhost:8000/items/1

# Create an item
curl -X POST http://localhost:8000/items \
  -H "Content-Type: application/json" \
  -d '{"name":"Monitor","price":299.99}'

# Get weather (cached for 120 seconds)
curl http://localhost:8000/weather/London
```

## Project Structure

```
examples/fastapi-starter/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app, routes, lifespan
│   ├── models.py        # Pydantic models
│   └── module.py        # Custom ForgeModule
├── forge.config.toml    # Forge static config
├── .env                 # Environment overrides (git-ignored)
├── .env.example         # Template for .env
├── requirements.txt
└── README.md
```
