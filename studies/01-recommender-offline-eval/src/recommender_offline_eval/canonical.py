"""Frozen constants and config for the official MovieLens demo."""

from __future__ import annotations

from typing import Final

from .config import CanonicalRunConfig, DatasetSpec, ModelSpec

CANONICAL_SEED: Final[int] = 0
CANONICAL_TOP_K: Final[int] = 10
CANONICAL_SESSION_STEPS: Final[int] = 4
CANONICAL_SLATE_SIZE: Final[int] = 10
CANONICAL_CHOICE_POOL: Final[int] = 5
CANONICAL_POSITIVE_RATING_THRESHOLD: Final[int] = 4
CANONICAL_MIN_USER_RATINGS: Final[int] = 10
CANONICAL_MIN_USER_POSITIVE_RATINGS: Final[int] = 5
CANONICAL_TEST_HOLDOUT_POSITIVES: Final[int] = 2
CANONICAL_POPULARITY_WEIGHT: Final[float] = 0.25
CANONICAL_DIVERSITY_WEIGHT: Final[float] = 0.35
CANONICAL_SHORTLIST_SIZE: Final[int] = 75

BUCKET_ORDER: Final[list[str]] = [
    "Conservative mainstream",
    "Explorer / novelty-seeking",
    "Niche-interest",
    "Low-patience",
]

TRACE_BUCKET_ORDER: Final[list[str]] = [
    "Explorer / novelty-seeking",
    "Niche-interest",
    "Low-patience",
]

BUCKET_DESCRIPTIONS: Final[dict[str, str]] = {
    "Conservative mainstream": (
        "Prefers familiar, high-exposure items and tolerates safe recommendations."
    ),
    "Explorer / novelty-seeking": (
        "Values discovery and variety, and rewards recommendation sets that surface less"
        " familiar items."
    ),
    "Niche-interest": (
        "Has narrower taste clusters and benefits when the model can match specialized"
        " catalog pockets."
    ),
    "Low-patience": (
        "Needs good recommendations quickly and loses utility faster when sequences feel"
        " stale."
    ),
}

METRIC_DEFINITIONS: Final[dict[str, str]] = {
    "Recall@10": "Mean recall on held-out positive items per eligible user.",
    "NDCG@10": "Mean NDCG on held-out positive items per eligible user.",
    "Bucket utility": (
        "Mean simulated per-step utility for a fixed bucket over the short canonical"
        " session."
    ),
    "Novelty": "Mean of 1 - popularity_norm over recommended or consumed items.",
    "Repetition": "Mean similarity to the user's recent consumed items.",
    "Catalog concentration": "Share of recommendations that fall in the top popularity decile.",
}

CANONICAL_DATASET_SPEC: Final[DatasetSpec] = DatasetSpec(
    type="movielens_100k",
    name="MovieLens 100K",
    dataset_id="movielens-100k",
)

CANONICAL_BASELINE_MODEL: Final[ModelSpec] = ModelSpec(
    type="popularity",
    label="Popularity baseline",
)

CANONICAL_CANDIDATE_MODEL: Final[ModelSpec] = ModelSpec(
    type="genre_profile",
    label="Genre-profile recommender with popularity prior",
    params={
        "popularity_weight": CANONICAL_POPULARITY_WEIGHT,
        "diversity_weight": CANONICAL_DIVERSITY_WEIGHT,
        "shortlist_size": CANONICAL_SHORTLIST_SIZE,
    },
)

CANONICAL_RUN_CONFIG: Final[CanonicalRunConfig] = CanonicalRunConfig(
    dataset=CANONICAL_DATASET_SPEC,
    baseline_model=CANONICAL_BASELINE_MODEL,
    candidate_model=CANONICAL_CANDIDATE_MODEL,
    artifact_mode="canonical",
    seed=CANONICAL_SEED,
    top_k=CANONICAL_TOP_K,
    session_steps=CANONICAL_SESSION_STEPS,
    slate_size=CANONICAL_SLATE_SIZE,
    choice_pool=CANONICAL_CHOICE_POOL,
    positive_rating_threshold=CANONICAL_POSITIVE_RATING_THRESHOLD,
    min_user_ratings=CANONICAL_MIN_USER_RATINGS,
    min_user_positive_ratings=CANONICAL_MIN_USER_POSITIVE_RATINGS,
    test_holdout_positive_count=CANONICAL_TEST_HOLDOUT_POSITIVES,
)
