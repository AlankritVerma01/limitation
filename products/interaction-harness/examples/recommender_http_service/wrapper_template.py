"""Minimal template for wrapping an existing recommender behind the harness contract.

Replace `score_items` with calls into your own model or ranking pipeline.
The goal is to show the shape a real customer-owned service can take without
teaching the harness to load arbitrary model formats directly.
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field


class RecommendationRequest(BaseModel):
    request_id: str
    agent_id: str
    scenario_name: str
    step_index: int
    history_depth: int
    history_item_ids: list[str] = Field(default_factory=list)
    recent_exposure_ids: list[str] = Field(default_factory=list)
    preferred_genres: list[str] = Field(default_factory=list)
    scenario_profile: str = ""


def create_app() -> FastAPI:
    app = FastAPI(title="Custom Recommender Wrapper Template", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service_kind": "external"}

    @app.get("/metadata")
    def metadata() -> dict[str, str]:
        return {
            "service_kind": "external",
            "backend_name": "MyWrappedRecommender",
            "dataset": "replace-me",
            "model_kind": "replace-me",
            "model_id": "replace-me",
        }

    @app.post("/recommendations")
    def recommendations(payload: RecommendationRequest) -> dict[str, object]:
        items = score_items(payload)
        return {
            "request_id": payload.request_id,
            "items": items,
        }

    return app


def score_items(payload: RecommendationRequest) -> list[dict[str, object]]:
    """Replace this with your actual model or ranking pipeline call."""
    return [
        {
            "item_id": "replace-me",
            "title": "Replace Me",
            "genre": "replace-me",
            "score": 0.0,
            "rank": 1,
            "popularity": 0.0,
            "novelty": 0.0,
        }
    ]
