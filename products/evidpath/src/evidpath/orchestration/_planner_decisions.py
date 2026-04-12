"""Decision-making helpers for deterministic and provider-backed planning."""

from __future__ import annotations

import json
import os
from typing import Any

from ..generation_support import (
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
from ._planner_support import optional_str


def plan_decisions(
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
    summary = (
        "Deterministic planner preserved explicit inputs and reused existing artifacts "
        "when available."
    )
    if workflow_type == "compare" and not brief.strip():
        summary = (
            "Deterministic planner kept compare on built-in coverage because no shared "
            "brief was provided."
        )
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
        else (optional_str(parsed.get("semantic_model")) or semantic_model)
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
        "Choose compact, launch-grade coverage.\n"
        "Treat semantic advisory as a first-class planned step that always stays advisory-only.\n"
        "When semantic inputs are not explicit, prefer `provider` when safely available, otherwise `fixture`; avoid `off`.\n"
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
        allowed.add(
            "use_built_in_scenarios"
            if field_name == "scenario_action"
            else "use_built_in_population"
        )
    if action not in allowed:
        raise ValueError(f"Provider planner returned unsupported {field_name} `{action}`.")
    if action == "planner_reuse_existing" and not available:
        raise ValueError(
            f"Provider planner requested reuse for `{field_name}` but no artifact exists."
        )
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
    if value.strip() == "off" and default != "off":
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
