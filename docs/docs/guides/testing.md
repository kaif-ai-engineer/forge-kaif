# Testing Your App

forge is designed to make testing easy. Each module supports test-specific features
like config overrides and mock providers.

## Config Overrides in Tests

```python
import pytest
from forge.config import ForgeConfig, override


def test_with_overridden_config():
    with override({"database.url": "sqlite:///:memory:"}):
        config = ForgeConfig()
        assert config.database.url == "sqlite:///:memory:"
```

## Using the MockAdapter for AI Tests

Test AI completions without any API keys or network calls:

```python
import pytest
from forge.ai import MockAdapter


@pytest.mark.asyncio
async def test_ai_completion():
    adapter = MockAdapter()
    response = await adapter.complete(
        messages=[{"role": "user", "content": "Hello"}],
        model="mock",
    )
    assert response.content is not None
```

## Testing Retry Logic

```python
import pytest
from forge.retry import RetryModule, retry


class TemporaryError(Exception):
    pass


call_count = 0


@retry(attempts=3, backoff="constant")
async def flaky_function():
    global call_count
    call_count += 1
    if call_count < 3:
        raise TemporaryError("Not ready yet")
    return "success"


@pytest.mark.asyncio
async def test_retry_eventually_succeeds():
    global call_count
    call_count = 0
    result = await flaky_function()
    assert result == "success"
    assert call_count == 3
```

## Testing Health Checks

```python
import pytest
from forge.health import HealthResult, check


@check("test_check")
async def always_ok():
    return HealthResult.ok()


@pytest.mark.asyncio
async def test_health_check():
    result = await always_ok()
    assert result.is_ok
```

## Testing with the Full Runtime

```python
import pytest
from forge import ForgeRuntime, ConfigModule


@pytest.fixture
async def runtime():
    runtime = ForgeRuntime()
    runtime.register(ConfigModule())
    await runtime.init()
    yield runtime
    await runtime.teardown()


@pytest.mark.asyncio
async def test_runtime_initializes(runtime):
    assert runtime.is_initialized
```
