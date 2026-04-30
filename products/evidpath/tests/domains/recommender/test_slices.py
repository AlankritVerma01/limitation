from __future__ import annotations

import json
from pathlib import Path

from evidpath.audit import execute_recommender_audit
from evidpath.domains.recommender import (
    ARTIFACT_FILENAME,
    discover_recommender_slices,
    ensure_reference_artifacts,
    extract_recommender_slice_features,
)
from evidpath.regression import run_regression_audit
from evidpath.schema import RegressionTarget


def _build_modified_candidate_artifacts(
    baseline_dir: Path, candidate_dir: Path
) -> None:
    ensure_reference_artifacts(baseline_dir)
    candidate_dir.mkdir(parents=True, exist_ok=True)
    baseline_payload = json.loads(
        (baseline_dir / ARTIFACT_FILENAME).read_text(encoding="utf-8")
    )
    candidate_payload = dict(baseline_payload)
    candidate_payload["artifact_id"] = "candidate-slice-discovery"
    candidate_items = []
    for item in baseline_payload["items"]:
        updated = dict(item)
        if item["genre"] in {"documentary", "horror"}:
            updated["quality"] = 0.99
            updated["popularity"] = 0.97
            updated["novelty"] = 0.96
        else:
            updated["quality"] = 0.04
            updated["popularity"] = 0.04
            updated["novelty"] = 0.06
        candidate_items.append(updated)
    candidate_payload["items"] = candidate_items
    (candidate_dir / ARTIFACT_FILENAME).write_text(
        json.dumps(candidate_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_recommender_slice_features_are_bucketed_and_deterministic(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)
    run_result = execute_recommender_audit(
        seed=7,
        output_dir=str(tmp_path / "audit"),
        service_artifact_dir=str(artifact_dir),
    )
    first_trace = run_result.traces[0]
    first_score = next(
        score
        for score in run_result.trace_scores
        if score.trace_id == first_trace.trace_id
    )

    features = extract_recommender_slice_features(
        trace_score=first_score,
        trace=first_trace,
    )
    labels = {f"{feature.key}={feature.value}" for feature in features}

    assert any(label.startswith("scenario_profile=") for label in labels)
    assert any(label.startswith("dominant_failure_mode=") for label in labels)
    assert any(label.startswith("utility_bucket=") for label in labels)
    assert any(label.startswith("trust_delta_bucket=") for label in labels)
    assert any(label.startswith("skip_rate_bucket=") for label in labels)


def test_discovered_slices_include_deterministic_one_and_two_feature_signatures(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)
    run_result = execute_recommender_audit(
        seed=9,
        output_dir=str(tmp_path / "audit"),
        service_artifact_dir=str(artifact_dir),
    )

    slice_discovery = discover_recommender_slices(
        scored_traces=run_result.trace_scores,
        traces=run_result.traces,
        run_config=run_result.run_config,
    )
    assert slice_discovery.slice_summaries
    assert all(
        1 <= len(slice_summary.feature_signature) <= 2
        for slice_summary in slice_discovery.slice_summaries
    )
    assert all(
        slice_summary.trace_count >= 2
        for slice_summary in slice_discovery.slice_summaries
    )


def test_single_run_results_include_slice_summaries_and_optional_membership(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)

    without_membership = execute_recommender_audit(
        seed=3,
        output_dir=str(tmp_path / "without-membership"),
        service_artifact_dir=str(artifact_dir),
    )
    without_membership.metadata["include_slice_membership"] = False
    from evidpath.audit import write_run_artifacts

    write_run_artifacts(without_membership)
    without_payload = json.loads(
        Path(
            without_membership.run_config.rollout.output_dir, "results.json"
        ).read_text(encoding="utf-8")
    )
    assert without_payload["slice_discovery"]["slice_summaries"]
    assert without_payload["slice_discovery"]["memberships"] == []

    with_membership = execute_recommender_audit(
        seed=3,
        output_dir=str(tmp_path / "with-membership"),
        service_artifact_dir=str(artifact_dir),
    )
    with_membership.metadata["include_slice_membership"] = True
    write_run_artifacts(with_membership)
    with_payload = json.loads(
        Path(with_membership.run_config.rollout.output_dir, "results.json").read_text(
            encoding="utf-8"
        )
    )
    assert with_payload["slice_discovery"]["slice_summaries"]
    assert with_payload["slice_discovery"]["memberships"]
    report_text = Path(
        with_membership.run_config.rollout.output_dir, "report.md"
    ).read_text(encoding="utf-8")
    assert "## Discovered Failure Slices" in report_text


def test_same_vs_same_regression_keeps_slice_deltas_stable(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)
    result = run_regression_audit(
        baseline_target=RegressionTarget(
            "baseline", "reference_artifact", str(artifact_dir)
        ),
        candidate_target=RegressionTarget(
            "candidate", "reference_artifact", str(artifact_dir)
        ),
        base_seed=5,
        rerun_count=2,
        output_dir=str(tmp_path / "regression"),
    )
    payload = json.loads(
        Path(result["regression_summary_path"]).read_text(encoding="utf-8")
    )
    assert payload["slice_deltas"]
    assert all(
        delta["change_type"] == "stable"
        and delta["trace_count_delta"] == 0
        and delta["session_utility_delta"] == 0.0
        and delta["trust_delta_delta"] == 0.0
        and delta["skip_rate_delta"] == 0.0
        for delta in payload["slice_deltas"]
    )


def test_changed_regression_surfaces_slice_changes(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    _build_modified_candidate_artifacts(baseline_dir, candidate_dir)
    result = run_regression_audit(
        baseline_target=RegressionTarget(
            "baseline", "reference_artifact", str(baseline_dir)
        ),
        candidate_target=RegressionTarget(
            "candidate", "reference_artifact", str(candidate_dir)
        ),
        base_seed=6,
        rerun_count=2,
        output_dir=str(tmp_path / "regression"),
    )
    payload = json.loads(
        Path(result["regression_summary_path"]).read_text(encoding="utf-8")
    )
    report_text = Path(result["regression_report_path"]).read_text(encoding="utf-8")

    assert payload["slice_deltas"]
    assert any(delta["change_type"] != "stable" for delta in payload["slice_deltas"])
    assert "## Discovered Slice Changes" in report_text
