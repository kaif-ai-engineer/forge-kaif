"""
Retry and resilience module — exponential backoff, jitter, and circuit breaker.

Provides the ``@retry`` decorator and ``CircuitBreaker`` class for handling
transient failures in external service calls. Supports configurable backoff
strategies, exception filtering, and automatic logging.
"""

from forge.retry.backoff import constant, exponential, get_backoff, linear
from forge.retry.circuit import CircuitBreaker, CircuitBreakerOpenError, CircuitBreakerState
from forge.retry.module import NonRetryableError, RetryError, RetryModule, retry

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "CircuitBreakerState",
    "NonRetryableError",
    "RetryError",
    "RetryModule",
    "constant",
    "exponential",
    "get_backoff",
    "linear",
    "retry",
]
