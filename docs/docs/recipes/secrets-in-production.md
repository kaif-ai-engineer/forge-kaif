# Secrets in Production

Manage API keys, database passwords, and other secrets securely with forge.

## The Problem

Hardcoding secrets is insecure. Environment variables are better but don't scale.
You need a consistent way to load and validate secrets without exposing them in logs.

## The Solution

forge's config module treats secret values as first-class citizens with automatic
masking in logs.

## Using SecretStr

```python
from pydantic import BaseModel, Field
from pydantic import SecretStr


class DatabaseConfig(BaseModel):
    url: SecretStr
    password: SecretStr
```

## Environment Variable Loading

```bash
# .env (never committed to git)
DATABASE_URL=postgresql://user:password@prod-db:5432/myapp
OPENAI_API_KEY=sk-proj-...
REDIS_URL=redis://:password@prod-redis:6379/0
```

```python
from forge.config import ForgeConfig

config = ForgeConfig()
# Secrets are automatically loaded from environment
```

## Secret Masking in Logs

forge automatically masks secret values in all log output:

```python
logger.info("Connecting to database", url=config.database.url)
# Log output: {"url": "postgresql://user:****@prod-db:5432/myapp"}
```

## Validation at Startup

Ensure required secrets are present before the app starts:

```python
from forge.config import require

require(
    "DATABASE_URL",
    "OPENAI_API_KEY",
    "REDIS_URL",
    "JWT_SECRET",
)
# Raises ConfigurationError with clear message if any are missing
```

## Production Best Practices

1. **Use a secrets manager** (AWS Secrets Manager, Vault, GCP Secret Manager) in production
2. **Never commit `.env` files** to version control
3. **Use `forge check config`** in CI to validate configuration before deployment
4. **Rotate secrets regularly** — forge's config module supports hot-reload
5. **Set `FORGE_DEBUG=false`** in production to prevent accidental secret exposure
