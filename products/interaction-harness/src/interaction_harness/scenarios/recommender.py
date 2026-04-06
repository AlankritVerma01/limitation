"""Transitional compatibility shim for recommender scenario helpers.

The real implementation now lives in `interaction_harness.domains.recommender`.
This shim is retained for one cleanup phase so older imports keep working while
the recommender domain package becomes the primary ownership path.
"""

from __future__ import annotations

from ..domains.recommender.scenarios import (
    BUILT_IN_RECOMMENDER_SCENARIO_CONFIGS,
    BUILT_IN_RECOMMENDER_SCENARIO_NAMES,
    build_scenarios,
    resolve_built_in_recommender_scenarios,
)

__all__ = [
    "BUILT_IN_RECOMMENDER_SCENARIO_CONFIGS",
    "BUILT_IN_RECOMMENDER_SCENARIO_NAMES",
    "build_scenarios",
    "resolve_built_in_recommender_scenarios",
]
