"""Cohort analysis for the search domain."""

from __future__ import annotations

from collections import Counter, defaultdict

from ...schema import (
    AnalysisResult,
    CohortSummary,
    RiskFlag,
    RunConfig,
    SessionTrace,
    SliceDiscoveryResult,
    TraceScore,
)


class SearchAnalyzer:
    """Summarize search cohorts and risk flags."""

    def analyze(
        self,
        scored_traces: tuple[TraceScore, ...],
        traces: tuple[SessionTrace, ...],
        run_config: RunConfig,
    ) -> AnalysisResult:
        del traces, run_config
        grouped: dict[tuple[str, str], list[TraceScore]] = defaultdict(list)
        for score in scored_traces:
            grouped[(score.scenario_name, score.archetype_label)].append(score)

        summaries: list[CohortSummary] = []
        risk_flags: list[RiskFlag] = []
        for (scenario_name, archetype_label), scores in grouped.items():
            trace_count = len(scores)
            abandonment_rate = _mean(1.0 if score.abandoned else 0.0 for score in scores)
            mean_utility = _mean(score.session_utility for score in scores)
            mean_engagement = _mean(score.engagement for score in scores)
            mean_frustration = _mean(score.frustration for score in scores)
            mean_skip_rate = _mean(score.skip_rate for score in scores)
            mean_risk = _mean(score.trace_risk_score for score in scores)
            risk_level = _risk_level(mean_risk)
            dominant_failure = _dominant_failure(scores)
            representative_failure = _representative_failure(scores)
            representative_success = _representative_success(scores)
            summaries.append(
                CohortSummary(
                    scenario_name=scenario_name,
                    archetype_label=archetype_label,
                    trace_count=trace_count,
                    abandonment_rate=round(abandonment_rate, 6),
                    mean_session_utility=round(mean_utility, 6),
                    mean_engagement=round(mean_engagement, 6),
                    mean_frustration=round(mean_frustration, 6),
                    risk_level=risk_level,
                    representative_trace_id=(
                        representative_failure.trace_id
                        if representative_failure is not None
                        else representative_success.trace_id
                        if representative_success is not None
                        else None
                    ),
                    mean_skip_rate=round(mean_skip_rate, 6),
                    dominant_failure_mode=dominant_failure,
                    high_risk_trace_count=sum(
                        score.trace_risk_score >= 0.65 for score in scores
                    ),
                    representative_success_trace_id=(
                        representative_success.trace_id if representative_success else None
                    ),
                    representative_failure_trace_id=(
                        representative_failure.trace_id if representative_failure else None
                    ),
                )
            )
            if risk_level != "low" and representative_failure is not None:
                risk_flags.append(
                    RiskFlag(
                        scenario_name=scenario_name,
                        archetype_label=archetype_label,
                        severity=risk_level,
                        message=(
                            f"{archetype_label} is underserved in {scenario_name} "
                            f"due to {dominant_failure.replace('_', ' ')}."
                        ),
                        trace_id=representative_failure.trace_id,
                        dominant_failure_mode=dominant_failure,
                        evidence_summary=representative_failure.failure_evidence_summary,
                    )
                )

        summaries.sort(
            key=lambda summary: (
                _risk_rank(summary.risk_level),
                summary.scenario_name,
                summary.archetype_label,
            ),
            reverse=True,
        )
        risk_flags.sort(
            key=lambda flag: (
                _risk_rank(flag.severity),
                flag.scenario_name,
                flag.archetype_label,
            ),
            reverse=True,
        )
        return AnalysisResult(
            cohort_summaries=tuple(summaries),
            risk_flags=tuple(risk_flags),
            slice_discovery=SliceDiscoveryResult(()),
        )


def _dominant_failure(scores: list[TraceScore]):
    counts = Counter()
    for score in scores:
        if score.dominant_failure_mode != "no_major_failure":
            counts[score.dominant_failure_mode] += max(0.1, score.trace_risk_score)
    if not counts:
        return "no_major_failure"
    return counts.most_common(1)[0][0]


def _representative_failure(scores: list[TraceScore]) -> TraceScore | None:
    candidates = [
        score for score in scores if score.dominant_failure_mode != "no_major_failure"
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda score: (score.trace_risk_score, -score.session_utility))


def _representative_success(scores: list[TraceScore]) -> TraceScore | None:
    candidates = [
        score
        for score in scores
        if score.dominant_failure_mode == "no_major_failure" and not score.abandoned
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda score: score.session_utility)


def _mean(values) -> float:
    values = tuple(values)
    if not values:
        return 0.0
    return sum(values) / len(values)


def _risk_level(risk_score: float):
    if risk_score >= 0.62:
        return "high"
    if risk_score >= 0.34:
        return "medium"
    return "low"


def _risk_rank(severity: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}[severity]
