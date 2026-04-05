"""Default run configuration for the interaction harness."""

from __future__ import annotations

import re
from pathlib import Path

from .agents.recommender import build_seeded_archetypes
from .schema import RolloutConfig, RunConfig, ScenarioConfig, ScoringConfig
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
    service_mode: str = "reference",
    service_artifact_dir: str | None = None,
    adapter_base_url: str | None = None,
    run_name: str | None = None,
) -> RunConfig:
    """Build the default single-run config for the recommender harness."""
    resolved_run_name = run_name or DEFAULT_RUN_NAME
    selected = scenario_names or (
        "returning-user-home-feed",
        "sparse-history-home-feed",
    )
    scenario_map = {
        "returning-user-home-feed": ScenarioConfig(
            name="returning-user-home-feed",
            max_steps=5,
            allowed_actions=("click", "skip", "abandon"),
            history_depth=4,
            description="Returning user home-feed session with meaningful prior history.",
        ),
        "sparse-history-home-feed": ScenarioConfig(
            name="sparse-history-home-feed",
            max_steps=5,
            allowed_actions=("click", "skip", "abandon"),
            history_depth=1,
            description="Sparse-history home-feed session with limited prior behavior.",
        ),
    }
    unknown_scenarios = sorted(set(selected).difference(scenario_map))
    if unknown_scenarios:
        raise ValueError(
            f"Unknown scenario names: {', '.join(unknown_scenarios)}."
        )
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
        scenarios=tuple(scenario_map[name] for name in selected),
        rollout=rollout,
        scoring=ScoringConfig(),
        agent_seeds=build_seeded_archetypes(),
    )
