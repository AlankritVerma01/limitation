"""Shared execution behavior for planned workflows."""

from __future__ import annotations

from pathlib import Path

from ..artifacts.run_manifest import write_run_manifest
from ..artifacts.run_plan import load_run_plan
from ..audit import execute_domain_audit, write_run_artifacts
from ..cli_app.progress import ProgressCallback, emit_progress
from ..regression import run_domain_regression_audit
from ..schema import RegressionTarget
from .coverage import (
    optional_text,
    resolve_compare_planned_coverage,
    resolve_run_swarm_packs,
)
from .types import (
    AuditExecutionOutcome,
    AuditExecutionRequest,
    CompareExecutionOutcome,
    CompareExecutionRequest,
    RunSwarmExecutionOutcome,
    RunSwarmExecutionRequest,
)


def execute_saved_audit_plan(
    run_plan_path: str,
    *,
    progress_callback: ProgressCallback | None = None,
) -> AuditExecutionOutcome:
    """Execute one persisted audit plan without re-planning."""
    plan = load_run_plan(run_plan_path)
    payload = plan.payload
    target = payload["target"]
    run_shaping = payload["run_shaping"]
    return execute_audit_plan(
        plan,
        AuditExecutionRequest(
            domain_name=str(payload["domain"]),
            output_root=str(payload["planned_artifacts"]["output_dir"]),
            service_mode=str(target.get("service_mode", "")),
            service_artifact_dir=optional_text(target.get("service_artifact_dir")),
            adapter_base_url=optional_text(target.get("adapter_base_url")),
            seed=int(run_shaping["seed"]),
            output_dir=str(payload["planned_artifacts"]["output_dir"]),
            run_name=optional_text(run_shaping.get("run_name")),
            include_slice_membership=bool(
                run_shaping.get("include_slice_membership", False)
            ),
        ),
        progress_callback=progress_callback,
    )


def execute_audit_plan(
    plan,
    request: AuditExecutionRequest,
    *,
    progress_callback: ProgressCallback | None = None,
) -> AuditExecutionOutcome:
    """Execute one audit plan through the deterministic audit path."""
    payload = plan.payload
    coverage_intent = payload["coverage_intent"]
    scenario_intent = coverage_intent["scenario"]
    swarm_intent = coverage_intent["swarm"]
    scenario_decision = str(scenario_intent.get("decision", ""))
    swarm_decision = str(swarm_intent.get("decision", ""))
    scenario_pack_path = (
        plan.scenario_pack_path if scenario_decision == "explicit_reuse" else None
    )
    population_pack_path = (
        plan.population_pack_path if swarm_decision == "explicit_reuse" else None
    )
    scenario_name = str(scenario_intent.get("built_in_selection", "all") or "all")
    scenario_names = None if scenario_name == "all" else (scenario_name,)
    run_result = execute_domain_audit(
        domain_name=request.domain_name,
        seed=request.seed,
        output_dir=request.output_dir,
        scenario_names=scenario_names,
        scenario_pack_path=scenario_pack_path,
        population_pack_path=population_pack_path,
        service_mode=request.service_mode,
        service_artifact_dir=request.service_artifact_dir,
        adapter_base_url=request.adapter_base_url,
        run_name=request.run_name,
        semantic_mode=plan.semantic_mode,
        semantic_model=plan.semantic_model,
        semantic_profile=plan.semantic_profile,
        progress_callback=progress_callback,
    )
    run_result.metadata["run_plan_path"] = plan.plan_path
    run_result.metadata["run_plan_id"] = plan.plan_id
    run_result.metadata["planner_mode"] = plan.planner_mode
    run_result.metadata["planner_provider_name"] = plan.planner_provider_name
    run_result.metadata["planner_model_name"] = plan.planner_model_name
    run_result.metadata["planner_model_profile"] = plan.planner_model_profile
    run_result.metadata["planner_summary"] = plan.planner_summary
    run_result.metadata["include_slice_membership"] = request.include_slice_membership
    run_result.metadata["semantic_advisory_origin"] = plan.semantic_decision_origin
    run_result.metadata["semantic_advisory_gating"] = plan.semantic_gating
    run_result.metadata["semantic_advisory_rationale"] = plan.semantic_rationale
    if plan.semantic_artifact_path is not None:
        run_result.metadata["semantic_advisory_path"] = plan.semantic_artifact_path
    run_result.metadata["run_manifest_path"] = str(
        Path(run_result.run_config.rollout.output_dir) / "run_manifest.json"
    )
    result = write_run_artifacts(run_result, progress_callback=progress_callback)
    manifest_path = write_run_manifest(
        run_result,
        artifact_paths=result,
        workflow_type="audit",
        workflow_metadata={
            "coverage_source": plan.coverage_source,
            "scenario_generation_mode": plan.scenario_generation_mode,
            "swarm_generation_mode": plan.swarm_generation_mode,
            "scenario_pack_path": scenario_pack_path or "",
            "population_pack_path": population_pack_path or "",
            "run_plan_path": plan.plan_path,
            "run_plan_id": plan.plan_id,
            "semantic_advisory_origin": plan.semantic_decision_origin,
            "semantic_advisory_gating": plan.semantic_gating,
        },
    )
    return AuditExecutionOutcome(
        result={
            **result,
            "scenario_pack_path": scenario_pack_path or "",
            "population_pack_path": population_pack_path or "",
            "coverage_source": plan.coverage_source,
            "scenario_generation_mode": plan.scenario_generation_mode,
            "swarm_generation_mode": plan.swarm_generation_mode,
            "run_plan_path": plan.plan_path,
            "run_manifest_path": manifest_path,
        },
        run_result=run_result,
        scenario_pack_path=scenario_pack_path,
        population_pack_path=population_pack_path,
        coverage_source=plan.coverage_source,
        scenario_generation_mode=plan.scenario_generation_mode,
        swarm_generation_mode=plan.swarm_generation_mode,
        manifest_path=manifest_path,
    )


def execute_saved_run_swarm_plan(
    run_plan_path: str,
    *,
    progress_callback: ProgressCallback | None = None,
) -> RunSwarmExecutionOutcome:
    """Execute one persisted run-swarm plan without re-planning."""
    plan = load_run_plan(run_plan_path)
    payload = plan.payload
    target = payload["target"]
    run_shaping = payload["run_shaping"]
    return execute_run_swarm_plan(
        plan,
        RunSwarmExecutionRequest(
            domain_name=str(payload["domain"]),
            brief=str(payload["brief"]),
            output_root=str(payload["planned_artifacts"]["output_dir"]),
            service_mode=str(target.get("service_mode", "")),
            service_artifact_dir=optional_text(target.get("service_artifact_dir")),
            adapter_base_url=optional_text(target.get("adapter_base_url")),
            seed=int(run_shaping["seed"]),
            output_dir=str(payload["planned_artifacts"]["output_dir"]),
            run_name=optional_text(run_shaping.get("run_name")),
        ),
        progress_callback=progress_callback,
    )


def execute_run_swarm_plan(
    plan,
    request: RunSwarmExecutionRequest,
    *,
    progress_callback: ProgressCallback | None = None,
) -> RunSwarmExecutionOutcome:
    """Execute one run-swarm plan through the deterministic audit path."""
    explicit_inputs = plan.payload.get("explicit_user_inputs", {})
    if not isinstance(explicit_inputs, dict):
        explicit_inputs = {}
    explicit_scenario_pack_path = explicit_inputs.get("scenario_pack_path")
    explicit_population_pack_path = explicit_inputs.get("population_pack_path")
    if explicit_scenario_pack_path is None and plan.scenario_generation_mode == "reused":
        explicit_scenario_pack_path = plan.scenario_pack_path
    if explicit_population_pack_path is None and plan.swarm_generation_mode == "reused":
        explicit_population_pack_path = plan.population_pack_path
    emit_progress(
        progress_callback,
        phase="resolve_generation_mode",
        message=f"Using generation mode: {plan.generation_mode}",
        stage="finish",
    )
    (
        scenario_pack_path,
        population_pack_path,
        coverage_source,
        scenario_generation_mode,
        swarm_generation_mode,
    ) = resolve_run_swarm_packs(
        brief=request.brief,
        explicit_scenario_pack_path=optional_text(explicit_scenario_pack_path),
        explicit_population_pack_path=optional_text(explicit_population_pack_path),
        domain_name=request.domain_name,
        output_root=request.output_root,
        generation_mode=plan.generation_mode,
        scenario_action=plan.scenario_action,
        population_action=plan.population_action,
        ai_profile=plan.ai_profile,
        scenario_count=plan.scenario_count,
        population_size=plan.population_size,
        population_candidate_count=plan.population_candidate_count,
        planned_scenario_pack_path=plan.scenario_pack_path,
        planned_population_pack_path=plan.population_pack_path,
        progress_callback=progress_callback,
    )
    run_result = execute_domain_audit(
        domain_name=request.domain_name,
        seed=request.seed,
        output_dir=request.output_dir,
        scenario_pack_path=scenario_pack_path,
        population_pack_path=population_pack_path,
        service_mode=request.service_mode,
        service_artifact_dir=request.service_artifact_dir,
        adapter_base_url=request.adapter_base_url,
        run_name=request.run_name,
        semantic_mode=plan.semantic_mode,
        semantic_model=plan.semantic_model,
        semantic_profile=plan.semantic_profile,
        progress_callback=progress_callback,
    )
    run_result.metadata["run_plan_path"] = plan.plan_path
    run_result.metadata["run_plan_id"] = plan.plan_id
    run_result.metadata["planner_mode"] = plan.planner_mode
    run_result.metadata["planner_provider_name"] = plan.planner_provider_name
    run_result.metadata["planner_model_name"] = plan.planner_model_name
    run_result.metadata["planner_model_profile"] = plan.planner_model_profile
    run_result.metadata["planner_summary"] = plan.planner_summary
    run_result.metadata["semantic_advisory_origin"] = plan.semantic_decision_origin
    run_result.metadata["semantic_advisory_gating"] = plan.semantic_gating
    run_result.metadata["semantic_advisory_rationale"] = plan.semantic_rationale
    if plan.semantic_artifact_path is not None:
        run_result.metadata["semantic_advisory_path"] = plan.semantic_artifact_path
    run_result.metadata["run_manifest_path"] = str(
        Path(run_result.run_config.rollout.output_dir) / "run_manifest.json"
    )
    result = write_run_artifacts(run_result, progress_callback=progress_callback)
    manifest_path = write_run_manifest(
        run_result,
        artifact_paths=result,
        workflow_type="run-swarm",
        workflow_metadata={
            "coverage_source": coverage_source,
            "scenario_generation_mode": scenario_generation_mode,
            "swarm_generation_mode": swarm_generation_mode,
            "brief": request.brief,
            "scenario_pack_path": scenario_pack_path,
            "population_pack_path": population_pack_path,
            "ai_profile": plan.ai_profile if coverage_source != "reused" else "",
            "run_plan_path": plan.plan_path,
            "run_plan_id": plan.plan_id,
            "semantic_advisory_origin": plan.semantic_decision_origin,
            "semantic_advisory_gating": plan.semantic_gating,
        },
    )
    return RunSwarmExecutionOutcome(
        result={
            **result,
            "scenario_pack_path": scenario_pack_path,
            "population_pack_path": population_pack_path,
            "coverage_source": coverage_source,
            "scenario_generation_mode": scenario_generation_mode,
            "swarm_generation_mode": swarm_generation_mode,
            "run_plan_path": plan.plan_path,
            "run_manifest_path": manifest_path,
        },
        run_result=run_result,
        scenario_pack_path=scenario_pack_path,
        population_pack_path=population_pack_path,
        coverage_source=coverage_source,
        scenario_generation_mode=scenario_generation_mode,
        swarm_generation_mode=swarm_generation_mode,
        manifest_path=manifest_path,
    )


def execute_saved_compare_plan(
    run_plan_path: str,
    *,
    progress_callback: ProgressCallback | None = None,
) -> CompareExecutionOutcome:
    """Execute one persisted compare plan without re-planning."""
    plan = load_run_plan(run_plan_path)
    payload = plan.payload
    run_shaping = payload["run_shaping"]
    targets = payload["targets"]
    scenario_name = str(payload["coverage_intent"]["scenario"].get("built_in_selection", "all") or "all")
    return execute_compare_plan(
        plan,
        CompareExecutionRequest(
            domain_name=str(payload["domain"]),
            brief=optional_text(payload.get("brief")),
            output_root=str(payload["planned_artifacts"]["output_dir"]),
            baseline_target=_regression_target_from_plan(targets["baseline"]),
            candidate_target=_regression_target_from_plan(targets["candidate"]),
            seed=int(run_shaping["seed"]),
            output_dir=str(payload["planned_artifacts"]["output_dir"]),
            policy_mode=str(run_shaping.get("policy_mode", "default")),
            scenario_name=scenario_name,
        ),
        progress_callback=progress_callback,
    )


def execute_compare_plan(
    compare_plan,
    request: CompareExecutionRequest,
    *,
    progress_callback: ProgressCallback | None = None,
) -> CompareExecutionOutcome:
    """Execute one compare plan through the deterministic regression path."""
    scenario_pack_path, population_pack_path = resolve_compare_planned_coverage(
        brief=request.brief,
        output_root=request.output_root,
        domain_name=request.domain_name,
        generation_mode=compare_plan.generation_mode,
        ai_profile=compare_plan.ai_profile,
        scenario_count=compare_plan.scenario_count,
        population_size=compare_plan.population_size,
        population_candidate_count=compare_plan.population_candidate_count,
        scenario_generation_mode=compare_plan.scenario_generation_mode,
        swarm_generation_mode=compare_plan.swarm_generation_mode,
        scenario_pack_path=compare_plan.scenario_pack_path,
        population_pack_path=compare_plan.population_pack_path,
        progress_callback=progress_callback,
    )
    result = run_domain_regression_audit(
        domain_name=request.domain_name,
        baseline_target=request.baseline_target,
        candidate_target=request.candidate_target,
        base_seed=request.seed,
        rerun_count=compare_plan.rerun_count or 1,
        output_dir=request.output_dir,
        scenario_names=None if request.scenario_name == "all" else (request.scenario_name,),
        scenario_pack_path=scenario_pack_path,
        population_pack_path=population_pack_path,
        semantic_mode=compare_plan.semantic_mode,
        semantic_model=compare_plan.semantic_model,
        semantic_profile=compare_plan.semantic_profile,
        policy_mode=request.policy_mode,
        planning_metadata={
            "run_plan_path": compare_plan.plan_path,
            "run_plan_id": compare_plan.plan_id,
            "planner_mode": compare_plan.planner_mode,
            "planner_provider_name": compare_plan.planner_provider_name,
            "planner_model_name": compare_plan.planner_model_name,
            "planner_model_profile": compare_plan.planner_model_profile,
            "planner_summary": compare_plan.planner_summary,
            "scenario_generation_mode": compare_plan.scenario_generation_mode,
            "swarm_generation_mode": compare_plan.swarm_generation_mode,
            "coverage_source": compare_plan.coverage_source,
            "semantic_advisory_origin": compare_plan.semantic_decision_origin,
            "semantic_advisory_gating": compare_plan.semantic_gating,
            "semantic_advisory_path": compare_plan.semantic_artifact_path or "",
            "semantic_advisory_rationale": compare_plan.semantic_rationale,
        },
        progress_callback=progress_callback,
    )
    return CompareExecutionOutcome(
        result={**result, "run_plan_path": compare_plan.plan_path},
        scenario_pack_path=scenario_pack_path,
        population_pack_path=population_pack_path,
        coverage_source=compare_plan.coverage_source,
        scenario_generation_mode=compare_plan.scenario_generation_mode,
        swarm_generation_mode=compare_plan.swarm_generation_mode,
    )


def _regression_target_from_plan(payload: dict[str, object]) -> RegressionTarget:
    mode = str(payload.get("mode", ""))
    if mode not in {"reference_artifact", "external_url"}:
        raise SystemExit(f"Saved plan has unsupported compare target mode `{mode}`.")
    return RegressionTarget(
        label=str(payload.get("label", "")),
        mode=mode,
        service_artifact_dir=optional_text(payload.get("service_artifact_dir")),
        adapter_base_url=optional_text(payload.get("adapter_base_url")),
    )
