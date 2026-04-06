from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import interaction_harness as ih
import pytest
from interaction_harness.audit import execute_recommender_audit, write_run_artifacts
from interaction_harness.cli import main
from interaction_harness.config import build_recommender_run_config, build_run_config
from interaction_harness.domain_registry import get_domain_definition
from interaction_harness.regression import (
    _default_regression_output_dir,
    run_regression_audit,
)
from interaction_harness.scenarios.recommender import (
    resolve_built_in_recommender_scenarios,
)
from interaction_harness.schema import RegressionTarget
from interaction_harness.services.reference_artifacts import (
    ARTIFACT_FILENAME,
    ensure_reference_artifacts,
)
from interaction_harness.services.reference_recommender import (
    run_reference_recommender_service,
)


def _build_modified_candidate_artifacts(baseline_dir: Path, candidate_dir: Path) -> None:
    ensure_reference_artifacts(baseline_dir)
    candidate_dir.mkdir(parents=True, exist_ok=True)
    baseline_payload = json.loads((baseline_dir / ARTIFACT_FILENAME).read_text(encoding="utf-8"))
    candidate_payload = dict(baseline_payload)
    candidate_payload["artifact_id"] = "candidate-portability-expansion"
    candidate_items = []
    for item in baseline_payload["items"]:
        updated = dict(item)
        if item["genre"] in {"documentary", "drama"}:
            updated["quality"] = 0.98
            updated["popularity"] = 0.97
            updated["novelty"] = 0.96
        else:
            updated["quality"] = 0.08
            updated["popularity"] = 0.09
            updated["novelty"] = 0.07
        candidate_items.append(updated)
    candidate_payload["items"] = candidate_items
    (candidate_dir / ARTIFACT_FILENAME).write_text(
        json.dumps(candidate_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_domain_registry_resolves_recommender_definition() -> None:
    definition = get_domain_definition("recommender")

    assert definition.name == "recommender"
    assert "Recommender" in definition.audit_report_title
    assert "Regression" in definition.regression_report_title
    assert callable(definition.resolve_inputs)
    assert callable(definition.build_run_config)
    assert callable(definition.build_target_identity)


def test_light_public_surface_exports_new_helpers() -> None:
    assert ih.build_run_config is build_run_config
    assert ih.build_recommender_run_config is build_recommender_run_config
    assert ih.get_domain_definition is get_domain_definition


def test_shared_build_run_config_does_not_resolve_recommender_inputs() -> None:
    scenarios = resolve_built_in_recommender_scenarios(("returning-user-home-feed",))
    with patch("interaction_harness.config.resolve_recommender_inputs") as resolver:
        run_config = build_run_config(
            seed=2,
            scenarios=scenarios,
            agent_seeds=tuple(),
        )

    resolver.assert_not_called()
    assert run_config.scenarios == scenarios
    assert run_config.agent_seeds == ()


def test_recommender_run_config_still_resolves_inputs() -> None:
    run_config, resolved_inputs = build_recommender_run_config(
        seed=2,
        scenario_names=("returning-user-home-feed",),
    )

    assert run_config.scenarios == resolved_inputs.scenarios
    assert run_config.agent_seeds == resolved_inputs.agent_seeds
    assert resolved_inputs.metadata["scenario_source"] == "built_in"


def test_audit_runs_through_domain_runner_and_writes_domain_title(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)

    run_result = execute_recommender_audit(
        seed=9,
        output_dir=str(tmp_path / "audit"),
        service_artifact_dir=str(artifact_dir),
    )
    write_run_artifacts(run_result)
    report_text = Path(run_result.run_config.rollout.output_dir, "report.md").read_text(
        encoding="utf-8"
    )

    assert run_result.metadata["domain_name"] == "recommender"
    assert report_text.startswith("# Interaction Harness Recommender Audit")


def test_single_run_external_url_path_still_works(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)

    with run_reference_recommender_service(str(artifact_dir)) as (base_url, _metadata):
        run_result = execute_recommender_audit(
            seed=3,
            output_dir=str(tmp_path / "audit"),
            adapter_base_url=base_url,
        )

    assert run_result.metadata["service_mode"] == "external"
    assert run_result.metadata["service_kind"] == "reference"


def test_compare_supports_external_url_targets(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    _build_modified_candidate_artifacts(baseline_dir, candidate_dir)

    with run_reference_recommender_service(str(candidate_dir)) as (candidate_url, _metadata):
        result = run_regression_audit(
            baseline_target=RegressionTarget(
                "baseline",
                "reference_artifact",
                service_artifact_dir=str(baseline_dir),
            ),
            candidate_target=RegressionTarget(
                "candidate",
                "external_url",
                adapter_base_url=candidate_url,
            ),
            base_seed=4,
            rerun_count=2,
            output_dir=str(tmp_path / "regression"),
        )

    payload = json.loads(Path(result["regression_summary_path"]).read_text(encoding="utf-8"))
    report_text = Path(result["regression_report_path"]).read_text(encoding="utf-8")
    assert payload["candidate_summary"]["target"]["mode"] == "external_url"
    assert payload["metadata"]["domain_name"] == "recommender"
    assert payload["metadata"]["candidate_target_mode"] == "external_url"
    assert payload["metadata"]["baseline_target_identity"]
    assert payload["metadata"]["candidate_target_identity"]
    assert report_text.startswith("# Interaction Harness Regression Audit")


def test_cli_compare_requires_exactly_one_target_reference(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--compare",
                "--baseline-artifact-dir",
                str(artifact_dir),
                "--candidate-artifact-dir",
                str(artifact_dir),
                "--candidate-base-url",
                "http://localhost:9999",
            ]
        )

    assert (
        str(exc_info.value)
        == "--compare requires exactly one of --candidate-artifact-dir or --candidate-base-url."
    )


def test_default_regression_output_dir_distinguishes_external_urls_with_same_labels() -> None:
    definition = get_domain_definition("recommender")
    first = _default_regression_output_dir(
        baseline_target=RegressionTarget("same", "external_url", adapter_base_url="http://localhost:8001"),
        candidate_target=RegressionTarget("same", "external_url", adapter_base_url="http://localhost:8002"),
        base_seed=3,
        domain_definition=definition,
    )
    second = _default_regression_output_dir(
        baseline_target=RegressionTarget("same", "external_url", adapter_base_url="http://localhost:8011"),
        candidate_target=RegressionTarget("same", "external_url", adapter_base_url="http://localhost:8012"),
        base_seed=3,
        domain_definition=definition,
    )

    assert first != second


def test_default_regression_output_dir_distinguishes_artifact_targets_with_same_labels(tmp_path: Path) -> None:
    definition = get_domain_definition("recommender")
    first = _default_regression_output_dir(
        baseline_target=RegressionTarget("same", "reference_artifact", service_artifact_dir=str(tmp_path / "a")),
        candidate_target=RegressionTarget("same", "reference_artifact", service_artifact_dir=str(tmp_path / "b")),
        base_seed=3,
        domain_definition=definition,
    )
    second = _default_regression_output_dir(
        baseline_target=RegressionTarget("same", "reference_artifact", service_artifact_dir=str(tmp_path / "c")),
        candidate_target=RegressionTarget("same", "reference_artifact", service_artifact_dir=str(tmp_path / "d")),
        base_seed=3,
        domain_definition=definition,
    )

    assert first != second


def test_compare_help_mentions_external_urls(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    captured = capsys.readouterr()
    assert "artifact-backed or external URL targets" in captured.out
