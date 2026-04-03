from __future__ import annotations

import json
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
from recommender_offline_eval.report import (
    CHART_FILENAME,
    JSON_FILENAME,
    REPORT_FILENAME,
)
from recommender_offline_eval.run_demo import run_canonical_demo


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


def test_canonical_pipeline_outputs_are_stable(tmp_path) -> None:
    first_output = tmp_path / "run-a"
    second_output = tmp_path / "run-b"

    first_result = run_canonical_demo(output_dir=first_output)
    run_canonical_demo(output_dir=second_output)

    first_json = json.loads((first_output / JSON_FILENAME).read_text())
    second_json = json.loads((second_output / JSON_FILENAME).read_text())
    assert list(first_json.keys()) == [
        "run_summary",
        "offline_metrics",
        "bucket_utility",
        "behavioral_diagnostics",
        "key_takeaways",
        "trace_examples",
        "reproducibility",
    ]
    assert first_json == second_json

    first_report = (first_output / REPORT_FILENAME).read_text()
    second_report = (second_output / REPORT_FILENAME).read_text()
    assert first_report == second_report
    assert [line for line in first_report.splitlines() if line.startswith("## ")] == [
        "## Run summary",
        "## Standard offline metrics",
        "## Bucket-level utility",
        "## Behavioral diagnostics",
        "## Key takeaways",
        "## Short traces",
        "## Reproducibility note",
    ]

    first_chart = (first_output / CHART_FILENAME).read_text()
    second_chart = (second_output / CHART_FILENAME).read_text()
    assert first_chart == second_chart

    assert first_result["chart_path"].name == CHART_FILENAME
    assert first_result["report_path"].name == REPORT_FILENAME
    assert first_result["metrics_path"].name == JSON_FILENAME

    offline_rows = first_json["offline_metrics"]["rows"]
    model_a_offline = next(row for row in offline_rows if row["Model"] == "Model A")
    model_b_offline = next(row for row in offline_rows if row["Model"] == "Model B")
    assert model_a_offline["Recall@10"] > model_b_offline["Recall@10"]
    assert model_a_offline["NDCG@10"] > model_b_offline["NDCG@10"]

    bucket_rows = first_json["bucket_utility"]["rows"]
    explorer = next(
        row for row in bucket_rows if row["Bucket"] == "Explorer / novelty-seeking"
    )
    niche = next(row for row in bucket_rows if row["Bucket"] == "Niche-interest")
    assert explorer["Model B"] > explorer["Model A"]
    assert niche["Model B"] > niche["Model A"]

    behavior_rows = first_json["behavioral_diagnostics"]["rows"]
    model_a_behavior = next(row for row in behavior_rows if row["Model"] == "Model A")
    model_b_behavior = next(row for row in behavior_rows if row["Model"] == "Model B")
    assert model_b_behavior["Catalog concentration"] < model_a_behavior[
        "Catalog concentration"
    ]
