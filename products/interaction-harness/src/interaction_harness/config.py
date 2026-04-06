"""Default run configuration for the interaction harness."""

from __future__ import annotations

import re
from pathlib import Path

from .agents.recommender import build_seeded_archetypes
from .recommender_inputs import resolve_recommender_inputs
from .schema import AgentSeed, RolloutConfig, RunConfig, ScenarioConfig, ScoringConfig
from .services.reference_artifacts import DEFAULT_REFERENCE_ARTIFACT_DIR

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
    """Build the default single-run config for the recommender harness."""
    resolved_run_name = run_name or DEFAULT_RUN_NAME
    if scenarios is not None and scenario_names is not None:
        raise ValueError("scenario_names cannot be combined with explicit scenarios.")
    resolved_scenarios = scenarios or resolve_recommender_inputs(
        scenario_names=scenario_names,
    ).scenarios
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
    resolved_agent_seeds = agent_seeds or build_seeded_archetypes()
    return RunConfig(
        run_name=resolved_run_name,
        scenarios=resolved_scenarios,
        rollout=rollout,
        scoring=ScoringConfig(),
        agent_seeds=resolved_agent_seeds,
    )
