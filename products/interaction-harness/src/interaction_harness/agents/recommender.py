"""Transitional compatibility shim for the recommender policy module.

The real implementation now lives in `interaction_harness.domains.recommender`.
This shim is retained for one cleanup phase so older imports keep working while
the recommender domain package becomes the primary ownership path.
"""

from __future__ import annotations

from ..domains.recommender.policy import (
    CandidateEvaluation,
    RecommenderAgentPolicy,
    build_seeded_archetypes,
    initial_state_from_seed,
    normalize_runtime_item_signals,
)

__all__ = [
    "CandidateEvaluation",
    "RecommenderAgentPolicy",
    "build_seeded_archetypes",
    "initial_state_from_seed",
    "normalize_runtime_item_signals",
]
