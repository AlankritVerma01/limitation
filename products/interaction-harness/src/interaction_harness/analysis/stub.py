"""Seeded cohort summaries for the Chunk 1 stub flow."""

from __future__ import annotations

from collections import defaultdict

from ..schema import CohortSummary, RunConfig, TraceScore


class StubAnalyzer:
    """Groups scored traces by seeded archetype label."""

    def summarize(
        self,
        scored_traces: tuple[TraceScore, ...],
        run_config: RunConfig,
    ) -> list[CohortSummary]:
        del run_config
        grouped: dict[str, list[TraceScore]] = defaultdict(list)
        for trace_score in scored_traces:
            grouped[trace_score.archetype_label].append(trace_score)

        summaries: list[CohortSummary] = []
        for archetype_label, scores in grouped.items():
            trace_count = len(scores)
            abandonment_rate = sum(score.abandoned for score in scores) / trace_count
            mean_score = sum(score.mean_slate_score for score in scores) / trace_count
            summaries.append(
                CohortSummary(
                    archetype_label=archetype_label,
                    trace_count=trace_count,
                    abandonment_rate=round(abandonment_rate, 6),
                    mean_score=round(mean_score, 6),
                )
            )
        return sorted(summaries, key=lambda summary: summary.archetype_label)
