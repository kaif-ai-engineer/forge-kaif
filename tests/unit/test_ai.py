from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import BaseModel, Field

from forge.ai import (
    AIModule,
    AIProviderError,
    AIResponse,
    AllModelsFailedError,
    AnthropicAdapter,
    BaseAdapter,
    CompletionResponse,
    GeminiAdapter,
    Message,
    MockAdapter,
    ModelNotFoundError,
    ModelRouter,
    OpenAIAdapter,
    StreamChunk,
    StructuredOutputError,
    TokenCounter,
    TokenLimitError,
    complete,
    stream,
)
from forge.config.module import ConfigModule
from forge.core.exceptions import RuntimeNotInitializedError
from forge.core.module import HealthResult
from forge.core.runtime import ForgeRuntime
from forge.retry.module import RetryModule


# Pydantic schema for structured output tests
class Hero(BaseModel):
    name: str
    age: int
    powers: list[str] = Field(default_factory=list)


# 1. Test message convenience constructors
def test_message_convenience_constructors() -> None:
    sys = Message.system("system prompt")
    assert sys.role == "system"
    assert sys.content == "system prompt"

    usr = Message.user("hello")
    assert usr.role == "user"
    assert usr.content == "hello"

    ast = Message.assistant("hi there")
    assert ast.role == "assistant"
    assert ast.content == "hi there"


# 2. Test token counter count methods
def test_token_counter_count() -> None:
    assert TokenCounter.count_tokens("hello") == 1
    assert TokenCounter.count_tokens("hello world!") == 3
    msgs = [Message.user("hello"), Message.assistant("hi")]
    # 2 msgs * 4 overhead + chars_per_token
    # "hello" is 5 chars -> 1 token
    # "hi" is 2 chars -> 1 token
    # Total = 8 + 2 = 10
    assert TokenCounter.count_messages(msgs) == 10


# 3. Test token counter cost estimation
def test_token_counter_cost_estimation() -> None:
    from forge.ai.models import Usage

    u = Usage(input_tokens=1_000_000, output_tokens=1_000_000)
    cost = TokenCounter.estimate_cost(u, "gpt-4o")
    # input: 2.50, output: 10.00 per 1M tokens -> 12.50
    assert cost == 12.50

    cost_unknown = TokenCounter.estimate_cost(u, "unknown-model")
    assert cost_unknown == 0.0


# 4. Test token counter check budget raises TokenLimitError
def test_token_counter_check_budget() -> None:
    from forge.ai.models import CompletionRequest

    req = CompletionRequest(
        model="gpt-4o",
        messages=[Message.user("hello " * 1000)],  # 5000 chars -> 1250 tokens
    )
    with pytest.raises(TokenLimitError):
        TokenCounter.check_budget(req, 100)  # limit of 100 tokens

    # Should not raise if within budget
    TokenCounter.check_budget(req, 2000)


# 5. Test adapter resolution patterns
def test_adapter_resolution() -> None:
    router = ModelRouter()
    openai = OpenAIAdapter(api_key="sk-test")
    anthropic = AnthropicAdapter(api_key="sk-test")
    gemini = GeminiAdapter(api_key="sk-test")
    mock = MockAdapter()

    router.register("gpt-4o*", openai)
    router.register("claude*", anthropic)
    router.register("gemini*", gemini)
    router.register("*", mock)

    assert router.resolve("gpt-4o") is openai
    assert router.resolve("gpt-4o-mini") is openai
    assert router.resolve("claude-3-opus") is anthropic
    assert router.resolve("gemini-1.5-pro") is gemini
    assert router.resolve("unknown-model") is mock


# 6. Test MockAdapter complete
@pytest.mark.asyncio
async def test_mock_adapter_complete() -> None:
    from forge.ai.models import CompletionRequest

    adapter = MockAdapter(response_text="Hello, target!")
    req = CompletionRequest(model="mock", messages=[Message.user("hi")])
    res = await adapter.complete(req)

    assert res.content == "Hello, target!"
    assert res.provider == "mock"
    assert res.usage is not None
    assert res.usage.input_tokens > 0


# 7. Test MockAdapter stream
@pytest.mark.asyncio
async def test_mock_adapter_stream() -> None:
    from forge.ai.models import CompletionRequest

    adapter = MockAdapter(response_text="Hello stream")
    req = CompletionRequest(model="mock", messages=[Message.user("hi")])

    chunks = []
    async for chunk in adapter.stream(req):
        assert isinstance(chunk, StreamChunk)
        chunks.append(chunk)

    assert len(chunks) == 1
    assert chunks[0].delta == "Hello stream"
    assert chunks[0].finish_reason == "stop"
    assert chunks[0].provider == "mock"


# 8. Test ModelRouter complete
@pytest.mark.asyncio
async def test_router_complete() -> None:
    from forge.ai.models import CompletionRequest

    router = ModelRouter()
    adapter = MockAdapter(response_text="router response")
    router.register("mock*", adapter)

    req = CompletionRequest(model="mock-model", messages=[Message.user("hi")])
    res = await router.complete(req)
    assert res.content == "router response"


# 9. Test ModelRouter stream
@pytest.mark.asyncio
async def test_router_stream() -> None:
    from forge.ai.models import CompletionRequest

    router = ModelRouter()
    adapter = MockAdapter(response_text="router stream")
    router.register("mock*", adapter)

    req = CompletionRequest(model="mock-model", messages=[Message.user("hi")])
    chunks = []
    async for chunk in router.stream(req):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert chunks[0].delta == "router stream"


# 10. Test ModelRouter no adapter raises ModelNotFoundError
@pytest.mark.asyncio
async def test_router_no_adapter_raises() -> None:
    from forge.ai.models import CompletionRequest

    router = ModelRouter()
    req = CompletionRequest(model="unregistered", messages=[Message.user("hi")])
    with pytest.raises(ModelNotFoundError):
        await router.complete(req)

    with pytest.raises(ModelNotFoundError):
        async for _ in router.stream(req):
            pass


# 11. Test ModelRouter fallback chain success
@pytest.mark.asyncio
async def test_router_fallback_success() -> None:
    from forge.ai.models import CompletionRequest

    class FailingAdapter(BaseAdapter):
        @property
        def provider(self) -> str:
            return "failing"

        async def complete(self, request: CompletionRequest) -> Any:
            raise AIProviderError("API call failed")

        async def stream(self, request: CompletionRequest) -> Any:
            raise NotImplementedError

        def count_tokens(self, text: str) -> int:
            return 0

    router = ModelRouter()
    failing = FailingAdapter()
    success = MockAdapter(response_text="success fallback")

    router.register("primary", failing)
    router.register("secondary", success)

    req = CompletionRequest(model="primary", messages=[Message.user("hi")])
    res = await router.complete(req, fallback_models=["secondary"])
    assert res.content == "success fallback"
    assert res.model == "secondary"


# 12. Test ModelRouter fallback chain all fail raises AllModelsFailedError
@pytest.mark.asyncio
async def test_router_fallback_fails_all() -> None:
    from forge.ai.models import CompletionRequest

    class FailingAdapter(BaseAdapter):
        @property
        def provider(self) -> str:
            return "failing"

        async def complete(self, request: CompletionRequest) -> Any:
            raise AIProviderError("API call failed")

        async def stream(self, request: CompletionRequest) -> Any:
            raise NotImplementedError

        def count_tokens(self, text: str) -> int:
            return 0

    router = ModelRouter()
    router.register("primary", FailingAdapter())
    router.register("secondary", FailingAdapter())

    req = CompletionRequest(model="primary", messages=[Message.user("hi")])
    with pytest.raises(AllModelsFailedError):
        await router.complete(req, fallback_models=["secondary"])


# 13. Test Structured Output extraction JSON pure
def test_structured_extract_json_pure() -> None:
    from forge.ai.structured import extract_json

    data = extract_json('{"name": "Iron Man", "age": 45}')
    assert data["name"] == "Iron Man"
    assert data["age"] == 45


# 14. Test Structured Output extraction JSON markdown code block
def test_structured_extract_json_markdown() -> None:
    from forge.ai.structured import extract_json

    text = """
Some introductory text
```json
{
  "name": "Thor",
  "age": 1500
}
```
And final notes.
"""
    data = extract_json(text)
    assert data["name"] == "Thor"
    assert data["age"] == 1500


# 15. Test Structured Output extraction JSON embedded in prose
def test_structured_extract_json_embedded() -> None:
    from forge.ai.structured import extract_json

    text = 'The parsed response is: { "name": "Hulk", "age": 40 } which represents the character.'
    data = extract_json(text)
    assert data["name"] == "Hulk"
    assert data["age"] == 40


# 16. Test Structured Output extraction invalid JSON raises JSONDecodeError
def test_structured_extract_json_invalid_raises() -> None:
    from forge.ai.structured import extract_json

    with pytest.raises(json.JSONDecodeError):
        extract_json("no json here")


# 17. Test Structured Output Enforcer success first try
@pytest.mark.asyncio
async def test_structured_enforcer_success() -> None:
    from forge.ai.structured import StructuredOutputEnforcer

    enforcer = StructuredOutputEnforcer(max_retries=2)
    response_mock = CompletionResponse(
        model="mock",
        message=Message.assistant('{"name": "Captain America", "age": 100}'),
        usage=None,
    )

    async def complete_fn(msgs: list[Message]) -> CompletionResponse:
        return response_mock

    hero = await enforcer.enforce([Message.user("give hero")], Hero, complete_fn)
    assert hero.name == "Captain America"
    assert hero.age == 100


# 18. Test Structured Output Enforcer retry on validation failure
@pytest.mark.asyncio
async def test_structured_enforcer_retry() -> None:
    from forge.ai.structured import StructuredOutputEnforcer

    enforcer = StructuredOutputEnforcer(max_retries=2)

    calls = 0

    async def complete_fn(msgs: list[Message]) -> CompletionResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            # Invalid JSON
            return CompletionResponse(
                model="mock",
                message=Message.assistant("Not JSON"),
                usage=None,
            )
        # Valid JSON
        return CompletionResponse(
            model="mock",
            message=Message.assistant('{"name": "Black Widow", "age": 35}'),
            usage=None,
        )

    hero = await enforcer.enforce([Message.user("give hero")], Hero, complete_fn)
    assert hero.name == "Black Widow"
    assert hero.age == 35
    assert calls == 2


# 19. Test Structured Output Enforcer max retries exceeded raises StructuredOutputError
@pytest.mark.asyncio
async def test_structured_enforcer_max_retries() -> None:
    from forge.ai.structured import StructuredOutputEnforcer

    enforcer = StructuredOutputEnforcer(max_retries=1)  # 2 attempts total

    async def complete_fn(msgs: list[Message]) -> CompletionResponse:
        return CompletionResponse(
            model="mock",
            message=Message.assistant("Invalid JSON always"),
            usage=None,
        )

    with pytest.raises(StructuredOutputError) as exc_info:
        await enforcer.enforce([Message.user("give hero")], Hero, complete_fn)

    assert exc_info.value.schema_name == "Hero"
    assert exc_info.value.attempts == 2
    assert exc_info.value.last_response == "Invalid JSON always"


# 20. Test active runtime helper raises RuntimeNotInitializedError when not set
def test_global_active_runtime_not_initialized() -> None:
    # Ensure active is None
    ForgeRuntime._active = None
    with pytest.raises(RuntimeNotInitializedError):
        ForgeRuntime.get_active()


# Helper to initialize runtime for module test
async def _init_test_runtime() -> ForgeRuntime:
    runtime = ForgeRuntime()
    runtime.register(ConfigModule())
    runtime.register(RetryModule())
    runtime.register(AIModule())
    await runtime.init()
    return runtime


# 21. Test active runtime tracker success
@pytest.mark.asyncio
async def test_active_runtime_tracker() -> None:
    runtime = await _init_test_runtime()
    try:
        assert ForgeRuntime.get_active() is runtime
    finally:
        await runtime.teardown()


# 22. Test global convenience function complete
@pytest.mark.asyncio
async def test_global_complete() -> None:
    runtime = await _init_test_runtime()
    try:
        res = await complete([Message.user("test prompt")], model="mock-model")
        assert isinstance(res, AIResponse)
        assert res.content == "[mock response]"
        assert res.provider == "mock"
    finally:
        await runtime.teardown()


# 23. Test global convenience function complete with structured output
@pytest.mark.asyncio
async def test_global_complete_structured() -> None:
    runtime = await _init_test_runtime()
    ai_module = runtime.get(AIModule)
    # Set the mock adapter response text to a valid Hero JSON
    ai_module.router.resolve("*")._response_text = '{"name": "Spider-Man", "age": 18}'

    try:
        res = await complete([Message.user("test prompt")], model="mock-model", output_schema=Hero)
        assert isinstance(res, Hero)
        assert res.name == "Spider-Man"
        assert res.age == 18
    finally:
        await runtime.teardown()


# 24. Test global convenience function stream
@pytest.mark.asyncio
async def test_global_stream() -> None:
    runtime = await _init_test_runtime()
    try:
        chunks = []
        async for chunk in stream([Message.user("test prompt")], model="mock-model"):
            assert isinstance(chunk, StreamChunk)
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0].delta == "[mock response]"
        assert chunks[0].provider == "mock"
    finally:
        await runtime.teardown()


# 25. Test health check on mock provider
@pytest.mark.asyncio
async def test_module_health_check_mock() -> None:
    runtime = await _init_test_runtime()
    try:
        ai_module = runtime.get(AIModule)
        ai_module._config_ai.default_model = "mock-model"
        res = ai_module.health_check()
        assert res.status == HealthResult.OK
    finally:
        await runtime.teardown()


# 26. Test module metrics collection
@pytest.mark.asyncio
async def test_module_metrics() -> None:
    runtime = await _init_test_runtime()
    try:
        ai_module = runtime.get(AIModule)
        await complete([Message.user("test prompt")], model="mock-model")

        metrics = ai_module.get_metrics()
        assert metrics["request_count"] == 1
        assert metrics["token_count"]["input"] > 0
        assert metrics["token_count"]["output"] > 0
        assert metrics["cost_estimate"] >= 0.0
    finally:
        await runtime.teardown()


# 27. Test Gemini Adapter fallback to mock when SDK is not present
@pytest.mark.asyncio
async def test_gemini_adapter_fallback() -> None:
    from forge.ai.models import CompletionRequest

    adapter = GeminiAdapter(api_key=None)
    req = CompletionRequest(model="gemini-1.5-flash", messages=[Message.user("hi")])
    res = await adapter.complete(req)
    assert res.content == "[mock gemini response]"
    assert res.provider == "gemini"


# 28. Test Gemini Adapter stream mock fallback when SDK not installed
@pytest.mark.asyncio
async def test_gemini_adapter_stream_mock() -> None:
    from forge.ai.models import CompletionRequest

    adapter = GeminiAdapter(api_key="fake-key")
    req = CompletionRequest(model="gemini-1.5-flash", messages=[Message.user("hi")])
    chunks = []
    async for chunk in adapter.stream(req):
        assert isinstance(chunk, StreamChunk)
        chunks.append(chunk)

    assert len(chunks) == 1
    assert "[mock gemini chunk]" in chunks[0].delta
    assert chunks[0].finish_reason == "stop"
    assert chunks[0].provider == "gemini"
