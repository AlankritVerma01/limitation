from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final

CANONICAL_SEED: Final[int] = 0
CANONICAL_TOP_K: Final[int] = 10
CANONICAL_SESSION_STEPS: Final[int] = 4
CANONICAL_SLATE_SIZE: Final[int] = 10
CANONICAL_CHOICE_POOL: Final[int] = 5
CANONICAL_POPULARITY_WEIGHT: Final[float] = 0.25
CANONICAL_DIVERSITY_WEIGHT: Final[float] = 0.35
CANONICAL_SHORTLIST_SIZE: Final[int] = 75

MODEL_LABELS: Final[dict[str, str]] = {
    "Model A": "Popularity baseline",
    "Model B": "Genre-profile recommender with popularity prior",
}

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


@dataclass(frozen=True)
class CanonicalRunConfig:
    dataset_name: str = "MovieLens 100K"
    dataset_slug: str = "movielens-100k"
    train_test_split: str = (
        "Chronological split with each eligible user's last 2 positive interactions held out."
    )
    eligibility_rule: str = (
        "Users with at least 10 ratings and at least 5 positive ratings (rating >= 4)."
    )
    seed: int = CANONICAL_SEED
    top_k: int = CANONICAL_TOP_K
    session_steps: int = CANONICAL_SESSION_STEPS
    slate_size: int = CANONICAL_SLATE_SIZE
    choice_pool: int = CANONICAL_CHOICE_POOL
    popularity_weight: float = CANONICAL_POPULARITY_WEIGHT
    diversity_weight: float = CANONICAL_DIVERSITY_WEIGHT
    shortlist_size: int = CANONICAL_SHORTLIST_SIZE

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["bucket_order"] = BUCKET_ORDER
        payload["model_labels"] = MODEL_LABELS
        payload["metric_definitions"] = METRIC_DEFINITIONS
        return payload


CANONICAL_RUN_CONFIG: Final[CanonicalRunConfig] = CanonicalRunConfig()
