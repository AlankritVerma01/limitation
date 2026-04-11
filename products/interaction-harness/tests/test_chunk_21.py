from __future__ import annotations

import json
from pathlib import Path

from interaction_harness.cli import main
from interaction_harness.domains.recommender import ensure_reference_artifacts


def test_audit_writes_run_manifest_with_target_and_artifact_metadata(
    tmp_path: Path,
) -> None:
    result = main(
        [
            "audit",
            "--domain",
            "recommender",
            "--use-mock",
            "--output-dir",
            str(tmp_path / "audit"),
        ]
    )

    manifest_path = Path(str(result["run_manifest_path"]))
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["workflow_type"] == "audit"
    assert payload["domain"] == "recommender"
    assert payload["service"]["service_kind"] == "mock"
    assert payload["artifacts"]["report_path"].endswith("report.md")
    assert payload["artifacts"]["results_path"].endswith("results.json")
    assert payload["artifacts"]["traces_path"].endswith("traces.jsonl")


def test_run_swarm_writes_manifest_with_coverage_provenance(tmp_path: Path) -> None:
    result = main(
        [
            "run-swarm",
            "--domain",
            "recommender",
            "--use-mock",
            "--brief",
            "test manifest provenance for provider-free swarm generation",
            "--generation-mode",
            "fixture",
            "--output-dir",
            str(tmp_path / "run-swarm"),
        ]
    )

    manifest_path = Path(str(result["run_manifest_path"]))
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["workflow_type"] == "run-swarm"
    assert payload["coverage"]["scenario_source"] == "generated_pack"
    assert payload["coverage"]["scenario_pack_mode"] == "fixture"
    assert payload["coverage"]["population_source"] == "generated_pack"
    assert payload["coverage"]["population_pack_mode"] == "fixture"
    assert payload["workflow_metadata"]["coverage_source"] == "generated"
    assert payload["workflow_metadata"]["scenario_generation_mode"] == "fixture"
    assert payload["workflow_metadata"]["swarm_generation_mode"] == "fixture"


def test_compare_writes_regression_run_manifest(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    ensure_reference_artifacts(baseline_dir)
    ensure_reference_artifacts(candidate_dir)
    result = main(
        [
            "compare",
            "--domain",
            "recommender",
            "--baseline-artifact-dir",
            str(baseline_dir),
            "--candidate-artifact-dir",
            str(candidate_dir),
            "--scenario",
            "returning-user-home-feed",
            "--rerun-count",
            "1",
            "--output-dir",
            str(tmp_path / "compare"),
        ]
    )

    manifest_path = Path(str(result["run_manifest_path"]))
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["workflow_type"] == "compare"
    assert payload["domain"] == "recommender"
    assert payload["baseline"]["label"] == "baseline"
    assert payload["candidate"]["label"] == "candidate"
    assert payload["artifacts"]["regression_report_path"].endswith("regression_report.md")
    assert payload["artifacts"]["regression_summary_path"].endswith(
        "regression_summary.json"
    )
