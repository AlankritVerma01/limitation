from __future__ import annotations

import json
import random
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from evidpath.audit import (
    execute_recommender_audit,
    run_recommender_audit,
    write_run_artifacts,
)
from evidpath.cli import main
from evidpath.domains.recommender import (
    HttpNativeDriverConfig,
    HttpNativeRecommenderDriver,
    RecommenderAgentPolicy,
    RecommenderAnalyzer,
    RecommenderJudge,
    build_recommender_run_config,
    build_scenarios,
    build_seeded_archetypes,
    ensure_reference_artifacts,
    initial_state_from_seed,
    normalize_runtime_item_signals,
    project_recommender_population,
    project_recommender_scenarios,
    resolve_built_in_recommender_scenarios,
    run_mock_recommender_service,
    run_reference_recommender_service,
)
from evidpath.population_generation import generate_population_pack
from evidpath.reporting.json import JsonReportWriter
from evidpath.reporting.markdown import MarkdownReportWriter
from evidpath.rollout.engine import run_rollouts
from evidpath.scenario_generation import (
    build_scenario_pack,
    generate_scenario_pack,
)
from evidpath.schema import (
    Action,
    CohortSummary,
    DecisionExplanation,
    Observation,
    RiskFlag,
    RolloutConfig,
    RunConfig,
    RunResult,
    ScenarioConfig,
    ScenarioContext,
    ScoringConfig,
    SessionTrace,
    Slate,
    SlateItem,
    TraceScore,
    TraceStep,
    UtilityBreakdown,
)


def _build_recommender_run_config_only(**kwargs) -> RunConfig:
    run_config, _resolved_inputs = build_recommender_run_config(**kwargs)
    return run_config


def test_schema_objects_are_dataclass_serialization_friendly() -> None:
    run_config = RunConfig(
        run_name="test",
        scenarios=(
            ScenarioConfig(
                name="returning-user-home-feed",
                max_steps=5,
                allowed_actions=("click", "skip", "abandon"),
                history_depth=4,
                description="returning user",
            ),
        ),
        rollout=RolloutConfig(
            seed=0,
            output_dir="tmp",
            service_mode="mock",
            service_artifact_dir=None,
            adapter_base_url=None,
            service_timeout_seconds=2.0,
        ),
        scoring=ScoringConfig(),
        agent_seeds=build_seeded_archetypes(),
    )
    payload = asdict(run_config)
    assert payload["run_name"] == "test"
    assert len(payload["agent_seeds"]) == 4
    assert payload["scenarios"][0]["name"] == "returning-user-home-feed"


def test_http_adapter_normalizes_service_response() -> None:
    run_config = _build_recommender_run_config_only(
        seed=4,
        scenario_names=("returning-user-home-feed",),
    )
    scenario = build_scenarios(run_config.scenarios)[0]
    agent_seed = run_config.agent_seeds[0]
    observation = scenario.initialize(agent_seed, run_config)
    state = initial_state_from_seed(agent_seed, observation.scenario_context)
    with run_mock_recommender_service() as base_url:
        adapter = HttpNativeRecommenderDriver(
            HttpNativeDriverConfig(base_url=base_url, timeout_seconds=2.0)
        )
        slate = adapter.get_slate(state, observation, run_config.scenarios[0])
    assert isinstance(slate, Slate)
    assert len(slate.items) == 5
    assert slate.items[0].rank == 1


def test_recommender_run_config_uses_product_run_name() -> None:
    run_config = _build_recommender_run_config_only()
    assert run_config.run_name == "evidpath-audit"


def test_unknown_scenario_names_raise_clear_error() -> None:
    try:
        _build_recommender_run_config_only(scenario_names=("unknown-scenario",))
    except ValueError as exc:
        assert "Unknown scenario names" in str(exc)
    else:
        raise AssertionError(
            "Expected recommender run config builder to reject unknown scenarios."
        )


def test_scenarios_initialize_differently() -> None:
    run_config = _build_recommender_run_config_only(seed=3)
    scenarios = {
        scenario.name: scenario for scenario in build_scenarios(run_config.scenarios)
    }
    agent_seed = run_config.agent_seeds[0]
    returning = scenarios["returning-user-home-feed"].initialize(agent_seed, run_config)
    sparse = scenarios["sparse-history-home-feed"].initialize(agent_seed, run_config)
    assert (
        returning.scenario_context.history_depth > sparse.scenario_context.history_depth
    )
    assert (
        returning.scenario_context.scenario_name
        != sparse.scenario_context.scenario_name
    )


def test_agent_responses_differ_by_archetype() -> None:
    policy = RecommenderAgentPolicy()
    context = ScenarioContext(
        scenario_name="returning-user-home-feed",
        history_depth=4,
        history_item_ids=("action-1", "action-2"),
        description="returning",
    )
    observation = Observation(
        session_id="session",
        step_index=0,
        max_steps=5,
        available_actions=("click", "skip", "abandon"),
        scenario_context=context,
    )
    slate = Slate(
        slate_id="s-1",
        step_index=0,
        items=(
            SlateItem(
                "popular-action", "Popular Action", "action", 0.79, 1, 0.95, 0.12
            ),
            SlateItem("indie-doc", "Indie Doc", "documentary", 0.49, 2, 0.22, 0.88),
            SlateItem("genre-horror", "Genre Horror", "horror", 0.58, 3, 0.31, 0.76),
        ),
    )
    import random

    mainstream = initial_state_from_seed(build_seeded_archetypes()[0], context)
    explorer = initial_state_from_seed(build_seeded_archetypes()[1], context)
    scenario_config = ScenarioConfig(
        name=context.scenario_name,
        max_steps=5,
        allowed_actions=("click", "skip", "abandon"),
        history_depth=4,
        description="returning",
    )
    mainstream_decision = policy.choose_action(
        mainstream,
        slate,
        observation,
        scenario_config,
        random.Random(7),
    )
    explorer_decision = policy.choose_action(
        explorer,
        slate,
        observation,
        scenario_config,
        random.Random(7),
    )
    assert mainstream_decision.action != explorer_decision.action


def test_runtime_item_signal_normalization_is_deterministic() -> None:
    slate = Slate(
        slate_id="s-1",
        step_index=0,
        items=(
            SlateItem(
                "popular-action", "Popular Action", "action", 0.79, 1, 0.95, 0.12
            ),
            SlateItem("indie-doc", "Indie Doc", "documentary", 0.49, 2, 0.22, 0.88),
        ),
    )
    first = normalize_runtime_item_signals(slate)
    second = normalize_runtime_item_signals(slate)
    assert first == second
    assert first[0].familiarity_signal == 0.95
    assert first[1].quality_signal == 0.49


def test_same_archetype_behaves_differently_across_scenarios() -> None:
    policy = RecommenderAgentPolicy()
    returning_context = ScenarioContext(
        scenario_name="returning-user-home-feed",
        history_depth=4,
        history_item_ids=("action-1", "comedy-1", "family-1"),
        description="returning",
    )
    sparse_context = ScenarioContext(
        scenario_name="sparse-history-home-feed",
        history_depth=1,
        history_item_ids=("action-1",),
        description="sparse",
    )
    returning_observation = Observation(
        session_id="returning-session",
        step_index=0,
        max_steps=5,
        available_actions=("click", "skip", "abandon"),
        scenario_context=returning_context,
    )
    sparse_observation = Observation(
        session_id="sparse-session",
        step_index=0,
        max_steps=5,
        available_actions=("click", "skip", "abandon"),
        scenario_context=sparse_context,
    )
    scenario_config = ScenarioConfig(
        name="returning-user-home-feed",
        max_steps=5,
        allowed_actions=("click", "skip", "abandon"),
        history_depth=4,
        description="session",
    )
    slate = Slate(
        slate_id="s-2",
        step_index=0,
        items=(
            SlateItem("safe-drama", "Safe Drama", "drama", 0.64, 1, 0.97, 0.1),
            SlateItem("quirky-indie", "Quirky Indie", "indie", 0.52, 2, 0.28, 0.82),
        ),
    )
    seed = build_seeded_archetypes()[0]
    returning_state = initial_state_from_seed(seed, returning_context)
    sparse_state = initial_state_from_seed(seed, sparse_context)
    returning_decision = policy.choose_action(
        returning_state,
        slate,
        returning_observation,
        scenario_config,
        random.Random(5),
    )
    sparse_decision = policy.choose_action(
        sparse_state,
        slate,
        sparse_observation,
        scenario_config,
        random.Random(5),
    )
    assert returning_decision.action != sparse_decision.action


def test_judge_scores_handcrafted_trace() -> None:
    context = ScenarioContext(
        scenario_name="returning-user-home-feed",
        history_depth=4,
        history_item_ids=("action-1",),
        description="returning",
    )
    observation = Observation(
        session_id="s-1",
        step_index=0,
        max_steps=5,
        available_actions=("click", "skip", "abandon"),
        scenario_context=context,
    )
    state = initial_state_from_seed(build_seeded_archetypes()[0], context)
    clicked_state = state.__class__(
        **{
            **state.__dict__,
            "step_index": 1,
            "last_action": "click",
            "clicked_item_ids": ("popular-action",),
            "recent_exposure_ids": ("popular-action", "popular-action"),
            "satisfaction": 0.6,
            "frustration": 0.1,
        }
    )
    slate = Slate(
        slate_id="s-1",
        step_index=0,
        items=(
            SlateItem(
                "popular-action", "Popular Action", "action", 0.82, 1, 0.96, 0.08
            ),
            SlateItem(
                "popular-action", "Popular Action", "action", 0.82, 2, 0.96, 0.08
            ),
            SlateItem("safe-comedy", "Safe Comedy", "comedy", 0.74, 3, 0.84, 0.15),
        ),
    )
    trace = SessionTrace(
        trace_id="trace-1",
        seed=1,
        agent_seed=build_seeded_archetypes()[0],
        scenario_name=context.scenario_name,
        steps=(
            TraceStep(
                step_index=0,
                observation=observation,
                slate=slate,
                action=Action("click", "popular-action", "manual"),
                agent_state_before=state,
                agent_state_after=clicked_state,
            ),
        ),
        abandoned=False,
        completed_steps=1,
    )
    score = RecommenderJudge().score_trace(trace, ScoringConfig())
    assert score.concentration > 0.5
    assert score.repetition > 0.0
    assert score.session_utility > 0.0
    assert score.dominant_failure_mode == "no_major_failure"
    assert score.trust_delta == 0.0


def test_judge_classifies_trust_collapse_and_deltas() -> None:
    context = ScenarioContext(
        scenario_name="returning-user-home-feed",
        history_depth=4,
        history_item_ids=("action-1",),
        description="returning",
    )
    observation = Observation(
        session_id="s-2",
        step_index=0,
        max_steps=5,
        available_actions=("click", "skip", "abandon"),
        scenario_context=context,
    )
    initial_state = initial_state_from_seed(build_seeded_archetypes()[1], context)
    collapsed_state = initial_state.__class__(
        **{
            **initial_state.__dict__,
            "step_index": 3,
            "last_action": "abandon",
            "skipped_steps": 2,
            "trust": 0.34,
            "confidence": 0.48,
            "frustration": 0.31,
        }
    )
    trace = SessionTrace(
        trace_id="trace-trust-collapse",
        seed=11,
        agent_seed=build_seeded_archetypes()[1],
        scenario_name=context.scenario_name,
        steps=(
            TraceStep(
                step_index=0,
                observation=observation,
                slate=Slate(
                    slate_id="s-2",
                    step_index=0,
                    items=(
                        SlateItem("item-1", "Item 1", "romance", 0.31, 1, 0.84, 0.11),
                        SlateItem("item-2", "Item 2", "drama", 0.28, 2, 0.78, 0.12),
                    ),
                ),
                action=Action("skip", None, "no_item_above_threshold"),
                agent_state_before=initial_state,
                agent_state_after=collapsed_state,
                decision_explanation=DecisionExplanation(
                    chosen_item_id=None,
                    top_candidate_item_id="item-1",
                    action_threshold=0.7,
                    chosen_utility=0.0,
                    top_candidate_utility=0.33,
                    dominant_component="base_relevance",
                    top_candidate_breakdown=UtilityBreakdown(
                        base_relevance=0.31,
                        affinity=0.0,
                        familiarity=0.02,
                        novelty=0.01,
                        quality=0.0,
                        repetition_penalty=0.0,
                        scenario_adjustment=-0.03,
                        confidence_adjustment=0.02,
                        jitter=0.0,
                        total=0.33,
                    ),
                    reason="trust_collapsed",
                ),
                state_delta_summary="trust 0.71->0.34, confidence 0.69->0.48, frustration 0.00->0.31",
            ),
        ),
        abandoned=True,
        completed_steps=1,
    )
    score = RecommenderJudge().score_trace(trace, ScoringConfig())
    assert score.dominant_failure_mode == "early_abandonment"
    assert score.trust_delta < 0.0
    assert score.failure_evidence_summary.startswith("abandoned at step 1")


def test_repeated_low_fit_slates_can_trigger_abandonment() -> None:
    policy = RecommenderAgentPolicy()
    context = ScenarioContext(
        scenario_name="returning-user-home-feed",
        history_depth=4,
        history_item_ids=("action-1", "comedy-1"),
        description="returning",
    )
    observation = Observation(
        session_id="session",
        step_index=2,
        max_steps=5,
        available_actions=("click", "skip", "abandon"),
        scenario_context=context,
    )
    scenario_config = ScenarioConfig(
        name=context.scenario_name,
        max_steps=5,
        allowed_actions=("click", "skip", "abandon"),
        history_depth=4,
        description="returning",
    )
    low_patience = initial_state_from_seed(build_seeded_archetypes()[3], context)
    degraded_state = low_patience.__class__(
        **{
            **low_patience.__dict__,
            "patience_remaining": 1,
            "skipped_steps": 1,
            "frustration": 0.68,
            "trust": 0.16,
            "recent_exposure_ids": ("slow-drama", "slow-drama", "slow-drama"),
        }
    )
    slate = Slate(
        slate_id="poor-fit",
        step_index=2,
        items=(
            SlateItem("slow-drama", "Slow Drama", "drama", 0.34, 1, 0.61, 0.14),
            SlateItem("obscure-doc", "Obscure Doc", "documentary", 0.28, 2, 0.12, 0.93),
        ),
    )
    decision = policy.choose_action(
        degraded_state,
        slate,
        observation,
        scenario_config,
        random.Random(11),
    )
    assert decision.action.name == "abandon"
    assert decision.explanation.reason == "trust_collapsed"


def test_analyzer_groups_and_ranks_risks() -> None:
    analyzer = RecommenderAnalyzer()
    run_config = _build_recommender_run_config_only(
        seed=2,
        scenario_names=("returning-user-home-feed",),
    )
    traces = (
        SessionTrace(
            trace_id="trace-a",
            seed=1,
            agent_seed=build_seeded_archetypes()[3],
            scenario_name="returning-user-home-feed",
            steps=(),
            abandoned=True,
            completed_steps=1,
        ),
        SessionTrace(
            trace_id="trace-b",
            seed=2,
            agent_seed=build_seeded_archetypes()[3],
            scenario_name="returning-user-home-feed",
            steps=(),
            abandoned=False,
            completed_steps=5,
        ),
    )
    scores = (
        TraceScore(
            trace_id="trace-a",
            scenario_name="returning-user-home-feed",
            archetype_label="Low-patience",
            steps_completed=1,
            abandoned=True,
            click_count=0,
            session_utility=0.2,
            repetition=0.3,
            concentration=0.9,
            engagement=0.0,
            frustration=0.8,
            trust_delta=-0.4,
            confidence_delta=-0.2,
            frustration_delta=0.8,
            skip_rate=1.0,
            dominant_failure_mode="trust_collapse",
            trace_risk_score=0.92,
            failure_evidence_summary="abandoned at step 1 after trust fell 0.70->0.30",
        ),
        TraceScore(
            trace_id="trace-b",
            scenario_name="returning-user-home-feed",
            archetype_label="Low-patience",
            steps_completed=5,
            abandoned=False,
            click_count=3,
            session_utility=0.74,
            repetition=0.08,
            concentration=0.21,
            engagement=0.6,
            frustration=0.05,
            trust_delta=0.12,
            confidence_delta=0.08,
            frustration_delta=0.05,
            skip_rate=0.2,
            dominant_failure_mode="no_major_failure",
            trace_risk_score=0.18,
        ),
    )
    analysis = analyzer.analyze(scores, traces, run_config)
    assert analysis.cohort_summaries[0].risk_level == "high"
    assert analysis.risk_flags[0].severity == "high"
    assert analysis.cohort_summaries[0].dominant_failure_mode == "trust_collapse"
    assert analysis.cohort_summaries[0].representative_failure_trace_id == "trace-a"
    assert analysis.cohort_summaries[0].representative_success_trace_id == "trace-b"


def test_report_writers_consume_precomputed_result_only(tmp_path: Path) -> None:
    run_config = _build_recommender_run_config_only(seed=2, output_dir=str(tmp_path))
    run_result = RunResult(
        run_config=run_config,
        traces=(
            SessionTrace(
                trace_id="trace-failure",
                seed=1,
                agent_seed=build_seeded_archetypes()[1],
                scenario_name="returning-user-home-feed",
                steps=(),
                abandoned=True,
                completed_steps=2,
            ),
            SessionTrace(
                trace_id="trace-success",
                seed=2,
                agent_seed=build_seeded_archetypes()[1],
                scenario_name="returning-user-home-feed",
                steps=(),
                abandoned=False,
                completed_steps=5,
            ),
        ),
        trace_scores=(
            TraceScore(
                "trace-failure",
                "returning-user-home-feed",
                "Explorer / novelty-seeking",
                2,
                True,
                0,
                0.12,
                0.1,
                0.2,
                0.0,
                0.42,
                trust_delta=-0.32,
                confidence_delta=-0.21,
                frustration_delta=0.42,
                skip_rate=1.0,
                dominant_failure_mode="trust_collapse",
                trace_risk_score=0.81,
                failure_evidence_summary="abandoned at step 2 after trust fell 0.70->0.38",
            ),
            TraceScore(
                "trace-success",
                "returning-user-home-feed",
                "Explorer / novelty-seeking",
                5,
                False,
                3,
                0.72,
                0.05,
                0.16,
                0.6,
                0.04,
            ),
        ),
        cohort_summaries=(
            CohortSummary(
                "returning-user-home-feed",
                "Explorer / novelty-seeking",
                2,
                0.5,
                0.42,
                0.3,
                0.23,
                "high",
                representative_trace_id="trace-failure",
                mean_trust_delta=-0.1,
                mean_confidence_delta=-0.06,
                mean_skip_rate=0.6,
                dominant_failure_mode="trust_collapse",
                high_risk_trace_count=1,
                representative_success_trace_id="trace-success",
                representative_failure_trace_id="trace-failure",
            ),
        ),
        risk_flags=(
            RiskFlag(
                "returning-user-home-feed",
                "Explorer / novelty-seeking",
                "high",
                "Explorer / novelty-seeking is underserved in returning-user-home-feed due to trust collapse.",
                "trace-failure",
                dominant_failure_mode="trust_collapse",
                evidence_summary="abandoned at step 2 after trust fell 0.70->0.38",
            ),
        ),
        metadata={"source": "synthetic", "service_kind": "reference"},
    )
    report_paths = MarkdownReportWriter().write(run_result, tmp_path)
    results_paths = JsonReportWriter().write(run_result, tmp_path)
    assert Path(report_paths["report_path"]).exists()
    assert Path(results_paths["results_path"]).exists()
    assert Path(results_paths["traces_path"]).exists()
    report_body = Path(report_paths["report_path"]).read_text(encoding="utf-8")
    assert "## Launch Risks" in report_body
    assert "trace-failure" in report_body
    assert "trace-success" in report_body


def test_json_output_includes_enriched_score_fields(tmp_path: Path) -> None:
    paths = run_recommender_audit(
        seed=8,
        output_dir=str(tmp_path / "audit"),
        service_mode="mock",
    )
    payload = json.loads(Path(paths["results_path"]).read_text(encoding="utf-8"))
    trace_score = payload["trace_scores"][0]
    cohort_summary = payload["cohort_summaries"][0]
    risk_flag = payload["risk_flags"][0] if payload["risk_flags"] else None
    assert "dominant_failure_mode" in trace_score
    assert "trace_risk_score" in trace_score
    assert "representative_failure_trace_id" in cohort_summary
    if risk_flag is not None:
        assert "evidence_summary" in risk_flag


def test_trace_steps_include_decision_explanations() -> None:
    run_config = _build_recommender_run_config_only(
        seed=6,
        scenario_names=("returning-user-home-feed",),
        service_mode="mock",
        service_artifact_dir=None,
    )
    scenarios = build_scenarios(run_config.scenarios)
    with run_mock_recommender_service() as base_url:
        traces = run_rollouts(
            HttpNativeRecommenderDriver(
                HttpNativeDriverConfig(base_url=base_url, timeout_seconds=2.0)
            ),
            scenarios,
            RecommenderAgentPolicy(),
            run_config,
        )
    first_step = traces[0].steps[0]
    assert first_step.decision_explanation is not None
    assert first_step.decision_explanation.top_candidate_breakdown is not None
    assert first_step.state_delta_summary


def test_same_seed_produces_same_json_result(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    first_paths = run_recommender_audit(
        seed=5,
        output_dir=str(tmp_path / "first"),
        service_artifact_dir=str(artifact_dir),
    )
    second_paths = run_recommender_audit(
        seed=5,
        output_dir=str(tmp_path / "second"),
        service_artifact_dir=str(artifact_dir),
    )
    first_payload = json.loads(
        Path(first_paths["results_path"]).read_text(encoding="utf-8")
    )
    second_payload = json.loads(
        Path(second_paths["results_path"]).read_text(encoding="utf-8")
    )
    assert first_payload == second_payload


def test_different_seed_changes_output(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    first_paths = run_recommender_audit(
        seed=2,
        output_dir=str(tmp_path / "seed-2"),
        service_artifact_dir=str(artifact_dir),
    )
    second_paths = run_recommender_audit(
        seed=3,
        output_dir=str(tmp_path / "seed-3"),
        service_artifact_dir=str(artifact_dir),
    )
    first_payload = json.loads(
        Path(first_paths["results_path"]).read_text(encoding="utf-8")
    )
    second_payload = json.loads(
        Path(second_paths["results_path"]).read_text(encoding="utf-8")
    )
    assert first_payload["trace_scores"] != second_payload["trace_scores"]


def test_cli_runs_end_to_end_and_writes_outputs(tmp_path: Path) -> None:
    result = main(
        [
            "audit",
            "--domain",
            "recommender",
            "--seed",
            "7",
            "--scenario",
            "returning-user-home-feed",
            "--reference-artifact-dir",
            str(tmp_path / "artifacts"),
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert Path(result["report_path"]).exists()
    assert Path(result["results_path"]).exists()
    assert Path(result["traces_path"]).exists()


def test_cli_runs_both_scenarios(tmp_path: Path) -> None:
    result = main(
        [
            "audit",
            "--domain",
            "recommender",
            "--seed",
            "4",
            "--scenario",
            "all",
            "--reference-artifact-dir",
            str(tmp_path / "artifacts"),
            "--output-dir",
            str(tmp_path),
        ]
    )
    payload = json.loads(Path(result["results_path"]).read_text(encoding="utf-8"))
    scenario_names = {
        summary["scenario_name"] for summary in payload["cohort_summaries"]
    }
    assert scenario_names == {
        "returning-user-home-feed",
        "sparse-history-home-feed",
        "taste-elicitation-home-feed",
        "re-engagement-home-feed",
    }


def test_rollout_engine_is_transport_agnostic() -> None:
    run_config = _build_recommender_run_config_only(
        seed=6,
        scenario_names=("returning-user-home-feed",),
        service_mode="mock",
        service_artifact_dir=None,
    )
    scenarios = build_scenarios(run_config.scenarios)
    with run_mock_recommender_service() as base_url:
        traces = run_rollouts(
            HttpNativeRecommenderDriver(
                HttpNativeDriverConfig(base_url=base_url, timeout_seconds=2.0)
            ),
            scenarios,
            RecommenderAgentPolicy(),
            run_config,
        )
    assert traces
    assert all(trace.scenario_name == "returning-user-home-feed" for trace in traces)


def test_built_in_recommender_scenarios_now_include_broader_session_families() -> None:
    scenarios = resolve_built_in_recommender_scenarios()

    assert {scenario.name for scenario in scenarios} == {
        "returning-user-home-feed",
        "sparse-history-home-feed",
        "taste-elicitation-home-feed",
        "re-engagement-home-feed",
    }


def test_generated_scenarios_can_project_into_broader_runtime_profiles() -> None:
    pack = generate_scenario_pack(
        "test onboarding and re-engagement quality for movie discovery",
        generator_mode="fixture",
        scenario_count=6,
    )

    projected = project_recommender_scenarios(pack)

    assert {scenario.runtime_profile for scenario in projected} >= {
        "taste-elicitation-home-feed",
        "re-engagement-home-feed",
    }


def test_generated_population_projection_preserves_behavior_metadata() -> None:
    pack = generate_population_pack(
        "test a recommender for risk-sensitive but curious viewers",
        generator_mode="fixture",
        population_size=6,
        candidate_count=12,
    )

    runtime_seeds = project_recommender_population(pack)

    assert len(pack.personas) == len(runtime_seeds)
    assert all(persona.behavior_goal for persona in pack.personas)
    assert all(runtime_seed.behavior_goal for runtime_seed in runtime_seeds)
    assert all(runtime_seed.diversity_tags for runtime_seed in runtime_seeds)


def test_scenario_and_persona_context_shape_initial_state_more_directly() -> None:
    base_seed = build_seeded_archetypes()[0]
    generated_like_seed = replace(
        base_seed,
        behavior_goal="Reward exploration without a weak first impression.",
        diversity_tags=("novelty-seeking", "first-impression-sensitive"),
    )

    plain_context = ScenarioContext(
        scenario_name="returning-user-home-feed",
        runtime_profile="returning-user-home-feed",
        history_depth=4,
        history_item_ids=("action-1", "comedy-1"),
        description="Plain context.",
        context_hint="steady returning session",
        risk_focus_tags=(),
    )
    shaped_context = ScenarioContext(
        scenario_name="taste-elicitation-home-feed",
        runtime_profile="taste-elicitation-home-feed",
        history_depth=0,
        history_item_ids=(),
        description="Taste elicitation context.",
        context_hint="novel fresh onboarding session where first impression matters",
        risk_focus_tags=("cold-start", "weak-first-impression", "novelty-mismatch"),
    )

    base_state = initial_state_from_seed(base_seed, plain_context)
    shaped_state = initial_state_from_seed(generated_like_seed, shaped_context)

    assert shaped_state.click_threshold != base_state.click_threshold
    assert shaped_state.confidence != base_state.confidence
    assert shaped_state.behavior_goal
    assert shaped_state.scenario_risk_focus_tags


def test_behavioral_signals_are_emitted_in_trace_scores_and_results(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)

    run_result = execute_recommender_audit(
        seed=11,
        output_dir=str(tmp_path / "audit"),
        scenario_names=("taste-elicitation-home-feed",),
        service_artifact_dir=str(artifact_dir),
    )
    write_run_artifacts(run_result)
    payload = json.loads(
        Path(run_result.run_config.rollout.output_dir, "results.json").read_text(
            encoding="utf-8"
        )
    )

    assert all(
        0.0 <= score.first_impression_score <= 1.0 for score in run_result.trace_scores
    )
    assert all(
        0.0 <= score.abandonment_pressure <= 1.0 for score in run_result.trace_scores
    )
    assert "mean_first_impression_score" in payload["summary"]
    assert "mean_abandonment_pressure" in payload["summary"]
    assert payload["summary"]["artifact_contract_version"] == "v1"


def test_generated_scenario_pack_changes_runtime_behavior_vs_builtin(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)

    builtin_result = execute_recommender_audit(
        seed=4,
        output_dir=str(tmp_path / "builtin"),
        scenario_names=("returning-user-home-feed",),
        service_artifact_dir=str(artifact_dir),
    )
    custom_pack = build_scenario_pack(
        [
            {
                "scenario_id": "generated-risky-returning",
                "name": "Generated risky returning session",
                "description": "Returning session with stronger trust and first-impression pressure.",
                "test_goal": "Verify context shaping changes runtime behavior.",
                "risk_focus_tags": ["weak-first-impression", "trust-drop", "staleness"],
                "max_steps": 5,
                "allowed_actions": ["click", "skip", "abandon"],
                "adapter_hints": {
                    "recommender": {
                        "runtime_profile": "returning-user-home-feed",
                        "history_depth": 4,
                        "context_hint": "fresh but trustworthy returning session where first impression matters",
                    }
                },
            }
        ],
        brief="generated returning context",
        generator_mode="fixture",
        generated_at_utc="2026-01-01T00:00:00+00:00",
        domain_label="recommender",
    )
    from evidpath.scenario_generation import write_scenario_pack

    pack_path = tmp_path / "scenario-pack.json"
    write_scenario_pack(custom_pack, pack_path)
    generated_result = execute_recommender_audit(
        seed=4,
        output_dir=str(tmp_path / "generated"),
        scenario_pack_path=str(pack_path),
        service_artifact_dir=str(artifact_dir),
    )

    builtin_mean = sum(
        score.first_impression_score for score in builtin_result.trace_scores
    ) / len(builtin_result.trace_scores)
    generated_mean = sum(
        score.first_impression_score for score in generated_result.trace_scores
    ) / len(generated_result.trace_scores)

    assert builtin_mean != generated_mean


def test_external_url_metadata_is_clear_and_unreachable_targets_fail_cleanly(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)

    with run_reference_recommender_service(str(artifact_dir)) as (base_url, _metadata):
        run_result = execute_recommender_audit(
            seed=6,
            output_dir=str(tmp_path / "audit"),
            adapter_base_url=base_url,
        )

    assert run_result.metadata["target_endpoint_host"]
    assert run_result.metadata["service_metadata_status"] == "available"

    adapter = HttpNativeRecommenderDriver(
        HttpNativeDriverConfig(base_url="http://127.0.0.1:1", timeout_seconds=0.1)
    )
    state = run_result.traces[0].steps[0].agent_state_before
    observation = run_result.traces[0].steps[0].observation
    scenario_config = run_result.run_config.scenarios[0]
    with pytest.raises(RuntimeError) as exc_info:
        adapter.get_slate(state, observation, scenario_config)

    assert (
        "unreachable" in str(exc_info.value).lower()
        or "failed during" in str(exc_info.value).lower()
    )
