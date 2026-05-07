"""Driver configuration dataclasses for the recommender domain."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HttpNativeDriverConfig:
    """Configuration for the native HTTP recommender driver."""

    base_url: str
    timeout_seconds: float
