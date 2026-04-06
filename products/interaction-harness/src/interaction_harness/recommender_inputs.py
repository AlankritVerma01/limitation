"""Transitional compatibility shim for recommender runtime input resolution."""

from __future__ import annotations

from .domains.recommender.inputs import (
    project_recommender_population,
    project_recommender_scenarios,
    resolve_recommender_inputs,
)

__all__ = [
    "project_recommender_population",
    "project_recommender_scenarios",
    "resolve_recommender_inputs",
]
