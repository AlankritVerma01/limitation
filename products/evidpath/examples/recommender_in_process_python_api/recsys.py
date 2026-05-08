"""A tiny popularity recommender for the Python-API onboarding example."""

from __future__ import annotations

from evidpath import AdapterRequest, AdapterResponse, SlateItem
from evidpath.domains.recommender import CATALOG


def predict(request: AdapterRequest) -> AdapterResponse:
    """Score catalog items by popularity."""
    sorted_items = sorted(CATALOG, key=lambda item: item.popularity, reverse=True)[:5]
    items = tuple(
        SlateItem(
            item_id=item.item_id,
            title=item.title,
            genre=item.genre,
            score=0.9 - 0.1 * index,
            rank=index + 1,
            popularity=item.popularity,
            novelty=item.novelty,
        )
        for index, item in enumerate(sorted_items)
    )
    return AdapterResponse(request_id=request.request_id, items=items)
