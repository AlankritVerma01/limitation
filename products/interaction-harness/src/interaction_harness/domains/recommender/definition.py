"""Recommender-domain plug-in definition and owned seams."""

from __future__ import annotations

from dataclasses import replace

from ...regression_policy import default_regression_policy
from ...schema import RegressionPolicyOverride, RunConfig, RunResult, ScenarioConfig
from ..base import DomainDefinition, ResolvedRuntimeInputs, StandardDomainRunner
from .adapters import HttpRecommenderAdapter
from .analyzer import RecommenderAnalyzer
from .inputs import resolve_recommender_inputs
from .judge import RecommenderJudge
from .policy import RecommenderAgentPolicy
from .reporting import (
    build_recommender_regression_important_changes,
    build_recommender_regression_summary,
    build_recommender_run_executive_summary,
    select_recommender_representative_cohorts,
)
from .services import (
    build_recommender_target_audit_kwargs,
    build_recommender_target_identity,
    open_recommender_service_context,
)

_AUDIT_TITLE = "Interaction Harness Recommender Audit"
_REGRESSION_TITLE = "Interaction Harness Regression Audit"
_SUMMARY_METRICS = (
    "mean_session_utility",
    "abandonment_rate",
    "mean_engagement",
    "mean_frustration",
    "mean_trust_delta",
    "mean_skip_rate",
    "high_risk_cohort_count",
)


def build_recommender_domain_definition() -> DomainDefinition:
    """Build the in-repo plug-in definition for the recommender wedge."""
    definition = DomainDefinition(
        name="recommender",
        audit_report_title=_AUDIT_TITLE,
        regression_report_title=_REGRESSION_TITLE,
        resolve_inputs=resolve_recommender_inputs,
        build_run_config=build_recommender_run_config,
        build_target_identity=build_recommender_target_identity,
        build_target_audit_kwargs=build_recommender_target_audit_kwargs,
        build_runtime_scenarios=build_recommender_runtime_scenarios,
        open_service_context=open_recommender_service_context,
        build_adapter=build_recommender_adapter,
        build_policy=RecommenderAgentPolicy,
        build_judge=RecommenderJudge,
        build_analyzer=RecommenderAnalyzer,
        summary_metric_names=_SUMMARY_METRICS,
        summarize_run_metrics=summarize_recommender_run_metrics,
        build_default_regression_policy=build_recommender_default_regression_policy,
        build_run_executive_summary=build_recommender_run_executive_summary,
        select_representative_cohorts=select_recommender_representative_cohorts,
        build_regression_summary=build_recommender_regression_summary,
        build_regression_important_changes=build_recommender_regression_important_changes,
        runner=None,
    )
    return replace(definition, runner=StandardDomainRunner(definition=definition))


def build_recommender_run_config(
    *,
    seed: int = 0,
    output_dir: str | None = None,
    scenario_names: tuple[str, ...] | None = None,
    scenario_pack_path: str | None = None,
    population_pack_path: str | None = None,
    service_mode: str = "reference",
    service_artifact_dir: str | None = None,
    adapter_base_url: str | None = None,
    run_name: str | None = None,
) -> tuple[RunConfig, ResolvedRuntimeInputs]:
    """Resolve recommender runtime inputs, then build a run config from them."""
    from ...config import build_run_config

    resolved_inputs = resolve_recommender_inputs(
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
        run_name=run_name,
    )
    return run_config, resolved_inputs


def build_recommender_runtime_scenarios(
    scenario_configs: tuple[ScenarioConfig, ...]
) -> tuple:
    """Build runtime recommender scenarios from saved or built-in configs."""
    from .scenarios import build_scenarios

    return build_scenarios(scenario_configs)


def build_recommender_adapter(base_url: str, timeout_seconds: float) -> HttpRecommenderAdapter:
    """Build the recommender adapter for one running target endpoint."""
    return HttpRecommenderAdapter(base_url, timeout_seconds=timeout_seconds)


def summarize_recommender_run_metrics(run_result: RunResult) -> dict[str, float]:
    """Extract the recommender summary metrics used by reruns and diffs."""
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


def build_recommender_default_regression_policy(
    metric_overrides: tuple[RegressionPolicyOverride, ...] = (),
    cohort_overrides: tuple[RegressionPolicyOverride, ...] = (),
):
    """Return the recommender-owned default regression policy."""
    return default_regression_policy(
        metric_overrides=metric_overrides,
        cohort_overrides=cohort_overrides,
    )


def _mean(values) -> float:
    values = tuple(values)
    if not values:
        return 0.0
    return sum(values) / len(values)
