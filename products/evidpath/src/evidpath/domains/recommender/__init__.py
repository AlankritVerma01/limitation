"""Recommender domain package.

This package is the first full cross-cutting domain implementation for
Evidpath. Shared orchestration should depend on the definition and
helpers exported here rather than on scattered recommender-owned modules.
"""

from .analyzer import RecommenderAnalyzer
from .catalog import CATALOG, history_for_genres
from .definition import (
    build_recommender_domain_definition,
    build_recommender_run_config,
)
from .drivers import HttpNativeDriverConfig, HttpNativeRecommenderDriver
from .inputs import (
    project_recommender_population,
    project_recommender_scenarios,
    resolve_recommender_inputs,
)
from .judge import RecommenderJudge
from .mock_recommender import run_mock_recommender_service
from .policy import (
    RecommenderAgentPolicy,
    build_seeded_archetypes,
    initial_state_from_seed,
    normalize_runtime_item_signals,
)
from .reference_artifacts import (
    ARTIFACT_FILENAME,
    build_reference_artifacts,
    ensure_reference_artifacts,
    load_reference_artifacts,
)
from .reference_recommender import run_reference_recommender_service
from .scenarios import (
    BUILT_IN_RECOMMENDER_SCENARIO_NAMES,
    BUILT_IN_RECOMMENDER_SCENARIOS,
    RecommenderScenario,
    build_scenarios,
    resolve_built_in_recommender_scenarios,
)
from .slices import (
    discover_recommender_slices,
    extract_recommender_slice_features,
)

__all__ = [
    "ARTIFACT_FILENAME",
    "CATALOG",
    "BUILT_IN_RECOMMENDER_SCENARIOS",
    "BUILT_IN_RECOMMENDER_SCENARIO_NAMES",
    "HttpNativeDriverConfig",
    "HttpNativeRecommenderDriver",
    "RecommenderAnalyzer",
    "RecommenderAgentPolicy",
    "RecommenderJudge",
    "RecommenderScenario",
    "build_reference_artifacts",
    "build_recommender_domain_definition",
    "build_recommender_run_config",
    "build_scenarios",
    "build_seeded_archetypes",
    "discover_recommender_slices",
    "ensure_reference_artifacts",
    "extract_recommender_slice_features",
    "history_for_genres",
    "initial_state_from_seed",
    "load_reference_artifacts",
    "normalize_runtime_item_signals",
    "project_recommender_population",
    "project_recommender_scenarios",
    "resolve_built_in_recommender_scenarios",
    "resolve_recommender_inputs",
    "run_mock_recommender_service",
    "run_reference_recommender_service",
]
