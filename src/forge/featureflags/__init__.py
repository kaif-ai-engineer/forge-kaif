"""
Feature Flags module — boolean, percentage rollout, and user-segment evaluation.

Provides typed flag definitions, evaluation context, consistent-hash based
percentage rollout, in-memory and Redis-backed storage, and CLI management.
"""

from __future__ import annotations

from forge.featureflags.evaluator import FlagEvaluator
from forge.featureflags.exceptions import (
    FeatureFlagError,
    FlagEvaluationError,
    FlagNotFoundError,
    FlagStoreError,
    InvalidFlagDefinitionError,
)
from forge.featureflags.models import (
    EvaluationContext,
    EvaluationReason,
    EvaluationResult,
    FlagDefinition,
    FlagRule,
    FlagType,
    SegmentRule,
)
from forge.featureflags.module import FeatureFlagsModule
from forge.featureflags.store import MemoryFlagStore, RedisFlagStore

__all__ = [
    "EvaluationContext",
    "EvaluationReason",
    "EvaluationResult",
    "FeatureFlagError",
    "FeatureFlagsModule",
    "FlagDefinition",
    "FlagEvaluationError",
    "FlagEvaluator",
    "FlagNotFoundError",
    "FlagRule",
    "FlagStoreError",
    "FlagType",
    "InvalidFlagDefinitionError",
    "MemoryFlagStore",
    "RedisFlagStore",
    "SegmentRule",
]
