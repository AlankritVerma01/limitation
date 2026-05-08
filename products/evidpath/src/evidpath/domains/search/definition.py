"""Search-domain plug-in definition and owned seams."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from ...regression_policy import default_regression_policy
from ...schema import RegressionPolicyOverride, RunConfig, RunResult, ScenarioConfig
from ..base import DomainDefinition, ResolvedRuntimeInputs, StandardDomainRunner
from .analyzer import SearchAnalyzer
from .drivers import (
    HttpNativeSearchDriver,
    HttpNativeSearchDriverConfig,
    HttpSchemaMappedSearchDriver,
    HttpSchemaMappedSearchDriverConfig,
    InProcessSearchDriver,
    InProcessSearchDriverConfig,
)
from .inputs import resolve_search_inputs
from .judge import SearchJudge
from .policy import SearchAgentPolicy
from .services import (
    build_reference_search_driver,
    build_search_target_audit_kwargs,
    build_search_target_identity,
    check_search_target,
    open_search_service_context,
)

_AUDIT_TITLE = "Evidpath Search Audit"
_REGRESSION_TITLE = "Evidpath Search Regression Audit"
_SUMMARY_METRICS = (
    "mean_session_utility",
    "abandonment_rate",
    "mean_engagement",
    "mean_skip_rate",
    "mean_top_bucket_relevance",
    "mean_freshness_percentile",
    "mean_snippet_query_overlap",
    "mean_intra_list_diversity",
    "mean_type_mix_distance",
    "high_risk_cohort_count",
)


def build_search_domain_definition() -> DomainDefinition:
    """Build the in-repo plug-in definition for the search domain."""
    definition = DomainDefinition(
        name="search",
        audit_report_title=_AUDIT_TITLE,
        regression_report_title=_REGRESSION_TITLE,
        resolve_inputs=resolve_search_inputs,
        build_run_config=build_search_run_config,
        build_target_identity=build_search_target_identity,
        build_target_audit_kwargs=build_search_target_audit_kwargs,
        check_target=check_search_target,
        build_runtime_scenarios=build_search_runtime_scenarios,
        open_service_context=open_search_service_context,
        build_driver=build_search_driver,
        build_policy=SearchAgentPolicy,
        build_judge=SearchJudge,
        build_analyzer=SearchAnalyzer,
        summary_metric_names=_SUMMARY_METRICS,
        summarize_run_metrics=summarize_search_run_metrics,
        build_default_regression_policy=build_search_default_regression_policy,
        runner=None,
    )
    return replace(definition, runner=StandardDomainRunner(definition=definition))


def build_search_run_config(
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
    """Resolve search runtime inputs, then build a run config from them."""
    from ...config import build_run_config

    resolved_inputs = resolve_search_inputs(
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
        run_name=run_name,
    )
    return run_config, resolved_inputs


def build_search_runtime_scenarios(
    scenario_configs: tuple[ScenarioConfig, ...],
) -> tuple:
    """Build runtime search scenarios from saved or built-in configs."""
    from .scenarios import build_scenarios

    return build_scenarios(scenario_configs)


def build_search_driver(
    driver_kind: str,
    driver_config: Mapping[str, object],
    base_url: str | None,
    timeout_seconds: float,
):
    """Construct one search driver from driver kind plus config."""
    if driver_kind == "http_native_reference":
        return build_reference_search_driver()
    if driver_kind == "http_native_external":
        resolved_base_url = base_url or str(driver_config.get("base_url", ""))
        if not resolved_base_url:
            raise ValueError(f"Driver kind `{driver_kind}` requires a base URL.")
        return HttpNativeSearchDriver(
            HttpNativeSearchDriverConfig(
                base_url=resolved_base_url,
                timeout_seconds=timeout_seconds,
            )
        )
    if driver_kind == "in_process":
        return InProcessSearchDriver(InProcessSearchDriverConfig.from_dict(driver_config))
    if driver_kind == "http_schema_mapped":
        return HttpSchemaMappedSearchDriver(
            HttpSchemaMappedSearchDriverConfig.from_dict(
                driver_config,
                timeout_seconds=timeout_seconds,
            )
        )
    raise ValueError(f"Unsupported search driver kind: {driver_kind}")


def summarize_search_run_metrics(run_result: RunResult) -> dict[str, float]:
    """Extract search summary metrics used by reruns and diffs."""
    trace_scores = run_result.trace_scores
    cohort_summaries = run_result.cohort_summaries
    return {
        "mean_session_utility": _mean(score.session_utility for score in trace_scores),
        "abandonment_rate": _mean(1.0 if score.abandoned else 0.0 for score in trace_scores),
        "mean_engagement": _mean(score.engagement for score in trace_scores),
        "mean_skip_rate": _mean(score.skip_rate for score in trace_scores),
        "mean_top_bucket_relevance": _mean(
            _metric(score, "top_bucket_relevance") for score in trace_scores
        ),
        "mean_freshness_percentile": _mean(
            _metric(score, "freshness_percentile") for score in trace_scores
        ),
        "mean_snippet_query_overlap": _mean(
            _metric(score, "snippet_query_overlap") for score in trace_scores
        ),
        "mean_intra_list_diversity": _mean(
            _metric(score, "intra_list_diversity") for score in trace_scores
        ),
        "mean_type_mix_distance": _mean(
            _metric(score, "type_mix_distance") for score in trace_scores
        ),
        "high_risk_cohort_count": float(
            sum(1 for cohort in cohort_summaries if cohort.risk_level == "high")
        ),
    }


def build_search_default_regression_policy(
    metric_overrides: tuple[RegressionPolicyOverride, ...] = (),
    cohort_overrides: tuple[RegressionPolicyOverride, ...] = (),
):
    """Return the search-owned default regression policy."""
    return default_regression_policy(
        metric_overrides=metric_overrides,
        cohort_overrides=cohort_overrides,
    )


def _metric(score, name: str) -> float:
    value = score.domain_metrics.get(name, 0.0)
    return float(value) if isinstance(value, (int, float)) else 0.0


def _mean(values) -> float:
    values = tuple(values)
    if not values:
        return 0.0
    return sum(values) / len(values)
