from __future__ import annotations

import math

import numpy as np
from recommender_offline_eval.buckets import bucket_utility
from recommender_offline_eval.evaluator import (
    catalog_concentration_score,
    ndcg_at_k,
    novelty_score,
    recall_at_k,
    repetition_score,
)


def test_recall_at_k() -> None:
    assert recall_at_k([1, 2, 3], [2, 4], 3) == 0.5


def test_ndcg_at_k() -> None:
    expected = (1.0 / math.log2(3) + 1.0 / math.log2(4)) / (
        1.0 / math.log2(2) + 1.0 / math.log2(3)
    )
    assert ndcg_at_k([1, 2, 3], [2, 3], 3) == expected


def test_bucket_utility() -> None:
    score = bucket_utility(
        "Explorer / novelty-seeking",
        affinity=0.4,
        popularity=0.2,
        novelty=0.8,
        repetition=0.1,
    )
    assert score == 0.45 * 0.4 + 0.35 * 0.8 - 0.20 * 0.1


def test_novelty_score() -> None:
    assert novelty_score([0.2, 0.5, 1.0]) == 0.43333333333333335


def test_repetition_score() -> None:
    vectors = [
        np.array([1.0, 0.0]),
        np.array([1.0, 0.0]),
        np.array([0.0, 1.0]),
    ]
    assert repetition_score(vectors) == 0.5


def test_catalog_concentration_score() -> None:
    assert catalog_concentration_score([True, False, True, True]) == 0.75
