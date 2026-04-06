"""Shared deterministic risk helpers for recommender analysis layers."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from ..schema import FailureMode, RiskSeverity, TraceScore


def dominant_failure_mode(scores: Sequence[TraceScore]) -> FailureMode:
    """Choose one dominant failure mode, weighted by trace severity."""
    weighted_counts: Counter[FailureMode] = Counter()
    for score in scores:
        if score.dominant_failure_mode == "no_major_failure":
            continue
        weighted_counts[score.dominant_failure_mode] += max(0.1, score.trace_risk_score)
    if not weighted_counts:
        return "no_major_failure"
    return weighted_counts.most_common(1)[0][0]


def aggregate_risk_score(
    *,
    abandonment_rate: float,
    mean_session_utility: float,
    mean_frustration_delta: float,
    mean_trust_delta: float,
    mean_stale_exposure_rate: float,
    mean_concentration: float,
    trace_scores: Sequence[TraceScore],
) -> float:
    """Blend aggregate and worst-case trace signals into one bounded risk score."""
    if not trace_scores:
        return 0.0
    base = 0.0
    base += 0.35 * abandonment_rate
    base += max(0.0, 0.58 - mean_session_utility) * 0.45
    base += max(0.0, mean_frustration_delta) * 0.22
    base += max(0.0, -mean_trust_delta) * 0.28
    base += max(0.0, mean_stale_exposure_rate - 0.2) * 0.22
    if mean_session_utility < 0.55:
        base += max(0.0, mean_concentration - 0.45) * 0.18
    base += 0.2 * (sum(score.trace_risk_score for score in trace_scores) / len(trace_scores))
    base += 0.18 * max(score.trace_risk_score for score in trace_scores)
    if any(score.trace_risk_score >= 0.8 for score in trace_scores):
        base += 0.08
    return max(0.0, min(1.0, base))


def risk_level_for_score(risk_score: float) -> RiskSeverity:
    """Map one bounded risk score into the stable severity buckets."""
    if risk_score >= 0.62:
        return "high"
    if risk_score >= 0.34:
        return "medium"
    return "low"


def risk_rank(severity: str) -> int:
    """Return a sortable rank for low/medium/high severities."""
    return {"low": 0, "medium": 1, "high": 2}[severity]
