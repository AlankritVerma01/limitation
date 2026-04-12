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

import pytest
from interaction_harness.cli import main
from interaction_harness.orchestration.types import RunSwarmPlanContext
from interaction_harness.population_generation import (
    generate_population_pack,
    write_population_pack,
)
from interaction_harness.run_plan import PlannedWorkflow
from interaction_harness.scenario_generation import (
    generate_scenario_pack,
    write_scenario_pack,
)

EXAMPLE_SERVICE_DIR = (
    Path(__file__).resolve().parents[1] / "examples" / "recommender_http_service"
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
            scenario_action="explicit_reuse" if scenario_generation_mode == "reused" else "generate_new",
            population_action="explicit_reuse" if swarm_generation_mode == "reused" else "generate_new",
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


def test_run_swarm_help_surfaces_the_brief_driven_path(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["run-swarm", "--help"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert "--brief" in captured.out
    assert "--generation-mode" in captured.out
    assert "saved swarm" in captured.out


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
    fake_scenario_pack = generate_scenario_pack("provider scenario brief", generator_mode="fixture")
    fake_population_pack = generate_population_pack(
        "provider population brief",
        generator_mode="fixture",
        population_size=8,
        candidate_count=16,
    )
    with (
        patch(
            "interaction_harness.cli.plan_run_swarm",
            return_value=_planned_workflow(
                tmp_path=tmp_path / "run-swarm",
                brief="test provider mode",
                generation_mode="provider",
                scenario_pack_path=str((tmp_path / "run-swarm") / "scenario-pack.json"),
                population_pack_path=str((tmp_path / "run-swarm") / "population-pack.json"),
                scenario_generation_mode="provider",
                swarm_generation_mode="provider",
                coverage_source="generated",
            ),
        ),
        patch(
            "interaction_harness.orchestration.coverage.generate_scenario_pack",
            return_value=fake_scenario_pack,
        ) as mock_generate_scenarios,
        patch(
            "interaction_harness.orchestration.coverage.generate_population_pack",
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
            "interaction_harness.cli.plan_run_swarm",
            return_value=_planned_workflow(
                tmp_path=tmp_path / "run-swarm",
                brief="test provider hard failure",
                generation_mode="provider",
                scenario_pack_path=str((tmp_path / "run-swarm") / "scenario-pack.json"),
                population_pack_path=str((tmp_path / "run-swarm") / "population-pack.json"),
                scenario_generation_mode="provider",
                swarm_generation_mode="provider",
                coverage_source="generated",
            ),
        ),
        patch(
            "interaction_harness.orchestration.coverage.generate_scenario_pack",
            side_effect=RuntimeError("Provider-backed scenario generation failed after retrying."),
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
    scenario_pack = generate_scenario_pack("saved scenario reuse brief", generator_mode="fixture")
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
            "interaction_harness.cli.plan_run_swarm",
            return_value=_planned_workflow(
                tmp_path=tmp_path / "run-swarm",
                brief="mix saved scenarios with generated swarm",
                generation_mode="provider",
                scenario_pack_path=str(scenario_pack_path),
                population_pack_path=str((tmp_path / "run-swarm") / "population-pack.json"),
                scenario_generation_mode="reused",
                swarm_generation_mode="provider",
                coverage_source="mixed",
            ),
        ),
        patch(
            "interaction_harness.orchestration.coverage.generate_population_pack",
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


def test_run_swarm_reuses_both_explicit_packs_without_generating(tmp_path: Path) -> None:
    scenario_pack = generate_scenario_pack("saved scenario reuse brief", generator_mode="fixture")
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
        patch("interaction_harness.orchestration.coverage.generate_scenario_pack") as mock_generate_scenarios,
        patch("interaction_harness.orchestration.coverage.generate_population_pack") as mock_generate_population,
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
    scenario_pack = generate_scenario_pack("partial reuse scenario brief", generator_mode="fixture")
    scenario_pack_path = tmp_path / "saved-scenarios.json"
    write_scenario_pack(scenario_pack, scenario_pack_path)
    fake_population_pack = generate_population_pack(
        "generated missing swarm brief",
        generator_mode="fixture",
        population_size=8,
        candidate_count=16,
    )

    with (
        patch("interaction_harness.orchestration.coverage.generate_scenario_pack") as mock_generate_scenarios,
        patch(
            "interaction_harness.orchestration.coverage.generate_population_pack",
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


def test_run_swarm_external_target_writes_pack_artifacts_and_report(tmp_path: Path) -> None:
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

    first_payload = json.loads(Path(str(first_result["results_path"])).read_text(encoding="utf-8"))
    replay_payload = json.loads(Path(str(replay_result["results_path"])).read_text(encoding="utf-8"))
    for summary_payload in (first_payload["summary"], replay_payload["summary"]):
        summary_payload.pop("run_plan_id", None)
        summary_payload.pop("planner_mode", None)
    assert first_payload["summary"] == replay_payload["summary"]
    assert first_payload["risk_flags"] == replay_payload["risk_flags"]
    assert first_payload["metadata"]["scenario_pack_id"] == replay_payload["metadata"]["scenario_pack_id"]
    assert first_payload["metadata"]["population_pack_id"] == replay_payload["metadata"]["population_pack_id"]
