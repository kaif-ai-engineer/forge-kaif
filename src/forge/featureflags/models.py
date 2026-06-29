from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, Field


class FlagType(enum.StrEnum):
    """Supported feature flag evaluation types."""

    BOOLEAN = "boolean"
    PERCENTAGE = "percentage"
    SEGMENT = "segment"


class EvaluationContext(BaseModel):
    """Contextual information used during flag evaluation."""

    user_id: str
    region: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)


class SegmentRule(BaseModel):
    """A rule defining a user segment for flag targeting."""

    attribute: str
    operator: str = "eq"
    values: list[str] = Field(default_factory=list)


class FlagRule(BaseModel):
    """An override rule for a feature flag."""

    value: Any
    segments: list[SegmentRule] = Field(default_factory=list)
    percentage: int | None = Field(default=None, ge=0, le=100)


class FlagDefinition(BaseModel):
    """Definition of a single feature flag."""

    name: str
    type: FlagType = FlagType.BOOLEAN
    default_value: Any = False
    description: str = ""
    rules: list[FlagRule] = Field(default_factory=list)
    overrides: dict[str, Any] = Field(default_factory=dict)


class EvaluationReason(enum.StrEnum):
    """Reason why a flag evaluated to a particular value."""

    DEFAULT = "default"
    OVERRIDE = "override"
    RULE_MATCH = "rule_match"
    PERCENTAGE_ROLLOUT = "percentage_rollout"
    SEGMENT_MATCH = "segment_match"
    NO_MATCH = "no_match"


class EvaluationResult(BaseModel):
    """Result of a single flag evaluation."""

    flag_name: str
    value: Any
    reason: EvaluationReason = EvaluationReason.DEFAULT
    matched_rule_index: int | None = None
