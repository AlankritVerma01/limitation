"""Run configuration builders for the interaction harness."""

from __future__ import annotations

import re
from pathlib import Path

from .domains.base import ResolvedRuntimeInputs
from .domains.recommender.reference_artifacts import DEFAULT_REFERENCE_ARTIFACT_DIR
from .schema import AgentSeed, RolloutConfig, RunConfig, ScenarioConfig, ScoringConfig

DEFAULT_OUTPUT_DIR = (
    Path(__file__).resolve().parents[4] / "products" / "interaction-harness" / "output"
)
DEFAULT_RUN_NAME = "interaction-harness-audit"


def slugify_name(value: str) -> str:
    """Return a filesystem-friendly slug for run and label names."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "run"


def build_default_run_config(
    seed: int = 0,
    output_dir: str | None = None,
    scenario_names: tuple[str, ...] | None = None,
    scenarios: tuple[ScenarioConfig, ...] | None = None,
    agent_seeds: tuple[AgentSeed, ...] | None = None,
    service_mode: str = "reference",
    service_artifact_dir: str | None = None,
    adapter_base_url: str | None = None,
    run_name: str | None = None,
) -> RunConfig:
    """Build the compatibility default single-run config for the recommender harness."""
    from .domains.recommender.inputs import resolve_recommender_inputs
    from .domains.recommender.policy import build_seeded_archetypes

    if scenarios is not None and scenario_names is not None:
        raise ValueError("scenario_names cannot be combined with explicit scenarios.")
    if scenarios is not None or agent_seeds is not None:
        return build_run_config(
            seed=seed,
            output_dir=output_dir,
            scenarios=scenarios or resolve_recommender_inputs(scenario_names=scenario_names).scenarios,
            agent_seeds=agent_seeds or build_seeded_archetypes(),
            service_mode=service_mode,
            service_artifact_dir=service_artifact_dir,
            adapter_base_url=adapter_base_url,
            run_name=run_name,
        )
    run_config, _resolved_inputs = build_recommender_run_config(
        seed=seed,
        output_dir=output_dir,
        scenario_names=scenario_names,
        service_mode=service_mode,
        service_artifact_dir=service_artifact_dir,
        adapter_base_url=adapter_base_url,
        run_name=run_name,
    )
    return run_config


def build_run_config(
    *,
    seed: int = 0,
    output_dir: str | None = None,
    scenarios: tuple[ScenarioConfig, ...],
    agent_seeds: tuple[AgentSeed, ...],
    service_mode: str = "reference",
    service_artifact_dir: str | None = None,
    adapter_base_url: str | None = None,
    run_name: str | None = None,
) -> RunConfig:
    """Build a run config from explicit runtime inputs without domain defaulting."""
    resolved_run_name = run_name or DEFAULT_RUN_NAME
    rollout = RolloutConfig(
        seed=seed,
        output_dir=str(
            output_dir
            or DEFAULT_OUTPUT_DIR / slugify_name(resolved_run_name) / f"seed-{seed}"
        ),
        service_mode=service_mode,
        service_artifact_dir=(
            str(service_artifact_dir or DEFAULT_REFERENCE_ARTIFACT_DIR)
            if service_mode == "reference"
            else service_artifact_dir
        ),
        adapter_base_url=adapter_base_url,
        service_timeout_seconds=2.0,
    )
    return RunConfig(
        run_name=resolved_run_name,
        scenarios=scenarios,
        rollout=rollout,
        scoring=ScoringConfig(),
        agent_seeds=agent_seeds,
    )


def build_recommender_run_config(
    *,
    seed: int = 0,
    output_dir: str | None = None,
    scenario_names: tuple[str, ...] | None = None,
    scenario_pack_path: str | None = None,
    population_pack_path: str | None = None,
    service_mode: str = "reference",
    service_artifact_dir: str | None = None,
    adapter_base_url: str | None = None,
    run_name: str | None = None,
) -> tuple[RunConfig, ResolvedRuntimeInputs]:
    """Compatibility wrapper for the recommender-owned run-config builder."""
    from .domains.recommender.definition import (
        build_recommender_run_config as _build_recommender_run_config,
    )

    return _build_recommender_run_config(
        seed=seed,
        output_dir=output_dir,
        scenario_names=scenario_names,
        scenario_pack_path=scenario_pack_path,
        population_pack_path=population_pack_path,
        service_mode=service_mode,
        service_artifact_dir=service_artifact_dir,
        adapter_base_url=adapter_base_url,
        run_name=run_name,
    )
