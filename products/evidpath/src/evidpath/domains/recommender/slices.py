"""Recommender-specific slice extraction and summarization."""

from __future__ import annotations

from ...analysis.slice_discovery import SliceTraceInput, build_slice_id, discover_slices
from ...schema import (
    RunConfig,
    SessionTrace,
    SliceDiscoveryResult,
    SliceFeature,
    SliceSummary,
    TraceScore,
)
from .metrics import (
    aggregate_risk_score,
    dominant_failure_mode,
    risk_level_for_score,
)


def discover_recommender_slices(
    *,
    scored_traces: tuple[TraceScore, ...],
    traces: tuple[SessionTrace, ...],
    run_config: RunConfig,
) -> SliceDiscoveryResult:
    """Discover deterministic failure slices from recommender trace evidence."""
    del run_config
    trace_lookup = {trace.trace_id: trace for trace in traces}
    trace_inputs = tuple(
        SliceTraceInput(
            trace_score=score,
            features=extract_recommender_slice_features(
                trace_score=score,
                trace=trace_lookup[score.trace_id],
            ),
        )
        for score in scored_traces
        if score.trace_id in trace_lookup
    )
    return discover_slices(
        trace_inputs,
        summarize_slice=_summarize_recommender_slice,
        top_limit=5,
    )


def extract_recommender_slice_features(
    *,
    trace_score: TraceScore,
    trace: SessionTrace,
) -> tuple[SliceFeature, ...]:
    """Extract readable bucketed slice features from one recommender trace."""
    scenario_profile = ""
    if trace.steps:
        scenario_profile = trace.steps[0].observation.scenario_context.runtime_profile or "unspecified"
    features = [
        SliceFeature("scenario_profile", scenario_profile or "unspecified"),
        SliceFeature("scenario_name", trace.scenario_name),
        SliceFeature("archetype", trace.agent_seed.archetype_label),
        SliceFeature("dominant_failure_mode", trace_score.dominant_failure_mode),
        SliceFeature("abandoned", str(trace_score.abandoned).lower()),
        SliceFeature(
            "abandoned_early",
            str(bool(trace_score.abandoned and (trace_score.abandonment_step or 99) <= 2)).lower(),
        ),
        SliceFeature("utility_bucket", _utility_bucket(trace_score.session_utility)),
        SliceFeature("trust_delta_bucket", _trust_delta_bucket(trace_score.trust_delta)),
        SliceFeature("skip_rate_bucket", _skip_rate_bucket(trace_score.skip_rate)),
        SliceFeature("repetition_bucket", _repetition_bucket(trace_score.repetition)),
        SliceFeature("concentration_bucket", _concentration_bucket(trace_score.concentration)),
        SliceFeature(
            "genre_alignment_bucket",
            _genre_alignment_bucket(trace_score.genre_alignment_rate),
        ),
        SliceFeature(
            "novelty_intensity_bucket",
            _novelty_intensity_bucket(trace_score.novelty_intensity),
        ),
        SliceFeature(
            "first_impression_bucket",
            _first_impression_bucket(trace_score.first_impression_score),
        ),
        SliceFeature(
            "abandonment_pressure_bucket",
            _abandonment_pressure_bucket(trace_score.abandonment_pressure),
        ),
    ]
    return tuple(features)


def _summarize_recommender_slice(
    feature_signature: tuple[str, ...],
    scores: tuple[TraceScore, ...],
) -> SliceSummary:
    abandonment_rate = _mean(1.0 if score.abandoned else 0.0 for score in scores)
    mean_session_utility = _mean(score.session_utility for score in scores)
    mean_frustration_delta = _mean(score.frustration_delta for score in scores)
    mean_trust_delta = _mean(score.trust_delta for score in scores)
    mean_stale_exposure_rate = _mean(score.stale_exposure_rate for score in scores)
    mean_concentration = _mean(score.concentration for score in scores)
    mean_first_impression_score = _mean(score.first_impression_score for score in scores)
    mean_abandonment_pressure = _mean(score.abandonment_pressure for score in scores)
    mean_skip_rate = _mean(score.skip_rate for score in scores)
    mean_trace_risk_score = _mean(score.trace_risk_score for score in scores)
    slice_failure_mode = dominant_failure_mode(scores)
    risk_score = aggregate_risk_score(
        abandonment_rate=abandonment_rate,
        mean_session_utility=mean_session_utility,
        mean_frustration_delta=mean_frustration_delta,
        mean_trust_delta=mean_trust_delta,
        mean_stale_exposure_rate=mean_stale_exposure_rate,
        mean_concentration=mean_concentration,
        mean_first_impression_score=mean_first_impression_score,
        mean_abandonment_pressure=mean_abandonment_pressure,
        trace_scores=scores,
    )
    representative_trace_ids = tuple(
        score.trace_id
        for score in sorted(
            scores,
            key=lambda score: (score.trace_risk_score, -score.session_utility),
            reverse=True,
        )[:3]
    )
    return SliceSummary(
        slice_id=build_slice_id(feature_signature),
        feature_signature=feature_signature,
        trace_count=len(scores),
        risk_level=risk_level_for_score(risk_score),
        dominant_failure_mode=slice_failure_mode,
        abandonment_rate=round(abandonment_rate, 6),
        mean_session_utility=round(mean_session_utility, 6),
        mean_trust_delta=round(mean_trust_delta, 6),
        mean_skip_rate=round(mean_skip_rate, 6),
        mean_trace_risk_score=round(mean_trace_risk_score, 6),
        representative_trace_ids=representative_trace_ids,
    )


def _utility_bucket(value: float) -> str:
    if value < 0.45:
        return "low"
    if value < 0.62:
        return "medium"
    return "high"


def _trust_delta_bucket(value: float) -> str:
    if value <= -0.25:
        return "strong_drop"
    if value <= -0.08:
        return "drop"
    if value >= 0.08:
        return "gain"
    return "stable"


def _skip_rate_bucket(value: float) -> str:
    if value >= 0.67:
        return "high"
    if value >= 0.34:
        return "medium"
    return "low"


def _repetition_bucket(value: float) -> str:
    if value >= 0.34:
        return "high"
    if value >= 0.15:
        return "medium"
    return "low"


def _concentration_bucket(value: float) -> str:
    if value >= 0.65:
        return "high"
    if value >= 0.45:
        return "medium"
    return "low"


def _genre_alignment_bucket(value: float) -> str:
    if value == 0.0:
        return "none"
    if value < 0.35:
        return "low"
    if value < 0.7:
        return "medium"
    return "high"


def _novelty_intensity_bucket(value: float) -> str:
    if value >= 0.65:
        return "high"
    if value >= 0.35:
        return "medium"
    return "low"


def _first_impression_bucket(value: float) -> str:
    if value < 0.35:
        return "weak"
    if value < 0.6:
        return "mixed"
    return "strong"


def _abandonment_pressure_bucket(value: float) -> str:
    if value >= 0.6:
        return "high"
    if value >= 0.3:
        return "medium"
    return "low"


def _mean(values) -> float:
    values = tuple(values)
    if not values:
        return 0.0
    return sum(values) / len(values)
