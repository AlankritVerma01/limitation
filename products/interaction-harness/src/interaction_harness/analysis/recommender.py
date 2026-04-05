"""Cohort analysis for richer recommender interaction audits."""

from __future__ import annotations

from collections import Counter, defaultdict

from ..schema import (
    AnalysisResult,
    CohortSummary,
    FailureMode,
    RiskFlag,
    RunConfig,
    SessionTrace,
    TraceScore,
)


class RecommenderAnalyzer:
    """Groups by scenario and archetype, then ranks risk deterministically."""

    def analyze(
        self,
        scored_traces: tuple[TraceScore, ...],
        traces: tuple[SessionTrace, ...],
        run_config: RunConfig,
    ) -> AnalysisResult:
        del run_config
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
            dominant_failure_mode = self._dominant_failure_mode(scores)
            cohort_risk_score = self._cohort_risk_score(
                abandonment_rate=abandonment_rate,
                mean_session_utility=mean_utility,
                mean_frustration_delta=mean_frustration_delta,
                mean_trust_delta=mean_trust_delta,
                mean_stale_exposure_rate=mean_stale_exposure_rate,
                mean_concentration=mean_concentration,
                trace_scores=scores,
            )
            risk_level = self._risk_level(cohort_risk_score)
            representative_failure = self._select_representative_failure(
                scores,
                dominant_failure_mode,
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
                    dominant_failure_mode=dominant_failure_mode,
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
                            f"due to {dominant_failure_mode.replace('_', ' ')}."
                        ),
                        trace_id=representative_failure.trace_id,
                        dominant_failure_mode=dominant_failure_mode,
                        evidence_summary=representative_failure.failure_evidence_summary,
                    )
                )

        summaries.sort(
            key=lambda summary: (
                self._risk_rank(summary.risk_level),
                summary.scenario_name,
                summary.archetype_label,
            ),
            reverse=True,
        )
        risk_flags.sort(
            key=lambda flag: (
                self._risk_rank(flag.severity),
                flag.scenario_name,
                flag.archetype_label,
            ),
            reverse=True,
        )
        return AnalysisResult(
            cohort_summaries=tuple(summaries),
            risk_flags=tuple(risk_flags),
        )

    def _dominant_failure_mode(self, scores: list[TraceScore]) -> FailureMode:
        """Choose the dominant failure mode, weighted by trace severity."""
        weighted_counts: Counter[FailureMode] = Counter()
        for score in scores:
            if score.dominant_failure_mode == "no_major_failure":
                continue
            weighted_counts[score.dominant_failure_mode] += max(0.1, score.trace_risk_score)
        if not weighted_counts:
            return "no_major_failure"
        return weighted_counts.most_common(1)[0][0]

    def _cohort_risk_score(
        self,
        *,
        abandonment_rate: float,
        mean_session_utility: float,
        mean_frustration_delta: float,
        mean_trust_delta: float,
        mean_stale_exposure_rate: float,
        mean_concentration: float,
        trace_scores: list[TraceScore],
    ) -> float:
        """Blend cohort-level and worst-trace signals into one risk score."""
        base = 0.0
        base += 0.35 * abandonment_rate
        base += max(0.0, 0.58 - mean_session_utility) * 0.45
        base += max(0.0, mean_frustration_delta) * 0.22
        base += max(0.0, -mean_trust_delta) * 0.28
        base += max(0.0, mean_stale_exposure_rate - 0.2) * 0.22
        if mean_session_utility < 0.55:
            base += max(0.0, mean_concentration - 0.45) * 0.18
        base += 0.2 * (
            sum(score.trace_risk_score for score in trace_scores) / len(trace_scores)
        )
        base += 0.18 * max(score.trace_risk_score for score in trace_scores)
        if any(score.trace_risk_score >= 0.8 for score in trace_scores):
            base += 0.08
        return max(0.0, min(1.0, base))

    def _risk_level(self, cohort_risk_score: float) -> str:
        if cohort_risk_score >= 0.62:
            return "high"
        if cohort_risk_score >= 0.34:
            return "medium"
        return "low"

    def _risk_rank(self, severity: str) -> int:
        return {"low": 0, "medium": 1, "high": 2}[severity]

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
