"""Shared pre-run planning artifacts and bounded orchestration helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any

from .config import DEFAULT_OUTPUT_DIR
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
