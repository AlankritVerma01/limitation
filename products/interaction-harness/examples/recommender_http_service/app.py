"""Customer-style example recommender HTTP service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

try:
    from .artifacts import (
        ARTIFACT_FILENAME,
        ensure_example_artifacts,
        load_example_artifacts,
        load_items,
    )
except ImportError:  # pragma: no cover - direct script startup fallback
    from artifacts import (  # type: ignore[no-redef]
        ARTIFACT_FILENAME,
        ensure_example_artifacts,
        load_example_artifacts,
        load_items,
    )


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


class RankedItem(BaseModel):
    item_id: str
    title: str
    genre: str
    score: float
    rank: int
    popularity: float
    novelty: float


class RecommendationResponse(BaseModel):
    request_id: str
    items: list[RankedItem]


@dataclass(frozen=True)
class ExampleServiceConfig:
    model_kind: str
    artifact_dir: str
    data_dir: str | None
    top_k: int


class ExampleRecommendationBackend:
    """Simple external-proof backend with swappable ranking behavior."""

    def __init__(self, config: ExampleServiceConfig) -> None:
        artifact_path = ensure_example_artifacts(config.artifact_dir, data_dir=config.data_dir)
        payload = load_example_artifacts(artifact_path.parent)
        self._items = load_items(artifact_path.parent)
        self._artifact_id = str(payload["artifact_id"])
        self._dataset = str(payload["dataset"])
        self._data_source = str(payload.get("data_source", "unknown"))
        self._global_popularity_order = tuple(payload["global_popularity_order"])
        self._model_kind = config.model_kind
        self._top_k = config.top_k

    def metadata(self) -> dict[str, str | int]:
        return {
            "service_kind": "external",
            "backend_name": "ExampleExternalRecommenderService",
            "dataset": self._dataset,
            "data_source": self._data_source,
            "model_kind": self._model_kind,
            "model_id": f"{self._model_kind}-{self._artifact_id}",
            "artifact_id": self._artifact_id,
            "artifact_filename": ARTIFACT_FILENAME,
            "item_count": len(self._items),
            "artifact_contract_version": "v1",
        }

    def recommend(self, payload: RecommendationRequest) -> RecommendationResponse:
        ranked = []
        preferred_genres = set(payload.preferred_genres)
        recent_exposures = set(payload.recent_exposure_ids)
        history_similarity = self._history_similarity_lookup(payload.history_item_ids)
        scenario_profile = payload.scenario_profile or payload.scenario_name

        for item in self._items.values():
            exposure_penalty = 0.2 if item.item_id in recent_exposures else 0.0
            genre_match = len(set(item.genres).intersection(preferred_genres)) / max(
                1, len(item.genres)
            )
            if self._model_kind == "popularity":
                score = (
                    0.68 * item.popularity
                    + 0.15 * item.quality
                    + 0.12 * genre_match
                    + 0.05 * item.novelty
                )
            elif self._model_kind == "item-item-cf":
                similarity = history_similarity.get(item.item_id, 0.0)
                scenario_bias = 0.1 if scenario_profile == "returning-user-home-feed" else 0.0
                score = (
                    0.52 * similarity
                    + 0.16 * item.quality
                    + 0.16 * genre_match
                    + 0.11 * item.popularity
                    + 0.05 * item.novelty
                    + scenario_bias
                )
            elif self._model_kind == "genre-history-blend":
                history_genre_affinity = self._history_genre_affinity(payload.history_item_ids, item.genres)
                score = (
                    0.42 * history_genre_affinity
                    + 0.22 * genre_match
                    + 0.16 * item.quality
                    + 0.14 * item.novelty
                    + 0.06 * item.popularity
                )
            else:
                raise HTTPException(status_code=500, detail="unsupported_model_kind")
            score -= exposure_penalty
            score -= 0.01 * payload.step_index
            ranked.append((round(score, 6), item))

        ranked.sort(
            key=lambda entry: (
                entry[0],
                self._global_popularity_order.index(entry[1].item_id)
                if entry[1].item_id in self._global_popularity_order
                else len(self._global_popularity_order),
            ),
            reverse=True,
        )
        items = [
            RankedItem(
                item_id=item.item_id,
                title=item.title,
                genre=item.genre,
                score=score,
                rank=index,
                popularity=item.popularity,
                novelty=item.novelty,
            )
            for index, (score, item) in enumerate(ranked[: self._top_k], start=1)
        ]
        return RecommendationResponse(request_id=payload.request_id, items=items)

    def _history_similarity_lookup(self, history_item_ids: list[str]) -> dict[str, float]:
        similarity: dict[str, float] = {}
        for history_id in history_item_ids:
            item = self._items.get(history_id)
            if item is None:
                continue
            for neighbor_id, neighbor_score in item.neighbor_scores:
                similarity[neighbor_id] = max(similarity.get(neighbor_id, 0.0), neighbor_score)
        return similarity

    def _history_genre_affinity(
        self,
        history_item_ids: list[str],
        candidate_genres: tuple[str, ...],
    ) -> float:
        if not history_item_ids:
            return 0.0
        history_genres = [
            genre
            for item_id in history_item_ids
            if item_id in self._items
            for genre in self._items[item_id].genres
        ]
        if not history_genres:
            return 0.0
        shared = sum(1 for genre in candidate_genres if genre in history_genres)
        return shared / max(1, len(candidate_genres))


def create_app() -> FastAPI:
    """Create the example service app from environment configuration."""
    config = ExampleServiceConfig(
        model_kind=os.environ.get("IH_EXAMPLE_MODEL_KIND", "popularity"),
        artifact_dir=os.environ.get("IH_EXAMPLE_ARTIFACT_DIR", ""),
        data_dir=os.environ.get("IH_EXAMPLE_DATA_DIR") or None,
        top_k=int(os.environ.get("IH_EXAMPLE_TOP_K", "5")),
    )
    backend = ExampleRecommendationBackend(config)
    app = FastAPI(
        title="Interaction Harness Example Recommender Service",
        version="0.1.0",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service_kind": "external"}

    @app.get("/metadata")
    def metadata() -> dict[str, str | int]:
        return backend.metadata()

    @app.post("/recommendations")
    def recommendations(payload: RecommendationRequest) -> dict[str, Any]:
        response = backend.recommend(payload)
        return response.model_dump()

    return app


app = create_app()
