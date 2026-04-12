"""Deterministic in-package catalog helpers for the recommender domain."""

from __future__ import annotations

from ...schema import Item

CATALOG: tuple[Item, ...] = (
    Item("action-1", "Runway Chase", "action", 0.96, 0.08, 0.86),
    Item("action-2", "City Heist", "action", 0.88, 0.14, 0.81),
    Item("comedy-1", "Weekend Mixup", "comedy", 0.83, 0.19, 0.73),
    Item("drama-1", "Quiet Reckoning", "drama", 0.71, 0.34, 0.78),
    Item("sci-fi-1", "Orbit Theory", "sci-fi", 0.58, 0.68, 0.83),
    Item("sci-fi-2", "Signal Collapse", "sci-fi", 0.52, 0.74, 0.79),
    Item("thriller-1", "Shadow Protocol", "thriller", 0.64, 0.49, 0.8),
    Item("horror-1", "Glass Corridor", "horror", 0.39, 0.82, 0.76),
    Item("documentary-1", "Last Broadcast", "documentary", 0.28, 0.88, 0.72),
    Item("indie-1", "Night Window", "indie", 0.25, 0.91, 0.69),
    Item("romance-1", "Late Train Letters", "romance", 0.61, 0.37, 0.67),
    Item("family-1", "Summer Circuit", "family", 0.79, 0.23, 0.71),
)


def history_for_genres(preferred_genres: tuple[str, ...], depth: int) -> tuple[str, ...]:
    """Build a deterministic scenario history from the recommender catalog."""
    matching = [item.item_id for item in CATALOG if item.genre in preferred_genres]
    fallback = [item.item_id for item in CATALOG if item.genre not in preferred_genres]
    return tuple((matching + fallback)[:depth])
