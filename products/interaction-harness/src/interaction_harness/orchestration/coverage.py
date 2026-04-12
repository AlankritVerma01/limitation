"""Shared coverage resolution helpers for planned workflows."""

from __future__ import annotations

from pathlib import Path

from ..cli_progress import ProgressCallback, emit_progress
from ..population_generation import (
    build_default_population_pack_path,
    generate_population_pack,
    write_population_pack,
)
from ..scenario_generation import (
    build_default_scenario_pack_path,
    generate_scenario_pack,
    write_scenario_pack,
)


def ensure_reused_artifact(path: str | None, *, label: str) -> None:
    """Fail clearly when a saved plan expects a reusable artifact that is missing."""
    resolved = optional_text(path)
    if not resolved:
        raise SystemExit(f"Saved plan requires a {label}, but no path was provided.")
    if not Path(resolved).exists():
        raise SystemExit(
            f"Saved plan requires {label} at `{resolved}`, but that path does not exist."
        )


def resolve_run_swarm_packs(
    *,
    brief: str,
    explicit_scenario_pack_path: str | None,
    explicit_population_pack_path: str | None,
    domain_name: str,
    output_root: str,
    generation_mode: str,
    scenario_action: str,
    population_action: str,
    ai_profile: str,
    scenario_count: int | None,
    population_size: int | None,
    population_candidate_count: int | None,
    planned_scenario_pack_path: str | None,
    planned_population_pack_path: str | None,
    progress_callback: ProgressCallback | None = None,
) -> tuple[str, str, str, str, str]:
    scenario_pack_path = optional_text(explicit_scenario_pack_path)
    population_pack_path = optional_text(explicit_population_pack_path)
    generated_any = False
    reused_any = False
    scenario_generation_mode = "reused" if scenario_pack_path is not None else (
        "planner-reused" if scenario_action == "planner_reuse_existing" else generation_mode
    )
    swarm_generation_mode = "reused" if population_pack_path is not None else (
        "planner-reused" if population_action == "planner_reuse_existing" else generation_mode
    )

    if scenario_pack_path is None:
        if scenario_action == "planner_reuse_existing" and planned_scenario_pack_path is not None:
            ensure_reused_artifact(
                planned_scenario_pack_path,
                label="planner-selected scenario pack",
            )
            scenario_pack_path = planned_scenario_pack_path
            emit_progress(
                progress_callback,
                phase="reuse_scenario_pack",
                message="Reusing planner-selected scenario pack",
                stage="finish",
            )
            reused_any = True
        else:
            scenario_pack_path = generate_run_swarm_scenario_pack(
                brief=brief,
                output_root=output_root,
                domain_name=domain_name,
                generation_mode=generation_mode,
                ai_profile=ai_profile,
                scenario_count=scenario_count or 3,
                planned_path=planned_scenario_pack_path,
                progress_callback=progress_callback,
            )
            generated_any = True
    else:
        ensure_reused_artifact(
            scenario_pack_path,
            label="scenario pack",
        )
        emit_progress(
            progress_callback,
            phase="reuse_scenario_pack",
            message="Reusing scenario pack",
            stage="finish",
        )
        reused_any = True

    if population_pack_path is None:
        if population_action == "planner_reuse_existing" and planned_population_pack_path is not None:
            ensure_reused_artifact(
                planned_population_pack_path,
                label="planner-selected swarm pack",
            )
            population_pack_path = planned_population_pack_path
            emit_progress(
                progress_callback,
                phase="reuse_population_pack",
                message="Reusing planner-selected swarm pack",
                stage="finish",
            )
            reused_any = True
        else:
            population_pack_path = generate_run_swarm_population_pack(
                brief=brief,
                output_root=output_root,
                domain_name=domain_name,
                generation_mode=generation_mode,
                ai_profile=ai_profile,
                population_size=population_size,
                population_candidate_count=population_candidate_count,
                planned_path=planned_population_pack_path,
                progress_callback=progress_callback,
            )
            generated_any = True
    else:
        ensure_reused_artifact(
            population_pack_path,
            label="swarm pack",
        )
        emit_progress(
            progress_callback,
            phase="reuse_population_pack",
            message="Reusing swarm pack",
            stage="finish",
        )
        reused_any = True

    if generated_any and reused_any:
        coverage_source = "mixed"
    elif generated_any:
        coverage_source = "generated"
    else:
        coverage_source = "reused"
    return (
        scenario_pack_path,
        population_pack_path,
        coverage_source,
        scenario_generation_mode,
        swarm_generation_mode,
    )


def resolve_compare_planned_coverage(
    *,
    brief: str | None,
    output_root: str,
    domain_name: str,
    generation_mode: str,
    ai_profile: str,
    scenario_count: int,
    population_size: int | None,
    population_candidate_count: int | None,
    scenario_generation_mode: str,
    swarm_generation_mode: str,
    scenario_pack_path: str | None,
    population_pack_path: str | None,
    progress_callback: ProgressCallback | None = None,
) -> tuple[str | None, str | None]:
    if brief:
        if scenario_pack_path is None or population_pack_path is None:
            raise SystemExit("compare planning requires planned shared coverage paths when a brief is provided.")
        if scenario_generation_mode not in {"reused", "planner-reused"}:
            scenario_pack_path = generate_compare_scenario_pack(
                brief=brief,
                output_root=output_root,
                domain_name=domain_name,
                generation_mode=generation_mode,
                ai_profile=ai_profile,
                scenario_count=scenario_count,
                planned_path=scenario_pack_path,
                progress_callback=progress_callback,
            )
        else:
            ensure_reused_artifact(
                scenario_pack_path,
                label="shared compare scenario pack",
            )
            emit_progress(
                progress_callback,
                phase="reuse_scenario_pack",
                message="Reusing shared compare scenario pack",
                stage="finish",
            )
        if swarm_generation_mode not in {"reused", "planner-reused"}:
            population_pack_path = generate_compare_population_pack(
                brief=brief,
                output_root=output_root,
                domain_name=domain_name,
                generation_mode=generation_mode,
                ai_profile=ai_profile,
                population_size=population_size,
                population_candidate_count=population_candidate_count,
                planned_path=population_pack_path,
                progress_callback=progress_callback,
            )
        else:
            ensure_reused_artifact(
                population_pack_path,
                label="shared compare swarm pack",
            )
            emit_progress(
                progress_callback,
                phase="reuse_population_pack",
                message="Reusing shared compare swarm pack",
                stage="finish",
            )
    else:
        if scenario_pack_path is not None:
            ensure_reused_artifact(
                scenario_pack_path,
                label="compare scenario pack",
            )
        if population_pack_path is not None:
            ensure_reused_artifact(
                population_pack_path,
                label="compare swarm pack",
            )
    return scenario_pack_path, population_pack_path


def generate_run_swarm_scenario_pack(
    *,
    brief: str,
    output_root: str,
    domain_name: str,
    generation_mode: str,
    ai_profile: str,
    scenario_count: int,
    planned_path: str | None,
    progress_callback: ProgressCallback | None = None,
) -> str:
    pack = generate_scenario_pack(
        brief,
        generator_mode=generation_mode,
        scenario_count=scenario_count,
        domain_label=domain_name,
        model_profile=ai_profile,
        progress_callback=progress_callback,
    )
    scenario_pack_path = planned_path or build_default_scenario_pack_path(
        output_root,
        brief=brief,
        generator_mode=generation_mode,
    )
    emit_progress(
        progress_callback,
        phase="write_pack",
        message="Writing scenario pack",
        stage="start",
    )
    saved_path = write_scenario_pack(pack, scenario_pack_path)
    emit_progress(
        progress_callback,
        phase="write_pack",
        message="Wrote scenario pack",
        stage="finish",
    )
    return saved_path


def generate_run_swarm_population_pack(
    *,
    brief: str,
    output_root: str,
    domain_name: str,
    generation_mode: str,
    ai_profile: str,
    population_size: int | None,
    population_candidate_count: int | None,
    planned_path: str | None,
    progress_callback: ProgressCallback | None = None,
) -> str:
    pack = generate_population_pack(
        brief,
        generator_mode=generation_mode,
        population_size=population_size,
        candidate_count=population_candidate_count,
        domain_label=domain_name,
        model_profile=ai_profile,
        progress_callback=progress_callback,
    )
    population_pack_path = planned_path or build_default_population_pack_path(
        output_root,
        brief=brief,
        generator_mode=generation_mode,
    )
    emit_progress(
        progress_callback,
        phase="write_pack",
        message="Writing population pack",
        stage="start",
    )
    saved_path = write_population_pack(pack, population_pack_path)
    emit_progress(
        progress_callback,
        phase="write_pack",
        message="Wrote population pack",
        stage="finish",
    )
    return saved_path


def generate_compare_scenario_pack(
    *,
    brief: str,
    output_root: str,
    domain_name: str,
    generation_mode: str,
    ai_profile: str,
    scenario_count: int,
    planned_path: str,
    progress_callback: ProgressCallback | None = None,
) -> str:
    return generate_run_swarm_scenario_pack(
        brief=brief,
        output_root=output_root,
        domain_name=domain_name,
        generation_mode=generation_mode,
        ai_profile=ai_profile,
        scenario_count=scenario_count,
        planned_path=planned_path,
        progress_callback=progress_callback,
    )


def generate_compare_population_pack(
    *,
    brief: str,
    output_root: str,
    domain_name: str,
    generation_mode: str,
    ai_profile: str,
    population_size: int | None,
    population_candidate_count: int | None,
    planned_path: str,
    progress_callback: ProgressCallback | None = None,
) -> str:
    return generate_run_swarm_population_pack(
        brief=brief,
        output_root=output_root,
        domain_name=domain_name,
        generation_mode=generation_mode,
        ai_profile=ai_profile,
        population_size=population_size,
        population_candidate_count=population_candidate_count,
        planned_path=planned_path,
        progress_callback=progress_callback,
    )


def optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
