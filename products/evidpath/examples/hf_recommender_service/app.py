"""Hugging Face-backed recommender HTTP service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

try:
    from recommender_http_service.artifacts import (
        ARTIFACT_FILENAME,
        ExampleItem,
        ensure_example_artifacts,
        load_example_artifacts,
        load_items,
    )
except ImportError:  # pragma: no cover - direct script startup fallback
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from recommender_http_service.artifacts import (  # type: ignore[no-redef]
        ARTIFACT_FILENAME,
        ExampleItem,
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
class HFServiceConfig:
    model_kind: str
    artifact_dir: str
    data_dir: str | None
    top_k: int
    embedding_model_name: str
    batch_size: int


class HFTextEncoder:
    """Small wrapper around transformer tokenization and mean pooling."""

    def __init__(self, *, model_name: str, batch_size: int) -> None:
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - exercised in docs/runtime
            raise RuntimeError(
                "The Hugging Face recommender example requires the optional "
                "`evidpath[hf-example]` dependencies."
            ) from exc
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(model_name)
        self._model = AutoModel.from_pretrained(model_name)
        self._model.eval()
        self._device = torch.device("cpu")
        self._model.to(self._device)
        self._batch_size = max(1, batch_size)

    @property
    def torch(self):
        return self._torch

    def encode(self, texts: list[str]):
        if not texts:
            raise ValueError("texts must not be empty")
        embeddings = []
        for offset in range(0, len(texts), self._batch_size):
            batch = texts[offset : offset + self._batch_size]
            tokens = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=128,
                return_tensors="pt",
            )
            tokens = {key: value.to(self._device) for key, value in tokens.items()}
            with self._torch.no_grad():
                outputs = self._model(**tokens)
            token_embeddings = outputs.last_hidden_state
            attention_mask = tokens["attention_mask"].unsqueeze(-1)
            masked = token_embeddings * attention_mask
            counts = attention_mask.sum(dim=1).clamp(min=1)
            mean_pooled = masked.sum(dim=1) / counts
            normalized = self._torch.nn.functional.normalize(mean_pooled, p=2, dim=1)
            embeddings.append(normalized.cpu())
        return self._torch.cat(embeddings, dim=0)


class HFRecommendationBackend:
    """External wrapper that ranks items with Hugging Face text embeddings."""

    def __init__(self, config: HFServiceConfig) -> None:
        if config.model_kind not in {"hf-semantic", "hf-semantic-popularity-blend"}:
            raise ValueError(f"Unsupported HF recommender mode: {config.model_kind}")
        artifact_path = ensure_example_artifacts(config.artifact_dir, data_dir=config.data_dir)
        payload = load_example_artifacts(artifact_path.parent)
        self._items = load_items(artifact_path.parent)
        self._ordered_items = tuple(self._items[item_id] for item_id in sorted(self._items))
        self._artifact_id = str(payload["artifact_id"])
        self._dataset = str(payload["dataset"])
        self._data_source = str(payload.get("data_source", "unknown"))
        self._global_popularity_order = tuple(payload["global_popularity_order"])
        self._global_popularity_rank = {
            item_id: index for index, item_id in enumerate(self._global_popularity_order)
        }
        self._model_kind = config.model_kind
        self._top_k = config.top_k
        self._embedding_model_name = config.embedding_model_name
        self._encoder = HFTextEncoder(
            model_name=config.embedding_model_name,
            batch_size=config.batch_size,
        )
        self._item_embeddings = self._encoder.encode(
            [self._item_text(item) for item in self._ordered_items]
        )

    def metadata(self) -> dict[str, str | int]:
        return {
            "service_kind": "external",
            "backend_name": "HFExternalRecommenderService",
            "dataset": self._dataset,
            "data_source": self._data_source,
            "model_kind": self._model_kind,
            "model_id": f"{self._model_kind}-{self._artifact_id}",
            "artifact_id": self._artifact_id,
            "artifact_filename": ARTIFACT_FILENAME,
            "embedding_model_name": self._embedding_model_name,
            "item_count": len(self._ordered_items),
            "artifact_contract_version": "v1",
        }

    def recommend(self, payload: RecommendationRequest) -> RecommendationResponse:
        query_text = self._build_query_text(payload)
        query_embedding = self._encoder.encode([query_text])[0]
        semantic_scores = self._encoder.torch.mv(self._item_embeddings, query_embedding).tolist()
        preferred_genres = {genre.lower() for genre in payload.preferred_genres}
        recent_exposures = set(payload.recent_exposure_ids)
        history_items = set(payload.history_item_ids)
        ranked: list[tuple[float, ExampleItem]] = []

        for semantic_score, item in zip(semantic_scores, self._ordered_items, strict=True):
            genre_overlap = self._genre_overlap_score(item, preferred_genres)
            repetition_penalty = 0.08 if item.item_id in history_items else 0.0
            exposure_penalty = 0.22 if item.item_id in recent_exposures else 0.0
            step_penalty = 0.01 * payload.step_index
            if self._model_kind == "hf-semantic":
                score = (
                    0.84 * float(semantic_score)
                    + 0.08 * genre_overlap
                    + 0.04 * item.novelty
                    + 0.04 * item.quality
                )
            elif self._model_kind == "hf-semantic-popularity-blend":
                score = (
                    0.62 * float(semantic_score)
                    + 0.20 * item.popularity
                    + 0.10 * genre_overlap
                    + 0.08 * item.quality
                )
            else:  # pragma: no cover - safeguarded in __init__
                raise HTTPException(status_code=500, detail="unsupported_model_kind")
            score -= repetition_penalty + exposure_penalty + step_penalty
            ranked.append((round(score, 6), item))

        ranked.sort(
            key=lambda entry: (
                entry[0],
                -self._global_popularity_rank.get(entry[1].item_id, len(self._ordered_items)),
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

    def _build_query_text(self, payload: RecommendationRequest) -> str:
        history_descriptions = [
            self._item_text(self._items[item_id])
            for item_id in payload.history_item_ids
            if item_id in self._items
        ][:6]
        parts = [f"Scenario name: {payload.scenario_name}"]
        if payload.scenario_profile:
            parts.append(f"Scenario profile: {payload.scenario_profile}")
        if payload.preferred_genres:
            parts.append(
                "Preferred genres: " + ", ".join(sorted(dict.fromkeys(payload.preferred_genres)))
            )
        if history_descriptions:
            parts.append("History: " + " | ".join(history_descriptions))
        else:
            parts.append("History: sparse or unavailable")
        return ". ".join(parts)

    def _genre_overlap_score(self, item: ExampleItem, preferred_genres: set[str]) -> float:
        if not preferred_genres:
            return 0.0
        overlap = sum(1 for genre in item.genres if genre in preferred_genres)
        return overlap / max(1, len(item.genres))

    def _item_text(self, item: ExampleItem) -> str:
        return f"{item.title}. Genres: {', '.join(item.genres)}."


def create_app() -> FastAPI:
    """Create the HF recommender app from environment configuration."""
    config = HFServiceConfig(
        model_kind=os.environ.get("IH_HF_MODEL_KIND", "hf-semantic"),
        artifact_dir=os.environ.get("IH_HF_ARTIFACT_DIR", ""),
        data_dir=os.environ.get("IH_HF_DATA_DIR") or None,
        top_k=int(os.environ.get("IH_HF_TOP_K", "5")),
        embedding_model_name=os.environ.get(
            "IH_HF_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"
        ),
        batch_size=int(os.environ.get("IH_HF_BATCH_SIZE", "64")),
    )
    backend = HFRecommendationBackend(config)
    app = FastAPI(
        title="Evidpath HF Recommender Service",
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
        return backend.recommend(payload).model_dump()

    return app
