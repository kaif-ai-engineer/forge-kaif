# Production Deployment

This guide covers deploying forge-powered applications to production.

## Environment Configuration

### Configuration Priority

forge resolves configuration in this order (highest to lowest):

1. Environment variables (prefixed with `FORGE_`)
2. `.env.{environment}` (e.g., `.env.production`)
3. `.env.local`
4. `.env`
5. `forge.config.toml`
6. Module defaults

### Production Setup

```bash
# .env.production
FORGE_ENVIRONMENT=production
FORGE_DEBUG=false
FORGE_LOG__LEVEL=INFO
FORGE_AI__DEFAULT_MODEL=gpt-4o
FORGE_CACHE__DEFAULT_TTL=300
```

### Required Key Validation

Ensure critical configuration is present at startup:

```python
from forge.config import require

require(
    "DATABASE_URL",
    "OPENAI_API_KEY",
    "REDIS_URL",
)
```

## Health Checks for Kubernetes

Mount the forge health router and configure Kubernetes probes:

```python
from forge.health import HealthModule, health_router

app.mount("/health", health_router)
```

Kubernetes deployment configuration:

```yaml
# deployment.yaml
spec:
  containers:
    - name: my-app
      livenessProbe:
        httpGet:
          path: /health
          port: 8000
        initialDelaySeconds: 5
        periodSeconds: 10
      readinessProbe:
        httpGet:
          path: /ready
          port: 8000
        initialDelaySeconds: 10
        periodSeconds: 5
```

## Logging in Production

forge outputs structured JSON logs by default in production. These integrate with
any log aggregator:

```json
{
  "timestamp": "2025-01-15T10:30:00.123Z",
  "level": "INFO",
  "module": "my_app",
  "message": "Request completed",
  "trace_id": "abc-123-def-456",
  "duration_ms": 245
}
```

## Caching

Use Redis-backed caching in production for persistence across restarts:

```python
from forge.cache import cached

@cached(ttl=3600, backend="redis")
async def get_expensive_data():
    ...
```

## Graceful Shutdown

forge handles `SIGTERM` and `SIGINT` automatically to perform a graceful shutdown
with configurable timeout:

```python
runtime = ForgeRuntime()
runtime.use_defaults()
await runtime.init(shutdown_timeout=30)  # 30 second grace period
```
