"""Shared pre-run plan contract, loading, and validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any

from ..config import DEFAULT_OUTPUT_DIR
from ..domain_registry import list_public_domain_definitions
from .constants import (
    ALLOWED_AI_PROFILES,
    ALLOWED_GENERATION_MODES,
    ALLOWED_SCENARIO_ACTIONS,
    ALLOWED_SEMANTIC_MODES,
    ALLOWED_SWARM_ACTIONS,
    ALLOWED_WORKFLOW_TYPES,
    RUN_PLAN_CONTRACT_VERSION,
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
    if workflow_type not in ALLOWED_WORKFLOW_TYPES:
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
        if generation_mode not in ALLOWED_GENERATION_MODES:
            raise ValueError(
                _prefix_plan_error(
                    plan_path,
                    f"Run plan has unsupported generation mode `{generation_mode or 'missing'}`.",
                )
            )
        ai_profile = str(run_shaping.get("ai_profile", "")).strip()
        if ai_profile not in ALLOWED_AI_PROFILES:
            raise ValueError(
                _prefix_plan_error(
                    plan_path,
                    f"Run plan has unsupported AI profile `{ai_profile or 'missing'}`.",
                )
            )
    semantic_mode = str(run_shaping.get("semantic_mode", "")).strip()
    if semantic_mode not in ALLOWED_SEMANTIC_MODES:
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
    if mode not in ALLOWED_SEMANTIC_MODES:
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
    if scenario_decision not in ALLOWED_SCENARIO_ACTIONS:
        raise ValueError(
            _prefix_plan_error(
                plan_path,
                f"Run plan has unsupported scenario coverage decision `{scenario_decision or 'missing'}`.",
            )
        )
    swarm_decision = str(swarm_intent.get("decision", "")).strip()
    if swarm_decision not in ALLOWED_SWARM_ACTIONS:
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
