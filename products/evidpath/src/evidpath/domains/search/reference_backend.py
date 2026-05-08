"""Deterministic reference search backend for driver and CI tests."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from typing import Any

from .contracts import SearchRequest, SearchResponse, SearchResult

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class ReferenceSearchBackend:
    """Tiny deterministic search ranker backed by a checked-in corpus."""

    documents: tuple[dict[str, Any], ...]

    @classmethod
    def from_artifacts(cls) -> "ReferenceSearchBackend":
        artifact = resources.files(__package__).joinpath("reference_search_artifacts.json")
        payload = json.loads(artifact.read_text(encoding="utf-8"))
        return cls(documents=tuple(payload["documents"]))

    def predict(self, request: SearchRequest) -> SearchResponse:
        scored: list[tuple[float, float, str, dict[str, Any]]] = []
        query_tokens = _tokens(request.query)
        for document in self.documents:
            keywords = set(document.get("keywords", ()))
            overlap = query_tokens & keywords
            if not overlap:
                continue
            lexical_score = len(overlap) / max(len(query_tokens), 1)
            personalization = _personalization_boost(request, document)
            freshness = float(document.get("freshness_score", 0.0))
            freshness_boost = 0.12 * freshness if request.freshness_window_days else 0.0
            score = min(1.0, lexical_score + personalization + freshness_boost)
            scored.append((score, freshness, str(document["result_id"]), document))
        scored.sort(key=lambda entry: (-entry[0], -entry[1], entry[2]))
        results = tuple(
            _to_result(document, score=score, rank=index + 1)
            for index, (score, _freshness, _result_id, document) in enumerate(
                scored[: request.max_results]
            )
        )
        return SearchResponse(request_id=request.request_id, results=results)

    def get_service_metadata(self) -> dict[str, str]:
        """Return stable metadata for reference-mode audit artifacts."""
        return {
            "service_kind": "reference_search",
            "backend_name": "reference-search",
            "model_kind": "deterministic_fixture",
        }


def search(request: SearchRequest) -> SearchResponse:
    """Search the deterministic reference corpus."""
    return ReferenceSearchBackend.from_artifacts().predict(request)


def _tokens(value: str) -> set[str]:
    return set(_TOKEN_RE.findall(value.lower()))


def _personalization_boost(
    request: SearchRequest,
    document: dict[str, Any],
) -> float:
    preferred = request.user_context.get("preferred_genres", ())
    if not isinstance(preferred, tuple):
        return 0.0
    keywords = set(document.get("keywords", ()))
    return 0.08 if keywords.intersection(preferred) else 0.0


def _to_result(document: dict[str, Any], *, score: float, rank: int) -> SearchResult:
    return SearchResult(
        result_id=str(document["result_id"]),
        title=str(document["title"]),
        snippet=str(document["snippet"]),
        url=str(document["url"]),
        result_type=str(document["result_type"]),
        relevance_score=score,
        rank=rank,
        freshness_timestamp=str(document.get("freshness_timestamp", "")),
        freshness_score=float(document.get("freshness_score", 0.0)),
    )
