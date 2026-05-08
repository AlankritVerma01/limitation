"""Deterministic trace scoring for search interaction audits."""

from __future__ import annotations

import re
from collections import Counter

from ...schema import FailureMode, ScoringConfig, SessionTrace, TraceScore

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_EXPECTED_TYPE_MIX: dict[str, dict[str, float]] = {
    "navigational": {"navigational": 0.75, "help": 0.25},
    "informational-long-tail": {"article": 0.8, "help": 0.2},
    "time-sensitive": {"news": 0.75, "article": 0.25},
    "ambiguous": {"article": 0.45, "review": 0.35, "navigational": 0.2},
    "typo": {"help": 0.6, "article": 0.4},
    "zero-result": {},
    "personalized-vs-anonymous": {"article": 0.75, "commerce": 0.25},
}


class SearchJudge:
    """Scores a completed search trace using deterministic ranked-list diagnostics."""

    def score_trace(
        self,
        session_trace: SessionTrace,
        scoring_config: ScoringConfig,
    ) -> TraceScore:
        del scoring_config
        ranked_lists = [step.ranked_list for step in session_trace.steps]
        exposures = [item for ranked_list in ranked_lists for item in ranked_list.items]
        click_count = sum(step.action.name == "click" for step in session_trace.steps)
        skip_count = sum(step.action.name == "skip" for step in session_trace.steps)
        engagement = (
            click_count / session_trace.completed_steps
            if session_trace.completed_steps
            else 0.0
        )
        skip_rate = (
            skip_count / session_trace.completed_steps
            if session_trace.completed_steps
            else 0.0
        )
        runtime_profile = _runtime_profile(session_trace)
        query = _query(session_trace)

        top_bucket_relevance = _mean(
            item.score for ranked_list in ranked_lists for item in ranked_list.items[:3]
        )
        tail_bucket_relevance = _mean(
            item.score for ranked_list in ranked_lists for item in ranked_list.items[3:]
        )
        freshness_percentile = _mean(_freshness_score(item) for item in exposures)
        intra_list_diversity = _mean(
            _diversity(ranked_list.items, runtime_profile)
            for ranked_list in ranked_lists
        )
        type_mix_distance = _type_mix_distance(exposures, runtime_profile)
        snippet_query_overlap = _mean(_snippet_overlap(item, query) for item in exposures)
        zero_result_rate = _mean(
            1.0 if not ranked_list.items else 0.0 for ranked_list in ranked_lists
        )
        mean_click_quality = _mean(_clicked_result_scores(session_trace))

        if runtime_profile == "zero-result":
            search_quality = 1.0 if zero_result_rate == 1.0 else 0.0
        else:
            search_quality = (
                (0.38 * top_bucket_relevance)
                + (0.2 * snippet_query_overlap)
                + (0.17 * freshness_percentile)
                + (0.15 * intra_list_diversity)
                + (0.1 * (1.0 - type_mix_distance))
            )
        dominant_failure_mode = _classify_failure_mode(
            session_trace=session_trace,
            runtime_profile=runtime_profile,
            search_quality=search_quality,
            top_bucket_relevance=top_bucket_relevance,
            snippet_query_overlap=snippet_query_overlap,
            intra_list_diversity=intra_list_diversity,
            zero_result_rate=zero_result_rate,
        )
        trace_risk_score = _trace_risk_score(
            session_trace=session_trace,
            search_quality=search_quality,
            runtime_profile=runtime_profile,
            type_mix_distance=type_mix_distance,
            zero_result_rate=zero_result_rate,
            dominant_failure_mode=dominant_failure_mode,
        )
        domain_metrics = {
            "top_bucket_relevance": round(top_bucket_relevance, 6),
            "tail_bucket_relevance": round(tail_bucket_relevance, 6),
            "freshness_percentile": round(freshness_percentile, 6),
            "intra_list_diversity": round(intra_list_diversity, 6),
            "type_mix_distance": round(type_mix_distance, 6),
            "snippet_query_overlap": round(snippet_query_overlap, 6),
            "zero_result_rate": round(zero_result_rate, 6),
            "mean_click_quality": round(mean_click_quality, 6),
            "search_quality": round(search_quality, 6),
            "trace_risk_score": round(trace_risk_score, 6),
            "dominant_failure_mode": dominant_failure_mode,
        }
        final_state = session_trace.steps[-1].agent_state_after if session_trace.steps else None
        frustration = final_state.frustration if final_state else 0.0
        return TraceScore(
            trace_id=session_trace.trace_id,
            scenario_name=session_trace.scenario_name,
            archetype_label=session_trace.agent_seed.archetype_label,
            steps_completed=session_trace.completed_steps,
            abandoned=session_trace.abandoned,
            click_count=click_count,
            session_utility=float(domain_metrics["search_quality"]),
            repetition=0.0,
            concentration=type_mix_distance,
            engagement=round(engagement, 6),
            frustration=round(frustration, 6),
            abandonment_step=session_trace.completed_steps
            if session_trace.abandoned
            else None,
            mean_click_quality=float(domain_metrics["mean_click_quality"]),
            mean_top_candidate_utility=float(domain_metrics["top_bucket_relevance"]),
            skip_rate=round(skip_rate, 6),
            dominant_failure_mode=dominant_failure_mode,
            trace_risk_score=float(domain_metrics["trace_risk_score"]),
            failure_evidence_summary=_evidence_summary(
                dominant_failure_mode=dominant_failure_mode,
                search_quality=float(domain_metrics["search_quality"]),
                top_bucket_relevance=float(domain_metrics["top_bucket_relevance"]),
                snippet_query_overlap=float(domain_metrics["snippet_query_overlap"]),
                type_mix_distance=float(domain_metrics["type_mix_distance"]),
                zero_result_rate=float(domain_metrics["zero_result_rate"]),
            ),
            domain_metrics=domain_metrics,
        )


def _classify_failure_mode(
    *,
    session_trace: SessionTrace,
    runtime_profile: str,
    search_quality: float,
    top_bucket_relevance: float,
    snippet_query_overlap: float,
    intra_list_diversity: float,
    zero_result_rate: float,
) -> FailureMode:
    if runtime_profile == "zero-result" and zero_result_rate == 1.0:
        return "no_major_failure"
    if session_trace.abandoned:
        return "early_abandonment"
    if runtime_profile == "zero-result" and zero_result_rate < 1.0:
        return "low_relevance"
    if top_bucket_relevance < 0.45 or snippet_query_overlap < 0.15:
        return "low_relevance"
    if runtime_profile == "ambiguous" and intra_list_diversity < 0.45:
        return "over_repetition"
    if search_quality < 0.5:
        return "low_relevance"
    return "no_major_failure"


def _trace_risk_score(
    *,
    session_trace: SessionTrace,
    search_quality: float,
    runtime_profile: str,
    type_mix_distance: float,
    zero_result_rate: float,
    dominant_failure_mode: FailureMode,
) -> float:
    score = max(0.0, 1.0 - search_quality) * 0.58
    score += type_mix_distance * 0.22
    zero_result_success = runtime_profile == "zero-result" and zero_result_rate == 1.0
    if session_trace.abandoned and not zero_result_success:
        score += 0.25
    if zero_result_rate == 1.0 and _runtime_profile(session_trace) != "zero-result":
        score += 0.25
    if dominant_failure_mode != "no_major_failure":
        score += 0.12
    return min(1.0, score)


def _runtime_profile(session_trace: SessionTrace) -> str:
    if not session_trace.steps:
        return ""
    return session_trace.steps[0].observation.scenario_context.runtime_profile


def _query(session_trace: SessionTrace) -> str:
    if not session_trace.steps:
        return ""
    context = session_trace.steps[0].observation.scenario_context
    return context.context_hint or context.description or context.scenario_name


def _freshness_score(item) -> float:
    value = item.metadata.get("freshness_score", 0.0)
    return float(value) if isinstance(value, (int, float)) else 0.0


def _clicked_result_scores(session_trace: SessionTrace) -> tuple[float, ...]:
    scores: list[float] = []
    for step in session_trace.steps:
        selected_item_id = step.action.selected_item_id
        if step.action.name != "click" or selected_item_id is None:
            continue
        clicked = next(
            (
                item
                for item in step.ranked_list.items
                if item.item_id == selected_item_id
            ),
            None,
        )
        if clicked is not None:
            scores.append(clicked.score)
    return tuple(scores)


def _diversity(items, runtime_profile: str) -> float:
    if not items:
        return 0.0
    types = {item.item_type or "unknown" for item in items}
    required_interpretations = 3 if runtime_profile == "ambiguous" else len(items)
    return len(types) / max(len(items), required_interpretations)


def _type_mix_distance(items, runtime_profile: str) -> float:
    if not items:
        return 0.0 if runtime_profile == "zero-result" else 1.0
    expected = _EXPECTED_TYPE_MIX.get(runtime_profile, {})
    if not expected:
        return 0.0
    counts = Counter(item.item_type or "unknown" for item in items)
    total = sum(counts.values())
    observed = {key: count / total for key, count in counts.items()}
    all_types = set(expected) | set(observed)
    return sum(abs(observed.get(key, 0.0) - expected.get(key, 0.0)) for key in all_types) / 2


def _snippet_overlap(item, query: str) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    snippet = item.metadata.get("snippet", "")
    title = item.title
    result_tokens = _tokens(f"{title} {snippet}")
    return len(query_tokens & result_tokens) / len(query_tokens)


def _tokens(value: str) -> set[str]:
    return set(_TOKEN_RE.findall(value.lower()))


def _mean(values) -> float:
    values = tuple(values)
    if not values:
        return 0.0
    return sum(values) / len(values)


def _evidence_summary(
    *,
    dominant_failure_mode: FailureMode,
    search_quality: float,
    top_bucket_relevance: float,
    snippet_query_overlap: float,
    type_mix_distance: float,
    zero_result_rate: float,
) -> str:
    return (
        f"{dominant_failure_mode}: search_quality={search_quality:.3f}, "
        f"top_bucket_relevance={top_bucket_relevance:.3f}, "
        f"snippet_query_overlap={snippet_query_overlap:.3f}, "
        f"type_mix_distance={type_mix_distance:.3f}, "
        f"zero_result_rate={zero_result_rate:.3f}"
    )
