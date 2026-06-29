# Cache Module

`forge.cache` — Decorator-based caching with in-memory LRU and Redis backends.

## Overview

The Cache module provides a simple, decorator-based caching API with pluggable
backends. Cache function results with a single decorator, and switch between
in-memory and Redis backends by changing configuration.

## Installation

```bash
pip install forge-runtime
# For Redis backend:
pip install forge-runtime[redis]
```

## Quick Start

```python
from forge.cache import cached

@cached(ttl=300)  # Cache for 5 minutes
async def get_user(user_id: int):
    return await db.fetch_user(user_id)
```

## Key Features

### Configurable TTL

```python
@cached(ttl=60)       # 60 seconds
@cached(ttl=3600)     # 1 hour
@cached(ttl=86400)    # 24 hours
```

### Custom Cache Keys

```python
@cached(key="user:{user_id}")
async def get_user(user_id: int):
    ...
```

### Backend Selection

```python
@cached(backend="memory")   # In-memory LRU (default)
@cached(backend="redis")    # Redis-backed
```

### Invalidation

```python
from forge.cache import invalidate

await invalidate("user:42")  # Remove a specific entry
```

### Manual Cache Operations

```python
from forge.cache import CacheModule

cache = CacheModule()
await cache.set("key", value, ttl=300)
value = await cache.get("key")
exists = await cache.has("key")
await cache.delete("key")
await cache.clear()
```

## API Reference

::: forge.cache
    options:
      show_root_heading: false
      show_bases: false
      show_source: false
