from __future__ import annotations

import json
from pathlib import Path

from interaction_harness.cli import _build_parser, main
from interaction_harness.domains.recommender import ensure_reference_artifacts
from interaction_harness.regression import run_regression_audit
from interaction_harness.schema import RegressionTarget


def test_single_run_report_includes_executive_summary_and_compact_traces(tmp_path: Path) -> None:
    result = main(
        [
            "audit",
            "--domain",
            "recommender",
            "--seed",
            "11",
            "--use-mock",
            "--run-name",
            "Polished Demo Run",
            "--output-dir",
            str(tmp_path / "single"),
        ]
    )
    report_body = Path(result["report_path"]).read_text(encoding="utf-8")
    results_payload = json.loads(Path(result["results_path"]).read_text(encoding="utf-8"))
    assert "## Executive Summary" in report_body
    assert "## Representative Traces To Inspect" in report_body
    assert "Highest-Risk Cohorts" in report_body or "Strongest Cohorts" in report_body
    assert results_payload["summary"]["display_name"] == "Polished Demo Run"
    assert results_payload["summary"]["run_id"].startswith("run-")
    assert results_payload["summary"]["generated_at_utc"] == "<normalized>"


def test_regression_outputs_include_summary_and_most_important_changes(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)
    result = run_regression_audit(
        baseline_target=RegressionTarget(
            label="stable-baseline",
            mode="reference_artifact",
            service_artifact_dir=str(artifact_dir),
        ),
        candidate_target=RegressionTarget(
            label="stable-candidate",
            mode="reference_artifact",
            service_artifact_dir=str(artifact_dir),
        ),
        base_seed=3,
        rerun_count=2,
        output_dir=str(tmp_path / "regression"),
    )
    report_body = Path(result["regression_report_path"]).read_text(encoding="utf-8")
    payload = json.loads(Path(result["regression_summary_path"]).read_text(encoding="utf-8"))
    assert "## Executive Summary" in report_body
    assert "## Most Important Changes" in report_body
    assert payload["summary"]["display_name"] == "stable-baseline vs stable-candidate"
    assert payload["summary"]["regression_id"].startswith("reg-")
    assert payload["summary"]["generated_at_utc"] == "<normalized>"
    assert "overall_direction" in payload["summary"]


def test_cli_help_mentions_compare_and_run_name() -> None:
    help_text = _build_parser().format_help()
    assert "audit" in help_text
    assert "compare" in help_text
    assert "generate-scenarios" in help_text
    assert "generate-population" in help_text
    assert "serve-reference" in help_text
    assert "--compare" not in help_text


def test_compare_mode_accepts_label_overrides(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    ensure_reference_artifacts(baseline_dir)
    ensure_reference_artifacts(candidate_dir)
    result = main(
        [
            "compare",
            "--domain",
            "recommender",
            "--seed",
            "5",
            "--rerun-count",
            "2",
            "--baseline-artifact-dir",
            str(baseline_dir),
            "--candidate-artifact-dir",
            str(candidate_dir),
            "--baseline-label",
            "current-prod",
            "--candidate-label",
            "next-build",
            "--output-dir",
            str(tmp_path / "compare"),
        ]
    )
    payload = json.loads(Path(result["regression_summary_path"]).read_text(encoding="utf-8"))
    assert payload["summary"]["baseline_label"] == "current-prod"
    assert payload["summary"]["candidate_label"] == "next-build"
