"""Test-only stub domain used to prove the in-repo plug-in contract.

This module is architecture smoke-test infrastructure. It is not part of the
supported recommender product story.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import nullcontext
from dataclasses import dataclass, replace
from hashlib import sha1

from ..config import build_run_config, slugify_name
from ..regression_policy import default_regression_policy
from ..schema import (
    Action,
    ActionDecision,
    AgentSeed,
    AgentState,
    AnalysisResult,
    CohortSummary,
    DecisionExplanation,
    Observation,
    RegressionPolicy,
    RegressionPolicyOverride,
    RegressionTarget,
    RunConfig,
    RunResult,
    ScenarioConfig,
    ScenarioContext,
    ScoringConfig,
    SessionTrace,
    Slate,
    SlateItem,
    TraceScore,
    UtilityBreakdown,
)
from .base import DomainDefinition, ResolvedRuntimeInputs, StandardDomainRunner

_AUDIT_TITLE = "Evidpath Stub Audit"
_REGRESSION_TITLE = "Evidpath Stub Regression"
_SUMMARY_METRICS = (
    "mean_session_utility",
    "abandonment_rate",
    "mean_engagement",
    "mean_frustration",
    "mean_trust_delta",
    "mean_skip_rate",
    "high_risk_cohort_count",
)


def build_stub_domain_definition() -> DomainDefinition:
    """Build a minimal smoke-test domain that satisfies the full plug-in contract."""
    definition = DomainDefinition(
        name="stub",
        audit_report_title=_AUDIT_TITLE,
        regression_report_title=_REGRESSION_TITLE,
        resolve_inputs=resolve_stub_inputs,
        build_run_config=build_stub_run_config,
        build_target_identity=build_stub_target_identity,
        build_target_audit_kwargs=build_stub_target_audit_kwargs,
        build_runtime_scenarios=build_stub_runtime_scenarios,
        open_service_context=open_stub_service_context,
        build_driver=build_stub_driver,
        build_policy=StubAgentPolicy,
        build_judge=StubJudge,
        build_analyzer=StubAnalyzer,
        summary_metric_names=_SUMMARY_METRICS,
        summarize_run_metrics=summarize_stub_run_metrics,
        build_default_regression_policy=build_stub_default_regression_policy,
        public=False,
        runner=None,
    )
    return replace(definition, runner=StandardDomainRunner(definition=definition))


def resolve_stub_inputs(
    scenario_names: tuple[str, ...] | None = None,
    scenario_pack_path: str | None = None,
    population_pack_path: str | None = None,
) -> ResolvedRuntimeInputs:
    """Return one tiny deterministic scenario and population for smoke tests."""
    del scenario_pack_path, population_pack_path
    selected_names = scenario_names or ("stub-eval",)
    scenarios = tuple(_build_stub_scenario_config(name) for name in selected_names)
    return ResolvedRuntimeInputs(
        scenarios=scenarios,
        agent_seeds=(_build_stub_agent_seed(),),
        metadata={
            "scenario_source": "built_in",
            "population_source": "built_in_seeds",
            "population_size_source": "built_in",
        },
    )


def build_stub_run_config(
    *,
    seed: int = 0,
    output_dir: str | None = None,
    scenario_names: tuple[str, ...] | None = None,
    scenario_pack_path: str | None = None,
    population_pack_path: str | None = None,
    service_mode: str = "reference",
    service_artifact_dir: str | None = None,
    adapter_base_url: str | None = None,
    driver_kind: str | None = None,
    driver_config: Mapping[str, object] | None = None,
    run_name: str | None = None,
) -> tuple[RunConfig, ResolvedRuntimeInputs]:
    """Resolve stub inputs, then build an explicit generic run config."""
    resolved_inputs = resolve_stub_inputs(
        scenario_names=scenario_names,
        scenario_pack_path=scenario_pack_path,
        population_pack_path=population_pack_path,
    )
    run_config = build_run_config(
        seed=seed,
        output_dir=output_dir,
        scenarios=resolved_inputs.scenarios,
        agent_seeds=resolved_inputs.agent_seeds,
        service_mode=service_mode,
        service_artifact_dir=service_artifact_dir,
        adapter_base_url=adapter_base_url,
        driver_kind=driver_kind,
        driver_config=driver_config,
        run_name=run_name or "stub-audit",
    )
    return run_config, resolved_inputs


def build_stub_target_identity(target: RegressionTarget) -> str:
    """Return a short stable identity for stub-domain targets."""
    if target.driver_kind == "in_process":
        raw = str(target.driver_config.get("import_path", "in_process"))
        label = slugify_name(raw)
        prefix = "in-proc"
    elif target.driver_kind == "http_native_external":
        raw = str(target.driver_config.get("base_url", ""))
        label = slugify_name(raw or "external")
        prefix = "url"
    else:
        raw = str(target.driver_config.get("artifact_dir", "stub-artifact"))
        label = slugify_name(raw)
        prefix = "artifact"
    digest = sha1(raw.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{label}-{digest}"


def build_stub_target_audit_kwargs(target: RegressionTarget) -> dict[str, object]:
    """Translate stub regression targets into audit-time overrides."""
    if target.driver_kind == "http_native_reference":
        artifact_dir = str(target.driver_config.get("artifact_dir", ""))
        return {
            "service_mode": "reference",
            "service_artifact_dir": artifact_dir,
        }
    if target.driver_kind == "http_native_external":
        base_url = target.driver_config.get("base_url")
        if not isinstance(base_url, str) or not base_url:
            raise ValueError(
                "http_native_external targets require driver_config.base_url."
            )
        return {"adapter_base_url": base_url}
    if target.driver_kind == "in_process":
        return {
            "driver_kind": "in_process",
            "driver_config": dict(target.driver_config),
        }
    raise NotImplementedError(f"Unsupported stub driver kind: {target.driver_kind}")


def build_stub_runtime_scenarios(
    scenario_configs: tuple[ScenarioConfig, ...]
) -> tuple["StubScenario", ...]:
    """Build runtime scenarios from stub scenario configs."""
    return tuple(StubScenario(config) for config in scenario_configs)


def open_stub_service_context(run_config: RunConfig):
    """Open a no-op local service context for the stub domain."""
    base_url = run_config.rollout.adapter_base_url or "stub://local"
    metadata = {
        "service_kind": "stub",
        "artifact_id": run_config.rollout.service_artifact_dir or "stub-artifact",
        "backend_name": "stub-backend",
    }
    return nullcontext((base_url, metadata))


def build_stub_driver(
    driver_kind: str,
    driver_config: Mapping[str, object],
    base_url: str | None,
    timeout_seconds: float,
) -> "StubDriver":
    """Build the local in-memory stub driver."""
    del driver_kind, driver_config
    return StubDriver(base_url=base_url or "stub://local", timeout_seconds=timeout_seconds)


def summarize_stub_run_metrics(run_result: RunResult) -> dict[str, float]:
    """Return the same summary metric shape used by the recommender wedge."""
    trace_scores = run_result.trace_scores
    cohort_summaries = run_result.cohort_summaries
    return {
        "mean_session_utility": _mean(score.session_utility for score in trace_scores),
        "abandonment_rate": _mean(1.0 if score.abandoned else 0.0 for score in trace_scores),
        "mean_engagement": _mean(score.engagement for score in trace_scores),
        "mean_frustration": _mean(score.frustration for score in trace_scores),
        "mean_trust_delta": _mean(score.trust_delta for score in trace_scores),
        "mean_skip_rate": _mean(score.skip_rate for score in trace_scores),
        "high_risk_cohort_count": float(
            sum(1 for cohort in cohort_summaries if cohort.risk_level == "high")
        ),
    }


def build_stub_default_regression_policy(
    metric_overrides: tuple[RegressionPolicyOverride, ...] = (),
    cohort_overrides: tuple[RegressionPolicyOverride, ...] = (),
) -> RegressionPolicy:
    """Reuse the portable default policy for the stub smoke-test domain."""
    return default_regression_policy(
        metric_overrides=metric_overrides,
        cohort_overrides=cohort_overrides,
    )


@dataclass(frozen=True)
class StubScenario:
    """Small deterministic scenario used by the smoke-test domain."""

    config: ScenarioConfig

    @property
    def scenario_id(self) -> str:
        return self.config.scenario_id or self.config.name

    @property
    def name(self) -> str:
        return self.config.name

    def initialize(self, agent_seed: AgentSeed, run_config: RunConfig) -> Observation:
        del agent_seed, run_config
        return self._observation(step_index=0)

    def next_observation(
        self,
        previous: Observation,
        run_config: RunConfig,
    ) -> Observation:
        del run_config
        return self._observation(step_index=previous.step_index + 1)

    def should_stop(self, observation: Observation) -> bool:
        return observation.step_index >= observation.max_steps

    def _observation(self, *, step_index: int) -> Observation:
        return Observation(
            session_id=f"{self.scenario_id}-session",
            step_index=step_index,
            max_steps=self.config.max_steps,
            available_actions=self.config.allowed_actions,
            scenario_context=ScenarioContext(
                scenario_name=self.config.name,
                history_depth=self.config.history_depth,
                history_item_ids=(),
                description=self.config.description,
                scenario_id=self.scenario_id,
                runtime_profile=self.config.runtime_profile,
                context_hint=self.config.context_hint,
            ),
        )


class StubDriver:
    """In-memory driver that emits a tiny deterministic slate."""

    def __init__(self, *, base_url: str, timeout_seconds: float) -> None:
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    def get_slate(
        self,
        agent_state: AgentState,
        observation: Observation,
        scenario_config: ScenarioConfig,
    ) -> Slate:
        del scenario_config
        items = (
            SlateItem(
                item_id=f"{agent_state.agent_id}-primary-{observation.step_index}",
                title="Primary candidate",
                genre=agent_state.preferred_genres[0],
                score=0.82,
                rank=1,
                popularity=0.55,
                novelty=0.45,
            ),
            SlateItem(
                item_id=f"{agent_state.agent_id}-backup-{observation.step_index}",
                title="Backup candidate",
                genre="general",
                score=0.41,
                rank=2,
                popularity=0.35,
                novelty=0.3,
            ),
        )
        return Slate(
            slate_id=f"{observation.scenario_context.scenario_id}-{agent_state.agent_id}-{observation.step_index}",
            step_index=observation.step_index,
            items=items,
        )

    def get_service_metadata(self) -> dict[str, str | int | float]:
        return {
            "service_kind": "stub",
            "artifact_id": "stub-artifact",
            "backend_name": "stub-backend",
        }


class StubAgentPolicy:
    """Minimal seeded-user policy used to validate the domain contract."""

    def initialize_state(
        self,
        agent_seed: AgentSeed,
        scenario_context: ScenarioContext,
    ) -> AgentState:
        return AgentState(
            agent_id=agent_seed.agent_id,
            archetype_label=agent_seed.archetype_label,
            step_index=0,
            click_threshold=0.5,
            preferred_genres=agent_seed.preferred_genres,
            popularity_preference=agent_seed.popularity_preference,
            novelty_preference=agent_seed.novelty_preference,
            repetition_tolerance=agent_seed.repetition_tolerance,
            sparse_history_confidence=agent_seed.sparse_history_confidence,
            abandonment_sensitivity=agent_seed.abandonment_sensitivity,
            engagement_baseline=agent_seed.engagement_baseline,
            quality_sensitivity=agent_seed.quality_sensitivity,
            repeat_exposure_penalty=agent_seed.repeat_exposure_penalty,
            novelty_fatigue=agent_seed.novelty_fatigue,
            frustration_recovery=agent_seed.frustration_recovery,
            history_reliance=agent_seed.history_reliance,
            skip_tolerance=agent_seed.skip_tolerance,
            abandonment_threshold=agent_seed.abandonment_threshold,
            patience_remaining=agent_seed.patience,
            last_action="start",
            history_item_ids=scenario_context.history_item_ids,
        )

    def choose_action(
        self,
        agent_state: AgentState,
        slate: Slate,
        observation: Observation,
        scenario_config: ScenarioConfig,
        rng,
    ) -> ActionDecision:
        del scenario_config, rng
        selected_item = slate.items[0]
        action_name = "click" if observation.step_index == 0 else "skip"
        selected_item_id = selected_item.item_id if action_name == "click" else None
        return ActionDecision(
            action=Action(
                name=action_name,
                selected_item_id=selected_item_id,
                reason="stub-policy",
            ),
            explanation=DecisionExplanation(
                chosen_item_id=selected_item_id,
                top_candidate_item_id=selected_item.item_id,
                action_threshold=0.5,
                chosen_utility=selected_item.score,
                top_candidate_utility=selected_item.score,
                dominant_component="base_relevance",
                top_candidate_breakdown=UtilityBreakdown(
                    base_relevance=selected_item.score,
                    affinity=0.6,
                    familiarity=0.3,
                    novelty=selected_item.novelty,
                    quality=0.7,
                    repetition_penalty=0.0,
                    scenario_adjustment=0.0,
                    confidence_adjustment=0.0,
                    jitter=0.0,
                    total=selected_item.score,
                ),
                reason="stub explanation",
            ),
        )

    def update_state(
        self,
        agent_state: AgentState,
        decision: ActionDecision,
        slate: Slate,
        observation: Observation,
        rng,
    ) -> AgentState:
        del observation, rng
        selected_item_id = decision.action.selected_item_id
        clicked_item_ids = agent_state.clicked_item_ids
        history_item_ids = agent_state.history_item_ids
        if selected_item_id is not None:
            clicked_item_ids = (*clicked_item_ids, selected_item_id)
            history_item_ids = (*history_item_ids, selected_item_id)
        return replace(
            agent_state,
            step_index=agent_state.step_index + 1,
            patience_remaining=max(0, agent_state.patience_remaining - 1),
            last_action=decision.action.name,
            history_item_ids=history_item_ids,
            recent_exposure_ids=tuple(item.item_id for item in slate.items),
            clicked_item_ids=clicked_item_ids,
            click_count=agent_state.click_count + (1 if decision.action.name == "click" else 0),
            skipped_steps=agent_state.skipped_steps + (1 if decision.action.name == "skip" else 0),
            satisfaction=agent_state.satisfaction + (0.25 if decision.action.name == "click" else 0.0),
            trust=agent_state.trust + (0.05 if decision.action.name == "click" else -0.01),
            confidence=agent_state.confidence + (0.03 if decision.action.name == "click" else 0.0),
            frustration=agent_state.frustration + (0.02 if decision.action.name == "skip" else 0.0),
        )

    def summarize_state_delta(
        self,
        before: AgentState,
        after: AgentState,
        decision: ActionDecision,
        observation: Observation,
    ) -> str:
        del before, observation
        return (
            f"Action `{decision.action.name}` moved trust to {after.trust:.2f} "
            f"and satisfaction to {after.satisfaction:.2f}."
        )


class StubJudge:
    """Simple deterministic judge for the stub domain."""

    def score_trace(
        self,
        session_trace: SessionTrace,
        scoring_config: ScoringConfig,
    ) -> TraceScore:
        del scoring_config
        clicks = sum(step.action.name == "click" for step in session_trace.steps)
        skips = sum(step.action.name == "skip" for step in session_trace.steps)
        final_state = session_trace.steps[-1].agent_state_after
        initial_state = session_trace.steps[0].agent_state_before
        session_utility = 0.7 if clicks else 0.35
        return TraceScore(
            trace_id=session_trace.trace_id,
            scenario_name=session_trace.scenario_name,
            archetype_label=session_trace.agent_seed.archetype_label,
            steps_completed=session_trace.completed_steps,
            abandoned=session_trace.abandoned,
            click_count=clicks,
            session_utility=session_utility,
            repetition=0.0,
            concentration=0.0,
            engagement=clicks / max(1, session_trace.completed_steps),
            frustration=final_state.frustration,
            mean_click_quality=0.82 if clicks else 0.0,
            mean_top_candidate_utility=0.82,
            trust_delta=round(final_state.trust - initial_state.trust, 6),
            confidence_delta=round(final_state.confidence - initial_state.confidence, 6),
            frustration_delta=round(final_state.frustration - initial_state.frustration, 6),
            skip_rate=skips / max(1, session_trace.completed_steps),
            click_depth=0.5 if clicks else 0.0,
            stale_exposure_rate=0.0,
            genre_alignment_rate=1.0 if clicks else 0.0,
            novelty_intensity=0.45,
            dominant_failure_mode="no_major_failure",
            trace_risk_score=0.1 if clicks else 0.3,
            failure_evidence_summary="Stable stub smoke-test trace.",
        )


class StubAnalyzer:
    """Minimal analyzer that proves domain-owned judge/analyzer seams."""

    def analyze(
        self,
        scored_traces: tuple[TraceScore, ...],
        traces: tuple[SessionTrace, ...],
        run_config: RunConfig,
    ) -> AnalysisResult:
        del traces, run_config
        score = scored_traces[0]
        return AnalysisResult(
            cohort_summaries=(
                CohortSummary(
                    scenario_name=score.scenario_name,
                    archetype_label=score.archetype_label,
                    trace_count=len(scored_traces),
                    abandonment_rate=0.0,
                    mean_session_utility=score.session_utility,
                    mean_engagement=score.engagement,
                    mean_frustration=score.frustration,
                    risk_level="low",
                    representative_trace_id=score.trace_id,
                    mean_trust_delta=score.trust_delta,
                    mean_confidence_delta=score.confidence_delta,
                    mean_skip_rate=score.skip_rate,
                    dominant_failure_mode=score.dominant_failure_mode,
                    high_risk_trace_count=0,
                    representative_success_trace_id=score.trace_id,
                ),
            ),
            risk_flags=(),
        )


def _build_stub_scenario_config(name: str) -> ScenarioConfig:
    scenario_id = f"stub-{slugify_name(name)}"
    return ScenarioConfig(
        name=name,
        max_steps=2,
        allowed_actions=("click", "skip"),
        history_depth=0,
        description="Minimal stub scenario for domain plug-in smoke tests.",
        scenario_id=scenario_id,
        test_goal="Verify that a new in-repo domain plugs into the shared harness.",
        runtime_profile="stub-runtime",
        context_hint="Keep behavior simple and deterministic.",
    )


def _build_stub_agent_seed() -> AgentSeed:
    return AgentSeed(
        agent_id="stub-agent",
        archetype_label="Stub Persona",
        preferred_genres=("general",),
        popularity_preference=0.5,
        novelty_preference=0.4,
        repetition_tolerance=0.6,
        sparse_history_confidence=0.5,
        abandonment_sensitivity=0.2,
        patience=2,
        engagement_baseline=0.5,
        quality_sensitivity=0.6,
        repeat_exposure_penalty=0.1,
        novelty_fatigue=0.1,
        frustration_recovery=0.3,
        history_reliance=0.4,
        skip_tolerance=1,
        abandonment_threshold=0.85,
    )


def _mean(values) -> float:
    values = tuple(values)
    if not values:
        return 0.0
    return sum(values) / len(values)
