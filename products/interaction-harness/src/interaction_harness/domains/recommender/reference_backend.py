"""Artifact-backed reference recommender backend."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ...schema import AdapterRequest
from .reference_artifacts import load_reference_artifacts


@dataclass(frozen=True)
class ReferenceItem:
    item_id: str
    title: str
    genre: str
    genres: tuple[str, ...]
    popularity: float
    novelty: float
    quality: float
    neighbor_scores: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class ReferenceServiceMetadata:
    service_kind: str
    backend_name: str
    artifact_id: str
    dataset: str
    item_count: int


class RecommendationBackend(Protocol):
    """Internal backend seam for the reference service."""

    def get_recommendations(self, request: AdapterRequest) -> dict: ...

    def metadata(self) -> dict[str, str | int | float]: ...


class ReferenceRecommendationBackend:
    """Lightweight profile/content/popularity hybrid backend."""

    def __init__(self, artifact_dir: str | Path) -> None:
        artifacts = load_reference_artifacts(artifact_dir)
        self._artifact_dir = str(Path(artifact_dir))
        self._items = {
            item["item_id"]: ReferenceItem(
                item_id=item["item_id"],
                title=item["title"],
                genre=item["genre"],
                genres=tuple(item["genres"]),
                popularity=float(item["popularity"]),
                novelty=float(item["novelty"]),
                quality=float(item["quality"]),
                neighbor_scores=tuple(
                    (neighbor["item_id"], float(neighbor["score"]))
                    for neighbor in item["neighbor_scores"]
                ),
            )
            for item in artifacts["items"]
        }
        self._artifact_id = str(artifacts["artifact_id"])
        self._dataset = str(artifacts["dataset"])
        self._global_top_item_ids = tuple(artifacts["global_top_item_ids"])

    def get_recommendations(self, request: AdapterRequest) -> dict:
        preferred_genres = set(request.preferred_genres)
        history_ids = tuple(request.history_item_ids)
        recent_exposure_ids = set(request.recent_exposure_ids)
        similarity_cache = self._history_similarity_lookup(history_ids)

        ranked_items = []
        for item in self._items.values():
            exposure_penalty = 0.15 if item.item_id in recent_exposure_ids else 0.0
            history_similarity = similarity_cache.get(item.item_id, 0.0)
            genre_match = len(set(item.genres).intersection(preferred_genres)) / max(
                1, len(item.genres)
            )
            scenario_profile = request.scenario_profile or request.scenario_name
            if scenario_profile == "returning-user-home-feed":
                score = (
                    (0.42 * history_similarity)
                    + (0.2 * genre_match)
                    + (0.17 * item.quality)
                    + (0.13 * item.popularity)
                    + (0.08 * item.novelty)
                )
            else:
                score = (
                    (0.18 * history_similarity)
                    + (0.18 * genre_match)
                    + (0.18 * item.quality)
                    + (0.3 * item.popularity)
                    + (0.16 * item.novelty)
                )
            score -= exposure_penalty
            score -= 0.02 * request.step_index
            ranked_items.append((round(score, 6), item))

        ranked_items.sort(
            key=lambda entry: (
                entry[0],
                self._global_top_item_ids.index(entry[1].item_id)
                if entry[1].item_id in self._global_top_item_ids
                else len(self._global_top_item_ids),
            ),
            reverse=True,
        )
        items = [
            {
                "item_id": item.item_id,
                "title": item.title,
                "genre": item.genre,
                "score": score,
                "rank": rank,
                "popularity": item.popularity,
                "novelty": item.novelty,
            }
            for rank, (score, item) in enumerate(ranked_items[:5], start=1)
        ]
        return {
            "request_id": request.request_id,
            "items": items,
            "service_metadata": self.metadata(),
        }

    def metadata(self) -> dict[str, str | int | float]:
        metadata = ReferenceServiceMetadata(
            service_kind="reference",
            backend_name="ReferenceRecommendationBackend",
            artifact_id=self._artifact_id,
            dataset=self._dataset,
            item_count=len(self._items),
        )
        return json.loads(json.dumps(metadata.__dict__, sort_keys=True))

    def _history_similarity_lookup(self, history_ids: tuple[str, ...]) -> dict[str, float]:
        similarity: dict[str, float] = {}
        for history_id in history_ids:
            item = self._items.get(history_id)
            if item is None:
                continue
            for neighbor_id, neighbor_score in item.neighbor_scores:
                similarity[neighbor_id] = max(similarity.get(neighbor_id, 0.0), neighbor_score)
        return similarity
