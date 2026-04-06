"""Recommender domain package.

This package is the first full cross-cutting domain implementation for the
interaction harness. Shared orchestration should depend on the definition and
helpers exported here rather than on scattered recommender-owned modules.
"""

from .definition import build_recommender_domain_definition
from .inputs import (
    project_recommender_population,
    project_recommender_scenarios,
    resolve_recommender_inputs,
)
from .policy import RecommenderAgentPolicy, build_seeded_archetypes
from .scenarios import (
    BUILT_IN_RECOMMENDER_SCENARIO_CONFIGS,
    BUILT_IN_RECOMMENDER_SCENARIO_NAMES,
    BUILT_IN_RECOMMENDER_SCENARIOS,
    RecommenderScenario,
    build_scenarios,
    resolve_built_in_recommender_scenarios,
)

__all__ = [
    "BUILT_IN_RECOMMENDER_SCENARIO_CONFIGS",
    "BUILT_IN_RECOMMENDER_SCENARIOS",
    "BUILT_IN_RECOMMENDER_SCENARIO_NAMES",
    "RecommenderAgentPolicy",
    "RecommenderScenario",
    "build_recommender_domain_definition",
    "build_scenarios",
    "build_seeded_archetypes",
    "project_recommender_population",
    "project_recommender_scenarios",
    "resolve_built_in_recommender_scenarios",
    "resolve_recommender_inputs",
]
