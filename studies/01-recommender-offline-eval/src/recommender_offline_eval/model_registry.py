"""Small registry for the built-in baseline and candidate models."""

from __future__ import annotations

from typing import Callable

from .config import ModelSpec
from .recommenders import GenreProfileRecommender, PopularityRecommender, Recommender

ModelFactory = Callable[[ModelSpec], Recommender]


def _build_popularity(spec: ModelSpec) -> Recommender:
    if spec.params:
        raise ValueError("popularity does not accept any params.")
    return PopularityRecommender(name=spec.label)


def _build_genre_profile(spec: ModelSpec) -> Recommender:
    allowed_keys = {"popularity_weight", "diversity_weight", "shortlist_size"}
    unknown_keys = sorted(set(spec.params) - allowed_keys)
    if unknown_keys:
        raise ValueError(
            "genre_profile received unsupported params: " + ", ".join(unknown_keys)
        )
    return GenreProfileRecommender(
        name=spec.label,
        popularity_weight=float(spec.params.get("popularity_weight", 0.25)),
        diversity_weight=float(spec.params.get("diversity_weight", 0.35)),
        shortlist_size=int(spec.params.get("shortlist_size", 75)),
    )


MODEL_REGISTRY: dict[str, ModelFactory] = {
    "popularity": _build_popularity,
    "genre_profile": _build_genre_profile,
}


def build_model(spec: ModelSpec) -> Recommender:
    try:
        factory = MODEL_REGISTRY[spec.type]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported model type {spec.type!r}. "
            f"Expected one of: {', '.join(sorted(MODEL_REGISTRY))}."
        ) from exc
    return factory(spec)
