from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from interaction_harness.audit import execute_recommender_audit, write_run_artifacts
from interaction_harness.domains.recommender import (
    ARTIFACT_FILENAME,
    ensure_reference_artifacts,
)
from interaction_harness.regression import run_regression_audit
from interaction_harness.schema import RegressionTarget
from interaction_harness.semantic_interpretation import (
    interpret_run_semantics,
)


def _build_modified_candidate_artifacts(baseline_dir: Path, candidate_dir: Path) -> None:
    ensure_reference_artifacts(baseline_dir)
    candidate_dir.mkdir(parents=True, exist_ok=True)
    baseline_payload = json.loads((baseline_dir / ARTIFACT_FILENAME).read_text(encoding="utf-8"))
    candidate_payload = dict(baseline_payload)
    candidate_payload["artifact_id"] = "candidate-semantic-interpretation"
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


def test_fixture_run_semantics_are_structured_and_stable(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)
    run_result = execute_recommender_audit(
        seed=7,
        output_dir=str(tmp_path / "audit"),
        service_artifact_dir=str(artifact_dir),
    )
    first = interpret_run_semantics(run_result, mode="fixture")
    second = interpret_run_semantics(run_result, mode="fixture")

    assert first is not None
    assert second is not None
    assert first.trace_explanations == second.trace_explanations
    assert first.advisory_summary == second.advisory_summary
    assert 1 <= len(first.trace_explanations) <= 3
    assert all(explanation.grounding_references for explanation in first.trace_explanations)


def test_provider_run_semantics_validate_exact_trace_ids(monkeypatch, tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)
    run_result = execute_recommender_audit(
        seed=4,
        output_dir=str(tmp_path / "audit"),
        service_artifact_dir=str(artifact_dir),
    )
    expected_ids = [
        explanation.trace_id
        for explanation in interpret_run_semantics(run_result, mode="fixture").trace_explanations
    ]
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    payload = {
        "output_text": json.dumps(
            {
                "advisory_summary": "The trace set shows deterministic failures and one contrast success.",
                "trace_explanations": [
                    {
                        "trace_id": trace_id,
                        "explanation_summary": f"{trace_id} shows a grounded advisory summary.",
                        "issue_theme": "grounded theme",
                        "recommended_follow_up": "Review the trace against the deterministic evidence.",
                        "grounding_references": ["dominant_failure_mode=trust_collapse"],
                    }
                    for trace_id in expected_ids
                ],
            }
        )
    }
    with patch(
        "interaction_harness.semantic_interpretation.request_provider_payload",
        return_value=payload,
    ):
        interpretation = interpret_run_semantics(run_result, mode="provider", model_name="gpt-5-mini")
    assert interpretation is not None
    assert interpretation.mode == "provider"
    assert [explanation.trace_id for explanation in interpretation.trace_explanations] == expected_ids


def test_provider_run_semantics_reject_malformed_json(monkeypatch, tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)
    run_result = execute_recommender_audit(
        seed=4,
        output_dir=str(tmp_path / "audit"),
        service_artifact_dir=str(artifact_dir),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch(
        "interaction_harness.semantic_interpretation.request_provider_payload",
        return_value={"output_text": "{not-json"},
    ):
        with pytest.raises(ValueError):
            interpret_run_semantics(run_result, mode="provider", model_name="gpt-5-mini")


def test_semantic_mode_off_preserves_deterministic_outputs(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)
    run_result = execute_recommender_audit(
        seed=2,
        output_dir=str(tmp_path / "audit"),
        service_artifact_dir=str(artifact_dir),
        semantic_mode="off",
    )
    write_run_artifacts(run_result)
    results_payload = json.loads(
        Path(run_result.run_config.rollout.output_dir, "results.json").read_text(encoding="utf-8")
    )
    assert "semantic_interpretation" not in results_payload


def test_fixture_semantic_mode_writes_single_run_outputs(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)
    run_result = execute_recommender_audit(
        seed=8,
        output_dir=str(tmp_path / "audit"),
        service_artifact_dir=str(artifact_dir),
        semantic_mode="fixture",
    )
    write_run_artifacts(run_result)
    results_payload = json.loads(
        Path(run_result.run_config.rollout.output_dir, "results.json").read_text(encoding="utf-8")
    )
    report_text = Path(run_result.run_config.rollout.output_dir, "report.md").read_text(
        encoding="utf-8"
    )
    assert results_payload["semantic_interpretation"]["mode"] == "fixture"
    assert results_payload["semantic_interpretation"]["trace_explanations"]
    assert "## Semantic Advisory" in report_text


def test_fixture_semantic_mode_writes_regression_outputs(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)
    result = run_regression_audit(
        baseline_target=RegressionTarget("baseline", "reference_artifact", str(artifact_dir)),
        candidate_target=RegressionTarget("candidate", "reference_artifact", str(artifact_dir)),
        base_seed=5,
        rerun_count=2,
        output_dir=str(tmp_path / "regression"),
        semantic_mode="fixture",
    )
    payload = json.loads(Path(result["regression_summary_path"]).read_text(encoding="utf-8"))
    report_text = Path(result["regression_report_path"]).read_text(encoding="utf-8")
    assert payload["semantic_interpretation"]["mode"] == "fixture"
    assert payload["semantic_interpretation"]["trace_explanations"]
    assert "## Semantic Advisory" in report_text


def test_regression_semantics_explain_only_selected_notable_traces(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    _build_modified_candidate_artifacts(baseline_dir, candidate_dir)
    result = run_regression_audit(
        baseline_target=RegressionTarget("baseline", "reference_artifact", str(baseline_dir)),
        candidate_target=RegressionTarget("candidate", "reference_artifact", str(candidate_dir)),
        base_seed=6,
        rerun_count=2,
        output_dir=str(tmp_path / "regression"),
        semantic_mode="fixture",
    )
    payload = json.loads(Path(result["regression_summary_path"]).read_text(encoding="utf-8"))
    explained_ids = [
        explanation["trace_id"]
        for explanation in payload["semantic_interpretation"]["trace_explanations"]
    ]
    notable_ids = [trace_delta["trace_id"] for trace_delta in payload["notable_trace_deltas"][:3]]
    assert explained_ids == notable_ids
    assert result["decision_status"] in {"pass", "warn", "fail"}
