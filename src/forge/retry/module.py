from __future__ import annotations

import asyncio
import functools
import logging
import time
from typing import TYPE_CHECKING, Any, ClassVar

from forge.core.module import ForgeModule, HealthResult
from forge.core.otel import get_meter
from forge.retry.backoff import get_backoff

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Self

    from forge.config.schema import RetryConfig
    from forge.core.runtime import ForgeRuntime


_logger = logging.getLogger(__name__)

# ── Exceptions ─────────────────────────────────────────────────────


class RetryError(Exception):
    """
    Raised when all retry attempts have been exhausted.

    Attributes
    ----------
    original_exception :
        The last exception raised by the wrapped callable.
    attempt_count :
        Total number of attempts made (including the initial call).
    total_delay :
        Total wall-clock time spent sleeping between retries.
    """

    def __init__(
        self,
        original_exception: Exception,
        attempt_count: int,
        total_delay: float,
    ) -> None:
        self.original_exception = original_exception
        self.attempt_count = attempt_count
        self.total_delay = total_delay
        super().__init__(
            f"All {attempt_count} retry attempt(s) exhausted "
            f"(total delay={total_delay:.2f}s): {original_exception}"
        )


class NonRetryableError(Exception):
    """Raise this inside a retried call to abort retrying immediately."""


# ── Retry (function API + context manager) ─────────────────────────


_retry_counter = None
_circuit_breaker_state_counter = None


def _get_retry_counter() -> Any:
    global _retry_counter  # noqa: PLW0603
    if _retry_counter is None:
        meter = get_meter()
        if meter is not None:
            _retry_counter = meter.create_counter(
                "retry.count",
                description="Total number of retry attempts",
                unit="1",
            )
    return _retry_counter


def _get_circuit_breaker_state_counter() -> Any:
    global _circuit_breaker_state_counter  # noqa: PLW0603
    if _circuit_breaker_state_counter is None:
        meter = get_meter()
        if meter is not None:
            _circuit_breaker_state_counter = meter.create_counter(
                "circuit.breaker.state",
                description="Circuit breaker state transitions",
                unit="1",
            )
    return _circuit_breaker_state_counter


class _RetryImpl:
    """Internal implementation — do not use directly; use :func:`retry` instead."""

    def __init__(
        self,
        *,
        attempts: int = 3,
        backoff: str = "exponential",
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: bool = True,
        timeout: float | None = None,
        retryable_exceptions: tuple[type[Exception], ...] | None = None,
    ) -> None:
        self._attempts = attempts
        self._backoff_strategy = backoff
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._jitter = jitter
        self._timeout = timeout
        self._retryable_exceptions = retryable_exceptions or (Exception,)
        self._backoff_fn = get_backoff(self._backoff_strategy)
        self._start_time: float = 0.0
        self._attempt_count: int = 0

    def __call__(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator usage: ``_RetryImpl(attempts=3)(async_func)``."""

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await self._execute(fn, *args, **kwargs)

        return wrapper

    async def __aenter__(self) -> Self:
        self._start_time = time.monotonic()
        self._attempt_count = 0
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        if exc_type is None or not isinstance(exc_val, Exception):
            return False
        if isinstance(exc_val, NonRetryableError):
            return False
        if not isinstance(exc_val, self._retryable_exceptions):
            return False
        return await self._handle_exception(exc_val)

    async def _execute(
        self,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        backoff_fn = get_backoff(self._backoff_strategy)
        start = time.monotonic()
        last_exc: Exception | None = None
        retry_counter = _get_retry_counter()

        for attempt in range(1, self._attempts + 1):
            try:
                if self._timeout is not None:
                    return await asyncio.wait_for(fn(*args, **kwargs), timeout=self._timeout)
                return await fn(*args, **kwargs)
            except NonRetryableError:
                raise
            except Exception as e:
                if not isinstance(e, self._retryable_exceptions):
                    raise
                last_exc = e
                if attempt < self._attempts:
                    if retry_counter is not None:
                        retry_counter.add(1, {"operation": _name(fn)})
                    delay = backoff_fn(attempt)
                    _logger.warning(
                        "Retry %s/%s for %r after %.2fs: %s",
                        attempt,
                        self._attempts,
                        _name(fn),
                        delay,
                        e,
                    )
                    await asyncio.sleep(delay)

        total = time.monotonic() - start
        if last_exc is None:
            raise RuntimeError("unreachable: final retry without exception")  # pragma: no cover
        raise RetryError(
            original_exception=last_exc,
            attempt_count=self._attempts,
            total_delay=total,
        )

    async def _handle_exception(self, exc: Exception) -> bool:
        if self._attempt_count >= self._attempts:
            raise RetryError(
                original_exception=exc,
                attempt_count=self._attempts,
                total_delay=time.monotonic() - self._start_time,
            ) from exc

        retry_counter = _get_retry_counter()
        if retry_counter is not None:
            retry_counter.add(1, {"operation": "context_manager"})

        delay = self._backoff_fn(self._attempt_count + 1)
        self._attempt_count += 1
        _logger.warning(
            "Retry %s/%s after %.2fs: %s",
            self._attempt_count,
            self._attempts,
            delay,
            exc,
        )
        await asyncio.sleep(delay)
        return True


def _name(fn: Callable[..., Any]) -> str:
    return getattr(fn, "__name__", str(fn))


def retry(
    fn: Callable[..., Any] | None = None,
    *,
    attempts: int = 3,
    backoff: str = "exponential",
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    timeout: float | None = None,
    retryable_exceptions: tuple[type[Exception], ...] | None = None,
) -> Any:
    """
    Async retry — use as a decorator or async context manager.

    Decorator form::

        @retry(attempts=3)
        async def fetch() -> bytes:
            ...

    Context manager form::

        async with retry(attempts=3):
            data = await fetch()
    """
    impl = _RetryImpl(
        attempts=attempts,
        backoff=backoff,
        base_delay=base_delay,
        max_delay=max_delay,
        jitter=jitter,
        timeout=timeout,
        retryable_exceptions=retryable_exceptions,
    )
    if fn is not None:
        return impl(fn)
    return impl


# ── RetryModule ────────────────────────────────────────────────────


class RetryModule(ForgeModule):
    name = "retry"
    dependencies: ClassVar[list[str]] = ["config"]

    def __init__(self) -> None:
        super().__init__()
        self._config_retry: RetryConfig | None = None

    async def setup(self, runtime: ForgeRuntime) -> None:
        from forge.config.module import ConfigModule

        config_module: ConfigModule = runtime.get(ConfigModule)  # type: ignore[assignment]
        self._config_retry = config_module.config.retry

    async def teardown(self) -> None:
        self._config_retry = None

    def health_check(self) -> HealthResult:
        return HealthResult.ok()

    def retry(
        self,
        fn: Callable[..., Any] | None = None,
        *,
        attempts: int | None = None,
        backoff: str | None = None,
        base_delay: float | None = None,
        max_delay: float | None = None,
        jitter: bool | None = None,
        timeout: float | None = None,
        retryable_exceptions: tuple[type[Exception], ...] | None = None,
    ) -> Any:
        """Return a :func:`retry` pre-configured with module defaults."""
        cfg = self._config_retry
        if cfg is None:
            raise RuntimeError("RetryModule not initialised")
        return retry(
            fn=fn,
            attempts=attempts if attempts is not None else cfg.default_attempts,
            backoff=backoff if backoff is not None else cfg.default_backoff,
            base_delay=base_delay if base_delay is not None else cfg.default_base_delay,
            max_delay=max_delay if max_delay is not None else cfg.default_max_delay,
            jitter=jitter if jitter is not None else cfg.default_jitter,
            timeout=timeout,
            retryable_exceptions=retryable_exceptions,
        )

    def circuit_breaker(
        self,
        failure_threshold: int | None = None,
        recovery_time: float | None = None,
        *,
        name: str = "",
    ) -> Any:
        """Return a :class:`~forge.retry.circuit.CircuitBreaker` with module defaults."""
        from forge.retry.circuit import CircuitBreaker

        cfg = self._config_retry
        if cfg is None:
            raise RuntimeError("RetryModule not initialised")
        cb_cfg = cfg.circuit_breaker
        return CircuitBreaker(
            failure_threshold=(
                failure_threshold if failure_threshold is not None else cb_cfg.failure_threshold
            ),
            recovery_time=(recovery_time if recovery_time is not None else cb_cfg.recovery_time),
            name=name,
        )
