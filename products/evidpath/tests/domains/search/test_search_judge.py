"""Tests for deterministic search trace scoring."""

from __future__ import annotations

from evidpath.domains.search import SearchJudge
from evidpath.schema import (
    Action,
    AgentSeed,
    AgentState,
    Observation,
    RankedItem,
    RankedList,
    ScenarioContext,
    ScoringConfig,
    SessionTrace,
    TraceStep,
    trace_metric,
)


def test_search_judge_scores_relevance_freshness_diversity_and_snippet_overlap() -> None:
    score = SearchJudge().score_trace(
        _trace(
            runtime_profile="time-sensitive",
            query="current weather alerts toronto",
            items=(
                _item(
                    "r1",
                    "Weather Alerts",
                    "Current weather warnings for Toronto.",
                    "news",
                    0.94,
                    1,
                    freshness_score=0.97,
                ),
                _item(
                    "r2",
                    "Toronto Forecast",
                    "Hourly weather details and radar.",
                    "article",
                    0.72,
                    2,
                    freshness_score=0.8,
                ),
            ),
        ),
        ScoringConfig(),
    )

    assert trace_metric(score, "top_bucket_relevance") == 0.83
    assert trace_metric(score, "freshness_percentile") == 0.885
    assert trace_metric(score, "intra_list_diversity") == 1.0
    assert trace_metric(score, "snippet_query_overlap") > 0.6
    assert score.mean_click_quality == 0.0
    assert score.dominant_failure_mode == "no_major_failure"


def test_search_judge_rewards_zero_result_scenario_with_empty_results() -> None:
    score = SearchJudge().score_trace(
        _trace(runtime_profile="zero-result", query="zzzz qqqq", items=()),
        ScoringConfig(),
    )

    assert score.session_utility == 1.0
    assert trace_metric(score, "zero_result_rate") == 1.0
    assert score.dominant_failure_mode == "no_major_failure"
    assert score.trace_risk_score == 0.0


def test_search_judge_treats_empty_zero_result_abandonment_as_success() -> None:
    score = SearchJudge().score_trace(
        _trace(
            runtime_profile="zero-result",
            query="zzzz qqqq",
            items=(),
            action_name="abandon",
            abandoned=True,
        ),
        ScoringConfig(),
    )

    assert score.abandoned is True
    assert trace_metric(score, "zero_result_rate") == 1.0
    assert score.dominant_failure_mode == "no_major_failure"
    assert score.trace_risk_score == 0.0


def test_search_judge_reports_click_quality_from_clicked_result() -> None:
    score = SearchJudge().score_trace(
        _trace(
            runtime_profile="time-sensitive",
            query="current weather alerts toronto",
            items=(
                _item(
                    "r1",
                    "Weather Alerts",
                    "Current weather warnings for Toronto.",
                    "news",
                    0.94,
                    1,
                    freshness_score=0.97,
                ),
                _item(
                    "r2",
                    "Toronto Forecast",
                    "Hourly weather details and radar.",
                    "article",
                    0.72,
                    2,
                    freshness_score=0.8,
                ),
            ),
            action_name="click",
            selected_item_id="r2",
        ),
        ScoringConfig(),
    )

    assert score.click_count == 1
    assert score.mean_click_quality == 0.72
    assert trace_metric(score, "mean_click_quality") == 0.72


def test_search_judge_flags_non_zero_results_for_zero_result_scenario() -> None:
    score = SearchJudge().score_trace(
        _trace(
            runtime_profile="zero-result",
            query="zzzz qqqq",
            items=(
                _item(
                    "r1",
                    "Unrelated",
                    "Generic fallback result.",
                    "article",
                    0.2,
                    1,
                    freshness_score=0.2,
                ),
            ),
        ),
        ScoringConfig(),
    )

    assert score.dominant_failure_mode == "low_relevance"
    assert score.trace_risk_score > 0.5


def test_search_judge_flags_collapsed_ambiguous_single_result_list() -> None:
    score = SearchJudge().score_trace(
        _trace(
            runtime_profile="ambiguous",
            query="jaguar",
            items=(
                _item(
                    "r1",
                    "Jaguar Electric SUV Review",
                    "Specs and buying advice for the latest Jaguar electric SUV.",
                    "review",
                    0.97,
                    1,
                    freshness_score=0.8,
                ),
            ),
        ),
        ScoringConfig(),
    )

    assert trace_metric(score, "intra_list_diversity") == 0.333333
    assert score.dominant_failure_mode == "over_repetition"


def _trace(
    *,
    runtime_profile: str,
    query: str,
    items: tuple[RankedItem, ...],
    action_name: str = "skip",
    selected_item_id: str | None = None,
    abandoned: bool = False,
) -> SessionTrace:
    context = ScenarioContext(
        scenario_name=f"{runtime_profile}-query",
        history_depth=0,
        history_item_ids=(),
        description="",
        scenario_id=f"{runtime_profile}-query",
        runtime_profile=runtime_profile,
        context_hint=query,
    )
    observation = Observation(
        session_id="session-1",
        step_index=0,
        max_steps=1,
        available_actions=("click", "skip", "abandon"),
        scenario_context=context,
    )
    before = _state()
    after = _state()
    ranked_list = RankedList(
        slate_id="ranked-list-1",
        step_index=0,
        items=items,
    )
    return SessionTrace(
        trace_id="trace-1",
        seed=0,
        agent_seed=_agent_seed(),
        scenario_name=context.scenario_name,
        scenario_id=context.scenario_id,
        steps=(
            TraceStep(
                step_index=0,
                observation=observation,
                ranked_list=ranked_list,
                action=Action(
                    name=action_name,
                    selected_item_id=selected_item_id,
                    reason="test fixture",
                ),
                agent_state_before=before,
                agent_state_after=after,
            ),
        ),
        abandoned=abandoned,
        completed_steps=1,
    )


def _item(
    item_id: str,
    title: str,
    snippet: str,
    item_type: str,
    score: float,
    rank: int,
    *,
    freshness_score: float,
) -> RankedItem:
    return RankedItem(
        item_id=item_id,
        title=title,
        genre="",
        score=score,
        rank=rank,
        popularity=0.0,
        novelty=0.0,
        item_type=item_type,
        metadata={
            "snippet": snippet,
            "url": f"https://example.com/{item_id}",
            "freshness_score": freshness_score,
        },
    )


def _agent_seed() -> AgentSeed:
    return AgentSeed(
        agent_id="agent-1",
        archetype_label="searcher",
        preferred_genres=("news",),
        popularity_preference=0.5,
        novelty_preference=0.5,
        repetition_tolerance=0.5,
        sparse_history_confidence=0.5,
        abandonment_sensitivity=0.5,
        patience=1,
        engagement_baseline=0.5,
        quality_sensitivity=0.5,
        repeat_exposure_penalty=0.1,
        novelty_fatigue=0.1,
        frustration_recovery=0.2,
        history_reliance=0.5,
        skip_tolerance=1,
        abandonment_threshold=0.8,
    )


def _state() -> AgentState:
    return AgentState(
        agent_id="agent-1",
        archetype_label="searcher",
        step_index=0,
        click_threshold=0.5,
        preferred_genres=("news",),
        popularity_preference=0.5,
        novelty_preference=0.5,
        repetition_tolerance=0.5,
        sparse_history_confidence=0.5,
        abandonment_sensitivity=0.5,
        engagement_baseline=0.5,
        quality_sensitivity=0.5,
        repeat_exposure_penalty=0.1,
        novelty_fatigue=0.1,
        frustration_recovery=0.2,
        history_reliance=0.5,
        skip_tolerance=1,
        abandonment_threshold=0.8,
        patience_remaining=1,
        last_action="start",
    )
