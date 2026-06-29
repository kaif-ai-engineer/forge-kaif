"""
Event bus module — decoupled, asynchronous module communication.

Provides an in-process event emitter and subscriber system for modules to
communicate without direct dependencies. Supports typed events, async
handlers, lifecycle event hooks, wildcard pattern subscriptions, and an
event history buffer for late-joining subscribers.
"""

from forge.events.event_types import (
    AI_REQUEST_COMPLETED,
    AI_REQUEST_FAILED,
    AI_REQUEST_STARTED,
    CACHE_HIT,
    CACHE_MISS,
    CACHE_SET,
    CONFIG_LOADED,
    HEALTH_CHECK_FAILED,
    RETRY_ATTEMPT_FAILED,
    RETRY_ATTEMPT_STARTED,
    RETRY_EXHAUSTED,
    RUNTIME_READY,
    RUNTIME_SHUTDOWN,
    AIRequestCompletedPayload,
    AIRequestFailedPayload,
    AIRequestStartedPayload,
    CacheHitPayload,
    CacheMissPayload,
    CacheSetPayload,
    EmptyPayload,
    RetryAttemptFailedPayload,
    RetryAttemptStartedPayload,
    RetryExhaustedPayload,
)
from forge.events.module import EventBusWrapper, EventRecord, EventsModule, Handler

__all__ = [
    "AI_REQUEST_COMPLETED",
    "AI_REQUEST_FAILED",
    "AI_REQUEST_STARTED",
    "CACHE_HIT",
    "CACHE_MISS",
    "CACHE_SET",
    "CONFIG_LOADED",
    "HEALTH_CHECK_FAILED",
    "RETRY_ATTEMPT_FAILED",
    "RETRY_ATTEMPT_STARTED",
    "RETRY_EXHAUSTED",
    "RUNTIME_READY",
    "RUNTIME_SHUTDOWN",
    "AIRequestCompletedPayload",
    "AIRequestFailedPayload",
    "AIRequestStartedPayload",
    "CacheHitPayload",
    "CacheMissPayload",
    "CacheSetPayload",
    "EmptyPayload",
    "EventBusWrapper",
    "EventRecord",
    "EventsModule",
    "Handler",
    "RetryAttemptFailedPayload",
    "RetryAttemptStartedPayload",
    "RetryExhaustedPayload",
]
