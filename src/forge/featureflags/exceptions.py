from __future__ import annotations

from forge.core.exceptions import ForgeError


class FeatureFlagError(ForgeError):
    """Base exception for all feature flag-related errors."""


class FlagNotFoundError(FeatureFlagError):
    """Raised when a requested flag is not found in the store."""


class FlagStoreError(FeatureFlagError):
    """Raised when a flag store operation fails."""


class FlagEvaluationError(FeatureFlagError):
    """Raised when flag evaluation encounters an error."""


class InvalidFlagDefinitionError(FeatureFlagError):
    """Raised when a flag definition is invalid or malformed."""
