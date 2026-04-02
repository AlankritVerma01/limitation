from __future__ import annotations

from dataclasses import dataclass

import numpy as np

BUCKET_WEIGHTS = {
    "Conservative mainstream": {
        "affinity": 0.55,
        "popularity": 0.35,
        "novelty": 0.00,
        "repetition": -0.10,
    },
    "Explorer / novelty-seeking": {
        "affinity": 0.45,
        "popularity": 0.00,
        "novelty": 0.35,
        "repetition": -0.20,
    },
    "Niche-interest": {
        "affinity": 0.70,
        "popularity": -0.10,
        "novelty": 0.20,
        "repetition": 0.00,
    },
    "Low-patience": {
        "affinity": 0.60,
        "popularity": 0.10,
        "novelty": 0.00,
        "repetition": -0.30,
    },
}


def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_norm = np.linalg.norm(left)
    right_norm = np.linalg.norm(right)
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return float(np.dot(left, right) / (left_norm * right_norm))


def repetition_penalty(
    item_vector: np.ndarray, history_vectors: list[np.ndarray]
) -> float:
    if not history_vectors:
        return 0.0
    recent = history_vectors[-2:]
    overlaps = [
        cosine_similarity(item_vector, history_vector) for history_vector in recent
    ]
    return float(np.mean(overlaps))


def bucket_utility(
    bucket_name: str,
    affinity: float,
    popularity: float,
    novelty: float,
    repetition: float,
) -> float:
    weights = BUCKET_WEIGHTS[bucket_name]
    return float(
        weights["affinity"] * affinity
        + weights["popularity"] * popularity
        + weights["novelty"] * novelty
        + weights["repetition"] * repetition
    )


def list_repetition_score(item_vectors: list[np.ndarray]) -> float:
    if len(item_vectors) < 2:
        return 0.0
    overlaps = [
        cosine_similarity(item_vectors[idx], item_vectors[idx + 1])
        for idx in range(len(item_vectors) - 1)
    ]
    return float(np.mean(overlaps))


@dataclass
class SessionResult:
    user_id: int
    bucket_name: str
    model_name: str
    mean_utility: float
    novelty_score: float
    repetition_score: float
    catalog_concentration: float
    session_fatigue_proxy: float
    trace: list[dict]


def simulate_session(
    user_id: int,
    recommender,
    bucket_name: str,
    dataset: dict,
    steps: int = 4,
    slate_size: int = 10,
    choice_pool: int = 5,
) -> SessionResult:
    user_profile = dataset["user_profiles"][user_id]
    item_vectors = dataset["item_vector_lookup"]
    item_popularity = dataset["item_popularity_lookup"]
    item_top_decile = dataset["item_top_decile_lookup"]
    item_titles = dataset["item_title_lookup"]

    history = list(dataset["user_recent_positive_history"].get(user_id, []))
    consumed = set(history)
    history_vectors = [
        item_vectors[item_id] for item_id in history if item_id in item_vectors
    ]

    utilities = []
    novelties = []
    repetitions = []
    concentrations = []
    trace = []

    for step in range(steps):
        slate = recommender.recommend(
            user_id=user_id,
            k=slate_size,
            exclude_seen=True,
            extra_exclude=consumed,
        )
        if slate.empty:
            break

        pool = slate.head(choice_pool).copy()
        scored_candidates = []
        for row in pool.itertuples():
            item_id = int(row.item_id)
            affinity = cosine_similarity(user_profile, item_vectors[item_id])
            popularity = float(item_popularity[item_id])
            novelty = 1.0 - popularity
            repetition = repetition_penalty(item_vectors[item_id], history_vectors)
            utility = bucket_utility(
                bucket_name, affinity, popularity, novelty, repetition
            )
            scored_candidates.append(
                {
                    "item_id": item_id,
                    "title": item_titles[item_id],
                    "model_rank_score": float(row.score),
                    "affinity": affinity,
                    "popularity": popularity,
                    "novelty": novelty,
                    "repetition_penalty": repetition,
                    "utility": utility,
                }
            )

        chosen = max(
            scored_candidates,
            key=lambda item: (item["utility"], item["model_rank_score"]),
        )
        history.append(chosen["item_id"])
        consumed.add(chosen["item_id"])
        history_vectors.append(item_vectors[chosen["item_id"]])

        utilities.append(chosen["utility"])
        novelties.append(chosen["novelty"])
        repetitions.append(chosen["repetition_penalty"])
        concentrations.append(1.0 if item_top_decile[chosen["item_id"]] else 0.0)
        trace.append(
            {
                "step": step + 1,
                "title": chosen["title"],
                "utility": chosen["utility"],
                "affinity": chosen["affinity"],
                "popularity": chosen["popularity"],
                "novelty": chosen["novelty"],
                "repetition_penalty": chosen["repetition_penalty"],
            }
        )

    fatigue = 0.0
    if len(repetitions) > 1:
        fatigue = float(np.mean(np.diff(repetitions)))

    return SessionResult(
        user_id=user_id,
        bucket_name=bucket_name,
        model_name=recommender.name,
        mean_utility=float(np.mean(utilities)) if utilities else 0.0,
        novelty_score=float(np.mean(novelties)) if novelties else 0.0,
        repetition_score=float(np.mean(repetitions)) if repetitions else 0.0,
        catalog_concentration=float(np.mean(concentrations)) if concentrations else 0.0,
        session_fatigue_proxy=fatigue,
        trace=trace,
    )
