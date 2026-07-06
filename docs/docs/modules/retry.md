# Retry Module

`forge.retry` — Exponential backoff, jitter, and circuit breaker for resilient
external service calls.

## Overview

The Retry module handles transient failures in external service calls with
configurable backoff strategies, circuit breaker protection, and automatic logging
of retry attempts. Works on async functions and as an async context manager.

## Installation

```bash
pip install forge-kaif
```

## Quick Start

```python
from forge.retry import retry

@retry(attempts=3, backoff="exponential")
async def fetch_data(url: str):
    # If this raises an exception, it will be retried
    # with exponential backoff (plus jitter)
    return await http_client.get(url)
```

## Key Features

### Backoff Strategies

```python
from forge.retry import retry

# Exponential backoff with full jitter (default)
@retry(attempts=5, backoff="exponential")

# Linear backoff
@retry(attempts=5, backoff="linear")

# Constant delay
@retry(attempts=5, backoff="constant")
```

### Circuit Breaker

```python
from forge.retry import CircuitBreaker

breaker = CircuitBreaker(
    failure_threshold=5,     # Open after 5 failures
    recovery_time=60.0,      # Try again after 60 seconds
)

@retry(attempts=3, circuit_breaker=breaker)
async def call_external_api():
    ...
```

### Manual Retry Context

```python
from forge.retry import attempt, CircuitBreaker

breaker = CircuitBreaker(failure_threshold=5, recovery_time=60)

async with attempt(max_attempts=3, circuit_breaker=breaker) as ctx:
    result = await call_external_api()
    if not result.is_success:
        ctx.retry()  # Trigger a retry
```

### Exception Filtering

```python
@retry(
    attempts=3,
    exceptions=[ConnectionError, TimeoutError],
)
async def call_api():
    # Only retry on ConnectionError and TimeoutError
    # Other exceptions pass through immediately
    ...
```

## API Reference

::: forge.retry
    options:
      show_root_heading: false
      show_bases: false
      show_source: false
