from __future__ import annotations

import pytest

from forge.featureflags._state import get_featureflags_module, set_featureflags_module
from forge.featureflags.evaluator import FlagEvaluator, _consistent_hash
from forge.featureflags.exceptions import FlagNotFoundError
from forge.featureflags.models import (
    EvaluationContext,
    EvaluationReason,
    FlagDefinition,
    FlagRule,
    FlagType,
    SegmentRule,
)
from forge.featureflags.store import MemoryFlagStore

# ---------------------------------------------------------------------------
# _consistent_hash
# ---------------------------------------------------------------------------


class TestConsistentHash:
    def test_deterministic(self) -> None:
        h1 = _consistent_hash("flag1:user1")
        h2 = _consistent_hash("flag1:user1")
        assert h1 == h2

    def test_in_range(self) -> None:
        for i in range(100):
            h = _consistent_hash(f"flag:user{i}")
            assert 0 <= h < 100

    def test_different_inputs_differ(self) -> None:
        h1 = _consistent_hash("flag1:user1")
        h2 = _consistent_hash("flag2:user1")
        h3 = _consistent_hash("flag1:user2")
        results = {h1, h2, h3}
        assert len(results) == 3


# ---------------------------------------------------------------------------
# MemoryFlagStore
# ---------------------------------------------------------------------------


class TestMemoryFlagStore:
    @pytest.mark.asyncio
    async def test_set_and_get(self) -> None:
        store = MemoryFlagStore()
        flag = FlagDefinition(name="test-flag", type=FlagType.BOOLEAN, default_value=True)
        await store.set_flag(flag)
        retrieved = await store.get_flag("test-flag")
        assert retrieved is not None
        assert retrieved.name == "test-flag"
        assert retrieved.default_value is True

    @pytest.mark.asyncio
    async def test_get_missing(self) -> None:
        store = MemoryFlagStore()
        assert await store.get_flag("nonexistent") is None

    @pytest.mark.asyncio
    async def test_delete(self) -> None:
        store = MemoryFlagStore()
        flag = FlagDefinition(name="to-delete")
        await store.set_flag(flag)
        assert await store.delete_flag("to-delete") is True
        assert await store.get_flag("to-delete") is None
        assert await store.delete_flag("to-delete") is False

    @pytest.mark.asyncio
    async def test_list_flags(self) -> None:
        store = MemoryFlagStore()
        await store.set_flag(FlagDefinition(name="a"))
        await store.set_flag(FlagDefinition(name="b"))
        flags = await store.list_flags()
        assert len(flags) == 2
        names = {f.name for f in flags}
        assert names == {"a", "b"}

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        store = MemoryFlagStore()
        await store.set_flag(FlagDefinition(name="x"))
        await store.close()
        assert len(await store.list_flags()) == 0


# ---------------------------------------------------------------------------
# FlagEvaluator — Boolean flags
# ---------------------------------------------------------------------------


class TestEvaluatorBoolean:
    @pytest.mark.asyncio
    async def test_default_value(self) -> None:
        store = MemoryFlagStore()
        await store.set_flag(FlagDefinition(name="feature-x", default_value=False))
        evaluator = FlagEvaluator(store)
        ctx = EvaluationContext(user_id="user1")
        result = await evaluator.evaluate("feature-x", ctx)
        assert result.value is False
        assert result.reason == EvaluationReason.DEFAULT

    @pytest.mark.asyncio
    async def test_override_by_user_id(self) -> None:
        store = MemoryFlagStore()
        await store.set_flag(
            FlagDefinition(
                name="feature-x",
                default_value=False,
                overrides={"user1": True},
            )
        )
        evaluator = FlagEvaluator(store)
        result = await evaluator.evaluate("feature-x", EvaluationContext(user_id="user1"))
        assert result.value is True
        assert result.reason == EvaluationReason.OVERRIDE

    @pytest.mark.asyncio
    async def test_override_by_region(self) -> None:
        store = MemoryFlagStore()
        await store.set_flag(
            FlagDefinition(
                name="feature-x",
                default_value=False,
                overrides={"us-east": True},
            )
        )
        evaluator = FlagEvaluator(store)
        result = await evaluator.evaluate(
            "feature-x", EvaluationContext(user_id="u1", region="us-east")
        )
        assert result.value is True
        assert result.reason == EvaluationReason.OVERRIDE

    @pytest.mark.asyncio
    async def test_flag_not_found(self) -> None:
        store = MemoryFlagStore()
        evaluator = FlagEvaluator(store)
        with pytest.raises(FlagNotFoundError):
            await evaluator.evaluate("no-such-flag", EvaluationContext(user_id="u1"))


# ---------------------------------------------------------------------------
# FlagEvaluator — Percentage rollout
# ---------------------------------------------------------------------------


class TestEvaluatorPercentage:
    @pytest.mark.asyncio
    async def test_percentage_zero(self) -> None:
        store = MemoryFlagStore()
        await store.set_flag(
            FlagDefinition(
                name="rollout-test",
                type=FlagType.PERCENTAGE,
                default_value=False,
                rules=[FlagRule(value=True, percentage=0)],
            )
        )
        evaluator = FlagEvaluator(store)
        ctx = EvaluationContext(user_id="user1")
        result = await evaluator.evaluate("rollout-test", ctx)
        assert result.reason == EvaluationReason.DEFAULT

    @pytest.mark.asyncio
    async def test_percentage_100(self) -> None:
        store = MemoryFlagStore()
        await store.set_flag(
            FlagDefinition(
                name="rollout-test",
                type=FlagType.PERCENTAGE,
                default_value=False,
                rules=[FlagRule(value=True, percentage=100)],
            )
        )
        evaluator = FlagEvaluator(store)
        ctx = EvaluationContext(user_id="user1")
        result = await evaluator.evaluate("rollout-test", ctx)
        assert result.value is True
        assert result.reason == EvaluationReason.PERCENTAGE_ROLLOUT

    @pytest.mark.asyncio
    async def test_percentage_deterministic(self) -> None:
        store = MemoryFlagStore()
        await store.set_flag(
            FlagDefinition(
                name="rollout-test",
                type=FlagType.PERCENTAGE,
                default_value=False,
                rules=[FlagRule(value=True, percentage=50)],
            )
        )
        evaluator = FlagEvaluator(store)
        ctx = EvaluationContext(user_id="user1")
        r1 = await evaluator.evaluate("rollout-test", ctx)
        r2 = await evaluator.evaluate("rollout-test", ctx)
        assert r1.value == r2.value
        assert r1.reason == r2.reason

    @pytest.mark.asyncio
    async def test_percentage_distribution(self) -> None:
        """Rough check that ~50% of users get True with 50% rollout."""
        store = MemoryFlagStore()
        await store.set_flag(
            FlagDefinition(
                name="rollout-test",
                type=FlagType.PERCENTAGE,
                default_value=False,
                rules=[FlagRule(value=True, percentage=50)],
            )
        )
        evaluator = FlagEvaluator(store)
        true_count = 0
        n = 500
        for i in range(n):
            result = await evaluator.evaluate("rollout-test", EvaluationContext(user_id=f"user{i}"))
            if result.value is True:
                true_count += 1
        # Should be roughly 50% (allow ±15% margin for a quick check)
        assert 175 <= true_count <= 325, f"Expected ~250 true, got {true_count}"


# ---------------------------------------------------------------------------
# FlagEvaluator — User-segment evaluation
# ---------------------------------------------------------------------------


class TestEvaluatorSegment:
    @pytest.mark.asyncio
    async def test_segment_user_id_match(self) -> None:
        store = MemoryFlagStore()
        await store.set_flag(
            FlagDefinition(
                name="beta-feature",
                type=FlagType.SEGMENT,
                default_value=False,
                rules=[
                    FlagRule(
                        value=True,
                        segments=[
                            SegmentRule(attribute="user_id", operator="eq", values=["beta-user"])
                        ],
                    )
                ],
            )
        )
        evaluator = FlagEvaluator(store)
        result = await evaluator.evaluate("beta-feature", EvaluationContext(user_id="beta-user"))
        assert result.value is True
        assert result.reason == EvaluationReason.SEGMENT_MATCH

    @pytest.mark.asyncio
    async def test_segment_user_id_no_match(self) -> None:
        store = MemoryFlagStore()
        await store.set_flag(
            FlagDefinition(
                name="beta-feature",
                type=FlagType.SEGMENT,
                default_value=False,
                rules=[
                    FlagRule(
                        value=True,
                        segments=[
                            SegmentRule(attribute="user_id", operator="eq", values=["beta-user"])
                        ],
                    )
                ],
            )
        )
        evaluator = FlagEvaluator(store)
        result = await evaluator.evaluate("beta-feature", EvaluationContext(user_id="normal-user"))
        assert result.value is False
        assert result.reason == EvaluationReason.DEFAULT

    @pytest.mark.asyncio
    async def test_segment_region_match(self) -> None:
        store = MemoryFlagStore()
        await store.set_flag(
            FlagDefinition(
                name="us-only",
                type=FlagType.SEGMENT,
                default_value=False,
                rules=[
                    FlagRule(
                        value=True,
                        segments=[
                            SegmentRule(
                                attribute="region", operator="eq", values=["us-east", "us-west"]
                            )
                        ],
                    )
                ],
            )
        )
        evaluator = FlagEvaluator(store)
        ctx = EvaluationContext(user_id="u1", region="us-east")
        result = await evaluator.evaluate("us-only", ctx)
        assert result.value is True

    @pytest.mark.asyncio
    async def test_segment_property_match(self) -> None:
        store = MemoryFlagStore()
        await store.set_flag(
            FlagDefinition(
                name="employee-only",
                type=FlagType.SEGMENT,
                default_value=False,
                rules=[
                    FlagRule(
                        value=True,
                        segments=[
                            SegmentRule(
                                attribute="properties.role",
                                operator="eq",
                                values=["admin", "engineer"],
                            )
                        ],
                    )
                ],
            )
        )
        evaluator = FlagEvaluator(store)
        ctx = EvaluationContext(user_id="u1", properties={"role": "engineer"})
        result = await evaluator.evaluate("employee-only", ctx)
        assert result.value is True

    @pytest.mark.asyncio
    async def test_segment_neq_operator(self) -> None:
        """Neq excludes matching values, so non-matching users get the default."""
        store = MemoryFlagStore()
        await store.set_flag(
            FlagDefinition(
                name="not-internal",
                type=FlagType.SEGMENT,
                default_value=False,
                rules=[
                    FlagRule(
                        value=True,
                        segments=[
                            SegmentRule(attribute="region", operator="neq", values=["internal"])
                        ],
                    )
                ],
            )
        )
        evaluator = FlagEvaluator(store)
        # Internal user does not match "neq internal" → falls to default (False)
        result = await evaluator.evaluate(
            "not-internal", EvaluationContext(user_id="u1", region="internal")
        )
        assert result.value is False
        # External user matches "neq internal" → gets rule value (True)
        result2 = await evaluator.evaluate(
            "not-internal", EvaluationContext(user_id="u2", region="external")
        )
        assert result2.value is True


# ---------------------------------------------------------------------------
# FlagEvaluator — Bulk evaluation
# ---------------------------------------------------------------------------


class TestEvaluatorBulk:
    @pytest.mark.asyncio
    async def test_evaluate_bulk(self) -> None:
        store = MemoryFlagStore()
        await store.set_flag(FlagDefinition(name="flag-a", default_value=True))
        await store.set_flag(FlagDefinition(name="flag-b", default_value=False))
        evaluator = FlagEvaluator(store)
        ctx = EvaluationContext(user_id="u1")
        results = await evaluator.evaluate_bulk(["flag-a", "flag-b", "no-such"], ctx)
        assert len(results) == 2
        assert results["flag-a"].value is True
        assert results["flag-b"].value is False

    @pytest.mark.asyncio
    async def test_evaluate_all(self) -> None:
        store = MemoryFlagStore()
        await store.set_flag(FlagDefinition(name="flag-a", default_value=True))
        await store.set_flag(FlagDefinition(name="flag-b", default_value=False))
        evaluator = FlagEvaluator(store)
        ctx = EvaluationContext(user_id="u1")
        results = await evaluator.evaluate_all(ctx)
        assert len(results) == 2
        assert "flag-a" in results
        assert "flag-b" in results


# ---------------------------------------------------------------------------
# FlagEvaluator — Edge cases
# ---------------------------------------------------------------------------


class TestEvaluatorEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_overrides(self) -> None:
        store = MemoryFlagStore()
        flag = FlagDefinition(name="empty-overrides", default_value="default", overrides={})
        await store.set_flag(flag)
        evaluator = FlagEvaluator(store)
        result = await evaluator.evaluate("empty-overrides", EvaluationContext(user_id="u1"))
        assert result.value == "default"
        assert result.reason == EvaluationReason.DEFAULT

    @pytest.mark.asyncio
    async def test_missing_store(self) -> None:
        evaluator = FlagEvaluator(MemoryFlagStore())
        ctx = EvaluationContext(user_id="u1")
        with pytest.raises(FlagNotFoundError):
            await evaluator.evaluate("nonexistent", ctx)

    @pytest.mark.asyncio
    async def test_property_value_as_any_type(self) -> None:
        store = MemoryFlagStore()
        await store.set_flag(
            FlagDefinition(
                name="tier-flag",
                type=FlagType.SEGMENT,
                default_value=False,
                rules=[
                    FlagRule(
                        value=True,
                        segments=[
                            SegmentRule(
                                attribute="properties.tier", operator="eq", values=["premium"]
                            )
                        ],
                    )
                ],
            )
        )
        evaluator = FlagEvaluator(store)
        ctx = EvaluationContext(user_id="u1", properties={"tier": "premium"})
        result = await evaluator.evaluate("tier-flag", ctx)
        assert result.value is True

    @pytest.mark.asyncio
    async def test_non_string_property_match(self) -> None:
        """Boolean True stringifies to 'True' and matches string-valued segments."""
        store = MemoryFlagStore()
        await store.set_flag(
            FlagDefinition(
                name="vip-flag",
                type=FlagType.SEGMENT,
                default_value=False,
                rules=[
                    FlagRule(
                        value=True,
                        segments=[
                            SegmentRule(attribute="properties.vip", operator="eq", values=["True"])
                        ],
                    )
                ],
            )
        )
        evaluator = FlagEvaluator(store)
        ctx = EvaluationContext(user_id="u1", properties={"vip": True})
        result = await evaluator.evaluate("vip-flag", ctx)
        # str(True) == "True" matches the segment values
        assert result.value is True


# ---------------------------------------------------------------------------
# _state helpers
# ---------------------------------------------------------------------------


class TestStateHelpers:
    def test_get_set_module(self) -> None:
        class FakeModule:
            name = "test"

        set_featureflags_module(FakeModule())  # type: ignore[arg-type]
        mod = get_featureflags_module()
        assert mod is not None
        assert mod.name == "test"

        set_featureflags_module(None)
        assert get_featureflags_module() is None
