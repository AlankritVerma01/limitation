"""Recommender-domain plug-in definition and owned factories."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse

from ..adapters.http import HttpRecommenderAdapter
from ..agents.recommender import RecommenderAgentPolicy
from ..analysis.recommender import RecommenderAnalyzer
from ..config import build_recommender_run_config, slugify_name
from ..judges.recommender import RecommenderJudge
from ..recommender_inputs import resolve_recommender_inputs
from ..regression_policy import default_regression_policy
from ..schema import (
    RegressionPolicyOverride,
    RegressionTarget,
    RunResult,
    ScenarioConfig,
)
from ..services.mock_recommender import run_mock_recommender_service
from ..services.reference_artifacts import ensure_reference_artifacts
from ..services.reference_recommender import run_reference_recommender_service
from .base import DomainDefinition, StandardDomainRunner

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
        runner=None,
    )
    return replace(definition, runner=StandardDomainRunner(definition=definition))


def build_recommender_runtime_scenarios(
    scenario_configs: tuple[ScenarioConfig, ...]
) -> tuple:
    """Build runtime recommender scenarios from saved or built-in configs."""
    from ..scenarios.recommender import build_scenarios

    return build_scenarios(scenario_configs)


def open_recommender_service_context(run_config):
    """Open the correct recommender service context for one run config."""
    if run_config.rollout.adapter_base_url is not None:
        return nullcontext((run_config.rollout.adapter_base_url, {}))
    if run_config.rollout.service_mode == "mock":
        return _mock_service_context()
    artifact_path = ensure_reference_artifacts(run_config.rollout.service_artifact_dir)
    return run_reference_recommender_service(str(artifact_path.parent))


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


def build_recommender_target_identity(target: RegressionTarget) -> str:
    """Build a short stable identity for recommender compare and audit targets."""
    if target.mode == "external_url":
        normalized_url = (target.adapter_base_url or "").rstrip("/")
        parsed = urlparse(normalized_url)
        label = slugify_name(parsed.netloc or parsed.path or "external")
        raw_identity = normalized_url
        prefix = "url"
    else:
        artifact_dir = str(Path(target.service_artifact_dir or "")).rstrip("/")
        label = slugify_name(Path(artifact_dir).name or "artifact")
        raw_identity = artifact_dir
        prefix = "artifact"
    return f"{prefix}-{label}-{_short_hash(raw_identity)}"


def build_recommender_target_audit_kwargs(target: RegressionTarget) -> dict[str, object]:
    """Translate a regression target into audit-time service overrides."""
    if target.mode == "reference_artifact":
        if not target.service_artifact_dir:
            raise ValueError("reference_artifact targets require service_artifact_dir.")
        return {
            "service_mode": "reference",
            "service_artifact_dir": target.service_artifact_dir,
        }
    if target.mode == "external_url":
        if not target.adapter_base_url:
            raise ValueError("external_url targets require adapter_base_url.")
        return {"adapter_base_url": target.adapter_base_url}
    raise NotImplementedError(f"Unsupported regression target mode: {target.mode}")


@contextmanager
def _mock_service_context():
    """Normalize the mock service into the shared `(base_url, metadata)` shape."""
    with run_mock_recommender_service() as base_url:
        yield base_url, {}


def _mean(values) -> float:
    values = tuple(values)
    if not values:
        return 0.0
    return sum(values) / len(values)


def _short_hash(value: str) -> str:
    from hashlib import sha1

    return sha1(value.encode("utf-8")).hexdigest()[:8]
