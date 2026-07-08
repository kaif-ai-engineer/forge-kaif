"""
End-to-end integration tests for forge forge.

Validates all P0 modules work together in a real FastAPI application
context.  No external services are required — all adapters fall back
to mock behaviour when API keys are absent.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, ValidationError

from forge import ForgeRuntime
from forge.ai import AIModule, CompletionRequest, Message
from forge.cache import CacheModule
from forge.cache.decorators import cached
from forge.config.module import ConfigModule
from forge.config.schema import ForgeConfig
from forge.core.module import ModuleLifecycleState
from forge.health import health_router
from forge.health.module import HealthModule
from forge.log.module import LogModule
from forge.retry.circuit import CircuitBreakerOpenError
from forge.retry.module import RetryError, RetryModule
from forge.validation import ValidationModule, format_validation_error, validate

# ---------------------------------------------------------------------------
# 1. Runtime initialization with all modules
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runtime_init_with_all_default_modules() -> None:
    """Verify use_defaults() registers and initialises every P0 module."""
    runtime = ForgeRuntime()
    runtime.use_defaults()
    await runtime.init()

    try:
        assert runtime.is_initialized

        expected: list[type] = [
            ConfigModule,
            LogModule,
            RetryModule,
            HealthModule,
            CacheModule,
            ValidationModule,
            AIModule,
        ]
        for cls in expected:
            mod = runtime.get(cls)
            assert mod._lifecycle_state == ModuleLifecycleState.READY, (
                f"{cls.__name__} not in READY state"
            )

        # Events bus is wired
        events: list[str] = []

        async def capture(**_: Any) -> None:
            events.append("called")

        runtime.events.on("runtime.ready", capture)
        await runtime.events.emit("runtime.ready")
        await asyncio.sleep(0.02)
        assert "called" in events
    finally:
        await runtime.teardown()


# ---------------------------------------------------------------------------
# 2. Config loading from TOML + environment variables
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_config_loading_from_toml_and_env(tmp_path: Any, monkeypatch: Any) -> None:
    """TOML values are loaded; env vars override where no TOML key exists."""
    toml_content = """
[forge]
debug = true

[forge.log]
level = "DEBUG"
format = "json"
"""
    (tmp_path / "forge.config.toml").write_text(toml_content)

    monkeypatch.setenv("FORGE_AI_TIMEOUT", "99")
    monkeypatch.chdir(tmp_path)

    runtime = ForgeRuntime()
    cm = ConfigModule()
    runtime.register(cm)
    await runtime.init()

    try:
        cfg: ForgeConfig = cm.config

        # From TOML
        assert cfg.debug is True
        assert cfg.log.level == "DEBUG"
        assert cfg.log.format == "json"

        # From env var (no TOML key for ai.timeout)
        assert cfg.ai.timeout == 99

        # Default when not in TOML or env
        assert cfg.environment == "development"
        assert cfg.retry.default_attempts == 3

        # require() validates required env vars
        cm.require(["FORGE_ENVIRONMENT"])  # exists; no error

    finally:
        await runtime.teardown()


# ---------------------------------------------------------------------------
# 3. Structured logging output verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_structured_logging_json_output(capfd: Any, monkeypatch: Any) -> None:
    """Log messages in JSON format produce parseable structured output."""
    monkeypatch.setenv("FORGE_LOG_FORMAT", "json")

    runtime = ForgeRuntime()
    runtime.use_defaults()
    await runtime.init()

    try:
        logger = logging.getLogger("integration.test")
        logger.info("Hello %s", "world", extra={"user_id": 42, "action": "login"})

        # Allow the QueueListener background thread to flush
        await asyncio.sleep(0.1)

        _, err = capfd.readouterr()
        assert err, "No stderr output captured"

        # Find the JSON line from our logger
        lines = err.strip().splitlines()
        entry = None
        for line in lines:
            parsed = json.loads(line)
            if parsed.get("module") == "integration.test":
                entry = parsed
                break

        assert entry is not None, "integration.test log line not found"
        assert entry["level"] == "INFO"
        assert "Hello world" in entry["message"]
        assert entry["user_id"] == 42
        assert entry["action"] == "login"
    finally:
        await runtime.teardown()


# ---------------------------------------------------------------------------
# 4. Retry decorator with circuit breaker functionality
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_decorator_eventually_succeeds() -> None:
    """A flaky function that fails twice then succeeds."""
    runtime = ForgeRuntime()
    runtime.use_defaults()
    await runtime.init()

    try:
        retry_mod: RetryModule = runtime.get(RetryModule)
        attempt_count = 0

        @retry_mod.retry(attempts=3, base_delay=0.01, jitter=False)
        async def flaky(x: int) -> int:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError("not yet")
            return x * 2

        result = await flaky(21)
        assert result == 42
        assert attempt_count == 3
    finally:
        await runtime.teardown()


@pytest.mark.asyncio
async def test_retry_decorator_exhaustion() -> None:
    """Retry raises RetryError after all attempts are consumed."""
    runtime = ForgeRuntime()
    runtime.use_defaults()
    await runtime.init()

    try:
        retry_mod: RetryModule = runtime.get(RetryModule)

        @retry_mod.retry(attempts=2, base_delay=0.01, jitter=False)
        async def always_fails() -> str:
            raise RuntimeError("persistent failure")

        with pytest.raises(RetryError) as exc_info:
            await always_fails()

        assert exc_info.value.attempt_count == 2
        assert "persistent failure" in str(exc_info.value)
    finally:
        await runtime.teardown()


@pytest.mark.asyncio
async def test_circuit_breaker_opens_then_recovers() -> None:
    """Circuit breaker transitions OPEN → HALF_OPEN → CLOSED."""
    runtime = ForgeRuntime()
    runtime.use_defaults()
    await runtime.init()

    try:
        retry_mod: RetryModule = runtime.get(RetryModule)
        cb = retry_mod.circuit_breaker(failure_threshold=3, recovery_time=0.3, name="test-cb")

        assert cb.state.value == "CLOSED"

        # Trigger failures to open the circuit
        for _ in range(3):
            with pytest.raises(ValueError, match="boom"):
                async with cb:
                    raise ValueError("boom")

        assert cb.state.value == "OPEN"

        # Calls while OPEN are rejected immediately
        with pytest.raises(CircuitBreakerOpenError):
            async with cb:
                pass  # pragma: no cover

        # Wait for recovery_time to elapse (triggers HALF_OPEN)
        await asyncio.sleep(0.35)

        # Next call succeeds -> transitions to CLOSED
        async with cb:
            result = "ok"
        assert result == "ok"
        assert cb.state.value == "CLOSED"
    finally:
        await runtime.teardown()


# ---------------------------------------------------------------------------
# 5. AI module with MockAdapter integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ai_module_mock_adapter_completion() -> None:
    """AIModule returns a mock CompletionResponse via MockAdapter (catch-all)."""
    runtime = ForgeRuntime()
    runtime.use_defaults()
    await runtime.init()

    try:
        ai_mod: AIModule = runtime.get(AIModule)

        request = CompletionRequest(
            model="my-custom-model",  # only matches "*" → MockAdapter
            messages=[Message.user("hello")],
        )

        response = await ai_mod.complete(request)

        assert response.model == "my-custom-model"
        assert response.provider == "mock"
        assert "[mock response]" in response.content
        assert response.usage is not None
        assert response.usage.input_tokens > 0
        assert response.usage.output_tokens > 0

        # Metrics are tracked
        metrics = ai_mod.get_metrics()
        assert metrics["request_count"] == 1
        assert metrics["token_count"]["total"] > 0
    finally:
        await runtime.teardown()


@pytest.mark.asyncio
async def test_ai_module_streaming() -> None:
    """AIModule streams mock chunks."""
    runtime = ForgeRuntime()
    runtime.use_defaults()
    await runtime.init()

    try:
        ai_mod: AIModule = runtime.get(AIModule)

        request = CompletionRequest(
            model="my-stream-model",
            messages=[Message.user("stream test")],
            stream=True,
        )

        chunks = []
        async for chunk in ai_mod.stream(request):
            chunks.append(chunk)

        assert len(chunks) >= 1
        assert "[mock response]" in chunks[0].delta
        assert chunks[0].provider == "mock"
    finally:
        await runtime.teardown()


# ---------------------------------------------------------------------------
# 6. Health endpoint responses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_endpoint_liveness() -> None:
    """GET /health returns 200 when runtime is initialised."""
    runtime = ForgeRuntime()
    runtime.use_defaults()
    await runtime.init()

    try:
        app = FastAPI()
        app.include_router(health_router)

        with TestClient(app) as client:
            resp = client.get("/health")

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["status"] == "healthy"
    finally:
        await runtime.teardown()


@pytest.mark.asyncio
async def test_health_endpoint_readiness() -> None:
    """GET /ready returns 200 and includes module check results."""
    runtime = ForgeRuntime()
    runtime.use_defaults()
    await runtime.init()

    try:
        app = FastAPI()
        app.include_router(health_router)

        with TestClient(app) as client:
            resp = client.get("/ready")

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["status"] == "healthy"

        # include_details=True means checks are present
        checks = payload.get("checks", {})
        assert "runtime" in checks
        assert "config" in checks
        assert "log" in checks
        assert "cache" in checks
        assert "ai" in checks
        assert checks["runtime"]["status"] == "ok"
    finally:
        await runtime.teardown()


@pytest.mark.asyncio
async def test_health_endpoint_unhealthy_without_runtime() -> None:
    """GET /health returns 503 when no HealthModule is active."""
    app = FastAPI()
    app.include_router(health_router)

    with TestClient(app) as client:
        resp = client.get("/health")

    assert resp.status_code == 503
    assert resp.json()["status"] == "unhealthy"


# ---------------------------------------------------------------------------
# 7. Cache decorator behaviour (hit / miss / expiry / invalidation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cached_decorator_hit_and_miss() -> None:
    """@cached returns cached result on repeat call with same args."""
    runtime = ForgeRuntime()
    runtime.use_defaults()
    await runtime.init()

    try:
        call_count = 0

        @cached(ttl=60, key="add:{a}:{b}")
        async def add(a: int, b: int) -> int:
            nonlocal call_count
            call_count += 1
            return a + b

        # Miss
        r1 = await add(3, 4)
        assert r1 == 7
        assert call_count == 1

        # Hit
        r2 = await add(3, 4)
        assert r2 == 7
        assert call_count == 1

        # Different args → miss
        r3 = await add(5, 6)
        assert r3 == 11
        assert call_count == 2
    finally:
        await runtime.teardown()


@pytest.mark.asyncio
async def test_cached_decorator_ttl_expiry() -> None:
    """Cache entry expires after TTL elapses."""
    runtime = ForgeRuntime()
    runtime.use_defaults()
    await runtime.init()

    try:
        call_count = 0

        @cached(ttl=1, key="ttl:{x}")
        async def compute(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 10

        # Miss
        assert await compute(7) == 70
        assert call_count == 1

        # Hit
        assert await compute(7) == 70
        assert call_count == 1

        # Wait for TTL expiry
        await asyncio.sleep(1.1)

        # Miss again
        assert await compute(7) == 70
        assert call_count == 2
    finally:
        await runtime.teardown()


@pytest.mark.asyncio
async def test_cached_decorator_invalidate() -> None:
    """Manually invalidating a cached entry forces a re-compute."""
    runtime = ForgeRuntime()
    runtime.use_defaults()
    await runtime.init()

    try:
        call_count = 0

        @cached(key="fetch:{item_id}")
        async def fetch_item(item_id: int) -> int:
            nonlocal call_count
            call_count += 1
            return item_id

        assert await fetch_item(42) == 42
        assert call_count == 1

        assert await fetch_item(42) == 42
        assert call_count == 1

        invalidate_fn = fetch_item.invalidate
        await invalidate_fn(42)

        assert await fetch_item(42) == 42
        assert call_count == 2
    finally:
        await runtime.teardown()


# ---------------------------------------------------------------------------
# 8. Validation error responses (422 status, detailed payload)
# ---------------------------------------------------------------------------


class UserPayload(BaseModel):
    name: str = Field(min_length=2)
    email: str = Field(pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    age: int = Field(gt=0, lt=150)


def test_validation_http_exception_on_invalid_data() -> None:
    """@validate raises HTTPException(422) with detailed errors."""

    @validate(UserPayload)
    def create_user(data: UserPayload) -> str:
        return data.name

    invalid = {"name": "X", "email": "not-an-email", "age": -5}

    with pytest.raises(HTTPException) as exc_info:
        create_user(invalid)

    assert exc_info.value.status_code == 422
    details = exc_info.value.detail
    assert isinstance(details, list)

    loc_map: dict[str, Any] = {}
    for d in details:
        key = d["loc"][-1] if isinstance(d["loc"], list) else d["loc"]
        loc_map[key] = d

    assert "name" in loc_map
    assert "email" in loc_map
    assert "age" in loc_map

    for d in details:
        assert d["loc"][0] == "body"
        assert d["msg"] != ""
        assert d["type"] != ""


@pytest.mark.asyncio
async def test_validation_async_with_http_exception() -> None:
    """@validate on async functions also raises HTTPException(422)."""

    @validate(UserPayload)
    async def async_create(data: UserPayload) -> str:
        return data.name

    invalid = {"name": "X", "email": "bad", "age": 200}

    with pytest.raises(HTTPException) as exc_info:
        await async_create(invalid)

    assert exc_info.value.status_code == 422
    details = exc_info.value.detail
    assert len(details) == 3


def test_format_validation_error_produces_consistent_schema() -> None:
    """format_validation_error returns ValidationErrorResponse with body prefix."""
    from forge.validation import ValidationErrorResponse

    try:
        UserPayload(name="A", email="x", age=-1)
    except ValidationError as exc:
        error_response = format_validation_error(exc)

    assert isinstance(error_response, ValidationErrorResponse)
    assert len(error_response.detail) == 3

    for detail in error_response.detail:
        assert detail.loc[0] == "body"
        assert detail.msg != ""
        assert detail.type != ""


def test_validation_passes_through_valid_pydantic_instance() -> None:
    """When given an already-validated instance, @validate passes it through."""

    @validate(UserPayload)
    def handle(data: UserPayload) -> str:
        return data.name

    valid = UserPayload(name="Alice", email="alice@example.com", age=30)
    result = handle(valid)
    assert result == "Alice"
