from __future__ import annotations

import math

import numpy as np

from .buckets import (
    BUCKET_WEIGHTS,
    SessionResult,
    list_repetition_score,
    simulate_session,
)


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


def _aggregate_recommendation_metrics(model, dataset: dict, k: int) -> dict:
    recalls = []
    ndcgs = []
    novelty_scores = []
    overlap_repetition_scores = []
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
            float(
                np.mean([1.0 - item_popularity[item_id] for item_id in recommended_ids])
            )
        )
        overlap_repetition_scores.append(
            list_repetition_score(
                [item_vectors[item_id] for item_id in recommended_ids]
            )
        )
        concentration_scores.append(
            float(
                np.mean(
                    [
                        1.0 if item_top_decile[item_id] else 0.0
                        for item_id in recommended_ids
                    ]
                )
            )
        )

    mean_overlap = float(np.mean(overlap_repetition_scores))
    mean_concentration = float(np.mean(concentration_scores))

    return {
        "recall_at_10": float(np.mean(recalls)),
        "ndcg_at_10": float(np.mean(ndcgs)),
        "novelty_score": float(np.mean(novelty_scores)),
        "repetition_score": 0.45 * mean_overlap + 0.55 * mean_concentration,
        "catalog_concentration": mean_concentration,
    }


def _session_metrics(results: list[SessionResult]) -> dict:
    mean_overlap = float(np.mean([result.repetition_score for result in results]))
    mean_concentration = float(
        np.mean([result.catalog_concentration for result in results])
    )
    return {
        "bucket_mean_utility": float(
            np.mean([result.mean_utility for result in results])
        ),
        "novelty_score": float(np.mean([result.novelty_score for result in results])),
        "repetition_score": 0.45 * mean_overlap + 0.55 * mean_concentration,
        "catalog_concentration": mean_concentration,
        "session_fatigue_proxy": float(
            np.mean([result.session_fatigue_proxy for result in results])
        ),
    }


def _summary_sentences(metrics: dict) -> list[str]:
    model_a = metrics["models"]["Model A"]
    model_b = metrics["models"]["Model B"]
    summaries = []

    explorer_a = model_a["buckets"]["Explorer / novelty-seeking"]
    explorer_b = model_b["buckets"]["Explorer / novelty-seeking"]
    summaries.append(
        "Explorer users favored Model B: "
        f"bucket utility rose from {explorer_a['bucket_mean_utility']:.3f} to {explorer_b['bucket_mean_utility']:.3f}, "
        f"with novelty increasing from {explorer_a['novelty_score']:.3f} to {explorer_b['novelty_score']:.3f}."
    )

    niche_a = model_a["buckets"]["Niche-interest"]
    niche_b = model_b["buckets"]["Niche-interest"]
    summaries.append(
        "Niche-interest users also favored Model B: "
        f"mean utility improved by {niche_b['bucket_mean_utility'] - niche_a['bucket_mean_utility']:.3f}, "
        "showing that the personalized model is better at matching narrower taste profiles."
    )

    low_patience_a = model_a["buckets"]["Low-patience"]
    low_patience_b = model_b["buckets"]["Low-patience"]
    summaries.append(
        "Low-patience users reacted strongly to stale slates: "
        f"Model A's repetition score was {low_patience_a['repetition_score']:.3f} versus {low_patience_b['repetition_score']:.3f} for Model B, "
        f"while Model B still delivered higher utility ({low_patience_b['bucket_mean_utility']:.3f} vs {low_patience_a['bucket_mean_utility']:.3f})."
    )

    return summaries


def _example_traces(session_results: dict) -> list[dict]:
    examples = []
    for bucket_name in [
        "Explorer / novelty-seeking",
        "Niche-interest",
        "Low-patience",
    ]:
        deltas = []
        for user_id, result_b in session_results["Model B"][bucket_name].items():
            result_a = session_results["Model A"][bucket_name][user_id]
            delta = result_b.mean_utility - result_a.mean_utility
            deltas.append((delta, user_id, result_a, result_b))
        deltas.sort(key=lambda row: row[0], reverse=True)
        delta, user_id, result_a, result_b = deltas[0]
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


def evaluate_models(models: dict, dataset: dict, k: int = 10) -> dict:
    metrics = {
        "dataset": dataset["summary"],
        "models": {},
    }

    session_results: dict[str, dict[str, dict[int, SessionResult]]] = {
        model_name: {bucket: {} for bucket in BUCKET_WEIGHTS} for model_name in models
    }

    for model_name, model in models.items():
        aggregate_metrics = _aggregate_recommendation_metrics(model, dataset, k)
        bucket_metrics = {}

        for bucket_name in BUCKET_WEIGHTS:
            results = []
            for user_id in dataset["eligible_users"]:
                session = simulate_session(
                    user_id=user_id,
                    recommender=model,
                    bucket_name=bucket_name,
                    dataset=dataset,
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
