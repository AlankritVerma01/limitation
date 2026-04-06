"""Recommender-specific input resolution for runs and generated artifacts."""

from __future__ import annotations

from .agents.recommender import build_seeded_archetypes
from .domains.base import ResolvedRuntimeInputs
from .population_generation import load_population_pack, project_recommender_population
from .scenario_generation import load_scenario_pack, project_recommender_scenarios
from .scenarios.recommender import resolve_built_in_recommender_scenarios
from .schema import AgentSeed, ScenarioConfig


def resolve_recommender_inputs(
    *,
    scenario_names: tuple[str, ...] | None = None,
    scenario_pack_path: str | None = None,
    population_pack_path: str | None = None,
) -> ResolvedRuntimeInputs:
    """Resolve recommender runtime inputs from built-ins and saved packs."""
    scenarios, scenario_metadata = _resolve_scenarios(
        scenario_names=scenario_names,
        scenario_pack_path=scenario_pack_path,
    )
    agent_seeds, population_metadata = _resolve_population(
        population_pack_path=population_pack_path,
    )
    return ResolvedRuntimeInputs(
        scenarios=scenarios,
        agent_seeds=agent_seeds,
        metadata={**scenario_metadata, **population_metadata},
    )


def _resolve_scenarios(
    *,
    scenario_names: tuple[str, ...] | None,
    scenario_pack_path: str | None,
) -> tuple[tuple[ScenarioConfig, ...], dict[str, str]]:
    """Resolve recommender scenarios from built-ins or a saved scenario pack."""
    if scenario_pack_path is not None:
        if scenario_names is not None:
            raise ValueError(
                "scenario_names cannot be combined with scenario_pack_path in a single recommender run."
            )
        pack = load_scenario_pack(scenario_pack_path)
        return (
            project_recommender_scenarios(pack),
            {
                "scenario_source": "generated_pack",
                "scenario_pack_id": pack.metadata.pack_id,
                "scenario_pack_mode": pack.metadata.generator_mode,
                "scenario_pack_domain": pack.metadata.domain_label,
                "scenario_count": len(pack.scenarios),
                "scenario_pack_path": scenario_pack_path,
            },
        )
    scenarios = resolve_built_in_recommender_scenarios(scenario_names)
    return scenarios, {
        "scenario_source": "built_in",
        "scenario_count": len(scenarios),
    }


def _resolve_population(
    *,
    population_pack_path: str | None,
) -> tuple[tuple[AgentSeed, ...], dict[str, str | int]]:
    """Resolve recommender runtime personas from built-ins or a saved population pack."""
    if population_pack_path is None:
        built_in = build_seeded_archetypes()
        return built_in, {
            "population_source": "built_in_seeds",
            "population_pack_size": len(built_in),
            "population_target_size": len(built_in),
            "population_size_source": "built_in",
        }
    pack = load_population_pack(population_pack_path)
    return (
        project_recommender_population(pack),
        {
            "population_source": "generated_pack",
            "population_pack_id": pack.metadata.pack_id,
            "population_pack_mode": pack.metadata.generator_mode,
            "population_pack_domain": pack.metadata.domain_label,
            "population_pack_size": pack.metadata.selected_count,
            "population_target_size": pack.metadata.target_population_size,
            "population_pack_candidate_count": pack.metadata.candidate_count,
            "population_size_source": pack.metadata.population_size_source,
            "population_pack_path": population_pack_path,
        },
    )
