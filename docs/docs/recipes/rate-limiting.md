# Rate-Limiting API Calls

Protect external APIs from excessive traffic using the retry module with custom
backoff strategies.

## The Problem

External APIs have rate limits. When you exceed them, requests fail. You need
sensible retry logic that respects rate limits without hammering the API.

## The Solution

Combine forge's `@retry` decorator with the circuit breaker to handle rate limits
gracefully.

## Basic Rate-Limiting

```python
from forge.retry import retry

@retry(attempts=5, backoff="exponential")
async def call_api(endpoint: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://api.example.com{endpoint}")
        response.raise_for_status()
        return response.json()
```

## Rate-Limit Aware with Circuit Breaker

```python
from forge.retry import retry, CircuitBreaker

breaker = CircuitBreaker(
    failure_threshold=10,    # Open circuit after 10 failures
    recovery_time=30.0,      # Wait 30 seconds before retrying
)

@retry(
    attempts=3,
    backoff="exponential",
    circuit_breaker=breaker,
)
async def call_api(endpoint: str):
    ...
```

## Manual Retry with Backoff

```python
from forge.retry import attempt

async def fetch_with_retry(url: str):
    async with attempt(max_attempts=5) as ctx:
        response = await http_client.get(url)
        if response.status_code == 429:  # Rate limited
            ctx.retry()  # Will wait with backoff
        response.raise_for_status()
        return response.json()
```
