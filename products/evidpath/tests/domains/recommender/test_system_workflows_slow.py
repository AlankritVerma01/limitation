from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from urllib import request

import evidpath as ih
import pytest
from evidpath.artifacts.run_plan import PlannedWorkflow
from evidpath.audit import execute_recommender_audit, write_run_artifacts
from evidpath.cli import main
from evidpath.config import build_run_config
from evidpath.domain_registry import get_domain_definition
from evidpath.domains.recommender import (
    ARTIFACT_FILENAME,
    build_recommender_run_config,
    ensure_reference_artifacts,
    resolve_built_in_recommender_scenarios,
    run_reference_recommender_service,
)
from evidpath.orchestration.types import RunSwarmPlanContext
from evidpath.population_generation import (
    generate_population_pack,
    write_population_pack,
)
from evidpath.regression import (
    _default_regression_output_dir,
    run_regression_audit,
)
from evidpath.scenario_generation import (
    generate_scenario_pack,
    write_scenario_pack,
)
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
    assert ih.get_domain_definition is get_domain_definition
    assert not hasattr(ih, "build_recommender_run_config")


def test_shared_build_run_config_does_not_resolve_recommender_inputs() -> None:
    scenarios = resolve_built_in_recommender_scenarios(("returning-user-home-feed",))
    with patch(
        "evidpath.domains.recommender.inputs.resolve_recommender_inputs"
    ) as resolver:
        run_config = build_run_config(
            seed=2,
            scenarios=scenarios,
            agent_seeds=tuple(),
        )

    resolver.assert_not_called()
    assert run_config.scenarios == scenarios
    assert run_config.agent_seeds == ()
    assert run_config.rollout.service_artifact_dir is None


def test_recommender_run_config_still_resolves_inputs() -> None:
    run_config, resolved_inputs = build_recommender_run_config(
        seed=2,
        scenario_names=("returning-user-home-feed",),
    )

    assert run_config.scenarios == resolved_inputs.scenarios
    assert run_config.agent_seeds == resolved_inputs.agent_seeds
    assert resolved_inputs.metadata["scenario_source"] == "built_in"


def test_audit_runs_through_domain_runner_and_writes_domain_title(
    tmp_path: Path,
) -> None:
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
    assert report_text.startswith("# Evidpath Recommender Audit")


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

    with run_reference_recommender_service(str(candidate_dir)) as (
        candidate_url,
        _metadata,
    ):
        result = run_regression_audit(
            baseline_target=RegressionTarget(
                "baseline",
                "http_native_reference",
                {"artifact_dir": str(baseline_dir)},
            ),
            candidate_target=RegressionTarget(
                "candidate",
                "http_native_external",
                {"base_url": candidate_url},
            ),
            base_seed=4,
            rerun_count=2,
            output_dir=str(tmp_path / "regression"),
        )

    payload = json.loads(
        Path(result["regression_summary_path"]).read_text(encoding="utf-8")
    )
    report_text = Path(result["regression_report_path"]).read_text(encoding="utf-8")
    assert payload["candidate_summary"]["target"]["driver_kind"] == "http_native_external"
    assert payload["metadata"]["domain_name"] == "recommender"
    assert payload["metadata"]["candidate_target_driver_kind"] == "http_native_external"
    assert payload["metadata"]["baseline_target_identity"]
    assert payload["metadata"]["candidate_target_identity"]
    assert report_text.startswith("# Evidpath Regression Audit")


def test_compare_honors_scenario_pack_path(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    ensure_reference_artifacts(baseline_dir)
    ensure_reference_artifacts(candidate_dir)
    scenario_pack = generate_scenario_pack(
        "test trust and exploration balance for returning users",
        generator_mode="fixture",
    )
    pack_path = tmp_path / "scenario-pack.json"
    write_scenario_pack(scenario_pack, pack_path)

    result = run_regression_audit(
        baseline_target=RegressionTarget(
            label="baseline",
            driver_kind="http_native_reference",
            driver_config={"artifact_dir": str(baseline_dir)},
        ),
        candidate_target=RegressionTarget(
            label="candidate",
            driver_kind="http_native_reference",
            driver_config={"artifact_dir": str(candidate_dir)},
        ),
        base_seed=4,
        rerun_count=1,
        output_dir=str(tmp_path / "regression"),
        scenario_pack_path=str(pack_path),
    )

    payload = json.loads(
        Path(result["regression_summary_path"]).read_text(encoding="utf-8")
    )
    assert payload["metadata"]["scenario_pack_path"] == "<normalized>"
    assert (
        payload["baseline_summary"]["metadata"]["scenario_pack_id"]
        == scenario_pack.metadata.pack_id
    )
    assert (
        payload["candidate_summary"]["metadata"]["scenario_pack_id"]
        == scenario_pack.metadata.pack_id
    )


def test_cli_compare_requires_exactly_one_target_reference(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "compare",
                "--domain",
                "recommender",
                "--baseline-artifact-dir",
                str(artifact_dir),
                "--candidate-artifact-dir",
                str(artifact_dir),
                "--candidate-url",
                "http://localhost:9999",
            ]
        )

    assert (
        str(exc_info.value)
        == "compare requires exactly one of --candidate-artifact-dir or --candidate-url."
    )


def test_default_regression_output_dir_distinguishes_external_urls_with_same_labels() -> (
    None
):
    definition = get_domain_definition("recommender")
    first = _default_regression_output_dir(
        baseline_target=RegressionTarget(
            "same", "http_native_external", {"base_url": "http://localhost:8001"}
        ),
        candidate_target=RegressionTarget(
            "same", "http_native_external", {"base_url": "http://localhost:8002"}
        ),
        base_seed=3,
        domain_definition=definition,
    )
    second = _default_regression_output_dir(
        baseline_target=RegressionTarget(
            "same", "http_native_external", {"base_url": "http://localhost:8011"}
        ),
        candidate_target=RegressionTarget(
            "same", "http_native_external", {"base_url": "http://localhost:8012"}
        ),
        base_seed=3,
        domain_definition=definition,
    )

    assert first != second


def test_default_regression_output_dir_distinguishes_artifact_targets_with_same_labels(
    tmp_path: Path,
) -> None:
    definition = get_domain_definition("recommender")
    first = _default_regression_output_dir(
        baseline_target=RegressionTarget(
            "same", "http_native_reference", {"artifact_dir": str(tmp_path / "a")}
        ),
        candidate_target=RegressionTarget(
            "same", "http_native_reference", {"artifact_dir": str(tmp_path / "b")}
        ),
        base_seed=3,
        domain_definition=definition,
    )
    second = _default_regression_output_dir(
        baseline_target=RegressionTarget(
            "same", "http_native_reference", {"artifact_dir": str(tmp_path / "c")}
        ),
        candidate_target=RegressionTarget(
            "same", "http_native_reference", {"artifact_dir": str(tmp_path / "d")}
        ),
        base_seed=3,
        domain_definition=definition,
    )

    assert first != second


EXAMPLE_SERVICE_DIR = (
    Path(__file__).resolve().parents[3] / "examples" / "recommender_http_service"
)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@contextmanager
def _run_example_service(
    *,
    model_kind: str,
    artifact_dir: Path,
):
    port = _free_port()
    env = os.environ.copy()
    env["IH_EXAMPLE_MODEL_KIND"] = model_kind
    env["IH_EXAMPLE_ARTIFACT_DIR"] = str(artifact_dir)
    process = subprocess.Popen(
        [
            sys.executable,
            str(EXAMPLE_SERVICE_DIR / "run.py"),
            "--model-kind",
            model_kind,
            "--artifact-dir",
            str(artifact_dir),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_health(base_url)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _wait_for_health(base_url: str) -> None:
    last_error: Exception | None = None
    for _ in range(80):
        try:
            with request.urlopen(f"{base_url}/health", timeout=0.5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("status") == "ok":
                return
        except Exception as exc:  # pragma: no cover - polling fallback
            last_error = exc
        time.sleep(0.1)
    raise RuntimeError(f"Example service did not become ready: {last_error}")


def _planned_workflow(
    *,
    tmp_path: Path,
    brief: str,
    generation_mode: str,
    scenario_pack_path: str | None,
    population_pack_path: str | None,
    scenario_generation_mode: str,
    swarm_generation_mode: str,
    coverage_source: str,
) -> RunSwarmPlanContext:
    plan_path = tmp_path / "run_plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text("{}", encoding="utf-8")
    return RunSwarmPlanContext(
        plan=PlannedWorkflow(
            payload={},
            plan_path=str(plan_path),
            plan_id="test-plan",
            planner_mode="deterministic",
            planner_provider_name="",
            planner_model_name="",
            planner_model_profile="",
            planner_summary=f"planned {brief}",
            scenario_pack_path=scenario_pack_path,
            population_pack_path=population_pack_path,
            scenario_action="explicit_reuse"
            if scenario_generation_mode == "reused"
            else "generate_new",
            population_action="explicit_reuse"
            if swarm_generation_mode == "reused"
            else "generate_new",
            scenario_generation_mode=scenario_generation_mode,
            swarm_generation_mode=swarm_generation_mode,
            coverage_source=coverage_source,
            generation_mode=generation_mode,
            ai_profile="fast",
            scenario_count=3,
            population_size=8,
            population_candidate_count=16,
            semantic_mode="off",
            semantic_model=None,
            semantic_profile="fast",
        ),
        service_mode="mock",
        service_artifact_dir=None,
        adapter_base_url=None,
        output_root=str(tmp_path),
    )


def test_run_swarm_rejects_auto_generation_mode(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "run-swarm",
                "--domain",
                "recommender",
                "--use-mock",
                "--brief",
                "test invalid auto mode",
                "--generation-mode",
                "auto",
                "--output-dir",
                str(tmp_path / "run-swarm"),
            ]
        )

    assert exc_info.value.code == 2


def test_run_swarm_fixture_mode_writes_generated_packs_and_report(
    tmp_path: Path,
    capsys,
) -> None:
    result = main(
        [
            "run-swarm",
            "--domain",
            "recommender",
            "--use-mock",
            "--brief",
            "test trust collapse for impatient and exploratory movie viewers",
            "--generation-mode",
            "fixture",
            "--output-dir",
            str(tmp_path / "run-swarm"),
        ]
    )

    captured = capsys.readouterr()
    assert "Using generation mode: fixture" in captured.err
    assert "Generating scenario candidates" in captured.err
    assert "Generating population candidates" in captured.err
    assert "Running traces" in captured.err
    assert "Swarm run complete:" in captured.out
    assert "Scenario generation: fixture" in captured.out
    assert "Swarm generation: fixture" in captured.out
    assert Path(str(result["scenario_pack_path"])).exists()
    assert Path(str(result["population_pack_path"])).exists()
    assert Path(str(result["report_path"])).exists()
    assert result["coverage_source"] == "generated"
    assert result["scenario_generation_mode"] == "fixture"
    assert result["swarm_generation_mode"] == "fixture"


def test_run_swarm_provider_mode_routes_both_generators_through_provider(
    tmp_path: Path,
) -> None:
    fake_scenario_pack = generate_scenario_pack(
        "provider scenario brief", generator_mode="fixture"
    )
    fake_population_pack = generate_population_pack(
        "provider population brief",
        generator_mode="fixture",
        population_size=8,
        candidate_count=16,
    )
    with (
        patch(
            "evidpath.cli_app.handlers.plan_run_swarm",
            return_value=_planned_workflow(
                tmp_path=tmp_path / "run-swarm",
                brief="test provider mode",
                generation_mode="provider",
                scenario_pack_path=str((tmp_path / "run-swarm") / "scenario-pack.json"),
                population_pack_path=str(
                    (tmp_path / "run-swarm") / "population-pack.json"
                ),
                scenario_generation_mode="provider",
                swarm_generation_mode="provider",
                coverage_source="generated",
            ),
        ),
        patch(
            "evidpath.orchestration.coverage.generate_scenario_pack",
            return_value=fake_scenario_pack,
        ) as mock_generate_scenarios,
        patch(
            "evidpath.orchestration.coverage.generate_population_pack",
            return_value=fake_population_pack,
        ) as mock_generate_population,
    ):
        result = main(
            [
                "run-swarm",
                "--domain",
                "recommender",
                "--use-mock",
                "--brief",
                "test provider mode",
                "--generation-mode",
                "provider",
                "--output-dir",
                str(tmp_path / "run-swarm"),
            ]
        )

    assert mock_generate_scenarios.call_args.kwargs["generator_mode"] == "provider"
    assert mock_generate_population.call_args.kwargs["generator_mode"] == "provider"
    assert result["scenario_generation_mode"] == "provider"
    assert result["swarm_generation_mode"] == "provider"


def test_run_swarm_provider_mode_still_fails_when_provider_generation_fails(
    tmp_path: Path,
) -> None:
    with (
        patch(
            "evidpath.cli_app.handlers.plan_run_swarm",
            return_value=_planned_workflow(
                tmp_path=tmp_path / "run-swarm",
                brief="test provider hard failure",
                generation_mode="provider",
                scenario_pack_path=str((tmp_path / "run-swarm") / "scenario-pack.json"),
                population_pack_path=str(
                    (tmp_path / "run-swarm") / "population-pack.json"
                ),
                scenario_generation_mode="provider",
                swarm_generation_mode="provider",
                coverage_source="generated",
            ),
        ),
        patch(
            "evidpath.orchestration.coverage.generate_scenario_pack",
            side_effect=RuntimeError(
                "Provider-backed scenario generation failed after retrying."
            ),
        ),
    ):
        with pytest.raises(RuntimeError):
            main(
                [
                    "run-swarm",
                    "--domain",
                    "recommender",
                    "--use-mock",
                    "--brief",
                    "test provider hard failure",
                    "--generation-mode",
                    "provider",
                    "--output-dir",
                    str(tmp_path / "run-swarm"),
                ]
            )


def test_run_swarm_mixed_reuse_summary_shows_separate_generation_fields(
    tmp_path: Path,
    capsys,
) -> None:
    scenario_pack = generate_scenario_pack(
        "saved scenario reuse brief", generator_mode="fixture"
    )
    scenario_pack_path = tmp_path / "saved-scenarios.json"
    write_scenario_pack(scenario_pack, scenario_pack_path)
    fake_population_pack = generate_population_pack(
        "generated provider swarm brief",
        generator_mode="fixture",
        population_size=8,
        candidate_count=16,
    )

    with (
        patch(
            "evidpath.cli_app.handlers.plan_run_swarm",
            return_value=_planned_workflow(
                tmp_path=tmp_path / "run-swarm",
                brief="mix saved scenarios with generated swarm",
                generation_mode="provider",
                scenario_pack_path=str(scenario_pack_path),
                population_pack_path=str(
                    (tmp_path / "run-swarm") / "population-pack.json"
                ),
                scenario_generation_mode="reused",
                swarm_generation_mode="provider",
                coverage_source="mixed",
            ),
        ),
        patch(
            "evidpath.orchestration.coverage.generate_population_pack",
            return_value=fake_population_pack,
        ),
    ):
        result = main(
            [
                "run-swarm",
                "--domain",
                "recommender",
                "--use-mock",
                "--brief",
                "mix saved scenarios with generated swarm",
                "--scenario-pack-path",
                str(scenario_pack_path),
                "--generation-mode",
                "provider",
                "--output-dir",
                str(tmp_path / "run-swarm"),
            ]
        )

    captured = capsys.readouterr()
    assert "Scenario generation: reused" in captured.out
    assert "Swarm generation: provider" in captured.out
    assert result["coverage_source"] == "mixed"
    assert result["scenario_generation_mode"] == "reused"
    assert result["swarm_generation_mode"] == "provider"


def test_run_swarm_reuses_both_explicit_packs_without_generating(
    tmp_path: Path,
) -> None:
    scenario_pack = generate_scenario_pack(
        "saved scenario reuse brief", generator_mode="fixture"
    )
    population_pack = generate_population_pack(
        "saved population reuse brief",
        generator_mode="fixture",
        population_size=8,
        candidate_count=16,
    )
    scenario_pack_path = tmp_path / "saved-scenarios.json"
    population_pack_path = tmp_path / "saved-population.json"
    write_scenario_pack(scenario_pack, scenario_pack_path)
    write_population_pack(population_pack, population_pack_path)

    with (
        patch(
            "evidpath.orchestration.coverage.generate_scenario_pack"
        ) as mock_generate_scenarios,
        patch(
            "evidpath.orchestration.coverage.generate_population_pack"
        ) as mock_generate_population,
    ):
        result = main(
            [
                "run-swarm",
                "--domain",
                "recommender",
                "--use-mock",
                "--brief",
                "this brief should be ignored because both packs are explicit",
                "--scenario-pack-path",
                str(scenario_pack_path),
                "--population-pack-path",
                str(population_pack_path),
                "--output-dir",
                str(tmp_path / "run-swarm"),
            ]
        )

    mock_generate_scenarios.assert_not_called()
    mock_generate_population.assert_not_called()
    assert result["coverage_source"] == "reused"
    assert str(result["scenario_pack_path"]) == str(scenario_pack_path)
    assert str(result["population_pack_path"]) == str(population_pack_path)


def test_run_swarm_reuses_one_explicit_pack_and_generates_the_missing_side(
    tmp_path: Path,
) -> None:
    scenario_pack = generate_scenario_pack(
        "partial reuse scenario brief", generator_mode="fixture"
    )
    scenario_pack_path = tmp_path / "saved-scenarios.json"
    write_scenario_pack(scenario_pack, scenario_pack_path)
    fake_population_pack = generate_population_pack(
        "generated missing swarm brief",
        generator_mode="fixture",
        population_size=8,
        candidate_count=16,
    )

    with (
        patch(
            "evidpath.orchestration.coverage.generate_scenario_pack"
        ) as mock_generate_scenarios,
        patch(
            "evidpath.orchestration.coverage.generate_population_pack",
            return_value=fake_population_pack,
        ) as mock_generate_population,
    ):
        result = main(
            [
                "run-swarm",
                "--domain",
                "recommender",
                "--use-mock",
                "--brief",
                "reuse one side and generate the other",
                "--scenario-pack-path",
                str(scenario_pack_path),
                "--generation-mode",
                "fixture",
                "--output-dir",
                str(tmp_path / "run-swarm"),
            ]
        )

    mock_generate_scenarios.assert_not_called()
    mock_generate_population.assert_called_once()
    assert result["coverage_source"] == "mixed"
    assert str(result["scenario_pack_path"]) == str(scenario_pack_path)
    assert Path(str(result["population_pack_path"])).exists()


def test_run_swarm_external_target_writes_pack_artifacts_and_report(
    tmp_path: Path,
) -> None:
    with _run_example_service(
        model_kind="popularity",
        artifact_dir=tmp_path / "external-service-artifacts",
    ) as base_url:
        result = main(
            [
                "run-swarm",
                "--domain",
                "recommender",
                "--target-url",
                base_url,
                "--brief",
                "test trust collapse for impatient and exploratory movie viewers",
                "--generation-mode",
                "fixture",
                "--seed",
                "7",
                "--output-dir",
                str(tmp_path / "external-run-swarm"),
            ]
        )

    payload = json.loads(Path(str(result["results_path"])).read_text(encoding="utf-8"))
    assert Path(str(result["scenario_pack_path"])).exists()
    assert Path(str(result["population_pack_path"])).exists()
    assert Path(str(result["report_path"])).exists()
    assert payload["summary"]["scenario_source"] == "generated_pack"
    assert payload["metadata"]["population_source"] == "generated_pack"
    assert payload["metadata"]["service_kind"] == "external"


def test_run_swarm_report_metadata_surfaces_pack_provenance(tmp_path: Path) -> None:
    result = main(
        [
            "run-swarm",
            "--domain",
            "recommender",
            "--use-mock",
            "--brief",
            "test provenance metadata for scenario and swarm generation",
            "--generation-mode",
            "fixture",
            "--output-dir",
            str(tmp_path / "run-swarm"),
        ]
    )

    report = Path(str(result["report_path"])).read_text(encoding="utf-8")
    assert "Scenario pack mode:" in report
    assert "Scenario pack model:" in report
    assert "Scenario pack profile:" in report
    assert "Swarm pack mode:" in report
    assert "Swarm pack model:" in report
    assert "Swarm pack profile:" in report


def test_run_swarm_saved_packs_can_be_replayed_through_audit_deterministically(
    tmp_path: Path,
) -> None:
    first_result = main(
        [
            "run-swarm",
            "--domain",
            "recommender",
            "--use-mock",
            "--brief",
            "test stable replay for impatient and exploratory users",
            "--generation-mode",
            "fixture",
            "--seed",
            "5",
            "--output-dir",
            str(tmp_path / "first-run"),
        ]
    )

    replay_result = main(
        [
            "audit",
            "--domain",
            "recommender",
            "--use-mock",
            "--seed",
            "5",
            "--semantic-mode",
            "fixture",
            "--scenario-pack-path",
            str(first_result["scenario_pack_path"]),
            "--population-pack-path",
            str(first_result["population_pack_path"]),
            "--output-dir",
            str(tmp_path / "replay-run"),
        ]
    )

    first_payload = json.loads(
        Path(str(first_result["results_path"])).read_text(encoding="utf-8")
    )
    replay_payload = json.loads(
        Path(str(replay_result["results_path"])).read_text(encoding="utf-8")
    )
    for summary_payload in (first_payload["summary"], replay_payload["summary"]):
        summary_payload.pop("run_plan_id", None)
        summary_payload.pop("planner_mode", None)
    assert first_payload["summary"] == replay_payload["summary"]
    assert first_payload["risk_flags"] == replay_payload["risk_flags"]
    assert (
        first_payload["metadata"]["scenario_pack_id"]
        == replay_payload["metadata"]["scenario_pack_id"]
    )
    assert (
        first_payload["metadata"]["population_pack_id"]
        == replay_payload["metadata"]["population_pack_id"]
    )
