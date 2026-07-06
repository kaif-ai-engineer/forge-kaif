"""
Core runtime — module registry, lifecycle, DI container, event bus, and context management.

Provides the ForgeModule base class, ForgeRuntime coordinator, and supporting
infrastructure for module initialization ordering, dependency injection, event
emission, and async context propagation.
"""

from forge.core.container import Container
from forge.core.context import (
    TraceContext,
    generate_span_id,
    generate_trace_id,
    get_baggage,
    get_baggage_item,
    get_span_id,
    get_trace_id,
    reset_baggage,
    reset_span_id,
    reset_trace_id,
    set_baggage,
    set_span_id,
    set_trace_id,
)
from forge.core.events import EventBus
from forge.core.exceptions import (
    CircularDependencyError,
    ConfigurationError,
    EventError,
    ForgeError,
    HealthCheckError,
    ModuleError,
    ModuleNotFoundError,
    ModuleRegistrationError,
    ModuleStateError,
    RuntimeNotInitializedError,
)
from forge.core.module import ForgeModule, HealthResult, ModuleLifecycleState
from forge.core.otel import get_meter, get_tracer, in_span, init_otel, is_otel_available
from forge.core.runtime import ForgeRuntime

Runtime = ForgeRuntime

__all__ = [
    "CircularDependencyError",
    "ConfigurationError",
    "Container",
    "EventBus",
    "EventError",
    "ForgeError",
    "ForgeModule",
    "ForgeRuntime",
    "HealthCheckError",
    "HealthResult",
    "ModuleError",
    "ModuleLifecycleState",
    "ModuleNotFoundError",
    "ModuleRegistrationError",
    "ModuleStateError",
    "Runtime",
    "RuntimeNotInitializedError",
    "TraceContext",
    "generate_span_id",
    "generate_trace_id",
    "get_baggage",
    "get_baggage_item",
    "get_meter",
    "get_span_id",
    "get_trace_id",
    "get_tracer",
    "in_span",
    "init_otel",
    "is_otel_available",
    "reset_baggage",
    "reset_span_id",
    "reset_trace_id",
    "set_baggage",
    "set_span_id",
    "set_trace_id",
]
