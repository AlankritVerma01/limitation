"""Search domain contracts and reference utilities."""

from .contracts import (
    SearchRequest,
    SearchResponse,
    SearchResult,
    request_to_payload,
    response_to_ranked_list,
)
from .reference_backend import ReferenceSearchBackend, search

__all__ = (
    "ReferenceSearchBackend",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    "request_to_payload",
    "response_to_ranked_list",
    "search",
)
