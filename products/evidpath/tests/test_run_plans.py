from __future__ import annotations

import json
from pathlib import Path

import pytest
from evidpath.artifacts.run_plan import RUN_PLAN_CONTRACT_VERSION
from evidpath.cli import main
from evidpath.domains.recommender import ensure_reference_artifacts
from evidpath.orchestration import (
    AuditExecutionRequest,
    AuditPlanRequest,
    RunSwarmExecutionRequest,
    RunSwarmPlanRequest,
    execute_audit_plan,
    execute_run_swarm_plan,
    plan_audit,
    plan_run_swarm,
)
from evidpath.population_generation import (
    build_default_population_pack_path,
    generate_population_pack,
    write_population_pack,
)
from evidpath.scenario_generation import (
    build_default_scenario_pack_path,
    generate_scenario_pack,
    write_scenario_pack,
)


def test_run_swarm_writes_run_plan_and_links_manifest(tmp_path: Path) -> None:
    result = main(
        [
            "run-swarm",
            "--domain",
            "recommender",
            "--use-mock",
            "--brief",
            "test planner artifact for impatient exploratory users",
            "--generation-mode",
            "fixture",
            "--output-dir",
            str(tmp_path / "run-swarm"),
        ]
    )

    plan_path = Path(str(result["run_plan_path"]))
    manifest_path = Path(str(result["run_manifest_path"]))
    report_path = Path(str(result["report_path"]))

    plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    report_text = report_path.read_text(encoding="utf-8")

    assert plan_payload["plan_version"] == RUN_PLAN_CONTRACT_VERSION
    assert plan_payload["workflow_type"] == "run-swarm"
    assert plan_payload["coverage_intent"]["scenario"]["decision"] == "generate_new"
    assert plan_payload["coverage_intent"]["swarm"]["decision"] == "generate_new"
    assert plan_payload["run_shaping"]["generation_mode"] == "fixture"
    assert plan_payload["semantic_advisory"]["role"] == "advisory_judge"
    assert plan_payload["semantic_advisory"]["enabled"] is True
    assert plan_payload["semantic_advisory"]["gating"] == "advisory_only"
    assert plan_payload["semantic_advisory"]["mode"] == "fixture"
    assert manifest_payload["run_plan"]["run_plan_path"] == str(plan_path)
    assert manifest_payload["run_plan"]["run_plan_id"] == plan_payload["plan_id"]
    assert manifest_payload["semantic_advisory"]["enabled"] is True
    assert "Run plan:" in report_text


def test_run_swarm_explicit_pack_paths_remain_authoritative_in_run_plan(
    tmp_path: Path,
) -> None:
    scenario_pack = generate_scenario_pack(
        "saved scenario pack", generator_mode="fixture"
    )
    population_pack = generate_population_pack(
        "saved population pack",
        generator_mode="fixture",
        population_size=8,
        candidate_count=16,
    )
    scenario_pack_path = tmp_path / "saved-scenarios.json"
    population_pack_path = tmp_path / "saved-population.json"
    write_scenario_pack(scenario_pack, scenario_pack_path)
    write_population_pack(population_pack, population_pack_path)

    result = main(
        [
            "run-swarm",
            "--domain",
            "recommender",
            "--use-mock",
            "--brief",
            "this brief should not override explicit packs",
            "--scenario-pack-path",
            str(scenario_pack_path),
            "--population-pack-path",
            str(population_pack_path),
            "--output-dir",
            str(tmp_path / "run-swarm"),
        ]
    )

    plan_payload = json.loads(
        Path(str(result["run_plan_path"])).read_text(encoding="utf-8")
    )
    assert plan_payload["coverage_intent"]["scenario"]["decision"] == "explicit_reuse"
    assert plan_payload["coverage_intent"]["swarm"]["decision"] == "explicit_reuse"
    assert plan_payload["planned_artifacts"]["scenario_pack_path"] == str(
        scenario_pack_path
    )
    assert plan_payload["planned_artifacts"]["population_pack_path"] == str(
        population_pack_path
    )


def test_compare_writes_run_plan_for_built_in_coverage_without_brief(
    tmp_path: Path,
) -> None:
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

    plan_path = Path(str(result["run_plan_path"]))
    manifest_path = Path(str(result["run_manifest_path"]))
    report_path = Path(str(result["regression_report_path"]))

    plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    report_text = report_path.read_text(encoding="utf-8")

    assert plan_payload["workflow_type"] == "compare"
    assert plan_payload["coverage_intent"]["coverage_source"] == "built_in"
    assert (
        plan_payload["coverage_intent"]["scenario"]["decision"]
        == "use_built_in_scenarios"
    )
    assert (
        plan_payload["coverage_intent"]["swarm"]["decision"]
        == "use_built_in_population"
    )
    assert plan_payload["semantic_advisory"]["enabled"] is True
    assert plan_payload["semantic_advisory"]["mode"] == "fixture"
    assert manifest_payload["run_plan"]["run_plan_path"] == str(plan_path)
    assert "Run plan:" in report_text


def test_compare_brief_driven_planning_generates_shared_coverage_and_keeps_manifest_linked(
    tmp_path: Path,
) -> None:
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
            "--brief",
            "compare trust collapse and novelty balance across the two systems",
            "--generation-mode",
            "fixture",
            "--rerun-count",
            "1",
            "--output-dir",
            str(tmp_path / "compare"),
        ]
    )

    plan_payload = json.loads(
        Path(str(result["run_plan_path"])).read_text(encoding="utf-8")
    )
    manifest_payload = json.loads(
        Path(str(result["run_manifest_path"])).read_text(encoding="utf-8")
    )
    scenario_pack_path = Path(
        str(plan_payload["planned_artifacts"]["scenario_pack_path"])
    )
    population_pack_path = Path(
        str(plan_payload["planned_artifacts"]["population_pack_path"])
    )

    assert (
        plan_payload["brief"]
        == "compare trust collapse and novelty balance across the two systems"
    )
    assert plan_payload["coverage_intent"]["coverage_source"] == "generated"
    assert plan_payload["coverage_intent"]["scenario"]["decision"] == "generate_new"
    assert plan_payload["coverage_intent"]["swarm"]["decision"] == "generate_new"
    assert scenario_pack_path.exists()
    assert population_pack_path.exists()
    assert manifest_payload["run_plan"]["run_plan_id"] == plan_payload["plan_id"]


def test_run_swarm_plan_and_manifest_capture_semantic_intent(tmp_path: Path) -> None:
    result = main(
        [
            "run-swarm",
            "--domain",
            "recommender",
            "--use-mock",
            "--brief",
            "test semantic advisory planning metadata",
            "--generation-mode",
            "fixture",
            "--semantic-mode",
            "fixture",
            "--output-dir",
            str(tmp_path / "run-swarm"),
        ]
    )

    plan_payload = json.loads(
        Path(str(result["run_plan_path"])).read_text(encoding="utf-8")
    )
    manifest_payload = json.loads(
        Path(str(result["run_manifest_path"])).read_text(encoding="utf-8")
    )
    assert plan_payload["run_shaping"]["semantic_mode"] == "fixture"
    assert plan_payload["semantic_advisory"]["decision_origin"] == "explicit_user_input"
    assert manifest_payload["semantic_mode"] == "fixture"
    assert manifest_payload["semantic_advisory"]["artifact_path"].endswith(
        "semantic_advisory.json"
    )
    assert manifest_payload["run_plan"]["run_plan_path"] == str(result["run_plan_path"])


def test_run_swarm_writes_semantic_advisory_sidecar_and_links_it_everywhere(
    tmp_path: Path,
) -> None:
    result = main(
        [
            "run-swarm",
            "--domain",
            "recommender",
            "--use-mock",
            "--brief",
            "test dedicated semantic advisory artifact",
            "--generation-mode",
            "fixture",
            "--output-dir",
            str(tmp_path / "run-swarm"),
        ]
    )

    semantic_path = Path(str(result["semantic_advisory_path"]))
    semantic_payload = json.loads(semantic_path.read_text(encoding="utf-8"))
    manifest_payload = json.loads(
        Path(str(result["run_manifest_path"])).read_text(encoding="utf-8")
    )
    report_text = Path(str(result["report_path"])).read_text(encoding="utf-8")

    assert semantic_path.exists()
    assert semantic_payload["advisory_only"] is True
    assert semantic_payload["semantic_mode"] == "fixture"
    assert manifest_payload["semantic_advisory"]["artifact_path"] == str(semantic_path)
    assert "Semantic advisory artifact:" in report_text
    assert "advisory only" in report_text.lower()


def test_compare_writes_semantic_regression_sidecar(tmp_path: Path) -> None:
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
            "--brief",
            "compare semantic advisory sidecars",
            "--generation-mode",
            "fixture",
            "--rerun-count",
            "1",
            "--output-dir",
            str(tmp_path / "compare"),
        ]
    )

    semantic_path = Path(str(result["semantic_regression_advisory_path"]))
    manifest_payload = json.loads(
        Path(str(result["run_manifest_path"])).read_text(encoding="utf-8")
    )
    report_text = Path(str(result["regression_report_path"])).read_text(
        encoding="utf-8"
    )

    assert semantic_path.exists()
    assert manifest_payload["semantic_advisory"]["artifact_path"] == str(semantic_path)
    assert "Semantic advisory artifact:" in report_text


def test_audit_writes_semantic_advisory_sidecar_when_enabled(tmp_path: Path) -> None:
    result = main(
        [
            "audit",
            "--domain",
            "recommender",
            "--use-mock",
            "--semantic-mode",
            "fixture",
            "--output-dir",
            str(tmp_path / "audit"),
        ]
    )

    semantic_path = Path(str(result["semantic_advisory_path"]))
    manifest_payload = json.loads(
        Path(str(result["run_manifest_path"])).read_text(encoding="utf-8")
    )

    assert semantic_path.exists()
    assert manifest_payload["semantic_advisory"]["artifact_path"] == str(semantic_path)
    assert (
        manifest_payload["semantic_advisory"]["decision_origin"]
        == "explicit_user_input"
    )


def test_plan_run_creates_audit_plan_without_execution(tmp_path: Path) -> None:
    output_dir = tmp_path / "planned-audit"
    result = main(
        [
            "plan-run",
            "--workflow",
            "audit",
            "--domain",
            "recommender",
            "--use-mock",
            "--scenario",
            "returning-user-home-feed",
            "--output-dir",
            str(output_dir),
        ]
    )

    plan_path = Path(str(result["run_plan_path"]))
    payload = json.loads(plan_path.read_text(encoding="utf-8"))

    assert payload["workflow_type"] == "audit"
    assert (
        payload["coverage_intent"]["scenario"]["decision"] == "use_built_in_scenarios"
    )
    assert (
        payload["coverage_intent"]["scenario"]["built_in_selection"]
        == "returning-user-home-feed"
    )
    assert payload["coverage_intent"]["swarm"]["decision"] == "use_built_in_population"
    assert not (output_dir / "report.md").exists()
    assert not (output_dir / "run_manifest.json").exists()


def test_execute_plan_runs_saved_audit_plan_without_replanning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "plan-exec-audit"
    plan_result = main(
        [
            "plan-run",
            "--workflow",
            "audit",
            "--domain",
            "recommender",
            "--use-mock",
            "--scenario",
            "returning-user-home-feed",
            "--output-dir",
            str(output_dir),
        ]
    )
    plan_path = str(plan_result["run_plan_path"])

    def _should_not_replan(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("execute-plan should not invoke plan_audit")

    monkeypatch.setattr("evidpath.cli_app.handlers.plan_audit", _should_not_replan)

    result = main(["execute-plan", "--run-plan-path", plan_path])

    assert Path(str(result["report_path"])).exists()
    manifest_payload = json.loads(
        Path(str(result["run_manifest_path"])).read_text(encoding="utf-8")
    )
    assert manifest_payload["run_plan"]["run_plan_path"] == plan_path


def test_plan_run_audit_rejects_generation_flags(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="does not support `--generation-mode`"):
        main(
            [
                "plan-run",
                "--workflow",
                "audit",
                "--domain",
                "recommender",
                "--use-mock",
                "--generation-mode",
                "fixture",
                "--output-dir",
                str(tmp_path / "planned-audit"),
            ]
        )


def test_plan_run_creates_run_swarm_plan_without_execution(tmp_path: Path) -> None:
    output_dir = tmp_path / "planned-run-swarm"
    result = main(
        [
            "plan-run",
            "--workflow",
            "run-swarm",
            "--domain",
            "recommender",
            "--use-mock",
            "--brief",
            "pressure test weak first slates",
            "--generation-mode",
            "fixture",
            "--output-dir",
            str(output_dir),
        ]
    )

    plan_path = Path(str(result["run_plan_path"]))
    plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))

    assert plan_payload["workflow_type"] == "run-swarm"
    assert plan_payload["planned_artifacts"]["output_dir"] == str(output_dir)
    assert not (output_dir / "report.md").exists()
    assert not (output_dir / "run_manifest.json").exists()


def test_execute_plan_runs_saved_run_swarm_plan_without_replanning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "plan-exec-run-swarm"
    plan_result = main(
        [
            "plan-run",
            "--workflow",
            "run-swarm",
            "--domain",
            "recommender",
            "--use-mock",
            "--brief",
            "execute saved swarm plan exactly as written",
            "--generation-mode",
            "fixture",
            "--output-dir",
            str(output_dir),
        ]
    )
    plan_path = str(plan_result["run_plan_path"])

    def _should_not_replan(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("execute-plan should not invoke plan_run_swarm")

    monkeypatch.setattr(
        "evidpath.cli_app.handlers.plan_run_swarm",
        _should_not_replan,
    )

    result = main(
        [
            "execute-plan",
            "--run-plan-path",
            plan_path,
        ]
    )

    assert Path(str(result["report_path"])).exists()
    manifest_payload = json.loads(
        Path(str(result["run_manifest_path"])).read_text(encoding="utf-8")
    )
    assert manifest_payload["run_plan"]["run_plan_path"] == plan_path


def test_plan_run_and_execute_plan_support_compare(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    ensure_reference_artifacts(baseline_dir)
    ensure_reference_artifacts(candidate_dir)
    output_dir = tmp_path / "planned-compare"

    plan_result = main(
        [
            "plan-run",
            "--workflow",
            "compare",
            "--domain",
            "recommender",
            "--baseline-artifact-dir",
            str(baseline_dir),
            "--candidate-artifact-dir",
            str(candidate_dir),
            "--brief",
            "compare trust collapse and novelty pressure",
            "--generation-mode",
            "fixture",
            "--rerun-count",
            "1",
            "--output-dir",
            str(output_dir),
        ]
    )

    plan_path = Path(str(plan_result["run_plan_path"]))
    plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan_payload["workflow_type"] == "compare"
    assert not (output_dir / "regression_report.md").exists()

    execute_result = main(
        [
            "execute-plan",
            "--run-plan-path",
            str(plan_path),
        ]
    )

    assert Path(str(execute_result["regression_report_path"])).exists()
    manifest_payload = json.loads(
        Path(str(execute_result["run_manifest_path"])).read_text(encoding="utf-8")
    )
    assert manifest_payload["run_plan"]["run_plan_path"] == str(plan_path)


def test_execute_plan_rejects_unsupported_plan_version(tmp_path: Path) -> None:
    output_dir = tmp_path / "bad-plan"
    plan_result = main(
        [
            "plan-run",
            "--workflow",
            "run-swarm",
            "--domain",
            "recommender",
            "--use-mock",
            "--brief",
            "bad version validation",
            "--generation-mode",
            "fixture",
            "--output-dir",
            str(output_dir),
        ]
    )
    plan_path = Path(str(plan_result["run_plan_path"]))
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    payload["plan_version"] = "v999"
    plan_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="Unsupported run-plan version"):
        main(["execute-plan", "--run-plan-path", str(plan_path)])


def test_execute_plan_replays_deterministically_from_same_saved_run_swarm_plan(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "replayable-plan"
    plan_result = main(
        [
            "plan-run",
            "--workflow",
            "run-swarm",
            "--domain",
            "recommender",
            "--use-mock",
            "--brief",
            "replay the same saved plan deterministically",
            "--generation-mode",
            "fixture",
            "--seed",
            "7",
            "--output-dir",
            str(output_dir),
        ]
    )
    plan_path = str(plan_result["run_plan_path"])

    first = main(["execute-plan", "--run-plan-path", plan_path])
    second = main(["execute-plan", "--run-plan-path", plan_path])

    first_summary = json.loads(
        Path(str(first["results_path"])).read_text(encoding="utf-8")
    )["summary"]
    second_summary = json.loads(
        Path(str(second["results_path"])).read_text(encoding="utf-8")
    )["summary"]

    assert first_summary == second_summary


def _disable_provider_credentials(monkeypatch) -> None:
    monkeypatch.setattr(
        "evidpath.orchestration._planner_decisions.provider_credentials_available",
        lambda: False,
    )
    monkeypatch.setattr(
        "evidpath.orchestration._planner_defaults.provider_credentials_available",
        lambda: False,
    )


def _run_swarm_request(
    tmp_path: Path,
    *,
    explicit_inputs: dict[str, object],
    generation_mode: str = "provider",
) -> RunSwarmPlanRequest:
    output_root = str(tmp_path / "orchestration")
    brief = "test planner-owned ai profile defaults"
    return RunSwarmPlanRequest(
        domain_name="recommender",
        brief=brief,
        generation_mode=generation_mode,
        output_root=output_root,
        target_config={
            "service_mode": "mock",
            "service_artifact_dir": "",
            "adapter_base_url": "",
        },
        explicit_inputs=explicit_inputs,
        scenario_pack_path=None,
        population_pack_path=None,
        scenario_count=3,
        population_size=8,
        population_candidate_count=16,
        ai_profile="fast",
        semantic_mode="off",
        semantic_model=None,
        semantic_profile="fast",
        default_scenario_pack_path=build_default_scenario_pack_path(
            output_root,
            brief=brief,
            generator_mode=generation_mode,
        ),
        default_population_pack_path=build_default_population_pack_path(
            output_root,
            brief=brief,
            generator_mode=generation_mode,
        ),
    )


def test_orchestration_planner_defaults_provider_runs_to_balanced_profile(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _disable_provider_credentials(monkeypatch)
    context = plan_run_swarm(
        _run_swarm_request(
            tmp_path,
            explicit_inputs={"brief": "test planner-owned ai profile defaults"},
        )
    )

    assert context.plan.ai_profile == "balanced"
    assert context.plan.payload["planner_selected_defaults"]["ai_profile"] == "balanced"
    assert context.plan.semantic_mode == "fixture"
    assert (
        context.plan.payload["semantic_advisory"]["decision_origin"]
        == "planner_selected_default"
    )


def test_orchestration_planner_preserves_explicit_ai_profile(
    tmp_path: Path, monkeypatch
) -> None:
    _disable_provider_credentials(monkeypatch)
    context = plan_run_swarm(
        _run_swarm_request(
            tmp_path,
            explicit_inputs={
                "brief": "test planner-owned ai profile defaults",
                "ai_profile": "deep",
            },
        )
    )

    assert context.plan.ai_profile == "deep"
    assert context.plan.payload["explicit_user_inputs"]["ai_profile"] == "deep"
    assert context.plan.payload["planner_selected_defaults"]["ai_profile"] == ""


def test_orchestration_executor_runs_run_swarm_plan_without_cli(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _disable_provider_credentials(monkeypatch)
    context = plan_run_swarm(
        _run_swarm_request(
            tmp_path,
            explicit_inputs={"brief": "execute through orchestration kernel"},
            generation_mode="fixture",
        )
    )

    outcome = execute_run_swarm_plan(
        context.plan,
        RunSwarmExecutionRequest(
            domain_name="recommender",
            brief=context.plan.payload["brief"],
            output_root=context.output_root,
            service_mode=context.service_mode,
            service_artifact_dir=context.service_artifact_dir,
            adapter_base_url=context.adapter_base_url,
            seed=0,
            output_dir=context.output_root,
            run_name=None,
        ),
    )

    assert Path(str(outcome.result["report_path"])).exists()
    assert Path(str(outcome.result["run_manifest_path"])).exists()


def test_orchestration_executor_runs_audit_plan_without_cli(tmp_path: Path) -> None:
    output_root = str(tmp_path / "audit")
    context = plan_audit(
        AuditPlanRequest(
            domain_name="recommender",
            output_root=output_root,
            target_config={
                "service_mode": "mock",
                "service_artifact_dir": "",
                "adapter_base_url": "",
            },
            explicit_inputs={"scenario": "returning-user-home-feed"},
            scenario_name="returning-user-home-feed",
            scenario_pack_path=None,
            population_pack_path=None,
            semantic_mode="off",
            semantic_model=None,
            semantic_profile="fast",
        )
    )

    outcome = execute_audit_plan(
        context.plan,
        AuditExecutionRequest(
            domain_name="recommender",
            output_root=context.output_root,
            service_mode=context.service_mode,
            service_artifact_dir=context.service_artifact_dir,
            adapter_base_url=context.adapter_base_url,
            seed=0,
            output_dir=context.output_root,
            run_name=None,
        ),
    )

    assert Path(str(outcome.result["report_path"])).exists()
    assert Path(str(outcome.result["run_manifest_path"])).exists()


def test_orchestration_planner_defaults_audit_semantics_to_fixture(
    tmp_path: Path,
) -> None:
    output_root = str(tmp_path / "audit-defaults")
    context = plan_audit(
        AuditPlanRequest(
            domain_name="recommender",
            output_root=output_root,
            target_config={
                "service_mode": "mock",
                "service_artifact_dir": "",
                "adapter_base_url": "",
            },
            explicit_inputs={"scenario": "returning-user-home-feed"},
            scenario_name="returning-user-home-feed",
            scenario_pack_path=None,
            population_pack_path=None,
            semantic_mode="off",
            semantic_model=None,
            semantic_profile="fast",
        )
    )

    assert context.plan.semantic_mode == "fixture"
    assert context.plan.semantic_profile == "fast"
    assert (
        context.plan.payload["semantic_advisory"]["decision_origin"]
        == "planner_selected_default"
    )


def test_run_swarm_and_plan_run_produce_equivalent_plan_shape(tmp_path: Path) -> None:
    direct_result = main(
        [
            "run-swarm",
            "--domain",
            "recommender",
            "--use-mock",
            "--brief",
            "compare the same planning surface",
            "--generation-mode",
            "fixture",
            "--output-dir",
            str(tmp_path / "direct"),
        ]
    )
    planned_result = main(
        [
            "plan-run",
            "--workflow",
            "run-swarm",
            "--domain",
            "recommender",
            "--use-mock",
            "--brief",
            "compare the same planning surface",
            "--generation-mode",
            "fixture",
            "--output-dir",
            str(tmp_path / "planned"),
        ]
    )

    direct_payload = _normalized_plan_payload(Path(str(direct_result["run_plan_path"])))
    planned_payload = _normalized_plan_payload(
        Path(str(planned_result["run_plan_path"]))
    )

    assert direct_payload["workflow_type"] == "run-swarm"
    assert planned_payload["workflow_type"] == "run-swarm"
    assert _normalized_coverage_intent(
        direct_payload["coverage_intent"]
    ) == _normalized_coverage_intent(planned_payload["coverage_intent"])
    assert direct_payload["run_shaping"] == planned_payload["run_shaping"]


def test_compare_and_plan_run_compare_produce_equivalent_plan_shape(
    tmp_path: Path,
) -> None:
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    ensure_reference_artifacts(baseline_dir)
    ensure_reference_artifacts(candidate_dir)

    direct_result = main(
        [
            "compare",
            "--domain",
            "recommender",
            "--baseline-artifact-dir",
            str(baseline_dir),
            "--candidate-artifact-dir",
            str(candidate_dir),
            "--brief",
            "compare the same planning surface",
            "--generation-mode",
            "fixture",
            "--rerun-count",
            "1",
            "--output-dir",
            str(tmp_path / "compare-direct"),
        ]
    )
    planned_result = main(
        [
            "plan-run",
            "--workflow",
            "compare",
            "--domain",
            "recommender",
            "--baseline-artifact-dir",
            str(baseline_dir),
            "--candidate-artifact-dir",
            str(candidate_dir),
            "--brief",
            "compare the same planning surface",
            "--generation-mode",
            "fixture",
            "--rerun-count",
            "1",
            "--output-dir",
            str(tmp_path / "compare-planned"),
        ]
    )

    direct_payload = _normalized_plan_payload(Path(str(direct_result["run_plan_path"])))
    planned_payload = _normalized_plan_payload(
        Path(str(planned_result["run_plan_path"]))
    )

    assert direct_payload["workflow_type"] == "compare"
    assert planned_payload["workflow_type"] == "compare"
    assert _normalized_coverage_intent(
        direct_payload["coverage_intent"]
    ) == _normalized_coverage_intent(planned_payload["coverage_intent"])
    assert direct_payload["run_shaping"] == planned_payload["run_shaping"]


def test_audit_and_plan_run_audit_produce_equivalent_plan_shape(tmp_path: Path) -> None:
    direct_result = main(
        [
            "audit",
            "--domain",
            "recommender",
            "--use-mock",
            "--scenario",
            "returning-user-home-feed",
            "--output-dir",
            str(tmp_path / "audit-direct"),
        ]
    )
    planned_result = main(
        [
            "plan-run",
            "--workflow",
            "audit",
            "--domain",
            "recommender",
            "--use-mock",
            "--scenario",
            "returning-user-home-feed",
            "--output-dir",
            str(tmp_path / "audit-planned"),
        ]
    )

    direct_payload = _normalized_plan_payload(Path(str(direct_result["run_plan_path"])))
    planned_payload = _normalized_plan_payload(
        Path(str(planned_result["run_plan_path"]))
    )

    assert direct_payload["workflow_type"] == "audit"
    assert planned_payload["workflow_type"] == "audit"
    assert _normalized_coverage_intent(
        direct_payload["coverage_intent"]
    ) == _normalized_coverage_intent(planned_payload["coverage_intent"])
    assert direct_payload["run_shaping"] == planned_payload["run_shaping"]


def _normalized_plan_payload(path: Path) -> dict[str, object]:
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("plan_id", None)
    payload.pop("generated_at_utc", None)
    planned_artifacts = payload.get("planned_artifacts", {})
    if isinstance(planned_artifacts, dict):
        planned_artifacts.pop("run_plan_path", None)
    return payload


def _normalized_coverage_intent(coverage_intent: object) -> object:
    if not isinstance(coverage_intent, dict):
        return coverage_intent
    normalized = dict(coverage_intent)
    for key in ("scenario", "swarm"):
        value = normalized.get(key)
        if isinstance(value, dict):
            normalized[key] = {
                inner_key: (
                    "<artifact>" if inner_key == "artifact_path" else inner_value
                )
                for inner_key, inner_value in value.items()
            }
    return normalized
