"""Cohort and slice-aware analysis for recommender interaction audits."""

from __future__ import annotations

from collections import defaultdict

from ..schema import (
    AnalysisResult,
    CohortSummary,
    FailureMode,
    RiskFlag,
    RunConfig,
    SessionTrace,
    TraceScore,
)
from .recommender_metrics import (
    aggregate_risk_score,
    dominant_failure_mode,
    risk_level_for_score,
    risk_rank,
)
from .recommender_slices import discover_recommender_slices


class RecommenderAnalyzer:
    """Summarize seeded cohorts, launch risks, and discovered failure slices."""

    def analyze(
        self,
        scored_traces: tuple[TraceScore, ...],
        traces: tuple[SessionTrace, ...],
        run_config: RunConfig,
    ) -> AnalysisResult:
        grouped: dict[tuple[str, str], list[TraceScore]] = defaultdict(list)
        for score in scored_traces:
            grouped[(score.scenario_name, score.archetype_label)].append(score)

        summaries: list[CohortSummary] = []
        risk_flags: list[RiskFlag] = []
        for (scenario_name, archetype_label), scores in grouped.items():
            trace_count = len(scores)
            abandonment_rate = sum(score.abandoned for score in scores) / trace_count
            mean_utility = sum(score.session_utility for score in scores) / trace_count
            mean_engagement = sum(score.engagement for score in scores) / trace_count
            mean_frustration = sum(score.frustration for score in scores) / trace_count
            mean_trust_delta = sum(score.trust_delta for score in scores) / trace_count
            mean_confidence_delta = (
                sum(score.confidence_delta for score in scores) / trace_count
            )
            mean_skip_rate = sum(score.skip_rate for score in scores) / trace_count
            mean_frustration_delta = (
                sum(score.frustration_delta for score in scores) / trace_count
            )
            mean_stale_exposure_rate = (
                sum(score.stale_exposure_rate for score in scores) / trace_count
            )
            mean_concentration = sum(score.concentration for score in scores) / trace_count
            cohort_failure_mode = dominant_failure_mode(scores)
            cohort_risk_score = aggregate_risk_score(
                abandonment_rate=abandonment_rate,
                mean_session_utility=mean_utility,
                mean_frustration_delta=mean_frustration_delta,
                mean_trust_delta=mean_trust_delta,
                mean_stale_exposure_rate=mean_stale_exposure_rate,
                mean_concentration=mean_concentration,
                trace_scores=scores,
            )
            risk_level = risk_level_for_score(cohort_risk_score)
            representative_failure = self._select_representative_failure(
                scores,
                cohort_failure_mode,
            )
            representative_success = self._select_representative_success(scores)
            high_risk_trace_count = sum(score.trace_risk_score >= 0.65 for score in scores)

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
                    mean_trust_delta=round(mean_trust_delta, 6),
                    mean_confidence_delta=round(mean_confidence_delta, 6),
                    mean_skip_rate=round(mean_skip_rate, 6),
                    dominant_failure_mode=cohort_failure_mode,
                    high_risk_trace_count=high_risk_trace_count,
                    representative_success_trace_id=(
                        representative_success.trace_id if representative_success is not None else None
                    ),
                    representative_failure_trace_id=(
                        representative_failure.trace_id if representative_failure is not None else None
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
                            f"due to {cohort_failure_mode.replace('_', ' ')}."
                        ),
                        trace_id=representative_failure.trace_id,
                        dominant_failure_mode=cohort_failure_mode,
                        evidence_summary=representative_failure.failure_evidence_summary,
                    )
                )

        summaries.sort(
            key=lambda summary: (
                risk_rank(summary.risk_level),
                summary.scenario_name,
                summary.archetype_label,
            ),
            reverse=True,
        )
        risk_flags.sort(
            key=lambda flag: (
                risk_rank(flag.severity),
                flag.scenario_name,
                flag.archetype_label,
            ),
            reverse=True,
        )
        return AnalysisResult(
            cohort_summaries=tuple(summaries),
            risk_flags=tuple(risk_flags),
            slice_discovery=discover_recommender_slices(
                scored_traces=scored_traces,
                traces=traces,
                run_config=run_config,
            ),
        )

    def _select_representative_failure(
        self,
        scores: list[TraceScore],
        dominant_failure_mode: FailureMode,
    ) -> TraceScore | None:
        """Pick the highest-severity trace inside the cohort's main failure mode."""
        candidates = [
            score
            for score in scores
            if score.dominant_failure_mode == dominant_failure_mode
            and score.dominant_failure_mode != "no_major_failure"
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda score: (score.trace_risk_score, -score.session_utility),
        )

    def _select_representative_success(
        self,
        scores: list[TraceScore],
    ) -> TraceScore | None:
        """Pick the strongest healthy trace for side-by-side inspection."""
        candidates = [
            score
            for score in scores
            if score.dominant_failure_mode == "no_major_failure"
            and not score.abandoned
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda score: score.session_utility)
