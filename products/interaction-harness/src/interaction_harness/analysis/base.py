"""Cohort analysis interface for scored traces."""

from __future__ import annotations

from typing import Protocol

from ..schema import AnalysisResult, RunConfig, SessionTrace, TraceScore


class Analyzer(Protocol):
    """Aggregates scored traces into cohort summaries."""

    def analyze(
        self,
        scored_traces: tuple[TraceScore, ...],
        traces: tuple[SessionTrace, ...],
        run_config: RunConfig,
    ) -> AnalysisResult: ...
