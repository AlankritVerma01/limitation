from __future__ import annotations

import json
from pathlib import Path

from interaction_harness.cli import main
from interaction_harness.regression import build_seed_schedule, run_regression_audit
from interaction_harness.schema import RegressionTarget
from interaction_harness.services.reference_artifacts import (
    ARTIFACT_FILENAME,
    ensure_reference_artifacts,
)


def test_seed_schedule_is_deterministic() -> None:
    assert build_seed_schedule(11, 3) == (11, 12, 13)


def test_same_artifact_dir_produces_zero_metric_deltas(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "shared-artifacts"
    ensure_reference_artifacts(artifact_dir)
    paths = run_regression_audit(
        baseline_target=RegressionTarget(
            label="baseline",
            mode="reference_artifact",
            service_artifact_dir=str(artifact_dir),
        ),
        candidate_target=RegressionTarget(
            label="candidate",
            mode="reference_artifact",
            service_artifact_dir=str(artifact_dir),
        ),
        base_seed=4,
        rerun_count=2,
        output_dir=str(tmp_path / "regression"),
    )
    payload = json.loads(Path(paths["regression_summary_path"]).read_text(encoding="utf-8"))
    assert payload["baseline_summary"]["seed_schedule"] == [4, 5]
    assert all(metric["delta"] == 0.0 for metric in payload["metric_deltas"])


def test_modified_candidate_artifact_produces_visible_deltas(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline-artifacts"
    candidate_dir = tmp_path / "candidate-artifacts"
    ensure_reference_artifacts(baseline_dir)
    candidate_dir.mkdir(parents=True, exist_ok=True)
    baseline_payload = json.loads(
        (baseline_dir / ARTIFACT_FILENAME).read_text(encoding="utf-8")
    )
    candidate_payload = dict(baseline_payload)
    candidate_payload["artifact_id"] = "candidate-regression-test"
    candidate_items = []
    for item in baseline_payload["items"]:
        updated = dict(item)
        if item["genre"] in {"documentary", "horror"}:
            updated["quality"] = 0.98
            updated["popularity"] = 0.92
            updated["novelty"] = 0.88
        elif item["genre"] in {"action", "comedy"}:
            updated["quality"] = 0.18
            updated["popularity"] = 0.12
            updated["novelty"] = 0.22
        candidate_items.append(updated)
    candidate_payload["items"] = candidate_items
    (candidate_dir / ARTIFACT_FILENAME).write_text(
        json.dumps(candidate_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths = run_regression_audit(
        baseline_target=RegressionTarget(
            label="baseline",
            mode="reference_artifact",
            service_artifact_dir=str(baseline_dir),
        ),
        candidate_target=RegressionTarget(
            label="candidate",
            mode="reference_artifact",
            service_artifact_dir=str(candidate_dir),
        ),
        base_seed=6,
        rerun_count=2,
        output_dir=str(tmp_path / "regression-different"),
    )
    payload = json.loads(Path(paths["regression_summary_path"]).read_text(encoding="utf-8"))
    assert payload["candidate_summary"]["metadata"]["artifact_id"] == "candidate-regression-test"
    assert any(abs(metric["delta"]) > 0.001 for metric in payload["metric_deltas"])


def test_cli_compare_mode_writes_regression_artifacts(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    ensure_reference_artifacts(baseline_dir)
    ensure_reference_artifacts(candidate_dir)
    result = main(
        [
            "--compare",
            "--seed",
            "7",
            "--rerun-count",
            "2",
            "--baseline-artifact-dir",
            str(baseline_dir),
            "--candidate-artifact-dir",
            str(candidate_dir),
            "--output-dir",
            str(tmp_path / "compare-output"),
        ]
    )
    assert Path(result["regression_report_path"]).exists()
    assert Path(result["regression_summary_path"]).exists()
    assert Path(result["regression_traces_path"]).exists()
    report_body = Path(result["regression_report_path"]).read_text(encoding="utf-8")
    assert "Regression Audit" in report_body
    assert "informational in this version" in report_body
