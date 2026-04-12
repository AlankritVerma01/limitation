"""Generic run configuration builders for Evidpath."""

from __future__ import annotations

import re
from pathlib import Path

from .schema import AgentSeed, RolloutConfig, RunConfig, ScenarioConfig, ScoringConfig

DEFAULT_OUTPUT_DIR = (
    Path(__file__).resolve().parents[4] / "products" / "evidpath" / "output"
)
DEFAULT_RUN_NAME = "evidpath-audit"


def slugify_name(value: str) -> str:
    """Return a filesystem-friendly slug for run and label names."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "run"


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
        service_artifact_dir=service_artifact_dir,
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
