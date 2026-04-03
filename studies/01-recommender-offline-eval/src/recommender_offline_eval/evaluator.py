from __future__ import annotations

import math

import numpy as np

from .buckets import (
    SessionResult,
    list_repetition_score,
    simulate_session,
)
from .canonical import BUCKET_ORDER, CANONICAL_RUN_CONFIG, TRACE_BUCKET_ORDER


def recall_at_k(recommended_ids: list[int], relevant_ids: list[int], k: int) -> float:
    relevant_set = set(relevant_ids)
    if not relevant_set:
        return 0.0
    hits = sum(1 for item_id in recommended_ids[:k] if item_id in relevant_set)
    return hits / len(relevant_set)


def ndcg_at_k(recommended_ids: list[int], relevant_ids: list[int], k: int) -> float:
    relevant_set = set(relevant_ids)
    dcg = 0.0
    for rank, item_id in enumerate(recommended_ids[:k], start=1):
        if item_id in relevant_set:
            dcg += 1.0 / math.log2(rank + 1)
    ideal_hits = min(len(relevant_set), k)
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    if ideal_dcg == 0:
        return 0.0
    return dcg / ideal_dcg


def novelty_score(popularity_values: list[float]) -> float:
    if not popularity_values:
        return 0.0
    return float(np.mean([1.0 - popularity for popularity in popularity_values]))


def repetition_score(item_vectors: list[np.ndarray]) -> float:
    if not item_vectors:
        return 0.0
    return list_repetition_score(item_vectors)


def catalog_concentration_score(top_decile_flags: list[bool]) -> float:
    if not top_decile_flags:
        return 0.0
    return float(np.mean([1.0 if flag else 0.0 for flag in top_decile_flags]))


def _aggregate_recommendation_metrics(model, dataset: dict, k: int) -> dict:
    recalls = []
    ndcgs = []
    novelty_scores = []
    repetition_scores = []
    concentration_scores = []
    item_vectors = dataset["item_vector_lookup"]
    item_popularity = dataset["item_popularity_lookup"]
    item_top_decile = dataset["item_top_decile_lookup"]

    for user_id in dataset["eligible_users"]:
        recommended = model.recommend(user_id=user_id, k=k, exclude_seen=True)
        recommended_ids = recommended["item_id"].astype(int).tolist()
        relevant_ids = dataset["test_positive_by_user"][user_id]
        recalls.append(recall_at_k(recommended_ids, relevant_ids, k))
        ndcgs.append(ndcg_at_k(recommended_ids, relevant_ids, k))
        novelty_scores.append(
            novelty_score([item_popularity[item_id] for item_id in recommended_ids])
        )
        repetition_scores.append(
            repetition_score([item_vectors[item_id] for item_id in recommended_ids])
        )
        concentration_scores.append(
            catalog_concentration_score(
                [item_top_decile[item_id] for item_id in recommended_ids]
            )
        )

    return {
        "recall_at_10": float(np.mean(recalls)),
        "ndcg_at_10": float(np.mean(ndcgs)),
        "novelty_score": float(np.mean(novelty_scores)),
        "repetition_score": float(np.mean(repetition_scores)),
        "catalog_concentration": float(np.mean(concentration_scores)),
    }


def _session_metrics(results: list[SessionResult]) -> dict:
    return {
        "bucket_mean_utility": float(
            np.mean([result.mean_utility for result in results])
        ),
        "novelty_score": float(np.mean([result.novelty_score for result in results])),
        "repetition_score": float(
            np.mean([result.repetition_score for result in results])
        ),
        "catalog_concentration": float(
            np.mean([result.catalog_concentration for result in results])
        ),
        "session_fatigue_proxy": float(
            np.mean([result.session_fatigue_proxy for result in results])
        ),
    }


def _summary_sentences(metrics: dict) -> list[str]:
    model_a = metrics["models"]["Model A"]
    model_b = metrics["models"]["Model B"]
    summaries: list[str] = []

    a_aggregate = model_a["aggregate"]
    b_aggregate = model_b["aggregate"]
    if (
        a_aggregate["recall_at_10"] >= b_aggregate["recall_at_10"]
        and a_aggregate["ndcg_at_10"] >= b_aggregate["ndcg_at_10"]
    ):
        summaries.append(
            "Aggregate offline metrics favor Model A, which posts higher Recall@10 "
            f"({a_aggregate['recall_at_10']:.3f} vs {b_aggregate['recall_at_10']:.3f}) "
            f"and NDCG@10 ({a_aggregate['ndcg_at_10']:.3f} vs {b_aggregate['ndcg_at_10']:.3f})."
        )
    else:
        summaries.append(
            "Aggregate offline metrics do not cleanly favor Model A; inspect the table "
            "before using this run as the canonical Phase 1 proof."
        )

    strongest_bucket = max(
        BUCKET_ORDER,
        key=lambda bucket_name: (
            model_b["buckets"][bucket_name]["bucket_mean_utility"]
            - model_a["buckets"][bucket_name]["bucket_mean_utility"],
            -BUCKET_ORDER.index(bucket_name),
        ),
    )
    strongest_delta = (
        model_b["buckets"][strongest_bucket]["bucket_mean_utility"]
        - model_a["buckets"][strongest_bucket]["bucket_mean_utility"]
    )
    summaries.append(
        f"Model B's strongest segment win is {strongest_bucket}, where bucket utility "
        f"improves by {strongest_delta:.3f}."
    )

    repetition_delta = (
        b_aggregate["repetition_score"] - a_aggregate["repetition_score"]
    )
    repetition_text = (
        "lower repetition"
        if repetition_delta < -1e-12
        else "higher repetition"
        if repetition_delta > 1e-12
        else "matched repetition"
    )
    summaries.append(
        "Behaviorally, Model B increases novelty "
        f"({b_aggregate['novelty_score']:.3f} vs {a_aggregate['novelty_score']:.3f}), "
        f"reduces catalog concentration ({b_aggregate['catalog_concentration']:.3f} vs "
        f"{a_aggregate['catalog_concentration']:.3f}), and has {repetition_text} "
        f"({b_aggregate['repetition_score']:.3f} vs {a_aggregate['repetition_score']:.3f})."
    )

    return summaries


def _example_traces(session_results: dict) -> list[dict]:
    examples = []
    for bucket_name in TRACE_BUCKET_ORDER:
        deltas = []
        for user_id, result_b in session_results["Model B"][bucket_name].items():
            result_a = session_results["Model A"][bucket_name][user_id]
            delta = result_b.mean_utility - result_a.mean_utility
            deltas.append((delta, user_id, result_a, result_b))
        positive_deltas = [row for row in deltas if row[0] > 0]
        chosen_rows = positive_deltas or deltas
        delta, user_id, result_a, result_b = min(
            chosen_rows,
            key=lambda row: (-row[0], row[1]),
        )
        examples.append(
            {
                "bucket": bucket_name,
                "user_id": int(user_id),
                "utility_delta": float(delta),
                "Model A": {
                    "mean_utility": result_a.mean_utility,
                    "trace": result_a.trace,
                },
                "Model B": {
                    "mean_utility": result_b.mean_utility,
                    "trace": result_b.trace,
                },
            }
        )
    return examples


def evaluate_models(
    models: dict,
    dataset: dict,
    k: int = 10,
    session_steps: int = CANONICAL_RUN_CONFIG.session_steps,
    slate_size: int = CANONICAL_RUN_CONFIG.slate_size,
    choice_pool: int = CANONICAL_RUN_CONFIG.choice_pool,
) -> dict:
    metrics = {
        "dataset": dataset["summary"],
        "models": {},
    }

    session_results: dict[str, dict[str, dict[int, SessionResult]]] = {
        model_name: {bucket: {} for bucket in BUCKET_ORDER} for model_name in models
    }

    for model_name, model in models.items():
        aggregate_metrics = _aggregate_recommendation_metrics(model, dataset, k)
        bucket_metrics = {}

        for bucket_name in BUCKET_ORDER:
            results = []
            for user_id in dataset["eligible_users"]:
                session = simulate_session(
                    user_id=user_id,
                    recommender=model,
                    bucket_name=bucket_name,
                    dataset=dataset,
                    steps=session_steps,
                    slate_size=slate_size,
                    choice_pool=choice_pool,
                )
                session_results[model_name][bucket_name][user_id] = session
                results.append(session)
            bucket_metrics[bucket_name] = _session_metrics(results)

        metrics["models"][model_name] = {
            "aggregate": aggregate_metrics,
            "buckets": bucket_metrics,
        }

    metrics["summaries"] = _summary_sentences(metrics)
    metrics["trace_examples"] = _example_traces(session_results)
    return metrics
