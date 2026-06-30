from __future__ import annotations

import contextlib
import hashlib
import logging
from collections.abc import Callable
from typing import Any

from forge.featureflags.exceptions import FlagNotFoundError
from forge.featureflags.models import (
    EvaluationContext,
    EvaluationReason,
    EvaluationResult,
    FlagDefinition,
    FlagRule,
    FlagType,
)
from forge.featureflags.store import FlagStore

logger = logging.getLogger(__name__)

_SegmentOpFn = Callable[[str, list[str]], bool]
_SEGMENT_OPERATORS: dict[str, _SegmentOpFn] = {}


def _register_operators() -> None:
    """Register segment operators lazily to avoid circular issues."""
    if _SEGMENT_OPERATORS:
        return
    _SEGMENT_OPERATORS["eq"] = lambda a, v: a in v
    _SEGMENT_OPERATORS["neq"] = lambda a, v: a not in v
    _SEGMENT_OPERATORS["contains"] = lambda a, v: any(val in a for val in v)
    _SEGMENT_OPERATORS["not_contains"] = lambda a, v: not any(val in a for val in v)
    _SEGMENT_OPERATORS["prefix"] = lambda a, v: any(a.startswith(val) for val in v)
    _SEGMENT_OPERATORS["suffix"] = lambda a, v: any(a.endswith(val) for val in v)


def _consistent_hash(input_str: str) -> int:
    """Compute a deterministic hash value in [0, 100) for percentage rollout."""
    digest = hashlib.sha256(input_str.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def _resolve_context_value(context: EvaluationContext, attr: str) -> Any:
    """Resolve a context attribute value by its path."""
    if attr == "user_id":
        return context.user_id
    if attr == "region":
        return context.region
    if attr.startswith("properties."):
        return context.properties.get(attr[len("properties.") :])
    return context.properties.get(attr)


def _evaluate_segment_rule(context: EvaluationContext, rule: Any) -> bool:
    """Evaluate a single segment rule against the evaluation context."""
    _register_operators()
    actual = _resolve_context_value(context, rule.attribute)
    if actual is None:
        return False
    op_fn = _SEGMENT_OPERATORS.get(rule.operator)
    if op_fn is None:
        logger.warning("Unknown segment operator: %s", rule.operator)
        return False
    return op_fn(str(actual), rule.values)


def _check_segments_match(context: EvaluationContext, segments: list[Any]) -> bool:
    """Check if the evaluation context matches all segment rules (AND logic)."""
    if not segments:
        return True
    return all(_evaluate_segment_rule(context, s) for s in segments)


class FlagEvaluator:
    """Evaluates feature flags against an evaluation context."""

    def __init__(self, store: FlagStore) -> None:
        self._store = store

    @property
    def store(self) -> FlagStore:
        return self._store

    async def evaluate(
        self,
        flag_name: str,
        context: EvaluationContext,
    ) -> EvaluationResult:
        """Evaluate a single feature flag for the given context."""
        flag = await self._store.get_flag(flag_name)
        if flag is None:
            raise FlagNotFoundError(f"Flag '{flag_name}' not found.")

        return self._evaluate_flag(flag, context)

    async def evaluate_bulk(
        self,
        flag_names: list[str],
        context: EvaluationContext,
    ) -> dict[str, EvaluationResult]:
        """Evaluate multiple feature flags for the given context."""
        results: dict[str, EvaluationResult] = {}
        for name in flag_names:
            with contextlib.suppress(FlagNotFoundError):
                results[name] = await self.evaluate(name, context)
        return results

    async def evaluate_all(
        self,
        context: EvaluationContext,
    ) -> dict[str, EvaluationResult]:
        """Evaluate all stored feature flags for the given context."""
        flags = await self._store.list_flags()
        results: dict[str, EvaluationResult] = {}
        for flag in flags:
            try:
                results[flag.name] = await self.evaluate(flag.name, context)
            except FlagNotFoundError:
                continue
            except Exception as exc:
                logger.warning("Failed to evaluate flag '%s': %s", flag.name, exc)
        return results

    def _evaluate_flag(
        self,
        flag: FlagDefinition,
        context: EvaluationContext,
    ) -> EvaluationResult:
        """Evaluate a flag definition against context."""
        # 1. Check overrides (highest priority)
        override_reason = self._check_overrides(flag, context)
        if override_reason is not None:
            return override_reason

        # 2. Check rules (e.g., percentage rollout, segment match)
        for idx, rule in enumerate(flag.rules):
            matched = self._evaluate_rule(flag, rule, context)
            if matched:
                return EvaluationResult(
                    flag_name=flag.name,
                    value=rule.value,
                    reason=self._reason_for_rule(flag.type, rule),
                    matched_rule_index=idx,
                )

        # 3. Fall back to default
        return EvaluationResult(
            flag_name=flag.name,
            value=flag.default_value,
            reason=EvaluationReason.DEFAULT,
        )

    def _check_overrides(
        self,
        flag: FlagDefinition,
        context: EvaluationContext,
    ) -> EvaluationResult | None:
        """Check if the user has a direct override."""
        if not flag.overrides:
            return None

        # Check user_id override
        if context.user_id in flag.overrides:
            return EvaluationResult(
                flag_name=flag.name,
                value=flag.overrides[context.user_id],
                reason=EvaluationReason.OVERRIDE,
            )

        # Check region override
        if context.region and context.region in flag.overrides:
            return EvaluationResult(
                flag_name=flag.name,
                value=flag.overrides[context.region],
                reason=EvaluationReason.OVERRIDE,
            )

        return None

    def _evaluate_rule(
        self,
        flag: FlagDefinition,
        rule: FlagRule,
        context: EvaluationContext,
    ) -> bool:
        """Evaluate a single rule against the context."""
        if flag.type == FlagType.PERCENTAGE:
            percentage = rule.percentage
            if percentage is not None:
                hash_input = f"{flag.name}:{context.user_id}"
                hash_val = _consistent_hash(hash_input)
                return hash_val < percentage

        if flag.type == FlagType.SEGMENT:
            segments = list(rule.segments or [])
            return _check_segments_match(context, segments)

        # Boolean or fallback: check segment conditions if present
        segments = list(rule.segments or [])
        if segments:
            return _check_segments_match(context, segments)

        # No segments — match all for boolean rules
        return True

    def _reason_for_rule(
        self,
        flag_type: FlagType,
        rule: FlagRule,
    ) -> EvaluationReason:
        """Determine the evaluation reason based on flag type and rule."""
        if flag_type == FlagType.PERCENTAGE:
            return EvaluationReason.PERCENTAGE_ROLLOUT
        if flag_type == FlagType.SEGMENT:
            return EvaluationReason.SEGMENT_MATCH
        return EvaluationReason.RULE_MATCH
