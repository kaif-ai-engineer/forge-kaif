from __future__ import annotations

import asyncio
import enum
import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from typing import Self

_logger = logging.getLogger(__name__)


class CircuitBreakerState(enum.Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenError(Exception):
    """Raised when a call is rejected because the circuit breaker is open."""


class CircuitBreaker:
    """
    Async circuit breaker with three-state machine.

    States: ``CLOSED`` (normal) → ``OPEN`` (failing) → ``HALF_OPEN`` (probing).
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_time: float = 60.0,
        *,
        name: str = "",
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if recovery_time < 0:
            raise ValueError("recovery_time must be >= 0")

        self._failure_threshold = failure_threshold
        self._recovery_time = recovery_time
        self._name = name or hex(id(self))

        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0

    @property
    def state(self) -> CircuitBreakerState:
        return self._state

    @property
    def name(self) -> str:
        return self._name

    async def call(self, coro: Any) -> Any:
        """Execute *coro* under circuit-breaker protection."""
        self._check_state()
        try:
            result = await coro
        except Exception:
            self._on_failure()
            raise
        else:
            self._on_success()
            return result

    async def __aenter__(self) -> Self:
        self._check_state()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        if exc_type is None:
            self._on_success()
        elif exc_type is not asyncio.CancelledError:
            self._on_failure()
        return False

    def __call__(self, fn: Any) -> Any:
        async def wrapper(*args: object, **kwargs: object) -> Any:
            return await self.call(fn(*args, **kwargs))

        wrapper.__name__ = fn.__name__
        wrapper.__qualname__ = fn.__qualname__
        wrapper.__module__ = fn.__module__
        wrapper.__doc__ = fn.__doc__
        return wrapper

    def reset(self) -> None:
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0

    def _check_state(self) -> None:
        if self._state is CircuitBreakerState.OPEN:
            if time.monotonic() - self._last_failure_time >= self._recovery_time:
                _logger.debug(
                    "Circuit breaker %r transitioning OPEN -> HALF_OPEN",
                    self._name,
                )
                self._state = CircuitBreakerState.HALF_OPEN
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker {self._name!r} is OPEN"
                )

    def _on_success(self) -> None:
        if self._state is CircuitBreakerState.HALF_OPEN:
            _logger.info("Circuit breaker %r recovered, closing", self._name)
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0

    def _on_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if (
            self._state is CircuitBreakerState.HALF_OPEN
            or self._failure_count >= self._failure_threshold
        ):
            _logger.warning(
                "Circuit breaker %r opening (failures=%d/%d)",
                self._name,
                self._failure_count,
                self._failure_threshold,
            )
            self._state = CircuitBreakerState.OPEN
