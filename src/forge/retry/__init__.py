"""
Retry and resilience module — exponential backoff, jitter, and circuit breaker.

Provides a @retry decorator and CircuitBreaker class for handling transient
failures in external service calls. Supports configurable backoff strategies,
exception filtering, and automatic logging.
"""
