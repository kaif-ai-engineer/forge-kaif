from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from forge.featureflags.module import FeatureFlagsModule

_active_featureflags_module: FeatureFlagsModule | None = None


def get_featureflags_module() -> FeatureFlagsModule | None:
    """Get the active featureflags module instance."""
    return _active_featureflags_module


def set_featureflags_module(module: FeatureFlagsModule | None) -> None:
    """Set the active featureflags module instance."""
    global _active_featureflags_module  # noqa: PLW0603
    _active_featureflags_module = module
