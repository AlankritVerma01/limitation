"""Judge interface for trace scoring."""

from __future__ import annotations

from typing import Protocol

from ..schema import ScoringConfig, SessionTrace, TraceScore


class Judge(Protocol):
    """Scores a completed trace without touching rollout mechanics."""

    def score_trace(
        self,
        session_trace: SessionTrace,
        scoring_config: ScoringConfig,
    ) -> TraceScore: ...
