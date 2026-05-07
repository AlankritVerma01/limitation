"""Shared bounded planning behavior for public workflows."""

from __future__ import annotations

import json
from pathlib import Path

from ..artifacts.run_plan import PlannedWorkflow, write_run_plan
from ._planner_decisions import plan_decisions
from ._planner_defaults import (
    build_semantic_advisory,
    default_audit_semantic_settings,
    default_generation_ai_profile,
    default_semantic_settings,
)
from ._planner_support import (
    coverage_display_mode,
    coverage_source,
    now_utc,
    optional_int,
    optional_str,
)
from .types import (
    AuditPlanContext,
    AuditPlanRequest,
    ComparePlanContext,
    ComparePlanRequest,
    RunSwarmPlanContext,
    RunSwarmPlanRequest,
)


def plan_audit(request: AuditPlanRequest) -> AuditPlanContext:
    """Build one audit plan plus the resolved target context."""
    semantic_defaults = default_audit_semantic_settings(
        explicit_inputs=request.explicit_inputs,
        fallback_mode=request.semantic_mode,
        fallback_model=request.semantic_model,
        fallback_profile=request.semantic_profile,
    )
    scenario_decision = (
        "explicit_reuse" if request.scenario_pack_path is not None else "use_built_in_scenarios"
    )
    population_decision = (
        "explicit_reuse"
        if request.population_pack_path is not None
        else "use_built_in_population"
    )
    scenario_generation_mode = (
        "reused" if request.scenario_pack_path is not None else "built_in"
    )
    swarm_generation_mode = (
        "reused" if request.population_pack_path is not None else "built_in"
    )
    coverage_source_value = coverage_source(
        scenario_mode=scenario_generation_mode,
        swarm_mode=swarm_generation_mode,
    )
    semantic_advisory = build_semantic_advisory(
        explicit_inputs=request.explicit_inputs,
        planner_mode="deterministic",
        semantic_mode=str(semantic_defaults["semantic_mode"]),
        semantic_model=optional_str(semantic_defaults["semantic_model"]),
        semantic_profile=str(semantic_defaults["semantic_profile"]),
        artifact_path=str(Path(request.output_root) / "semantic_advisory.json"),
    )
    payload = {
        "plan_version": "v1",
        "workflow_type": "audit",
        "domain": request.domain_name,
        "brief": "",
        "generated_at_utc": now_utc(),
        "planner": {
            "role": "shared_llm_orchestrator",
            "mode": "deterministic",
            "provider_name": "",
            "model_name": "",
            "model_profile": "",
            "summary": "Deterministic planner preserved direct audit target and coverage inputs.",
        },
        "target": dict(sorted(request.target_config.items())),
        "coverage_intent": {
            "scenario": {
                "decision": scenario_decision,
                "artifact_path": request.scenario_pack_path,
                "generator_mode": "reused" if request.scenario_pack_path is not None else "built_in",
                "built_in_selection": request.scenario_name,
            },
            "swarm": {
                "decision": population_decision,
                "artifact_path": request.population_pack_path,
                "generator_mode": "reused" if request.population_pack_path is not None else "built_in",
            },
            "coverage_source": coverage_source_value,
        },
        "run_shaping": {
            "seed": request.explicit_inputs.get("seed", 0),
            "run_name": optional_str(request.explicit_inputs.get("run_name")),
            "include_slice_membership": bool(
                request.explicit_inputs.get("include_slice_membership", False)
            ),
            "semantic_mode": semantic_defaults["semantic_mode"],
            "semantic_model": semantic_defaults["semantic_model"],
            "semantic_profile": semantic_defaults["semantic_profile"],
        },
        "semantic_advisory": semantic_advisory,
        "planned_artifacts": {
            "output_dir": request.output_root,
            "run_manifest_path": str(Path(request.output_root) / "run_manifest.json"),
            "semantic_advisory_path": semantic_advisory["artifact_path"],
            "scenario_pack_path": request.scenario_pack_path,
            "population_pack_path": request.population_pack_path,
        },
        "explicit_user_inputs": dict(sorted(request.explicit_inputs.items())),
        "planner_selected_defaults": {
            "include_slice_membership": (
                False if "include_slice_membership" not in request.explicit_inputs else None
            ),
            "semantic_mode": (
                semantic_defaults["semantic_mode"]
                if "semantic_mode" not in request.explicit_inputs
                else ""
            ),
            "semantic_model": (
                semantic_defaults["semantic_model"]
                if "semantic_model" not in request.explicit_inputs
                else ""
            ),
            "semantic_profile": (
                semantic_defaults["semantic_profile"]
                if "semantic_profile" not in request.explicit_inputs
                else ""
            ),
        },
    }
    plan_path, plan_id = write_run_plan(payload, output_dir=request.output_root)
    payload["plan_id"] = plan_id
    payload["planned_artifacts"]["run_plan_path"] = plan_path
    Path(plan_path).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return AuditPlanContext(
        plan=PlannedWorkflow(
            payload=payload,
            plan_path=plan_path,
            plan_id=plan_id,
            planner_mode="deterministic",
            planner_provider_name="",
            planner_model_name="",
            planner_model_profile="",
            planner_summary="Deterministic planner preserved direct audit target and coverage inputs.",
            scenario_pack_path=request.scenario_pack_path,
            population_pack_path=request.population_pack_path,
            scenario_action=scenario_decision,
            population_action=population_decision,
            scenario_generation_mode=scenario_generation_mode,
            swarm_generation_mode=swarm_generation_mode,
            coverage_source=coverage_source_value,
            generation_mode="",
            ai_profile="",
            scenario_count=None,
            population_size=None,
            population_candidate_count=None,
            semantic_mode=str(semantic_defaults["semantic_mode"]),
            semantic_model=optional_str(semantic_defaults["semantic_model"]),
            semantic_profile=str(semantic_defaults["semantic_profile"]),
            semantic_enabled=bool(semantic_advisory["enabled"]),
            semantic_gating=str(semantic_advisory["gating"]),
            semantic_decision_origin=str(semantic_advisory["decision_origin"]),
            semantic_artifact_path=optional_str(semantic_advisory["artifact_path"]),
            semantic_rationale=str(semantic_advisory["rationale"]),
        ),
        service_mode=str(request.target_config.get("service_mode", "")),
        service_artifact_dir=optional_str(request.target_config.get("service_artifact_dir")),
        adapter_base_url=optional_str(request.target_config.get("adapter_base_url")),
        driver_kind=optional_str(request.target_config.get("driver_kind")),
        driver_config=request.target_config.get("driver_config")
        if isinstance(request.target_config.get("driver_config"), dict)
        else None,
        output_root=request.output_root,
    )


def plan_run_swarm(request: RunSwarmPlanRequest) -> RunSwarmPlanContext:
    """Build one run-swarm plan plus the resolved target context."""
    available_artifacts = {
        "scenario_pack": {
            "path": request.default_scenario_pack_path,
            "exists": Path(request.default_scenario_pack_path).exists(),
        },
        "population_pack": {
            "path": request.default_population_pack_path,
            "exists": Path(request.default_population_pack_path).exists(),
        },
    }
    effective_ai_profile = default_generation_ai_profile(
        generation_mode=request.generation_mode,
        explicit_inputs=request.explicit_inputs,
        fallback_profile=request.ai_profile,
    )
    semantic_defaults = default_semantic_settings(
        generation_mode=request.generation_mode,
        explicit_inputs=request.explicit_inputs,
        fallback_mode=request.semantic_mode,
        fallback_model=request.semantic_model,
        fallback_profile=request.semantic_profile,
    )
    planner_decisions = plan_decisions(
        workflow_type="run-swarm",
        brief=request.brief,
        generation_mode=request.generation_mode,
        explicit_inputs=request.explicit_inputs,
        locked={
            "scenario_pack_path": request.scenario_pack_path,
            "population_pack_path": request.population_pack_path,
            "generation_mode": request.generation_mode,
            "ai_profile": request.explicit_inputs.get("ai_profile"),
            "scenario_count": request.explicit_inputs.get("scenario_count"),
            "population_size": request.explicit_inputs.get("population_size"),
            "population_candidate_count": request.explicit_inputs.get("population_candidate_count"),
            "semantic_mode": request.explicit_inputs.get("semantic_mode"),
            "semantic_model": request.explicit_inputs.get("semantic_model"),
            "semantic_profile": request.explicit_inputs.get("semantic_profile"),
        },
        available_artifacts=available_artifacts,
        ai_profile=effective_ai_profile,
        scenario_count=request.scenario_count,
        population_size=request.population_size,
        population_candidate_count=request.population_candidate_count,
        semantic_mode=str(semantic_defaults["semantic_mode"]),
        semantic_model=optional_str(semantic_defaults["semantic_model"]),
        semantic_profile=str(semantic_defaults["semantic_profile"]),
        rerun_count=None,
    )
    planned_scenario_path = request.scenario_pack_path or request.default_scenario_pack_path
    planned_population_path = request.population_pack_path or request.default_population_pack_path
    scenario_generation_mode = coverage_display_mode(
        explicit_path=request.scenario_pack_path,
        planner_action=str(planner_decisions["scenario_action"]),
        generation_mode=request.generation_mode,
    )
    swarm_generation_mode = coverage_display_mode(
        explicit_path=request.population_pack_path,
        planner_action=str(planner_decisions["population_action"]),
        generation_mode=request.generation_mode,
    )
    coverage_source_value = coverage_source(
        scenario_mode=scenario_generation_mode,
        swarm_mode=swarm_generation_mode,
    )
    semantic_advisory = build_semantic_advisory(
        explicit_inputs=request.explicit_inputs,
        planner_mode=str(planner_decisions["planner_mode"]),
        semantic_mode=str(planner_decisions["semantic_mode"]),
        semantic_model=optional_str(planner_decisions["semantic_model"]),
        semantic_profile=str(planner_decisions["semantic_profile"]),
        artifact_path=str(Path(request.output_root) / "semantic_advisory.json"),
    )
    payload = {
        "plan_version": "v1",
        "workflow_type": "run-swarm",
        "domain": request.domain_name,
        "brief": request.brief,
        "generated_at_utc": now_utc(),
        "planner": {
            "role": "shared_llm_orchestrator",
            "mode": planner_decisions["planner_mode"],
            "provider_name": planner_decisions["planner_provider_name"],
            "model_name": planner_decisions["planner_model_name"],
            "model_profile": planner_decisions["planner_model_profile"],
            "summary": planner_decisions["planner_summary"],
        },
        "target": dict(sorted(request.target_config.items())),
        "coverage_intent": {
            "scenario": {
                "decision": planner_decisions["scenario_action"],
                "artifact_path": planned_scenario_path,
                "generator_mode": request.generation_mode if request.scenario_pack_path is None else "reused",
            },
            "swarm": {
                "decision": planner_decisions["population_action"],
                "artifact_path": planned_population_path,
                "generator_mode": request.generation_mode if request.population_pack_path is None else "reused",
            },
            "coverage_source": coverage_source_value,
        },
        "run_shaping": {
            "seed": request.explicit_inputs.get("seed", 0),
            "run_name": optional_str(request.explicit_inputs.get("run_name")),
            "generation_mode": request.generation_mode,
            "ai_profile": planner_decisions["ai_profile"],
            "scenario_count": planner_decisions["scenario_count"],
            "population_size": planner_decisions["population_size"],
            "population_candidate_count": planner_decisions["population_candidate_count"],
            "semantic_mode": planner_decisions["semantic_mode"],
            "semantic_model": planner_decisions["semantic_model"],
            "semantic_profile": planner_decisions["semantic_profile"],
        },
        "semantic_advisory": semantic_advisory,
        "planned_artifacts": {
            "output_dir": request.output_root,
            "run_manifest_path": str(Path(request.output_root) / "run_manifest.json"),
            "semantic_advisory_path": semantic_advisory["artifact_path"],
            "scenario_pack_path": planned_scenario_path,
            "population_pack_path": planned_population_path,
        },
        "explicit_user_inputs": dict(sorted(request.explicit_inputs.items())),
        "planner_selected_defaults": {
            "ai_profile": planner_decisions["ai_profile"] if "ai_profile" not in request.explicit_inputs else "",
            "scenario_count": planner_decisions["scenario_count"] if "scenario_count" not in request.explicit_inputs else None,
            "population_size": planner_decisions["population_size"] if "population_size" not in request.explicit_inputs else None,
            "population_candidate_count": (
                planner_decisions["population_candidate_count"]
                if "population_candidate_count" not in request.explicit_inputs
                else None
            ),
            "semantic_mode": planner_decisions["semantic_mode"] if "semantic_mode" not in request.explicit_inputs else "",
            "semantic_model": planner_decisions["semantic_model"] if "semantic_model" not in request.explicit_inputs else "",
            "semantic_profile": (
                planner_decisions["semantic_profile"]
                if "semantic_profile" not in request.explicit_inputs
                else ""
            ),
        },
    }
    plan_path, plan_id = write_run_plan(payload, output_dir=request.output_root)
    payload["plan_id"] = plan_id
    payload["planned_artifacts"]["run_plan_path"] = plan_path
    Path(plan_path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return RunSwarmPlanContext(
        plan=PlannedWorkflow(
            payload=payload,
            plan_path=plan_path,
            plan_id=plan_id,
            planner_mode=str(planner_decisions["planner_mode"]),
            planner_provider_name=str(planner_decisions["planner_provider_name"]),
            planner_model_name=str(planner_decisions["planner_model_name"]),
            planner_model_profile=str(planner_decisions["planner_model_profile"]),
            planner_summary=str(planner_decisions["planner_summary"]),
            scenario_pack_path=planned_scenario_path,
            population_pack_path=planned_population_path,
            scenario_action=str(planner_decisions["scenario_action"]),
            population_action=str(planner_decisions["population_action"]),
            scenario_generation_mode=scenario_generation_mode,
            swarm_generation_mode=swarm_generation_mode,
            coverage_source=coverage_source_value,
            generation_mode=request.generation_mode,
            ai_profile=str(planner_decisions["ai_profile"]),
            scenario_count=int(planner_decisions["scenario_count"]),
            population_size=optional_int(planner_decisions["population_size"]),
            population_candidate_count=optional_int(planner_decisions["population_candidate_count"]),
            semantic_mode=str(planner_decisions["semantic_mode"]),
            semantic_model=optional_str(planner_decisions["semantic_model"]),
            semantic_profile=str(planner_decisions["semantic_profile"]),
            semantic_enabled=bool(semantic_advisory["enabled"]),
            semantic_gating=str(semantic_advisory["gating"]),
            semantic_decision_origin=str(semantic_advisory["decision_origin"]),
            semantic_artifact_path=optional_str(semantic_advisory["artifact_path"]),
            semantic_rationale=str(semantic_advisory["rationale"]),
        ),
        service_mode=str(request.target_config.get("service_mode", "")),
        service_artifact_dir=optional_str(request.target_config.get("service_artifact_dir")),
        adapter_base_url=optional_str(request.target_config.get("adapter_base_url")),
        driver_kind=optional_str(request.target_config.get("driver_kind")),
        driver_config=request.target_config.get("driver_config")
        if isinstance(request.target_config.get("driver_config"), dict)
        else None,
        output_root=request.output_root,
    )


def plan_compare(request: ComparePlanRequest) -> ComparePlanContext:
    """Build one compare plan plus the resolved compare target context."""
    brief_text = request.brief or ""
    available_artifacts = {
        "scenario_pack": {
            "path": request.default_scenario_pack_path or "",
            "exists": bool(request.default_scenario_pack_path) and Path(request.default_scenario_pack_path).exists(),
        },
        "population_pack": {
            "path": request.default_population_pack_path or "",
            "exists": bool(request.default_population_pack_path) and Path(request.default_population_pack_path).exists(),
        },
    }
    effective_ai_profile = default_generation_ai_profile(
        generation_mode=request.generation_mode,
        explicit_inputs=request.explicit_inputs,
        fallback_profile=request.ai_profile,
    )
    semantic_defaults = default_semantic_settings(
        generation_mode=request.generation_mode,
        explicit_inputs=request.explicit_inputs,
        fallback_mode=request.semantic_mode,
        fallback_model=request.semantic_model,
        fallback_profile=request.semantic_profile,
    )
    planner_decisions = plan_decisions(
        workflow_type="compare",
        brief=brief_text,
        generation_mode=request.generation_mode,
        explicit_inputs=request.explicit_inputs,
        locked={
            "scenario_pack_path": request.scenario_pack_path,
            "population_pack_path": request.population_pack_path,
            "generation_mode": request.generation_mode,
            "ai_profile": request.explicit_inputs.get("ai_profile"),
            "scenario_count": request.explicit_inputs.get("scenario_count"),
            "population_size": request.explicit_inputs.get("population_size"),
            "population_candidate_count": request.explicit_inputs.get("population_candidate_count"),
            "semantic_mode": request.explicit_inputs.get("semantic_mode"),
            "semantic_model": request.explicit_inputs.get("semantic_model"),
            "semantic_profile": request.explicit_inputs.get("semantic_profile"),
            "rerun_count": request.explicit_inputs.get("rerun_count"),
        },
        available_artifacts=available_artifacts,
        ai_profile=effective_ai_profile,
        scenario_count=request.scenario_count,
        population_size=request.population_size,
        population_candidate_count=request.population_candidate_count,
        semantic_mode=str(semantic_defaults["semantic_mode"]),
        semantic_model=optional_str(semantic_defaults["semantic_model"]),
        semantic_profile=str(semantic_defaults["semantic_profile"]),
        rerun_count=request.rerun_count,
    )
    effective_scenario_path = request.scenario_pack_path
    effective_population_path = request.population_pack_path
    scenario_generation_mode = "built_in"
    swarm_generation_mode = "built_in"
    coverage_source_value = "built_in"
    scenario_decision = "use_built_in_scenarios"
    population_decision = "use_built_in_population"
    if brief_text:
        if effective_scenario_path is None:
            effective_scenario_path = request.default_scenario_pack_path
        if effective_population_path is None:
            effective_population_path = request.default_population_pack_path
        scenario_decision = str(planner_decisions["scenario_action"])
        population_decision = str(planner_decisions["population_action"])
        scenario_generation_mode = coverage_display_mode(
            explicit_path=request.scenario_pack_path,
            planner_action=scenario_decision,
            generation_mode=request.generation_mode,
        )
        swarm_generation_mode = coverage_display_mode(
            explicit_path=request.population_pack_path,
            planner_action=population_decision,
            generation_mode=request.generation_mode,
        )
        coverage_source_value = coverage_source(
            scenario_mode=scenario_generation_mode,
            swarm_mode=swarm_generation_mode,
        )
    semantic_advisory = build_semantic_advisory(
        explicit_inputs=request.explicit_inputs,
        planner_mode=str(planner_decisions["planner_mode"]),
        semantic_mode=str(planner_decisions["semantic_mode"]),
        semantic_model=optional_str(planner_decisions["semantic_model"]),
        semantic_profile=str(planner_decisions["semantic_profile"]),
        artifact_path=str(Path(request.output_root) / "semantic_regression_advisory.json"),
    )
    payload = {
        "plan_version": "v1",
        "workflow_type": "compare",
        "domain": request.domain_name,
        "brief": brief_text,
        "generated_at_utc": now_utc(),
        "planner": {
            "role": "shared_llm_orchestrator",
            "mode": planner_decisions["planner_mode"],
            "provider_name": planner_decisions["planner_provider_name"],
            "model_name": planner_decisions["planner_model_name"],
            "model_profile": planner_decisions["planner_model_profile"],
            "summary": planner_decisions["planner_summary"],
        },
        "targets": {
            "baseline": dict(sorted(request.baseline_target_config.items())),
            "candidate": dict(sorted(request.candidate_target_config.items())),
        },
        "coverage_intent": {
            "scenario": {
                "decision": scenario_decision,
                "artifact_path": effective_scenario_path,
                "generator_mode": (
                    request.generation_mode
                    if brief_text and request.scenario_pack_path is None
                    else ("reused" if request.scenario_pack_path is not None else "built_in")
                ),
                "built_in_selection": request.scenario_name,
            },
            "swarm": {
                "decision": population_decision,
                "artifact_path": effective_population_path,
                "generator_mode": (
                    request.generation_mode
                    if brief_text and request.population_pack_path is None
                    else ("reused" if request.population_pack_path is not None else "built_in")
                ),
            },
            "coverage_source": coverage_source_value,
        },
        "run_shaping": {
            "seed": request.explicit_inputs.get("seed", 0),
            "policy_mode": request.explicit_inputs.get("policy_mode", "default"),
            "generation_mode": request.generation_mode,
            "ai_profile": planner_decisions["ai_profile"],
            "scenario_count": planner_decisions["scenario_count"],
            "population_size": planner_decisions["population_size"],
            "population_candidate_count": planner_decisions["population_candidate_count"],
            "semantic_mode": planner_decisions["semantic_mode"],
            "semantic_model": planner_decisions["semantic_model"],
            "semantic_profile": planner_decisions["semantic_profile"],
            "rerun_count": planner_decisions["rerun_count"],
        },
        "semantic_advisory": semantic_advisory,
        "planned_artifacts": {
            "output_dir": request.output_root,
            "run_manifest_path": str(Path(request.output_root) / "run_manifest.json"),
            "semantic_advisory_path": semantic_advisory["artifact_path"],
            "scenario_pack_path": effective_scenario_path,
            "population_pack_path": effective_population_path,
        },
        "explicit_user_inputs": dict(sorted(request.explicit_inputs.items())),
        "planner_selected_defaults": {
            "ai_profile": planner_decisions["ai_profile"] if "ai_profile" not in request.explicit_inputs else "",
            "scenario_count": planner_decisions["scenario_count"] if "scenario_count" not in request.explicit_inputs else None,
            "population_size": planner_decisions["population_size"] if "population_size" not in request.explicit_inputs else None,
            "population_candidate_count": (
                planner_decisions["population_candidate_count"]
                if "population_candidate_count" not in request.explicit_inputs
                else None
            ),
            "semantic_mode": planner_decisions["semantic_mode"] if "semantic_mode" not in request.explicit_inputs else "",
            "semantic_model": planner_decisions["semantic_model"] if "semantic_model" not in request.explicit_inputs else "",
            "semantic_profile": (
                planner_decisions["semantic_profile"]
                if "semantic_profile" not in request.explicit_inputs
                else ""
            ),
            "rerun_count": planner_decisions["rerun_count"] if "rerun_count" not in request.explicit_inputs else None,
        },
    }
    plan_path, plan_id = write_run_plan(payload, output_dir=request.output_root)
    payload["plan_id"] = plan_id
    payload["planned_artifacts"]["run_plan_path"] = plan_path
    Path(plan_path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ComparePlanContext(
        plan=PlannedWorkflow(
            payload=payload,
            plan_path=plan_path,
            plan_id=plan_id,
            planner_mode=str(planner_decisions["planner_mode"]),
            planner_provider_name=str(planner_decisions["planner_provider_name"]),
            planner_model_name=str(planner_decisions["planner_model_name"]),
            planner_model_profile=str(planner_decisions["planner_model_profile"]),
            planner_summary=str(planner_decisions["planner_summary"]),
            scenario_pack_path=effective_scenario_path,
            population_pack_path=effective_population_path,
            scenario_action=scenario_decision,
            population_action=population_decision,
            scenario_generation_mode=scenario_generation_mode,
            swarm_generation_mode=swarm_generation_mode,
            coverage_source=coverage_source_value,
            generation_mode=request.generation_mode,
            ai_profile=str(planner_decisions["ai_profile"]),
            scenario_count=int(planner_decisions["scenario_count"]),
            population_size=optional_int(planner_decisions["population_size"]),
            population_candidate_count=optional_int(planner_decisions["population_candidate_count"]),
            semantic_mode=str(planner_decisions["semantic_mode"]),
            semantic_model=optional_str(planner_decisions["semantic_model"]),
            semantic_profile=str(planner_decisions["semantic_profile"]),
            semantic_enabled=bool(semantic_advisory["enabled"]),
            semantic_gating=str(semantic_advisory["gating"]),
            semantic_decision_origin=str(semantic_advisory["decision_origin"]),
            semantic_artifact_path=optional_str(semantic_advisory["artifact_path"]),
            semantic_rationale=str(semantic_advisory["rationale"]),
            rerun_count=int(planner_decisions["rerun_count"]),
        ),
        baseline_target=request.baseline_target,
        candidate_target=request.candidate_target,
        output_root=request.output_root,
    )
