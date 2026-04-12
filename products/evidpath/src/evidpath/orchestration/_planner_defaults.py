"""Default-setting helpers for bounded workflow planning."""

from __future__ import annotations

from typing import Any

from ..generation_support import provider_credentials_available, resolve_provider_model
from ._planner_support import optional_str


def default_generation_ai_profile(
    *,
    generation_mode: str,
    explicit_inputs: dict[str, Any],
    fallback_profile: str,
) -> str:
    if "ai_profile" in explicit_inputs:
        return str(explicit_inputs["ai_profile"])
    if generation_mode == "provider":
        return "balanced"
    return fallback_profile


def default_audit_semantic_settings(
    *,
    explicit_inputs: dict[str, Any],
    fallback_mode: str,
    fallback_model: str | None,
    fallback_profile: str,
) -> dict[str, str]:
    if "semantic_mode" in explicit_inputs:
        explicit_mode = str(explicit_inputs["semantic_mode"])
        return {
            "semantic_mode": explicit_mode,
            "semantic_model": str(explicit_inputs.get("semantic_model") or fallback_model or ""),
            "semantic_profile": str(explicit_inputs.get("semantic_profile") or fallback_profile),
        }
    if fallback_mode not in {"", "off"}:
        return {
            "semantic_mode": fallback_mode,
            "semantic_model": fallback_model or "",
            "semantic_profile": fallback_profile,
        }
    return {
        "semantic_mode": "fixture",
        "semantic_model": "",
        "semantic_profile": str(explicit_inputs.get("semantic_profile") or "fast"),
    }


def default_semantic_settings(
    *,
    generation_mode: str,
    explicit_inputs: dict[str, Any],
    fallback_mode: str,
    fallback_model: str | None,
    fallback_profile: str,
) -> dict[str, str]:
    if "semantic_mode" in explicit_inputs:
        explicit_mode = str(explicit_inputs["semantic_mode"])
        return {
            "semantic_mode": explicit_mode,
            "semantic_model": str(explicit_inputs.get("semantic_model") or fallback_model or ""),
            "semantic_profile": str(explicit_inputs.get("semantic_profile") or fallback_profile),
        }
    if generation_mode == "provider" and provider_credentials_available():
        profile = str(explicit_inputs.get("semantic_profile") or "balanced")
        model_name, _ = resolve_provider_model(
            purpose="semantic_interpretation",
            explicit_model_name=optional_str(explicit_inputs.get("semantic_model"))
            or fallback_model,
            profile_name=profile,
        )
        return {
            "semantic_mode": "provider",
            "semantic_model": model_name,
            "semantic_profile": profile,
        }
    if generation_mode == "fixture":
        return {
            "semantic_mode": "fixture",
            "semantic_model": "",
            "semantic_profile": str(explicit_inputs.get("semantic_profile") or "fast"),
        }
    if fallback_mode != "off":
        return {
            "semantic_mode": fallback_mode,
            "semantic_model": fallback_model or "",
            "semantic_profile": fallback_profile,
        }
    return {
        "semantic_mode": "fixture",
        "semantic_model": "",
        "semantic_profile": str(explicit_inputs.get("semantic_profile") or "fast"),
    }


def build_semantic_advisory(
    *,
    explicit_inputs: dict[str, Any],
    planner_mode: str,
    semantic_mode: str,
    semantic_model: str | None,
    semantic_profile: str,
    artifact_path: str,
) -> dict[str, object]:
    explicit = any(
        key in explicit_inputs
        for key in ("semantic_mode", "semantic_model", "semantic_profile")
    )
    if explicit:
        origin = "explicit_user_input"
        rationale = "Semantic advisory settings came from explicit user inputs."
    elif planner_mode == "provider":
        origin = "planner_selected_provider"
        rationale = "Provider-backed planning selected the advisory semantic step."
    else:
        origin = "planner_selected_default"
        rationale = "Deterministic planning selected the advisory semantic step."
    return {
        "role": "advisory_judge",
        "enabled": semantic_mode != "off",
        "gating": "advisory_only",
        "mode": semantic_mode,
        "model": semantic_model or "",
        "profile": semantic_profile,
        "decision_origin": origin,
        "artifact_path": artifact_path,
        "rationale": (
            rationale if semantic_mode != "off" else "Semantic advisory disabled by plan."
        ),
    }
