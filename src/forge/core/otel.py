from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, cast

_logger = logging.getLogger(__name__)

_OTEL_AVAILABLE: bool = False
_INITIALIZED: bool = False

try:
    from opentelemetry import metrics as _otel_metrics
    from opentelemetry import trace as _otel_trace
    from opentelemetry.sdk.metrics import MeterProvider as _SdkMeterProvider
    from opentelemetry.sdk.trace import TracerProvider as _SdkTracerProvider

    _OTEL_AVAILABLE = True
except ImportError:
    _otel_metrics = None  # type: ignore[assignment]
    _otel_trace = None  # type: ignore[assignment]


def init_otel() -> None:
    """Initialise OTel providers for internal collection only (no exporters)."""
    global _INITIALIZED  # noqa: PLW0603
    if _INITIALIZED or not _OTEL_AVAILABLE:
        return

    _SdkTracerProvider()
    _otel_trace.set_tracer_provider(_SdkTracerProvider())

    _SdkMeterProvider()
    _otel_metrics.set_meter_provider(_SdkMeterProvider())

    _INITIALIZED = True
    _logger.debug("OpenTelemetry SDK initialised (internal collection, no exporters)")


def is_otel_available() -> bool:
    """Return ``True`` if the optional OTel packages are installed."""
    return _OTEL_AVAILABLE


def get_tracer(name: str = "forge", version: str = "") -> Any:
    """Return an OTel ``Tracer``, or ``None`` if OTel is not installed."""
    if not _OTEL_AVAILABLE:
        return None
    if not _INITIALIZED:
        init_otel()
    return cast("Any", _otel_trace).get_tracer(name, version or None)


def get_meter(name: str = "forge", version: str = "") -> Any:
    """Return an OTel ``Meter``, or ``None`` if OTel is not installed."""
    if not _OTEL_AVAILABLE:
        return None
    if not _INITIALIZED:
        init_otel()
    return cast("Any", _otel_metrics).get_meter(name, version or None)


def get_current_span_context() -> dict[str, str]:
    """
    Return the current OTel trace/span IDs as ``{trace_id, span_id}``.

    Returns empty dict if OTel is not available or no span is active.
    """
    if not _OTEL_AVAILABLE:
        return {}
    span = _otel_trace.get_current_span()
    span_context = span.get_span_context()
    if span_context.is_valid:
        trace_id = format(span_context.trace_id, "032x")
        span_id = format(span_context.span_id, "016x")
        return {"trace_id": trace_id, "span_id": span_id}
    return {}


@contextmanager
def in_span(
    name: str,
    attributes: dict[str, Any] | None = None,
    tracer: Any = None,
) -> Generator[Any, None, None]:
    """
    Context manager that creates an OTel span when OTel is available.

    Yields the span (or ``None`` when OTel is not installed).
    """
    tr = tracer or get_tracer()
    if tr is None:
        yield None
        return

    with tr.start_as_current_span(name) as span:
        if attributes:
            span.set_attributes(attributes)
        yield span
