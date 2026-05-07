from __future__ import annotations

from dataclasses import asdict

import pytest

from evidpath.domains.recommender.generation import (
    RecommenderPersonaProfile,
    _apply_behavior_plan_adjustments,
)


def _baseline_profile() -> RecommenderPersonaProfile:
    return RecommenderPersonaProfile(
        preferred_genres=("drama", "comedy"),
        popularity_preference=0.5,
        novelty_preference=0.5,
        repetition_tolerance=0.5,
        sparse_history_confidence=0.5,
        abandonment_sensitivity=0.5,
        patience=3,
        engagement_baseline=0.5,
        quality_sensitivity=0.5,
        repeat_exposure_penalty=0.5,
        novelty_fatigue=0.5,
        frustration_recovery=0.5,
        history_reliance=0.5,
        skip_tolerance=2,
        abandonment_threshold=0.5,
    )


# Baselines captured from the pre-refactor implementation (manual _replace_profile
# helper). Each entry pins the exact field deltas a single behavior tag applies
# to a profile whose floats are all 0.5, patience=3, skip_tolerance=2.
SINGLE_TAG_BASELINES: dict[str, dict[str, float | int]] = {
    "first-hit-or-leave": {
        "abandonment_sensitivity": 0.58,
        "patience": 2,
        "abandonment_threshold": 0.44,
    },
    "trust-before-explore": {
        "novelty_preference": 0.44,
        "quality_sensitivity": 0.58,
        "history_reliance": 0.56,
    },
    "novelty-rewarded-after-quality": {
        "novelty_preference": 0.58,
        "repetition_tolerance": 0.45,
        "quality_sensitivity": 0.54,
    },
    "genre-loyal": {
        "sparse_history_confidence": 0.46,
        "quality_sensitivity": 0.54,
        "history_reliance": 0.58,
    },
    "quickly-bored-by-repetition": {
        "novelty_preference": 0.54,
        "repetition_tolerance": 0.42,
        "repeat_exposure_penalty": 0.58,
    },
    "forgives-one-miss": {
        "abandonment_sensitivity": 0.44,
        "patience": 4,
        "frustration_recovery": 0.58,
    },
    "needs-confidence-from-history": {
        "sparse_history_confidence": 0.42,
        "history_reliance": 0.6,
    },
}


@pytest.mark.parametrize("tag,expected_deltas", list(SINGLE_TAG_BASELINES.items()))
def test_single_behavior_tag_matches_baseline(
    tag: str, expected_deltas: dict[str, float | int]
) -> None:
    base = _baseline_profile()
    result = _apply_behavior_plan_adjustments(base, (tag,))
    base_fields = asdict(base)
    for field, base_value in base_fields.items():
        expected = expected_deltas.get(field, base_value)
        actual = getattr(result, field)
        assert actual == pytest.approx(expected), (
            f"tag {tag!r} field {field}: expected {expected}, got {actual}"
        )


def test_composed_behavior_plan_matches_baseline() -> None:
    base = _baseline_profile()
    all_tags = tuple(SINGLE_TAG_BASELINES.keys())
    result = _apply_behavior_plan_adjustments(base, all_tags)
    expected = {
        "preferred_genres": ("drama", "comedy"),
        "popularity_preference": 0.5,
        "novelty_preference": 0.56,
        "repetition_tolerance": 0.37,
        "sparse_history_confidence": 0.38,
        "abandonment_sensitivity": 0.52,
        "patience": 3,
        "engagement_baseline": 0.5,
        "quality_sensitivity": 0.66,
        "repeat_exposure_penalty": 0.58,
        "novelty_fatigue": 0.5,
        "frustration_recovery": 0.58,
        "history_reliance": 0.74,
        "skip_tolerance": 2,
        "abandonment_threshold": 0.44,
    }
    for field, exp in expected.items():
        actual = getattr(result, field)
        if isinstance(exp, float):
            assert actual == pytest.approx(exp), f"{field}: {actual} != {exp}"
        else:
            assert actual == exp, f"{field}: {actual} != {exp}"


def test_clamps_hold_at_extremes() -> None:
    extreme = RecommenderPersonaProfile(
        preferred_genres=("drama",),
        popularity_preference=0.0,
        novelty_preference=1.0,
        repetition_tolerance=0.0,
        sparse_history_confidence=0.0,
        abandonment_sensitivity=1.0,
        patience=1,
        engagement_baseline=1.0,
        quality_sensitivity=1.0,
        repeat_exposure_penalty=1.0,
        novelty_fatigue=1.0,
        frustration_recovery=1.0,
        history_reliance=1.0,
        skip_tolerance=0,
        abandonment_threshold=0.1,
    )
    result = _apply_behavior_plan_adjustments(
        extreme, tuple(SINGLE_TAG_BASELINES.keys())
    )
    expected = {
        "preferred_genres": ("drama",),
        "popularity_preference": 0.0,
        "novelty_preference": 1.0,
        "repetition_tolerance": 0.0,
        "sparse_history_confidence": 0.0,
        "abandonment_sensitivity": 0.94,
        "patience": 2,
        "engagement_baseline": 1.0,
        "quality_sensitivity": 1.0,
        "repeat_exposure_penalty": 1.0,
        "novelty_fatigue": 1.0,
        "frustration_recovery": 1.0,
        "history_reliance": 1.0,
        "skip_tolerance": 0,
        "abandonment_threshold": 0.1,
    }
    for field, exp in expected.items():
        actual = getattr(result, field)
        if isinstance(exp, float):
            assert actual == pytest.approx(exp), f"{field}: {actual} != {exp}"
        else:
            assert actual == exp, f"{field}: {actual} != {exp}"


def test_unknown_tag_is_noop() -> None:
    base = _baseline_profile()
    result = _apply_behavior_plan_adjustments(base, ("does-not-exist",))
    assert result == base


def test_empty_plan_returns_input_unchanged() -> None:
    base = _baseline_profile()
    assert _apply_behavior_plan_adjustments(base, ()) == base
