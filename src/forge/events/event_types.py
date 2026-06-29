"""
Strongly-typed event definitions for the forge event bus.

Provides string constants for all standard event names and TypedDict
payload schemas for type-checking event emissions and subscriptions.
Payloads are plain dicts at runtime (loose coupling); TypedDicts serve
as documentation and IDE autocompletion aids.
"""

from __future__ import annotations

from typing import TypedDict

# ── Standard Event Names ─────────────────────────────────────────────
# Convention: ``{module}.{noun}.{verb_past_tense}``

RUNTIME_READY = "runtime.ready"
RUNTIME_SHUTDOWN = "runtime.shutdown"
CONFIG_LOADED = "config.loaded"
AI_REQUEST_STARTED = "ai.request.started"
AI_REQUEST_COMPLETED = "ai.request.completed"
AI_REQUEST_FAILED = "ai.request.failed"
CACHE_HIT = "cache.hit"
CACHE_MISS = "cache.miss"
CACHE_SET = "cache.set"
HEALTH_CHECK_FAILED = "health.check.failed"
RETRY_ATTEMPT_STARTED = "retry.attempt.started"
RETRY_ATTEMPT_FAILED = "retry.attempt.failed"
RETRY_EXHAUSTED = "retry.exhausted"

# ── Event Payload TypedDicts ─────────────────────────────────────────
# These are documentation / type-checking aids only.  The runtime
# delivers payloads as plain ``**kwargs`` dicts to preserve loose
# coupling between emitter and subscriber.

class EmptyPayload(TypedDict):
    """Events that carry no data beyond the event name."""


class AIRequestStartedPayload(TypedDict, total=False):
    model: str
    provider: str
    input_tokens: int | None


class AIRequestCompletedPayload(TypedDict, total=False):
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    trace_id: str | None


class AIRequestFailedPayload(TypedDict, total=False):
    model: str
    provider: str
    error: str
    duration_ms: float


class CacheHitPayload(TypedDict, total=False):
    key: str


class CacheMissPayload(TypedDict, total=False):
    key: str


class CacheSetPayload(TypedDict, total=False):
    key: str
    ttl: int | None


class RetryAttemptStartedPayload(TypedDict, total=False):
    attempt: int
    max_attempts: int
    delay: float


class RetryAttemptFailedPayload(TypedDict, total=False):
    attempt: int
    max_attempts: int
    error: str


class RetryExhaustedPayload(TypedDict, total=False):
    max_attempts: int
    duration: float
