"""Placeholder scoring for the Chunk 1 stub flow."""

from __future__ import annotations

from ..schema import ScoringConfig, SessionTrace, TraceScore


class StubJudge:
    """Scores traces with simple placeholder metrics."""

    def score_trace(
        self,
        session_trace: SessionTrace,
        scoring_config: ScoringConfig,
    ) -> TraceScore:
        del scoring_config
        total_slate_score = 0.0
        total_items = 0
        click_count = 0
        for step in session_trace.steps:
            total_slate_score += sum(item.score for item in step.slate.items)
            total_items += len(step.slate.items)
            if step.action.name == "click":
                click_count += 1
        mean_slate_score = total_slate_score / total_items if total_items else 0.0
        return TraceScore(
            trace_id=session_trace.trace_id,
            archetype_label=session_trace.agent_seed.archetype_label,
            steps_completed=session_trace.completed_steps,
            abandoned=session_trace.abandoned,
            click_count=click_count,
            mean_slate_score=round(mean_slate_score, 6),
        )
