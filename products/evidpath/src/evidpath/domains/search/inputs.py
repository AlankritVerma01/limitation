"""Runtime input resolution for the search domain."""

from __future__ import annotations

from ...domains.base import ResolvedRuntimeInputs
from ...schema import AgentSeed, ScenarioConfig
from .policy import build_seeded_search_archetypes
from .scenarios import resolve_built_in_search_scenarios


def resolve_search_inputs(
    *,
    scenario_names: tuple[str, ...] | None = None,
    scenario_pack_path: str | None = None,
    population_pack_path: str | None = None,
) -> ResolvedRuntimeInputs:
    """Resolve search runtime inputs from built-ins and seeded personas."""
    if scenario_pack_path is not None:
        raise ValueError("Search scenario packs are not supported yet.")
    if population_pack_path is not None:
        raise ValueError("Search population packs are not supported yet.")
    scenarios = resolve_built_in_search_scenarios(scenario_names)
    agent_seeds = build_seeded_search_archetypes()
    return ResolvedRuntimeInputs(
        scenarios=scenarios,
        agent_seeds=agent_seeds,
        metadata={
            "scenario_source": "built_in",
            "scenario_count": len(scenarios),
            "population_source": "built_in_seeds",
            "population_pack_size": len(agent_seeds),
            "population_target_size": len(agent_seeds),
            "population_size_source": "built_in",
        },
    )


def project_search_scenarios(_pack) -> tuple[ScenarioConfig, ...]:
    """Reject generated search scenario packs until search generation is specified."""
    raise ValueError("Search scenario packs are not supported yet.")


def project_search_population(_pack) -> tuple[AgentSeed, ...]:
    """Reject generated search population packs until search generation is specified."""
    raise ValueError("Search population packs are not supported yet.")
