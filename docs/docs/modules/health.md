# Health Module

`forge.health` — Kubernetes-compatible `/health` and `/ready` endpoints with
custom check registration.

## Overview

The Health module provides standardized health and readiness checking that works
with Kubernetes liveness and readiness probes out of the box. Every registered
module automatically contributes its `health_check()` method. Custom checks can be
added with a simple decorator.

## Installation

```bash
pip install forge-kaif
```

## Quick Start

```python
from forge.health import HealthModule, health_router

# Mount in your FastAPI app
app.mount("/health", health_router)
```

Built-in behavior:

| Endpoint | Purpose | Failure Behavior |
|----------|---------|-----------------|
| `/health` (liveness) | Is the process alive? | Kubernetes restarts the pod |
| `/ready` (readiness) | Can the process serve traffic? | Kubernetes stops sending traffic |

## Key Features

### Custom Health Checks

```python
from forge.health import check, HealthResult

@check("database")
async def check_database():
    if await db.is_connected():
        return HealthResult.ok()
    return HealthResult.error("Database connection lost")

@check("cache")
async def check_cache():
    if cache.latency_ms > 100:
        return HealthResult.degraded("Cache latency high")
    return HealthResult.ok()
```

### Module-Level Health

Every `ForgeModule` can implement a `health_check()` method that is automatically
registered:

```python
class MyModule(ForgeModule):
    name = "my_module"

    async def health_check(self) -> HealthResult:
        if self.is_healthy():
            return HealthResult.ok()
        return HealthResult.error("Module unhealthy")
```

### Check Timeout

Each health check runs with a configurable timeout to prevent hanging probes:

```python
config = HealthConfig(check_timeout_seconds=5)
```

## API Reference

::: forge.health
    options:
      show_root_heading: false
      show_bases: false
      show_source: false
