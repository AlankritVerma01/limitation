from __future__ import annotations

import json
from pathlib import Path

from recommender_offline_eval.supporting_artifacts import (
    CANONICAL_RESULT_SNAPSHOT_FILENAME,
    OFFLINE_VS_BUCKET_STORY_FILENAME,
    ROBUSTNESS_RESULTS_FILENAME,
    ROBUSTNESS_SUMMARY_FILENAME,
    build_robustness_payload,
    write_supporting_artifacts,
)


def _fake_public_results(*, holdout_count: int = 2) -> dict:
    return {
        "offline_metrics": {
            "rows": [
                {
                    "Model": "Model A",
                    "Recall@10": 0.088486 if holdout_count == 2 else 0.094883,
                    "NDCG@10": 0.057105 if holdout_count == 2 else 0.058201,
                },
                {
                    "Model": "Model B",
                    "Recall@10": 0.057569 if holdout_count == 2 else 0.056503,
                    "NDCG@10": 0.036194 if holdout_count == 2 else 0.035104,
                },
            ]
        },
        "bucket_utility": {
            "rows": [
                {
                    "Bucket": "Conservative mainstream",
                    "Model A": 0.51937,
                    "Model B": 0.531572,
                    "Delta (B-A)": 0.012202,
                },
                {
                    "Bucket": "Explorer / novelty-seeking",
                    "Model A": 0.338814,
                    "Model B": 0.522726,
                    "Delta (B-A)": 0.183912 if holdout_count == 2 else 0.184805,
                },
                {
                    "Bucket": "Niche-interest",
                    "Model A": 0.44323,
                    "Model B": 0.721956,
                    "Delta (B-A)": 0.278726 if holdout_count == 2 else 0.27987,
                },
                {
                    "Bucket": "Low-patience",
                    "Model A": 0.321101,
                    "Model B": 0.363795,
                    "Delta (B-A)": 0.042694 if holdout_count == 2 else 0.041,
                },
            ]
        },
        "behavioral_diagnostics": {
            "rows": [
                {
                    "Model": "Model A",
                    "Novelty": 0.395147,
                    "Repetition": 0.278523,
                    "Catalog concentration": 1.0,
                },
                {
                    "Model": "Model B",
                    "Novelty": 0.67763,
                    "Repetition": 0.663875,
                    "Catalog concentration": 0.717271 if holdout_count == 2 else 0.713753,
                },
            ]
        },
    }


def _fake_runner(config, *, data_dir, output_dir) -> dict:
    holdout_count = config.test_holdout_positive_count
    return {
        "public_results": _fake_public_results(holdout_count=holdout_count),
        "data_dir": data_dir,
        "output_dir": output_dir,
    }


def test_build_robustness_payload_captures_stable_story() -> None:
    payload = build_robustness_payload(runner=_fake_runner)

    assert payload["stability_checks"]["seed_rows_identical"] is True
    assert payload["stability_checks"]["core_story_stable"] is True
    assert payload["summary"]["seed_sensitivity"].startswith("Seed 0, 1, and 2")
    assert "directional conclusion" in payload["summary"]["split_sensitivity"]
    assert len(payload["variants"]) == 4


def test_write_supporting_artifacts_outputs_expected_files(tmp_path: Path) -> None:
    public_results = _fake_public_results()

    paths = write_supporting_artifacts(
        public_results,
        output_dir=tmp_path,
        runner=_fake_runner,
    )

    assert set(paths) == {
        "robustness_results_path",
        "robustness_summary_path",
        "offline_story_path",
        "snapshot_path",
    }
    assert (tmp_path / ROBUSTNESS_RESULTS_FILENAME).exists()
    assert (tmp_path / ROBUSTNESS_SUMMARY_FILENAME).exists()
    assert (tmp_path / OFFLINE_VS_BUCKET_STORY_FILENAME).exists()
    assert (tmp_path / CANONICAL_RESULT_SNAPSHOT_FILENAME).exists()

    payload = json.loads((tmp_path / ROBUSTNESS_RESULTS_FILENAME).read_text())
    assert payload["stability_checks"]["core_story_stable"] is True
    assert "What Was Checked For Stability" in (
        tmp_path / ROBUSTNESS_SUMMARY_FILENAME
    ).read_text()
    assert "What Offline Metrics Missed" in (
        tmp_path / OFFLINE_VS_BUCKET_STORY_FILENAME
    ).read_text()
