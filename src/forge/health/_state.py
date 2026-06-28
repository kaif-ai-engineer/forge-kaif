from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from forge.health.module import HealthModule

_active_health_module: HealthModule | None = None


def get_health_module() -> HealthModule | None:
    """Get the active health module instance."""
    return _active_health_module


def set_health_module(module: HealthModule | None) -> None:
    """Set the active health module instance."""
    global _active_health_module  # noqa: PLW0603
    _active_health_module = module
