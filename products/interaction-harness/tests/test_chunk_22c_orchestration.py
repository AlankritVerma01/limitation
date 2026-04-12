from __future__ import annotations

from pathlib import Path

from interaction_harness.cli import main
from interaction_harness.domains.recommender import ensure_reference_artifacts
from interaction_harness.orchestration import (
    AuditExecutionRequest,
    AuditPlanRequest,
    RunSwarmExecutionRequest,
    RunSwarmPlanRequest,
    execute_audit_plan,
    execute_run_swarm_plan,
    plan_audit,
    plan_run_swarm,
)
from interaction_harness.population_generation import build_default_population_pack_path
from interaction_harness.scenario_generation import build_default_scenario_pack_path


def _run_swarm_request(tmp_path: Path, *, explicit_inputs: dict[str, object]) -> RunSwarmPlanRequest:
    output_root = str(tmp_path / "orchestration")
    brief = "test planner-owned ai profile defaults"
    return RunSwarmPlanRequest(
        domain_name="recommender",
        brief=brief,
        generation_mode="provider",
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
            generator_mode="provider",
        ),
        default_population_pack_path=build_default_population_pack_path(
            output_root,
            brief=brief,
            generator_mode="provider",
        ),
    )


def test_orchestration_planner_defaults_provider_runs_to_balanced_profile(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "interaction_harness.orchestration.planner.provider_credentials_available",
        lambda: False,
    )
    context = plan_run_swarm(_run_swarm_request(tmp_path, explicit_inputs={"brief": "test planner-owned ai profile defaults"}))

    assert context.plan.ai_profile == "balanced"
    assert context.plan.payload["planner_selected_defaults"]["ai_profile"] == "balanced"
    assert context.plan.semantic_mode == "fixture"
    assert context.plan.payload["semantic_advisory"]["decision_origin"] == "planner_selected_default"


def test_orchestration_planner_preserves_explicit_ai_profile(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "interaction_harness.orchestration.planner.provider_credentials_available",
        lambda: False,
    )
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


def test_orchestration_executor_runs_run_swarm_plan_without_cli(tmp_path: Path) -> None:
    context = plan_run_swarm(_run_swarm_request(tmp_path, explicit_inputs={"brief": "execute through orchestration kernel"}))

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


def test_orchestration_planner_defaults_audit_semantics_to_fixture(tmp_path: Path) -> None:
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
    assert context.plan.payload["semantic_advisory"]["decision_origin"] == "planner_selected_default"


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
    planned_payload = _normalized_plan_payload(Path(str(planned_result["run_plan_path"])))

    assert direct_payload["workflow_type"] == "run-swarm"
    assert planned_payload["workflow_type"] == "run-swarm"
    assert _normalized_coverage_intent(direct_payload["coverage_intent"]) == _normalized_coverage_intent(
        planned_payload["coverage_intent"]
    )
    assert direct_payload["run_shaping"] == planned_payload["run_shaping"]


def test_compare_and_plan_run_compare_produce_equivalent_plan_shape(tmp_path: Path) -> None:
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
    planned_payload = _normalized_plan_payload(Path(str(planned_result["run_plan_path"])))

    assert direct_payload["workflow_type"] == "compare"
    assert planned_payload["workflow_type"] == "compare"
    assert _normalized_coverage_intent(direct_payload["coverage_intent"]) == _normalized_coverage_intent(
        planned_payload["coverage_intent"]
    )
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
    planned_payload = _normalized_plan_payload(Path(str(planned_result["run_plan_path"])))

    assert direct_payload["workflow_type"] == "audit"
    assert planned_payload["workflow_type"] == "audit"
    assert _normalized_coverage_intent(direct_payload["coverage_intent"]) == _normalized_coverage_intent(
        planned_payload["coverage_intent"]
    )
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
                inner_key: ("<artifact>" if inner_key == "artifact_path" else inner_value)
                for inner_key, inner_value in value.items()
            }
    return normalized
