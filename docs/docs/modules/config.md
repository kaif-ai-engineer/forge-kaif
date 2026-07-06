# Config Module

`forge.config` — Typed, validated, layered configuration from environment variables,
`.env` files, and TOML configuration files.

## Overview

The Config module eliminates boilerplate config loading. It uses Pydantic v2 and
`pydantic-settings` to provide a typed, validated configuration system with clear
priority ordering.

## Installation

The config module is part of the core `forge-kaif` package with no extra dependencies:

```bash
pip install forge-kaif
```

## Quick Start

```python
from forge.config import ForgeConfig

# Load config from environment + .env + defaults
config = ForgeConfig()
```

## Config Priority

Values are resolved in the following order (highest priority first):

1. Environment variables (prefixed with `FORGE_`)
2. `.env.{environment}` (e.g., `.env.production`)
3. `.env.local`
4. `.env`
5. `forge.config.toml`
6. Module defaults

## Key Features

### Typed Access

```python
config.environment       # str
config.debug             # bool
config.log.level         # str
config.ai.default_model  # str
```

### Required Key Validation

```python
from forge.config import require

require("DATABASE_URL", "OPENAI_API_KEY")
# Raises ConfigurationError with actionable message if missing
```

### Secret Masking

Secret values are automatically masked in logs and error messages:

```python
config.ai.openai_api_key
# Output: 'sk-...abc123'
```

### Test Overrides

```python
from forge.config import override

with override({"database.url": "sqlite:///:memory:"}):
    # Config is overridden within this context
    ...
```

### TOML Loading

```python
from forge.config import load_toml

settings = load_toml("forge.config.toml")
```

## Configuration Schema

The full `ForgeConfig` model includes nested configurations for each module:

```python
from forge.config import (
    ForgeConfig,
    LogConfig,
    AIConfig,
    RetryConfig,
    CacheConfig,
    HealthConfig,
)
```

## API Reference

::: forge.config
    options:
      show_root_heading: false
      show_bases: false
      show_source: false
