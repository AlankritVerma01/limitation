"""Shared pre-run planning artifacts and bounded orchestration helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any

from .config import DEFAULT_OUTPUT_DIR
from .domain_registry import list_public_domain_definitions
from .generation_support import (
    DEFAULT_PROVIDER_NAME,
    build_responses_endpoint,
    extract_response_text,
    load_dotenv_if_present,
    provider_credentials_available,
    read_retry_count_with_fallback,
    read_timeout_seconds_with_fallback,
    request_provider_payload,
    resolve_provider_model,
)

RUN_PLAN_CONTRACT_VERSION = "v1"

_ALLOWED_WORKFLOW_TYPES = {"run-swarm", "compare", "audit"}
_ALLOWED_AI_PROFILES = {"fast", "balanced", "deep"}
_ALLOWED_GENERATION_MODES = {"fixture", "provider"}
_ALLOWED_SEMANTIC_MODES = {"off", "fixture", "provider"}
_ALLOWED_SCENARIO_ACTIONS = {
    "generate_new",
    "planner_reuse_existing",
    "explicit_reuse",
    "use_built_in_scenarios",
}
_ALLOWED_SWARM_ACTIONS = {
    "generate_new",
    "planner_reuse_existing",
    "explicit_reuse",
    "use_built_in_population",
}


@dataclass(frozen=True)
class PlannedWorkflow:
    """Resolved planning decisions for one workflow before execution."""

    payload: dict[str, Any]
    plan_path: str
    plan_id: str
    planner_mode: str
    planner_provider_name: str
    planner_model_name: str
    planner_model_profile: str
    planner_summary: str
    scenario_pack_path: str | None
    population_pack_path: str | None
    scenario_action: str
    population_action: str
    scenario_generation_mode: str
    swarm_generation_mode: str
    coverage_source: str
    generation_mode: str
    ai_profile: str
    scenario_count: int | None
    population_size: int | None
    population_candidate_count: int | None
    semantic_mode: str
    semantic_model: str | None
    semantic_profile: str
    semantic_enabled: bool = False
    semantic_gating: str = "advisory_only"
    semantic_decision_origin: str = ""
    semantic_artifact_path: str | None = None
    semantic_rationale: str = ""
    rerun_count: int | None = None


def write_run_plan(payload: dict[str, Any], *, output_dir: str) -> tuple[str, str]:
    """Write the durable pre-run plan artifact and return path plus plan id."""
    resolved_output_dir = Path(output_dir or DEFAULT_OUTPUT_DIR)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    plan_path = resolved_output_dir / "run_plan.json"
    plan_id = str(payload.get("plan_id", ""))
    if not plan_id:
        plan_id = _build_plan_id(
            workflow_type=str(payload.get("workflow_type", "")),
            domain=str(payload.get("domain", "")),
            brief=str(payload.get("brief", "")),
        )
        payload = {**payload, "plan_id": plan_id}
    plan_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return str(plan_path), plan_id


def build_run_swarm_plan(
    *,
    domain_name: str,
    brief: str,
    generation_mode: str,
    output_root: str,
    target_config: dict[str, str],
    explicit_inputs: dict[str, Any],
    scenario_pack_path: str | None,
    population_pack_path: str | None,
    scenario_count: int,
    population_size: int | None,
    population_candidate_count: int | None,
    ai_profile: str,
    semantic_mode: str,
    semantic_model: str | None,
    semantic_profile: str,
    default_scenario_pack_path: str,
    default_population_pack_path: str,
) -> PlannedWorkflow:
    """Plan one brief-driven swarm workflow before execution."""
    available_artifacts = {
        "scenario_pack": {
            "path": default_scenario_pack_path,
            "exists": Path(default_scenario_pack_path).exists(),
        },
        "population_pack": {
            "path": default_population_pack_path,
            "exists": Path(default_population_pack_path).exists(),
        },
    }
    locked = {
        "scenario_pack_path": scenario_pack_path,
        "population_pack_path": population_pack_path,
        "generation_mode": generation_mode,
        "ai_profile": explicit_inputs.get("ai_profile"),
        "scenario_count": explicit_inputs.get("scenario_count"),
        "population_size": explicit_inputs.get("population_size"),
        "population_candidate_count": explicit_inputs.get("population_candidate_count"),
        "semantic_mode": explicit_inputs.get("semantic_mode"),
        "semantic_model": explicit_inputs.get("semantic_model"),
        "semantic_profile": explicit_inputs.get("semantic_profile"),
    }
    planner_decisions = _plan_decisions(
        workflow_type="run-swarm",
        brief=brief,
        generation_mode=generation_mode,
        explicit_inputs=explicit_inputs,
        locked=locked,
        available_artifacts=available_artifacts,
        ai_profile=ai_profile,
        scenario_count=scenario_count,
        population_size=population_size,
        population_candidate_count=population_candidate_count,
        semantic_mode=semantic_mode,
        semantic_model=semantic_model,
        semantic_profile=semantic_profile,
        rerun_count=None,
    )
    planned_scenario_path = scenario_pack_path
    planned_population_path = population_pack_path
    if planned_scenario_path is None:
        planned_scenario_path = (
            default_scenario_pack_path
            if planner_decisions["scenario_action"] == "generate_new"
            else default_scenario_pack_path
        )
    if planned_population_path is None:
        planned_population_path = (
            default_population_pack_path
            if planner_decisions["population_action"] == "generate_new"
            else default_population_pack_path
        )
    scenario_generation_mode = _coverage_display_mode(
        explicit_path=scenario_pack_path,
        planner_action=str(planner_decisions["scenario_action"]),
        generation_mode=generation_mode,
    )
    swarm_generation_mode = _coverage_display_mode(
        explicit_path=population_pack_path,
        planner_action=str(planner_decisions["population_action"]),
        generation_mode=generation_mode,
    )
    coverage_source = _coverage_source(
        scenario_mode=scenario_generation_mode,
        swarm_mode=swarm_generation_mode,
    )
    payload = {
        "plan_version": RUN_PLAN_CONTRACT_VERSION,
        "workflow_type": "run-swarm",
        "domain": domain_name,
        "brief": brief,
        "generated_at_utc": _now_utc(),
        "planner": {
            "role": "shared_llm_orchestrator",
            "mode": planner_decisions["planner_mode"],
            "provider_name": planner_decisions["planner_provider_name"],
            "model_name": planner_decisions["planner_model_name"],
            "model_profile": planner_decisions["planner_model_profile"],
            "summary": planner_decisions["planner_summary"],
        },
        "target": dict(sorted(target_config.items())),
        "coverage_intent": {
            "scenario": {
                "decision": planner_decisions["scenario_action"],
                "artifact_path": planned_scenario_path,
                "generator_mode": generation_mode if scenario_pack_path is None else "reused",
            },
            "swarm": {
                "decision": planner_decisions["population_action"],
                "artifact_path": planned_population_path,
                "generator_mode": generation_mode if population_pack_path is None else "reused",
            },
            "coverage_source": coverage_source,
        },
        "run_shaping": {
            "seed": explicit_inputs.get("seed", 0),
            "run_name": _optional_str(explicit_inputs.get("run_name")),
            "generation_mode": generation_mode,
            "ai_profile": planner_decisions["ai_profile"],
            "scenario_count": planner_decisions["scenario_count"],
            "population_size": planner_decisions["population_size"],
            "population_candidate_count": planner_decisions["population_candidate_count"],
            "semantic_mode": planner_decisions["semantic_mode"],
            "semantic_model": planner_decisions["semantic_model"],
            "semantic_profile": planner_decisions["semantic_profile"],
        },
        "planned_artifacts": {
            "output_dir": output_root,
            "run_manifest_path": str(Path(output_root) / "run_manifest.json"),
            "scenario_pack_path": planned_scenario_path,
            "population_pack_path": planned_population_path,
        },
        "explicit_user_inputs": dict(sorted(explicit_inputs.items())),
        "planner_selected_defaults": {
            "ai_profile": planner_decisions["ai_profile"] if "ai_profile" not in explicit_inputs else "",
            "scenario_count": planner_decisions["scenario_count"] if "scenario_count" not in explicit_inputs else None,
            "population_size": planner_decisions["population_size"] if "population_size" not in explicit_inputs else None,
            "population_candidate_count": (
                planner_decisions["population_candidate_count"]
                if "population_candidate_count" not in explicit_inputs
                else None
            ),
            "semantic_mode": planner_decisions["semantic_mode"] if "semantic_mode" not in explicit_inputs else "",
            "semantic_model": planner_decisions["semantic_model"] if "semantic_model" not in explicit_inputs else "",
            "semantic_profile": (
                planner_decisions["semantic_profile"]
                if "semantic_profile" not in explicit_inputs
                else ""
            ),
        },
    }
    plan_path, plan_id = write_run_plan(payload, output_dir=output_root)
    payload["plan_id"] = plan_id
    payload["planned_artifacts"]["run_plan_path"] = plan_path
    Path(plan_path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return PlannedWorkflow(
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
        coverage_source=coverage_source,
        generation_mode=generation_mode,
        ai_profile=str(planner_decisions["ai_profile"]),
        scenario_count=int(planner_decisions["scenario_count"]),
        population_size=_optional_int(planner_decisions["population_size"]),
        population_candidate_count=_optional_int(
            planner_decisions["population_candidate_count"]
        ),
        semantic_mode=str(planner_decisions["semantic_mode"]),
        semantic_model=_optional_str(planner_decisions["semantic_model"]),
        semantic_profile=str(planner_decisions["semantic_profile"]),
    )


def build_compare_plan(
    *,
    domain_name: str,
    brief: str | None,
    generation_mode: str,
    output_root: str,
    baseline_target: dict[str, str],
    candidate_target: dict[str, str],
    explicit_inputs: dict[str, Any],
    scenario_pack_path: str | None,
    population_pack_path: str | None,
    scenario_count: int,
    population_size: int | None,
    population_candidate_count: int | None,
    ai_profile: str,
    semantic_mode: str,
    semantic_model: str | None,
    semantic_profile: str,
    rerun_count: int,
    default_scenario_pack_path: str | None,
    default_population_pack_path: str | None,
    scenario_name: str,
) -> PlannedWorkflow:
    """Plan one compare workflow before execution."""
    brief_text = brief or ""
    available_artifacts = {
        "scenario_pack": {
            "path": default_scenario_pack_path or "",
            "exists": bool(default_scenario_pack_path) and Path(default_scenario_pack_path).exists(),
        },
        "population_pack": {
            "path": default_population_pack_path or "",
            "exists": bool(default_population_pack_path) and Path(default_population_pack_path).exists(),
        },
    }
    planner_decisions = _plan_decisions(
        workflow_type="compare",
        brief=brief_text,
        generation_mode=generation_mode,
        explicit_inputs=explicit_inputs,
        locked={
            "scenario_pack_path": scenario_pack_path,
            "population_pack_path": population_pack_path,
            "generation_mode": generation_mode,
            "ai_profile": explicit_inputs.get("ai_profile"),
            "scenario_count": explicit_inputs.get("scenario_count"),
            "population_size": explicit_inputs.get("population_size"),
            "population_candidate_count": explicit_inputs.get("population_candidate_count"),
            "semantic_mode": explicit_inputs.get("semantic_mode"),
            "semantic_model": explicit_inputs.get("semantic_model"),
            "semantic_profile": explicit_inputs.get("semantic_profile"),
            "rerun_count": explicit_inputs.get("rerun_count"),
        },
        available_artifacts=available_artifacts,
        ai_profile=ai_profile,
        scenario_count=scenario_count,
        population_size=population_size,
        population_candidate_count=population_candidate_count,
        semantic_mode=semantic_mode,
        semantic_model=semantic_model,
        semantic_profile=semantic_profile,
        rerun_count=rerun_count,
    )
    effective_scenario_path = scenario_pack_path
    effective_population_path = population_pack_path
    scenario_generation_mode = "built_in"
    swarm_generation_mode = "built_in"
    coverage_source = "built_in"
    scenario_decision = "use_built_in_scenarios"
    population_decision = "use_built_in_population"
    if brief_text:
        if effective_scenario_path is None:
            effective_scenario_path = default_scenario_pack_path
        if effective_population_path is None:
            effective_population_path = default_population_pack_path
        scenario_decision = str(planner_decisions["scenario_action"])
        population_decision = str(planner_decisions["population_action"])
        scenario_generation_mode = _coverage_display_mode(
            explicit_path=scenario_pack_path,
            planner_action=scenario_decision,
            generation_mode=generation_mode,
        )
        swarm_generation_mode = _coverage_display_mode(
            explicit_path=population_pack_path,
            planner_action=population_decision,
            generation_mode=generation_mode,
        )
        coverage_source = _coverage_source(
            scenario_mode=scenario_generation_mode,
            swarm_mode=swarm_generation_mode,
        )
    payload = {
        "plan_version": RUN_PLAN_CONTRACT_VERSION,
        "workflow_type": "compare",
        "domain": domain_name,
        "brief": brief_text,
        "generated_at_utc": _now_utc(),
        "planner": {
            "role": "shared_llm_orchestrator",
            "mode": planner_decisions["planner_mode"],
            "provider_name": planner_decisions["planner_provider_name"],
            "model_name": planner_decisions["planner_model_name"],
            "model_profile": planner_decisions["planner_model_profile"],
            "summary": planner_decisions["planner_summary"],
        },
        "targets": {
            "baseline": dict(sorted(baseline_target.items())),
            "candidate": dict(sorted(candidate_target.items())),
        },
        "coverage_intent": {
            "scenario": {
                "decision": scenario_decision,
                "artifact_path": effective_scenario_path,
                "generator_mode": (
                    generation_mode
                    if brief_text and scenario_pack_path is None
                    else ("reused" if scenario_pack_path is not None else "built_in")
                ),
                "built_in_selection": scenario_name,
            },
            "swarm": {
                "decision": population_decision,
                "artifact_path": effective_population_path,
                "generator_mode": (
                    generation_mode
                    if brief_text and population_pack_path is None
                    else ("reused" if population_pack_path is not None else "built_in")
                ),
            },
            "coverage_source": coverage_source,
        },
        "run_shaping": {
            "seed": explicit_inputs.get("seed", 0),
            "policy_mode": explicit_inputs.get("policy_mode", "default"),
            "generation_mode": generation_mode,
            "ai_profile": planner_decisions["ai_profile"],
            "scenario_count": planner_decisions["scenario_count"],
            "population_size": planner_decisions["population_size"],
            "population_candidate_count": planner_decisions["population_candidate_count"],
            "semantic_mode": planner_decisions["semantic_mode"],
            "semantic_model": planner_decisions["semantic_model"],
            "semantic_profile": planner_decisions["semantic_profile"],
            "rerun_count": planner_decisions["rerun_count"],
        },
        "planned_artifacts": {
            "output_dir": output_root,
            "run_manifest_path": str(Path(output_root) / "run_manifest.json"),
            "scenario_pack_path": effective_scenario_path,
            "population_pack_path": effective_population_path,
        },
        "explicit_user_inputs": dict(sorted(explicit_inputs.items())),
        "planner_selected_defaults": {
            "ai_profile": planner_decisions["ai_profile"] if "ai_profile" not in explicit_inputs else "",
            "scenario_count": planner_decisions["scenario_count"] if "scenario_count" not in explicit_inputs else None,
            "population_size": planner_decisions["population_size"] if "population_size" not in explicit_inputs else None,
            "population_candidate_count": (
                planner_decisions["population_candidate_count"]
                if "population_candidate_count" not in explicit_inputs
                else None
            ),
            "semantic_mode": planner_decisions["semantic_mode"] if "semantic_mode" not in explicit_inputs else "",
            "semantic_model": planner_decisions["semantic_model"] if "semantic_model" not in explicit_inputs else "",
            "semantic_profile": (
                planner_decisions["semantic_profile"]
                if "semantic_profile" not in explicit_inputs
                else ""
            ),
            "rerun_count": planner_decisions["rerun_count"] if "rerun_count" not in explicit_inputs else None,
        },
    }
    plan_path, plan_id = write_run_plan(payload, output_dir=output_root)
    payload["plan_id"] = plan_id
    payload["planned_artifacts"]["run_plan_path"] = plan_path
    Path(plan_path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return PlannedWorkflow(
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
        coverage_source=coverage_source,
        generation_mode=generation_mode,
        ai_profile=str(planner_decisions["ai_profile"]),
        scenario_count=int(planner_decisions["scenario_count"]),
        population_size=_optional_int(planner_decisions["population_size"]),
        population_candidate_count=_optional_int(
            planner_decisions["population_candidate_count"]
        ),
        semantic_mode=str(planner_decisions["semantic_mode"]),
        semantic_model=_optional_str(planner_decisions["semantic_model"]),
        semantic_profile=str(planner_decisions["semantic_profile"]),
        rerun_count=int(planner_decisions["rerun_count"]),
    )


def load_run_plan(path: str) -> PlannedWorkflow:
    """Load, validate, and normalize one persisted run plan."""
    plan_path = Path(path)
    try:
        payload = json.loads(plan_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Could not read run plan `{path}`: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Run plan `{path}` is not valid JSON.") from exc
    validated_payload = validate_run_plan_payload(payload, plan_path=str(plan_path))
    return planned_workflow_from_payload(validated_payload, plan_path=str(plan_path))


def validate_run_plan_payload(
    payload: Any,
    *,
    plan_path: str = "",
) -> dict[str, Any]:
    """Validate the persisted run-plan contract and return a normalized payload."""
    if not isinstance(payload, dict):
        raise ValueError(_prefix_plan_error(plan_path, "Run plan must be a JSON object."))
    version = str(payload.get("plan_version", "")).strip()
    if version != RUN_PLAN_CONTRACT_VERSION:
        raise ValueError(
            _prefix_plan_error(
                plan_path,
                f"Unsupported run-plan version `{version or 'missing'}`. Expected `{RUN_PLAN_CONTRACT_VERSION}`.",
            )
        )
    workflow_type = str(payload.get("workflow_type", "")).strip()
    if workflow_type not in _ALLOWED_WORKFLOW_TYPES:
        raise ValueError(
            _prefix_plan_error(
                plan_path,
                f"Unsupported workflow `{workflow_type or 'missing'}` in run plan.",
            )
        )
    domain_name = str(payload.get("domain", "")).strip()
    if domain_name not in set(list_public_domain_definitions()):
        raise ValueError(
            _prefix_plan_error(
                plan_path,
                f"Unsupported domain `{domain_name or 'missing'}` in run plan.",
            )
        )
    if not str(payload.get("plan_id", "")).strip():
        raise ValueError(_prefix_plan_error(plan_path, "Run plan is missing `plan_id`."))
    planner = _require_mapping(payload, "planner", plan_path=plan_path)
    planned_artifacts = _require_mapping(payload, "planned_artifacts", plan_path=plan_path)
    run_shaping = _require_mapping(payload, "run_shaping", plan_path=plan_path)
    coverage_intent = _require_mapping(payload, "coverage_intent", plan_path=plan_path)
    scenario_intent = _require_mapping(coverage_intent, "scenario", plan_path=plan_path)
    swarm_intent = _require_mapping(coverage_intent, "swarm", plan_path=plan_path)
    semantic_advisory = _semantic_advisory_payload(payload, plan_path=plan_path)
    _validate_run_shaping(run_shaping, workflow_type=workflow_type, plan_path=plan_path)
    _validate_semantic_advisory(
        semantic_advisory,
        run_shaping=run_shaping,
        plan_path=plan_path,
    )
    _validate_coverage_intent(
        scenario_intent=scenario_intent,
        swarm_intent=swarm_intent,
        workflow_type=workflow_type,
        plan_path=plan_path,
    )
    _validate_artifact_intent(
        planned_artifacts=planned_artifacts,
        scenario_intent=scenario_intent,
        swarm_intent=swarm_intent,
        workflow_type=workflow_type,
        plan_path=plan_path,
    )
    if workflow_type in {"run-swarm", "audit"}:
        target = _require_mapping(payload, "target", plan_path=plan_path)
        _validate_direct_target(
            target,
            workflow_type=workflow_type,
            plan_path=plan_path,
        )
    if workflow_type == "run-swarm":
        brief = str(payload.get("brief", "")).strip()
        if not brief:
            raise ValueError(
                _prefix_plan_error(plan_path, "`run-swarm` plans require a non-empty `brief`.")
            )
    if workflow_type == "compare":
        targets = _require_mapping(payload, "targets", plan_path=plan_path)
        baseline = _require_mapping(targets, "baseline", plan_path=plan_path)
        candidate = _require_mapping(targets, "candidate", plan_path=plan_path)
        _validate_compare_target(baseline, side_name="baseline", plan_path=plan_path)
        _validate_compare_target(candidate, side_name="candidate", plan_path=plan_path)
    if not isinstance(payload.get("explicit_user_inputs", {}), dict):
        raise ValueError(
            _prefix_plan_error(plan_path, "`explicit_user_inputs` must be a JSON object.")
        )
    if not isinstance(payload.get("planner_selected_defaults", {}), dict):
        raise ValueError(
            _prefix_plan_error(plan_path, "`planner_selected_defaults` must be a JSON object.")
        )
    _validate_planner_metadata(planner, plan_path=plan_path)
    return payload


def planned_workflow_from_payload(
    payload: dict[str, Any],
    *,
    plan_path: str,
) -> PlannedWorkflow:
    """Materialize one validated persisted plan into a reusable planning object."""
    coverage_intent = _require_mapping(payload, "coverage_intent", plan_path=plan_path)
    scenario_intent = _require_mapping(coverage_intent, "scenario", plan_path=plan_path)
    swarm_intent = _require_mapping(coverage_intent, "swarm", plan_path=plan_path)
    run_shaping = _require_mapping(payload, "run_shaping", plan_path=plan_path)
    planner = _require_mapping(payload, "planner", plan_path=plan_path)
    planned_artifacts = _require_mapping(payload, "planned_artifacts", plan_path=plan_path)
    workflow_type = str(payload.get("workflow_type", "")).strip()
    semantic_advisory = _semantic_advisory_payload(payload, plan_path=plan_path)
    scenario_action = str(scenario_intent.get("decision", ""))
    population_action = str(swarm_intent.get("decision", ""))
    scenario_pack_path = _optional_str(planned_artifacts.get("scenario_pack_path"))
    population_pack_path = _optional_str(planned_artifacts.get("population_pack_path"))
    scenario_generation_mode = _loaded_coverage_display_mode(
        decision=scenario_action,
        generator_mode=str(scenario_intent.get("generator_mode", "")),
    )
    swarm_generation_mode = _loaded_coverage_display_mode(
        decision=population_action,
        generator_mode=str(swarm_intent.get("generator_mode", "")),
    )
    return PlannedWorkflow(
        payload=payload,
        plan_path=plan_path,
        plan_id=str(payload.get("plan_id", "")),
        planner_mode=str(planner.get("mode", "")),
        planner_provider_name=str(planner.get("provider_name", "")),
        planner_model_name=str(planner.get("model_name", "")),
        planner_model_profile=str(planner.get("model_profile", "")),
        planner_summary=str(planner.get("summary", "")),
        scenario_pack_path=scenario_pack_path,
        population_pack_path=population_pack_path,
        scenario_action=scenario_action,
        population_action=population_action,
        scenario_generation_mode=scenario_generation_mode,
        swarm_generation_mode=swarm_generation_mode,
        coverage_source=str(coverage_intent.get("coverage_source", "")),
        generation_mode=(
            str(run_shaping.get("generation_mode", ""))
            if workflow_type != "audit"
            else ""
        ),
        ai_profile=str(run_shaping.get("ai_profile", "")) if workflow_type != "audit" else "",
        scenario_count=(
            int(run_shaping.get("scenario_count", 3))
            if workflow_type != "audit"
            else None
        ),
        population_size=(
            _optional_int(run_shaping.get("population_size"))
            if workflow_type != "audit"
            else None
        ),
        population_candidate_count=(
            _optional_int(run_shaping.get("population_candidate_count"))
            if workflow_type != "audit"
            else None
        ),
        semantic_mode=str(run_shaping.get("semantic_mode", "off")),
        semantic_model=_optional_str(run_shaping.get("semantic_model")),
        semantic_profile=str(run_shaping.get("semantic_profile", "")),
        semantic_enabled=bool(semantic_advisory.get("enabled", False)),
        semantic_gating=str(semantic_advisory.get("gating", "advisory_only")),
        semantic_decision_origin=str(semantic_advisory.get("decision_origin", "")),
        semantic_artifact_path=_optional_str(semantic_advisory.get("artifact_path")),
        semantic_rationale=str(semantic_advisory.get("rationale", "")),
        rerun_count=_optional_int(run_shaping.get("rerun_count")),
    )


def _plan_decisions(
    *,
    workflow_type: str,
    brief: str,
    generation_mode: str,
    explicit_inputs: dict[str, Any],
    locked: dict[str, Any],
    available_artifacts: dict[str, dict[str, Any]],
    ai_profile: str,
    scenario_count: int,
    population_size: int | None,
    population_candidate_count: int | None,
    semantic_mode: str,
    semantic_model: str | None,
    semantic_profile: str,
    rerun_count: int | None,
) -> dict[str, Any]:
    if generation_mode == "provider" and brief.strip() and provider_credentials_available():
        return _provider_plan_decisions(
            workflow_type=workflow_type,
            brief=brief,
            explicit_inputs=explicit_inputs,
            locked=locked,
            available_artifacts=available_artifacts,
            ai_profile=ai_profile,
            scenario_count=scenario_count,
            population_size=population_size,
            population_candidate_count=population_candidate_count,
            semantic_mode=semantic_mode,
            semantic_model=semantic_model,
            semantic_profile=semantic_profile,
            rerun_count=rerun_count,
        )
    return _deterministic_plan_decisions(
        workflow_type=workflow_type,
        brief=brief,
        explicit_inputs=explicit_inputs,
        available_artifacts=available_artifacts,
        ai_profile=ai_profile,
        scenario_count=scenario_count,
        population_size=population_size,
        population_candidate_count=population_candidate_count,
        semantic_mode=semantic_mode,
        semantic_model=semantic_model,
        semantic_profile=semantic_profile,
        rerun_count=rerun_count,
    )


def _deterministic_plan_decisions(
    *,
    workflow_type: str,
    brief: str,
    explicit_inputs: dict[str, Any],
    available_artifacts: dict[str, dict[str, Any]],
    ai_profile: str,
    scenario_count: int,
    population_size: int | None,
    population_candidate_count: int | None,
    semantic_mode: str,
    semantic_model: str | None,
    semantic_profile: str,
    rerun_count: int | None,
) -> dict[str, Any]:
    scenario_action = "explicit_reuse" if "scenario_pack_path" in explicit_inputs else "generate_new"
    population_action = (
        "explicit_reuse" if "population_pack_path" in explicit_inputs else "generate_new"
    )
    if scenario_action == "generate_new" and available_artifacts["scenario_pack"]["exists"]:
        scenario_action = "planner_reuse_existing"
    if population_action == "generate_new" and available_artifacts["population_pack"]["exists"]:
        population_action = "planner_reuse_existing"
    if not brief.strip() and "scenario_pack_path" not in explicit_inputs:
        scenario_action = "use_built_in_scenarios"
    if not brief.strip() and "population_pack_path" not in explicit_inputs:
        population_action = "use_built_in_population"
    summary = "Deterministic planner preserved explicit inputs and reused existing artifacts when available."
    if workflow_type == "compare" and not brief.strip():
        summary = "Deterministic planner kept compare on built-in coverage because no shared brief was provided."
    return {
        "planner_mode": "deterministic",
        "planner_provider_name": "",
        "planner_model_name": "",
        "planner_model_profile": "",
        "planner_summary": summary,
        "scenario_action": scenario_action,
        "population_action": population_action,
        "ai_profile": ai_profile,
        "scenario_count": scenario_count,
        "population_size": population_size,
        "population_candidate_count": population_candidate_count,
        "semantic_mode": semantic_mode,
        "semantic_model": semantic_model or "",
        "semantic_profile": semantic_profile,
        "rerun_count": rerun_count,
    }


def _provider_plan_decisions(
    *,
    workflow_type: str,
    brief: str,
    explicit_inputs: dict[str, Any],
    locked: dict[str, Any],
    available_artifacts: dict[str, dict[str, Any]],
    ai_profile: str,
    scenario_count: int,
    population_size: int | None,
    population_candidate_count: int | None,
    semantic_mode: str,
    semantic_model: str | None,
    semantic_profile: str,
    rerun_count: int | None,
) -> dict[str, Any]:
    import os

    load_dotenv_if_present()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _deterministic_plan_decisions(
            workflow_type=workflow_type,
            brief=brief,
            explicit_inputs=explicit_inputs,
            available_artifacts=available_artifacts,
            ai_profile=ai_profile,
            scenario_count=scenario_count,
            population_size=population_size,
            population_candidate_count=population_candidate_count,
            semantic_mode=semantic_mode,
            semantic_model=semantic_model,
            semantic_profile=semantic_profile,
            rerun_count=rerun_count,
        )
    planner_model_name, planner_model_profile = resolve_provider_model(
        purpose="run_planning",
        explicit_model_name=None,
        profile_name=ai_profile,
    )
    payload = request_provider_payload(
        endpoint=build_responses_endpoint(os.getenv("OPENAI_BASE_URL")),
        api_key=api_key,
        model_name=planner_model_name,
        prompt=_build_planner_prompt(
            workflow_type=workflow_type,
            brief=brief,
            explicit_inputs=explicit_inputs,
            locked=locked,
            available_artifacts=available_artifacts,
            ai_profile=ai_profile,
            scenario_count=scenario_count,
            population_size=population_size,
            population_candidate_count=population_candidate_count,
            semantic_mode=semantic_mode,
            semantic_model=semantic_model,
            semantic_profile=semantic_profile,
            rerun_count=rerun_count,
        ),
        timeout_seconds=read_timeout_seconds_with_fallback(
            "OPENAI_PLANNER_TIMEOUT_SECONDS",
            "OPENAI_TIMEOUT_SECONDS",
        ),
        retry_count=read_retry_count_with_fallback(
            "OPENAI_PLANNER_RETRY_COUNT",
            "OPENAI_RETRY_COUNT",
        ),
        purpose="run planning",
    )
    raw_text = extract_response_text(payload)
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError("Provider returned malformed JSON for run planning.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Provider run planner must return a JSON object.")
    scenario_action = _validated_action(
        parsed.get("scenario_action"),
        explicit_inputs=explicit_inputs,
        available=bool(available_artifacts["scenario_pack"]["exists"]),
        built_in_allowed=workflow_type == "compare" and not brief.strip(),
        default="generate_new" if brief.strip() else "use_built_in_scenarios",
        field_name="scenario_action",
    )
    population_action = _validated_action(
        parsed.get("population_action"),
        explicit_inputs=explicit_inputs,
        available=bool(available_artifacts["population_pack"]["exists"]),
        built_in_allowed=workflow_type == "compare" and not brief.strip(),
        default="generate_new" if brief.strip() else "use_built_in_population",
        field_name="population_action",
        explicit_flag_name="population_pack_path",
    )
    chosen_ai_profile = _validated_profile(
        parsed.get("ai_profile"),
        explicit_inputs=explicit_inputs,
        default=ai_profile,
    )
    chosen_semantic_mode = _validated_semantic_mode(
        parsed.get("semantic_mode"),
        explicit_inputs=explicit_inputs,
        default=semantic_mode,
    )
    chosen_semantic_profile = _validated_profile(
        parsed.get("semantic_profile"),
        explicit_inputs=explicit_inputs,
        default=semantic_profile,
        explicit_flag_name="semantic_profile",
    )
    chosen_semantic_model = (
        semantic_model
        if "semantic_model" in explicit_inputs
        else _optional_str(parsed.get("semantic_model"))
    )
    resolved_rerun_count = _validated_bounded_int(
        parsed.get("rerun_count"),
        explicit_inputs=explicit_inputs,
        explicit_flag_name="rerun_count",
        default=rerun_count,
        minimum=1,
        maximum=5,
    )
    return {
        "planner_mode": "provider",
        "planner_provider_name": DEFAULT_PROVIDER_NAME,
        "planner_model_name": planner_model_name,
        "planner_model_profile": planner_model_profile,
        "planner_summary": str(
            parsed.get(
                "planner_summary",
                "Provider planner selected bounded coverage and run-shaping decisions.",
            )
        ),
        "scenario_action": scenario_action,
        "population_action": population_action,
        "ai_profile": chosen_ai_profile,
        "scenario_count": _validated_bounded_int(
            parsed.get("scenario_count"),
            explicit_inputs=explicit_inputs,
            explicit_flag_name="scenario_count",
            default=scenario_count,
            minimum=1,
            maximum=5,
        ),
        "population_size": _validated_optional_bounded_int(
            parsed.get("population_size"),
            explicit_inputs=explicit_inputs,
            explicit_flag_name="population_size",
            default=population_size,
            minimum=4,
            maximum=16,
        ),
        "population_candidate_count": _validated_optional_bounded_int(
            parsed.get("population_candidate_count"),
            explicit_inputs=explicit_inputs,
            explicit_flag_name="population_candidate_count",
            default=population_candidate_count,
            minimum=4,
            maximum=32,
        ),
        "semantic_mode": chosen_semantic_mode,
        "semantic_model": chosen_semantic_model or "",
        "semantic_profile": chosen_semantic_profile,
        "rerun_count": resolved_rerun_count,
    }


def _build_planner_prompt(
    *,
    workflow_type: str,
    brief: str,
    explicit_inputs: dict[str, Any],
    locked: dict[str, Any],
    available_artifacts: dict[str, dict[str, Any]],
    ai_profile: str,
    scenario_count: int,
    population_size: int | None,
    population_candidate_count: int | None,
    semantic_mode: str,
    semantic_model: str | None,
    semantic_profile: str,
    rerun_count: int | None,
) -> str:
    payload = {
        "workflow_type": workflow_type,
        "brief": brief,
        "explicit_inputs": explicit_inputs,
        "locked": locked,
        "available_artifacts": available_artifacts,
        "defaults": {
            "ai_profile": ai_profile,
            "scenario_count": scenario_count,
            "population_size": population_size,
            "population_candidate_count": population_candidate_count,
            "semantic_mode": semantic_mode,
            "semantic_model": semantic_model,
            "semantic_profile": semantic_profile,
            "rerun_count": rerun_count,
        },
        "allowed_values": {
            "ai_profile": ["fast", "balanced", "deep"],
            "scenario_action": [
                "generate_new",
                "planner_reuse_existing",
                "explicit_reuse",
                "use_built_in_scenarios",
            ],
            "population_action": [
                "generate_new",
                "planner_reuse_existing",
                "explicit_reuse",
                "use_built_in_population",
            ],
            "semantic_mode": ["off", "fixture", "provider"],
            "scenario_count_range": {"min": 1, "max": 5},
            "population_size_range": {"min": 4, "max": 16},
            "population_candidate_count_range": {"min": 4, "max": 32},
            "rerun_count_range": {"min": 1, "max": 5},
        },
    }
    return (
        "You are a bounded orchestration planner for interaction audits.\n"
        "Return JSON only. Do not add markdown. Preserve explicit user inputs.\n"
        "Only choose `planner_reuse_existing` when the corresponding artifact exists.\n"
        "Choose compact, launch-grade coverage. Keep semantic_mode `off` unless advisory semantics add clear value.\n"
        "Return this exact shape:\n"
        "{\n"
        '  "planner_summary": "string",\n'
        '  "scenario_action": "string",\n'
        '  "population_action": "string",\n'
        '  "ai_profile": "string",\n'
        '  "scenario_count": 3,\n'
        '  "population_size": 12,\n'
        '  "population_candidate_count": 24,\n'
        '  "semantic_mode": "off",\n'
        '  "semantic_model": "string or empty",\n'
        '  "semantic_profile": "string",\n'
        '  "rerun_count": 3\n'
        "}\n"
        f"Planning context: {json.dumps(payload, sort_keys=True)}"
    )


def _validated_action(
    value: Any,
    *,
    explicit_inputs: dict[str, Any],
    available: bool,
    built_in_allowed: bool,
    default: str,
    field_name: str,
    explicit_flag_name: str = "scenario_pack_path",
) -> str:
    if explicit_flag_name in explicit_inputs:
        return "explicit_reuse"
    if not isinstance(value, str) or not value.strip():
        return default
    action = value.strip()
    allowed = {"generate_new", "planner_reuse_existing"}
    if built_in_allowed:
        allowed.add("use_built_in_scenarios" if field_name == "scenario_action" else "use_built_in_population")
    if action not in allowed:
        raise ValueError(f"Provider planner returned unsupported {field_name} `{action}`.")
    if action == "planner_reuse_existing" and not available:
        raise ValueError(f"Provider planner requested reuse for `{field_name}` but no artifact exists.")
    return action


def _validated_profile(
    value: Any,
    *,
    explicit_inputs: dict[str, Any],
    default: str,
    explicit_flag_name: str = "ai_profile",
) -> str:
    if explicit_flag_name in explicit_inputs:
        return str(explicit_inputs[explicit_flag_name])
    if not isinstance(value, str) or value.strip() not in {"fast", "balanced", "deep"}:
        return default
    return value.strip()


def _validated_semantic_mode(
    value: Any,
    *,
    explicit_inputs: dict[str, Any],
    default: str,
) -> str:
    if "semantic_mode" in explicit_inputs:
        return str(explicit_inputs["semantic_mode"])
    if not isinstance(value, str) or value.strip() not in {"off", "fixture", "provider"}:
        return default
    return value.strip()


def _validated_bounded_int(
    value: Any,
    *,
    explicit_inputs: dict[str, Any],
    explicit_flag_name: str,
    default: int | None,
    minimum: int,
    maximum: int,
) -> int | None:
    if explicit_flag_name in explicit_inputs:
        explicit_value = explicit_inputs[explicit_flag_name]
        return int(explicit_value) if explicit_value is not None else None
    if value is None:
        return default
    if not isinstance(value, int) or value < minimum or value > maximum:
        return default
    return int(value)


def _validated_optional_bounded_int(
    value: Any,
    *,
    explicit_inputs: dict[str, Any],
    explicit_flag_name: str,
    default: int | None,
    minimum: int,
    maximum: int,
) -> int | None:
    return _validated_bounded_int(
        value,
        explicit_inputs=explicit_inputs,
        explicit_flag_name=explicit_flag_name,
        default=default,
        minimum=minimum,
        maximum=maximum,
    )


def _coverage_display_mode(
    *,
    explicit_path: str | None,
    planner_action: str,
    generation_mode: str,
) -> str:
    if explicit_path is not None:
        return "reused"
    if planner_action == "planner_reuse_existing":
        return "planner-reused"
    if planner_action.startswith("use_built_in"):
        return "built_in"
    return generation_mode


def _coverage_source(*, scenario_mode: str, swarm_mode: str) -> str:
    modes = {scenario_mode, swarm_mode}
    if modes == {"reused"}:
        return "reused"
    if modes == {"built_in"}:
        return "built_in"
    if "planner-reused" in modes and len(modes) == 1:
        return "planner_reused"
    if modes <= {"fixture", "provider"} and len(modes) == 1:
        return "generated"
    if "planner-reused" in modes and modes <= {"planner-reused", "fixture", "provider"}:
        return "mixed"
    if "reused" in modes or "built_in" in modes:
        return "mixed"
    return "generated"


def _loaded_coverage_display_mode(*, decision: str, generator_mode: str) -> str:
    if decision == "explicit_reuse":
        return "reused"
    if decision == "planner_reuse_existing":
        return "planner-reused"
    if decision.startswith("use_built_in"):
        return "built_in"
    if generator_mode in {"reused", "built_in"}:
        return generator_mode
    return generator_mode or "fixture"


def _validate_run_shaping(
    run_shaping: dict[str, Any],
    *,
    workflow_type: str,
    plan_path: str,
) -> None:
    if workflow_type != "audit":
        generation_mode = str(run_shaping.get("generation_mode", "")).strip()
        if generation_mode not in _ALLOWED_GENERATION_MODES:
            raise ValueError(
                _prefix_plan_error(
                    plan_path,
                    f"Run plan has unsupported generation mode `{generation_mode or 'missing'}`.",
                )
            )
        ai_profile = str(run_shaping.get("ai_profile", "")).strip()
        if ai_profile not in _ALLOWED_AI_PROFILES:
            raise ValueError(
                _prefix_plan_error(
                    plan_path,
                    f"Run plan has unsupported AI profile `{ai_profile or 'missing'}`.",
                )
            )
    semantic_mode = str(run_shaping.get("semantic_mode", "")).strip()
    if semantic_mode not in _ALLOWED_SEMANTIC_MODES:
        raise ValueError(
            _prefix_plan_error(
                plan_path,
                f"Run plan has unsupported semantic mode `{semantic_mode or 'missing'}`.",
            )
        )
    if workflow_type != "audit":
        _ensure_bounded_int(
            run_shaping.get("scenario_count"),
            field_name="run_shaping.scenario_count",
            minimum=1,
            maximum=5,
            plan_path=plan_path,
        )
        _ensure_optional_bounded_int(
            run_shaping.get("population_size"),
            field_name="run_shaping.population_size",
            minimum=4,
            maximum=16,
            plan_path=plan_path,
        )
        _ensure_optional_bounded_int(
            run_shaping.get("population_candidate_count"),
            field_name="run_shaping.population_candidate_count",
            minimum=4,
            maximum=32,
            plan_path=plan_path,
        )
    _ensure_bounded_int(
        run_shaping.get("seed"),
        field_name="run_shaping.seed",
        minimum=0,
        maximum=10_000_000,
        plan_path=plan_path,
    )
    if workflow_type == "compare":
        policy_mode = str(run_shaping.get("policy_mode", "")).strip()
        if policy_mode not in {"default", "report_only"}:
            raise ValueError(
                _prefix_plan_error(
                    plan_path,
                    f"Run plan has unsupported compare policy mode `{policy_mode or 'missing'}`.",
                )
            )
        _ensure_bounded_int(
            run_shaping.get("rerun_count"),
            field_name="run_shaping.rerun_count",
            minimum=1,
            maximum=5,
            plan_path=plan_path,
        )


def _semantic_advisory_payload(
    payload: dict[str, Any],
    *,
    plan_path: str,
) -> dict[str, Any]:
    raw = payload.get("semantic_advisory")
    if isinstance(raw, dict):
        return raw
    run_shaping = _require_mapping(payload, "run_shaping", plan_path=plan_path)
    planned_artifacts = _require_mapping(payload, "planned_artifacts", plan_path=plan_path)
    semantic_mode = str(run_shaping.get("semantic_mode", "off"))
    return {
        "role": "advisory_judge",
        "enabled": semantic_mode != "off",
        "gating": "advisory_only",
        "mode": semantic_mode,
        "model": _optional_str(run_shaping.get("semantic_model")) or "",
        "profile": str(run_shaping.get("semantic_profile", "")),
        "decision_origin": (
            "explicit_user_input"
            if _has_explicit_semantic_inputs(payload)
            else "planner_selected_default"
        ),
        "artifact_path": str(planned_artifacts.get("semantic_advisory_path", "")),
        "rationale": (
            "Loaded legacy run plan without a dedicated semantic advisory section."
            if semantic_mode != "off"
            else "Semantic advisory disabled."
        ),
    }


def _has_explicit_semantic_inputs(payload: dict[str, Any]) -> bool:
    explicit_inputs = payload.get("explicit_user_inputs", {})
    if not isinstance(explicit_inputs, dict):
        return False
    return any(
        key in explicit_inputs
        for key in ("semantic_mode", "semantic_model", "semantic_profile")
    )


def _validate_semantic_advisory(
    semantic_advisory: dict[str, Any],
    *,
    run_shaping: dict[str, Any],
    plan_path: str,
) -> None:
    role = str(semantic_advisory.get("role", "")).strip()
    if role != "advisory_judge":
        raise ValueError(
            _prefix_plan_error(
                plan_path,
                f"Run plan has unsupported semantic advisory role `{role or 'missing'}`.",
            )
        )
    gating = str(semantic_advisory.get("gating", "")).strip()
    if gating != "advisory_only":
        raise ValueError(
            _prefix_plan_error(
                plan_path,
                "Run plan semantic advisory gating must be `advisory_only`.",
            )
        )
    if not isinstance(semantic_advisory.get("enabled"), bool):
        raise ValueError(
            _prefix_plan_error(
                plan_path,
                "Run plan semantic advisory `enabled` must be a boolean.",
            )
        )
    mode = str(semantic_advisory.get("mode", "")).strip()
    if mode not in _ALLOWED_SEMANTIC_MODES:
        raise ValueError(
            _prefix_plan_error(
                plan_path,
                f"Run plan has unsupported semantic advisory mode `{mode or 'missing'}`.",
            )
        )
    decision_origin = str(semantic_advisory.get("decision_origin", "")).strip()
    if decision_origin not in {
        "explicit_user_input",
        "planner_selected_default",
        "planner_selected_provider",
    }:
        raise ValueError(
            _prefix_plan_error(
                plan_path,
                "Run plan has unsupported semantic advisory decision origin "
                f"`{decision_origin or 'missing'}`.",
            )
        )
    if mode != str(run_shaping.get("semantic_mode", "")).strip():
        raise ValueError(
            _prefix_plan_error(
                plan_path,
                "Run plan semantic advisory mode must match run_shaping.semantic_mode.",
            )
        )


def _validate_coverage_intent(
    *,
    scenario_intent: dict[str, Any],
    swarm_intent: dict[str, Any],
    workflow_type: str,
    plan_path: str,
) -> None:
    scenario_decision = str(scenario_intent.get("decision", "")).strip()
    if scenario_decision not in _ALLOWED_SCENARIO_ACTIONS:
        raise ValueError(
            _prefix_plan_error(
                plan_path,
                f"Run plan has unsupported scenario coverage decision `{scenario_decision or 'missing'}`.",
            )
        )
    swarm_decision = str(swarm_intent.get("decision", "")).strip()
    if swarm_decision not in _ALLOWED_SWARM_ACTIONS:
        raise ValueError(
            _prefix_plan_error(
                plan_path,
                f"Run plan has unsupported swarm coverage decision `{swarm_decision or 'missing'}`.",
            )
        )
    if workflow_type == "run-swarm":
        if scenario_decision.startswith("use_built_in") or swarm_decision.startswith("use_built_in"):
            raise ValueError(
                _prefix_plan_error(
                    plan_path,
                    "`run-swarm` plans cannot use built-in compare coverage decisions.",
                )
            )
    if workflow_type == "audit":
        if scenario_decision not in {"explicit_reuse", "use_built_in_scenarios"}:
            raise ValueError(
                _prefix_plan_error(
                    plan_path,
                    "Audit plans may only use explicit scenario-pack reuse or built-in scenarios.",
                )
            )
        if swarm_decision not in {"explicit_reuse", "use_built_in_population"}:
            raise ValueError(
                _prefix_plan_error(
                    plan_path,
                    "Audit plans may only use explicit swarm-pack reuse or built-in population.",
                )
            )
    if workflow_type in {"compare", "audit"}:
        built_in_selection = str(scenario_intent.get("built_in_selection", "")).strip()
        if scenario_decision == "use_built_in_scenarios" and not built_in_selection:
            raise ValueError(
                _prefix_plan_error(
                    plan_path,
                    f"{workflow_type} plans using built-in scenarios must include `built_in_selection`.",
                )
            )


def _validate_artifact_intent(
    *,
    planned_artifacts: dict[str, Any],
    scenario_intent: dict[str, Any],
    swarm_intent: dict[str, Any],
    workflow_type: str,
    plan_path: str,
) -> None:
    if not str(planned_artifacts.get("output_dir", "")).strip():
        raise ValueError(_prefix_plan_error(plan_path, "Run plan is missing `planned_artifacts.output_dir`."))
    if not str(planned_artifacts.get("run_manifest_path", "")).strip():
        raise ValueError(
            _prefix_plan_error(plan_path, "Run plan is missing `planned_artifacts.run_manifest_path`.")
        )
    scenario_path = _optional_str(planned_artifacts.get("scenario_pack_path"))
    population_path = _optional_str(planned_artifacts.get("population_pack_path"))
    scenario_decision = str(scenario_intent.get("decision", ""))
    swarm_decision = str(swarm_intent.get("decision", ""))
    if workflow_type == "run-swarm":
        if scenario_decision != "use_built_in_scenarios" and not scenario_path:
            raise ValueError(
                _prefix_plan_error(
                    plan_path,
                    "Run plan is missing `planned_artifacts.scenario_pack_path` for run-swarm coverage.",
                )
            )
        if swarm_decision != "use_built_in_population" and not population_path:
            raise ValueError(
                _prefix_plan_error(
                    plan_path,
                    "Run plan is missing `planned_artifacts.population_pack_path` for run-swarm coverage.",
                )
            )
    if scenario_decision in {"explicit_reuse", "planner_reuse_existing"} and not scenario_path:
        raise ValueError(
            _prefix_plan_error(
                plan_path,
                "Run plan requests scenario-pack reuse but does not include a scenario pack path.",
            )
        )
    if swarm_decision in {"explicit_reuse", "planner_reuse_existing"} and not population_path:
        raise ValueError(
            _prefix_plan_error(
                plan_path,
                "Run plan requests swarm-pack reuse but does not include a population pack path.",
            )
        )


def _validate_direct_target(
    target: dict[str, Any],
    *,
    workflow_type: str,
    plan_path: str,
) -> None:
    service_mode = str(target.get("service_mode", "")).strip()
    if service_mode not in {"reference", "mock"}:
        raise ValueError(
            _prefix_plan_error(
                plan_path,
                f"Run plan has unsupported {workflow_type} service mode `{service_mode or 'missing'}`.",
            )
        )


def _validate_compare_target(
    target: dict[str, Any],
    *,
    side_name: str,
    plan_path: str,
) -> None:
    mode = str(target.get("mode", "")).strip()
    if mode not in {"reference_artifact", "external_url"}:
        raise ValueError(
            _prefix_plan_error(
                plan_path,
                f"Run plan has unsupported compare target mode `{mode or 'missing'}` for `{side_name}`.",
            )
        )
    if not str(target.get("label", "")).strip():
        raise ValueError(
            _prefix_plan_error(
                plan_path,
                f"Run plan is missing compare target label for `{side_name}`.",
            )
        )


def _validate_planner_metadata(planner: dict[str, Any], *, plan_path: str) -> None:
    role = str(planner.get("role", "")).strip()
    if not role:
        raise ValueError(_prefix_plan_error(plan_path, "Run plan is missing `planner.role`."))
    mode = str(planner.get("mode", "")).strip()
    if mode not in {"deterministic", "provider"}:
        raise ValueError(
            _prefix_plan_error(
                plan_path,
                f"Run plan has unsupported planner mode `{mode or 'missing'}`.",
            )
        )


def _require_mapping(
    payload: dict[str, Any],
    key: str,
    *,
    plan_path: str,
) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(
            _prefix_plan_error(plan_path, f"Run plan field `{key}` must be a JSON object.")
        )
    return value


def _ensure_bounded_int(
    value: Any,
    *,
    field_name: str,
    minimum: int,
    maximum: int,
    plan_path: str,
) -> None:
    if not isinstance(value, int) or value < minimum or value > maximum:
        raise ValueError(
            _prefix_plan_error(
                plan_path,
                f"Run plan field `{field_name}` must be an integer between {minimum} and {maximum}.",
            )
        )


def _ensure_optional_bounded_int(
    value: Any,
    *,
    field_name: str,
    minimum: int,
    maximum: int,
    plan_path: str,
) -> None:
    if value in (None, ""):
        return
    _ensure_bounded_int(
        value,
        field_name=field_name,
        minimum=minimum,
        maximum=maximum,
        plan_path=plan_path,
    )


def _prefix_plan_error(plan_path: str, message: str) -> str:
    if not plan_path:
        return message
    return f"Run plan `{plan_path}` is invalid: {message}"


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _build_plan_id(*, workflow_type: str, domain: str, brief: str) -> str:
    digest = sha1(
        json.dumps(
            {
                "workflow_type": workflow_type,
                "domain": domain,
                "brief": brief,
                "generated_at_utc": _now_utc(),
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:12]
    return f"{workflow_type}-{domain}-{digest}"


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
