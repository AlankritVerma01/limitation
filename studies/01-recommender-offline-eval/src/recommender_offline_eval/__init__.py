"""Public package surface for the recommender evaluation tool."""

from .config import DatasetSpec, EvaluationConfig, ModelSpec, load_evaluation_config
from .run_demo import (
    refresh_canonical_artifacts,
    run_canonical_demo,
    run_evaluation,
)

__all__ = [
    "DatasetSpec",
    "EvaluationConfig",
    "ModelSpec",
    "load_evaluation_config",
    "run_canonical_demo",
    "run_evaluation",
    "refresh_canonical_artifacts",
]
