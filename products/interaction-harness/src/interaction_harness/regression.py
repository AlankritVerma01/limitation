"""Regression orchestration for reruns and baseline-vs-candidate comparisons."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path

from .audit import write_run_artifacts
from .cli_progress import ProgressCallback, emit_progress
from .config import DEFAULT_OUTPUT_DIR, slugify_name
from .domain_registry import get_domain_definition
from .domains.base import DomainDefinition
from .regression_policy import evaluate_regression_policy
from .reporting.regression import RegressionJsonWriter, RegressionMarkdownWriter
from .schema import (
    CohortDelta,
    FailureMode,
    FailureModeCount,
    MetricDelta,
    MetricSummary,
    RegressionDiff,
    RegressionPolicy,
    RegressionPolicyOverride,
    RegressionTarget,
    RerunSummary,
    RiskFlagDelta,
    RunArtifactPaths,
    RunResult,
    SliceDelta,
    TraceDelta,
)
from .semantic_interpretation import interpret_regression_semantics

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def build_seed_schedule(base_seed: int, rerun_count: int) -> tuple[int, ...]:
    """Return a deterministic seed schedule for regression reruns."""
    if rerun_count <= 0:
        raise ValueError("rerun_count must be at least 1.")
    return tuple(base_seed + offset for offset in range(rerun_count))


def run_regression_audit(
    *,
    baseline_target: RegressionTarget,
    candidate_target: RegressionTarget,
    base_seed: int = 0,
    rerun_count: int = 3,
    output_dir: str | None = None,
    scenario_names: tuple[str, ...] | None = None,
    scenario_pack_path: str | None = None,
    population_pack_path: str | None = None,
    semantic_mode: str = "off",
    semantic_model: str = "gpt-5",
    policy_mode: str = "default",
    policy: RegressionPolicy | None = None,
    metric_overrides: tuple[RegressionPolicyOverride, ...] = (),
    cohort_overrides: tuple[RegressionPolicyOverride, ...] = (),
    progress_callback: ProgressCallback | None = None,
) -> dict[str, str | int]:
    """Run rerun summaries and baseline-vs-candidate diff artifacts."""
    return run_domain_regression_audit(
        domain_name="recommender",
        baseline_target=baseline_target,
        candidate_target=candidate_target,
        base_seed=base_seed,
        rerun_count=rerun_count,
        output_dir=output_dir,
        scenario_names=scenario_names,
        scenario_pack_path=scenario_pack_path,
        population_pack_path=population_pack_path,
        semantic_mode=semantic_mode,
        semantic_model=semantic_model,
        policy_mode=policy_mode,
        policy=policy,
        metric_overrides=metric_overrides,
        cohort_overrides=cohort_overrides,
        progress_callback=progress_callback,
    )


def run_domain_regression_audit(
    *,
    domain_name: str,
    baseline_target: RegressionTarget,
    candidate_target: RegressionTarget,
    base_seed: int = 0,
    rerun_count: int = 3,
    output_dir: str | None = None,
    scenario_names: tuple[str, ...] | None = None,
    scenario_pack_path: str | None = None,
    population_pack_path: str | None = None,
    semantic_mode: str = "off",
    semantic_model: str = "gpt-5",
    policy_mode: str = "default",
    policy: RegressionPolicy | None = None,
    metric_overrides: tuple[RegressionPolicyOverride, ...] = (),
    cohort_overrides: tuple[RegressionPolicyOverride, ...] = (),
    progress_callback: ProgressCallback | None = None,
) -> dict[str, str | int]:
    """Run one regression comparison through the registered domain plug-in."""
    domain_definition = get_domain_definition(domain_name)
    if domain_definition.runner is None:
        raise ValueError(f"Domain `{domain_name}` is missing a runner.")
    default_output_dir = _default_regression_output_dir(
        baseline_target=baseline_target,
        candidate_target=candidate_target,
        base_seed=base_seed,
        domain_definition=domain_definition,
    )
    resolved_output_dir = Path(output_dir or default_output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    baseline_summary, baseline_runs = _run_target_reruns(
        target=baseline_target,
        base_seed=base_seed,
        rerun_count=rerun_count,
        scenario_names=scenario_names,
        scenario_pack_path=scenario_pack_path,
        population_pack_path=population_pack_path,
        output_dir=resolved_output_dir / "baseline",
        domain_definition=domain_definition,
        progress_callback=progress_callback,
        phase_label="baseline_reruns",
        phase_message="Running baseline reruns",
    )
    candidate_summary, candidate_runs = _run_target_reruns(
        target=candidate_target,
        base_seed=base_seed,
        rerun_count=rerun_count,
        scenario_names=scenario_names,
        scenario_pack_path=scenario_pack_path,
        population_pack_path=population_pack_path,
        output_dir=resolved_output_dir / "candidate",
        domain_definition=domain_definition,
        progress_callback=progress_callback,
        phase_label="candidate_reruns",
        phase_message="Running candidate reruns",
    )
    resolved_policy = policy or domain_definition.build_default_regression_policy(
        metric_overrides,
        cohort_overrides,
    )
    emit_progress(
        progress_callback,
        phase="build_regression_diff",
        message="Building regression diff",
        stage="start",
    )
    regression_diff = RegressionDiff(
        gating_mode=policy_mode,
        baseline_summary=baseline_summary,
        candidate_summary=candidate_summary,
        metric_deltas=_build_metric_deltas(baseline_summary, candidate_summary),
        cohort_deltas=_build_cohort_deltas(baseline_runs, candidate_runs),
        risk_flag_deltas=_build_risk_flag_deltas(baseline_runs, candidate_runs),
        notable_trace_deltas=_build_trace_deltas(baseline_runs, candidate_runs),
        slice_deltas=_build_slice_deltas(baseline_runs, candidate_runs),
        semantic_interpretation=None,
        decision=None,
        metadata=_build_regression_metadata(
            baseline_target=baseline_target,
            candidate_target=candidate_target,
            base_seed=base_seed,
            rerun_count=rerun_count,
            scenario_names=scenario_names,
            scenario_pack_path=scenario_pack_path,
            population_pack_path=population_pack_path,
            baseline_summary=baseline_summary,
            candidate_summary=candidate_summary,
            policy_name=resolved_policy.name,
            policy_mode=policy_mode,
            domain_definition=domain_definition,
        ),
    )
    emit_progress(
        progress_callback,
        phase="build_regression_diff",
        message="Built regression diff",
        stage="finish",
    )
    emit_progress(
        progress_callback,
        phase="apply_regression_policy",
        message="Applying regression policy",
        stage="start",
    )
    regression_diff = RegressionDiff(
        gating_mode=regression_diff.gating_mode,
        baseline_summary=regression_diff.baseline_summary,
        candidate_summary=regression_diff.candidate_summary,
        metric_deltas=regression_diff.metric_deltas,
        cohort_deltas=regression_diff.cohort_deltas,
        risk_flag_deltas=regression_diff.risk_flag_deltas,
        notable_trace_deltas=regression_diff.notable_trace_deltas,
        slice_deltas=regression_diff.slice_deltas,
        semantic_interpretation=None,
        decision=evaluate_regression_policy(
            regression_diff,
            resolved_policy,
            gating_mode=policy_mode,
        ),
        metadata=regression_diff.metadata,
    )
    emit_progress(
        progress_callback,
        phase="apply_regression_policy",
        message="Applied regression policy",
        stage="finish",
    )
    emit_progress(
        progress_callback,
        phase="interpret_semantics",
        message="Interpreting semantics",
        stage="start",
    )
    regression_diff = RegressionDiff(
        gating_mode=regression_diff.gating_mode,
        baseline_summary=regression_diff.baseline_summary,
        candidate_summary=regression_diff.candidate_summary,
        metric_deltas=regression_diff.metric_deltas,
        cohort_deltas=regression_diff.cohort_deltas,
        risk_flag_deltas=regression_diff.risk_flag_deltas,
        notable_trace_deltas=regression_diff.notable_trace_deltas,
        slice_deltas=regression_diff.slice_deltas,
        semantic_interpretation=interpret_regression_semantics(
            regression_diff,
            mode=semantic_mode,
            model_name=semantic_model,
        ),
        decision=regression_diff.decision,
        metadata={
            **regression_diff.metadata,
            "semantic_mode": semantic_mode,
            "semantic_model": semantic_model if semantic_mode != "off" else "",
        },
    )
    emit_progress(
        progress_callback,
        phase="interpret_semantics",
        message=(
            "Semantic interpretation skipped"
            if semantic_mode == "off"
            else "Interpreted semantics"
        ),
        stage="finish",
    )
    emit_progress(
        progress_callback,
        phase="write_artifacts",
        message="Writing regression artifacts",
        stage="start",
    )
    markdown_paths = RegressionMarkdownWriter().write(regression_diff, resolved_output_dir)
    json_paths = RegressionJsonWriter().write(regression_diff, resolved_output_dir)
    emit_progress(
        progress_callback,
        phase="write_artifacts",
        message="Wrote regression artifacts",
        stage="finish",
    )
    decision = regression_diff.decision
    return {
        **markdown_paths,
        **json_paths,
        "decision_status": decision.status if decision is not None else "pass",
        "exit_code": decision.exit_code if decision is not None else 0,
    }


def _default_regression_output_dir(
    *,
    baseline_target: RegressionTarget,
    candidate_target: RegressionTarget,
    base_seed: int,
    domain_definition: DomainDefinition,
) -> Path:
    """Build the default output path for one regression comparison run."""
    return (
        DEFAULT_OUTPUT_DIR
        / "regression"
        / (
            f"{slugify_name(baseline_target.label)}-"
            f"{domain_definition.build_target_identity(baseline_target)}-vs-"
            f"{slugify_name(candidate_target.label)}-"
            f"{domain_definition.build_target_identity(candidate_target)}"
        )
        / f"seed-{base_seed}"
    )


def _build_regression_metadata(
    *,
    baseline_target: RegressionTarget,
    candidate_target: RegressionTarget,
    base_seed: int,
    rerun_count: int,
    scenario_names: tuple[str, ...] | None,
    scenario_pack_path: str | None,
    population_pack_path: str | None,
    baseline_summary: RerunSummary,
    candidate_summary: RerunSummary,
    policy_name: str,
    policy_mode: str,
    domain_definition: DomainDefinition,
) -> dict[str, str | int]:
    """Build stable metadata for a regression comparison bundle."""
    return {
        "regression_id": _build_regression_id(
            baseline_target,
            candidate_target,
            base_seed,
            rerun_count,
            scenario_names,
            baseline_summary.metadata,
            candidate_summary.metadata,
        ),
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "display_name": f"{baseline_target.label} vs {candidate_target.label}",
        "base_seed": base_seed,
        "rerun_count": rerun_count,
        "seed_schedule": ",".join(str(seed) for seed in baseline_summary.seed_schedule),
        "baseline_label": baseline_target.label,
        "candidate_label": candidate_target.label,
        "baseline_target_mode": baseline_target.mode,
        "candidate_target_mode": candidate_target.mode,
        "baseline_target_identity": domain_definition.build_target_identity(baseline_target),
        "candidate_target_identity": domain_definition.build_target_identity(candidate_target),
        "baseline_target_endpoint_host": str(
            baseline_summary.metadata.get("target_endpoint_host", "")
        ),
        "candidate_target_endpoint_host": str(
            candidate_summary.metadata.get("target_endpoint_host", "")
        ),
        "scenario_pack_path": scenario_pack_path or "",
        "population_pack_path": population_pack_path or "",
        "domain_name": domain_definition.name,
        "regression_report_title": domain_definition.regression_report_title,
        "policy_name": policy_name,
        "policy_mode": policy_mode,
        "artifact_contract_version": "v1",
    }


def _run_target_reruns(
    *,
    target: RegressionTarget,
    base_seed: int,
    rerun_count: int,
    scenario_names: tuple[str, ...] | None,
    scenario_pack_path: str | None,
    population_pack_path: str | None,
    output_dir: Path,
    domain_definition: DomainDefinition,
    progress_callback: ProgressCallback | None = None,
    phase_label: str = "reruns",
    phase_message: str = "Running reruns",
) -> tuple[RerunSummary, tuple[RunResult, ...]]:
    """Execute one target repeatedly and collect both results and artifact paths."""
    if domain_definition.runner is None:
        raise ValueError(f"Domain `{domain_definition.name}` is missing a runner.")
    seed_schedule = build_seed_schedule(base_seed, rerun_count)
    run_results: list[RunResult] = []
    run_artifacts: list[RunArtifactPaths] = []
    emit_progress(
        progress_callback,
        phase=phase_label,
        message=phase_message,
        stage="start",
    )
    for seed in seed_schedule:
        run_output_dir = output_dir / f"seed-{seed}"
        run_result = domain_definition.runner.execute_target_audit(
            target=target,
            seed=seed,
            output_dir=str(run_output_dir),
            scenario_names=scenario_names,
            scenario_pack_path=scenario_pack_path,
            population_pack_path=population_pack_path,
            progress_callback=progress_callback,
        )
        artifact_paths = write_run_artifacts(run_result)
        run_results.append(run_result)
        run_artifacts.append(
            RunArtifactPaths(
                seed=seed,
                output_dir=str(run_output_dir),
                report_path=artifact_paths["report_path"],
                results_path=artifact_paths["results_path"],
                traces_path=artifact_paths["traces_path"],
                chart_path=artifact_paths["chart_path"],
            )
        )
        emit_progress(
            progress_callback,
            phase=phase_label,
            message=phase_message,
            stage="update",
            current=len(run_results),
            total=len(seed_schedule),
        )
    emit_progress(
        progress_callback,
        phase=phase_label,
        message=phase_message,
        stage="finish",
    )

    return (
        _summarize_target_runs(
            target=target,
            run_results=tuple(run_results),
            seed_schedule=seed_schedule,
            run_artifacts=tuple(run_artifacts),
            domain_definition=domain_definition,
        ),
        tuple(run_results),
    )


def _summarize_target_runs(
    *,
    target: RegressionTarget,
    run_results: tuple[RunResult, ...],
    seed_schedule: tuple[int, ...],
    run_artifacts: tuple[RunArtifactPaths, ...],
    domain_definition: DomainDefinition,
) -> RerunSummary:
    """Collapse one target's reruns into stable metric and metadata summaries."""
    metric_values = {
        metric_name: [] for metric_name in domain_definition.summary_metric_names
    }
    failure_mode_counts: Counter[FailureMode] = Counter()
    for run_result in run_results:
        metrics = domain_definition.summarize_run_metrics(run_result)
        for metric_name, value in metrics.items():
            metric_values[metric_name].append(value)
        failure_mode_counts.update(score.dominant_failure_mode for score in run_result.trace_scores)

    metric_summaries = tuple(
        _build_metric_summary(metric_name, tuple(values))
        for metric_name, values in metric_values.items()
    )
    metadata = dict(run_results[0].metadata if run_results else {})
    metadata["target_label"] = target.label
    metadata["target_mode"] = target.mode
    metadata["target_identity"] = (
        str(run_results[0].metadata.get("target_identity", "")) if run_results else ""
    )
    return RerunSummary(
        target=target,
        run_count=len(run_results),
        seed_schedule=seed_schedule,
        metric_summaries=metric_summaries,
        high_risk_cohort_count_mean=_summary_metric_value(metric_summaries, "high_risk_cohort_count"),
        dominant_failure_mode_counts=tuple(
            FailureModeCount(failure_mode=mode, count=count)
            for mode, count in failure_mode_counts.most_common()
        ),
        metadata=metadata,
        run_artifacts=run_artifacts,
    )

def _build_metric_summary(metric_name: str, values: tuple[float, ...]) -> MetricSummary:
    """Summarize one metric across reruns using mean/min/max/range."""
    if not values:
        return MetricSummary(metric_name=metric_name, mean=0.0, minimum=0.0, maximum=0.0, spread=0.0)
    minimum = min(values)
    maximum = max(values)
    mean = sum(values) / len(values)
    return MetricSummary(
        metric_name=metric_name,
        mean=round(mean, 6),
        minimum=round(minimum, 6),
        maximum=round(maximum, 6),
        spread=round(maximum - minimum, 6),
    )


def _build_metric_deltas(
    baseline_summary: RerunSummary,
    candidate_summary: RerunSummary,
) -> tuple[MetricDelta, ...]:
    """Compute baseline-vs-candidate deltas from rerun metric means."""
    baseline_lookup = {metric.metric_name: metric for metric in baseline_summary.metric_summaries}
    candidate_lookup = {metric.metric_name: metric for metric in candidate_summary.metric_summaries}
    metric_names = sorted(set(baseline_lookup).intersection(candidate_lookup))
    return tuple(
        MetricDelta(
            metric_name=name,
            baseline_mean=baseline_lookup[name].mean,
            candidate_mean=candidate_lookup[name].mean,
            delta=round(candidate_lookup[name].mean - baseline_lookup[name].mean, 6),
        )
        for name in metric_names
    )


def _build_cohort_deltas(
    baseline_runs: tuple[RunResult, ...],
    candidate_runs: tuple[RunResult, ...],
) -> tuple[CohortDelta, ...]:
    """Aggregate cohort changes across reruns and rank the most important ones first."""
    baseline_lookup = _aggregate_cohorts(baseline_runs)
    candidate_lookup = _aggregate_cohorts(candidate_runs)
    deltas: list[CohortDelta] = []
    for key in sorted(set(baseline_lookup).union(candidate_lookup)):
        baseline = baseline_lookup.get(key, _empty_cohort_aggregate())
        candidate = candidate_lookup.get(key, _empty_cohort_aggregate())
        scenario_name, archetype_label = key
        deltas.append(
            CohortDelta(
                scenario_name=scenario_name,
                archetype_label=archetype_label,
                baseline_risk_level=baseline["risk_level"],
                candidate_risk_level=candidate["risk_level"],
                baseline_failure_mode=baseline["dominant_failure_mode"],
                candidate_failure_mode=candidate["dominant_failure_mode"],
                baseline_mean_session_utility=baseline["mean_session_utility"],
                candidate_mean_session_utility=candidate["mean_session_utility"],
                session_utility_delta=round(
                    candidate["mean_session_utility"] - baseline["mean_session_utility"], 6
                ),
                abandonment_rate_delta=round(
                    candidate["abandonment_rate"] - baseline["abandonment_rate"], 6
                ),
                trust_delta_delta=round(
                    candidate["mean_trust_delta"] - baseline["mean_trust_delta"], 6
                ),
                skip_rate_delta=round(
                    candidate["mean_skip_rate"] - baseline["mean_skip_rate"], 6
                ),
            )
        )
    deltas.sort(
        key=lambda delta: (
            abs(delta.session_utility_delta)
            + abs(delta.abandonment_rate_delta)
            + abs(delta.trust_delta_delta)
            + abs(delta.skip_rate_delta)
        ),
        reverse=True,
    )
    return tuple(deltas)


def _build_risk_flag_deltas(
    baseline_runs: tuple[RunResult, ...],
    candidate_runs: tuple[RunResult, ...],
) -> tuple[RiskFlagDelta, ...]:
    """Compare risk-flag counts and severities between two rerun sets."""
    baseline_lookup = _aggregate_risk_flags(baseline_runs)
    candidate_lookup = _aggregate_risk_flags(candidate_runs)
    deltas: list[RiskFlagDelta] = []
    for key in sorted(set(baseline_lookup).union(candidate_lookup)):
        baseline = baseline_lookup.get(key, {"count": 0, "top_severity": None})
        candidate = candidate_lookup.get(key, {"count": 0, "top_severity": None})
        scenario_name, archetype_label = key
        deltas.append(
            RiskFlagDelta(
                scenario_name=scenario_name,
                archetype_label=archetype_label,
                baseline_count=int(baseline["count"]),
                candidate_count=int(candidate["count"]),
                delta=int(candidate["count"] - baseline["count"]),
                baseline_top_severity=baseline["top_severity"],
                candidate_top_severity=candidate["top_severity"],
            )
        )
    deltas.sort(key=lambda delta: (abs(delta.delta), _risk_rank(delta.candidate_top_severity)), reverse=True)
    return tuple(deltas)


def _build_trace_deltas(
    baseline_runs: tuple[RunResult, ...],
    candidate_runs: tuple[RunResult, ...],
) -> tuple[TraceDelta, ...]:
    """Surface the most changed traces across baseline and candidate reruns."""
    baseline_lookup = _aggregate_trace_scores(baseline_runs)
    candidate_lookup = _aggregate_trace_scores(candidate_runs)
    deltas: list[TraceDelta] = []
    for trace_id in sorted(set(baseline_lookup).union(candidate_lookup)):
        baseline = baseline_lookup.get(trace_id, _empty_trace_aggregate(trace_id))
        candidate = candidate_lookup.get(trace_id, _empty_trace_aggregate(trace_id))
        deltas.append(
            TraceDelta(
                trace_id=trace_id,
                scenario_name=candidate["scenario_name"] or baseline["scenario_name"],
                archetype_label=candidate["archetype_label"] or baseline["archetype_label"],
                baseline_mean_utility=baseline["mean_session_utility"],
                candidate_mean_utility=candidate["mean_session_utility"],
                session_utility_delta=round(
                    candidate["mean_session_utility"] - baseline["mean_session_utility"], 6
                ),
                baseline_mean_risk_score=baseline["mean_trace_risk_score"],
                candidate_mean_risk_score=candidate["mean_trace_risk_score"],
                trace_risk_score_delta=round(
                    candidate["mean_trace_risk_score"] - baseline["mean_trace_risk_score"], 6
                ),
                baseline_failure_mode=baseline["dominant_failure_mode"],
                candidate_failure_mode=candidate["dominant_failure_mode"],
            )
        )
    deltas.sort(
        key=lambda delta: abs(delta.session_utility_delta) + abs(delta.trace_risk_score_delta),
        reverse=True,
    )
    return tuple(deltas[:12])


def _build_slice_deltas(
    baseline_runs: tuple[RunResult, ...],
    candidate_runs: tuple[RunResult, ...],
) -> tuple[SliceDelta, ...]:
    """Compare discovered deterministic slices between baseline and candidate reruns."""
    baseline_lookup = _aggregate_slices(baseline_runs)
    candidate_lookup = _aggregate_slices(candidate_runs)
    deltas: list[SliceDelta] = []
    for signature in sorted(set(baseline_lookup).union(candidate_lookup)):
        baseline = baseline_lookup.get(signature, _empty_slice_aggregate(signature))
        candidate = candidate_lookup.get(signature, _empty_slice_aggregate(signature))
        change_type = _slice_change_type(baseline["trace_count"], candidate["trace_count"])
        deltas.append(
            SliceDelta(
                slice_id=str(candidate["slice_id"] or baseline["slice_id"]),
                feature_signature=signature,
                baseline_trace_count=int(baseline["trace_count"]),
                candidate_trace_count=int(candidate["trace_count"]),
                trace_count_delta=int(candidate["trace_count"] - baseline["trace_count"]),
                baseline_risk_level=baseline["risk_level"],
                candidate_risk_level=candidate["risk_level"],
                baseline_failure_mode=baseline["dominant_failure_mode"],
                candidate_failure_mode=candidate["dominant_failure_mode"],
                baseline_mean_session_utility=float(baseline["mean_session_utility"]),
                candidate_mean_session_utility=float(candidate["mean_session_utility"]),
                session_utility_delta=round(
                    float(candidate["mean_session_utility"])
                    - float(baseline["mean_session_utility"]),
                    6,
                ),
                trust_delta_delta=round(
                    float(candidate["mean_trust_delta"]) - float(baseline["mean_trust_delta"]),
                    6,
                ),
                skip_rate_delta=round(
                    float(candidate["mean_skip_rate"]) - float(baseline["mean_skip_rate"]),
                    6,
                ),
                change_type=change_type,
            )
        )
    deltas.sort(
        key=lambda delta: (
            delta.change_type != "stable",
            abs(delta.trace_count_delta)
            + abs(delta.session_utility_delta)
            + abs(delta.trust_delta_delta)
            + abs(delta.skip_rate_delta),
            _risk_rank(delta.candidate_risk_level or delta.baseline_risk_level),
        ),
        reverse=True,
    )
    return tuple(deltas[:5])


def _aggregate_cohorts(run_results: tuple[RunResult, ...]) -> dict[tuple[str, str], dict[str, object]]:
    """Aggregate cohort summaries across reruns by scenario and archetype."""
    aggregate: dict[tuple[str, str], dict[str, object]] = defaultdict(
        lambda: {
            "mean_session_utility_values": [],
            "abandonment_rate_values": [],
            "mean_trust_delta_values": [],
            "mean_skip_rate_values": [],
            "risk_levels": Counter(),
            "failure_modes": Counter(),
        }
    )
    for run_result in run_results:
        for cohort in run_result.cohort_summaries:
            key = (cohort.scenario_name, cohort.archetype_label)
            bucket = aggregate[key]
            bucket["mean_session_utility_values"].append(cohort.mean_session_utility)
            bucket["abandonment_rate_values"].append(cohort.abandonment_rate)
            bucket["mean_trust_delta_values"].append(cohort.mean_trust_delta)
            bucket["mean_skip_rate_values"].append(cohort.mean_skip_rate)
            bucket["risk_levels"][cohort.risk_level] += 1
            bucket["failure_modes"][cohort.dominant_failure_mode] += 1
    resolved: dict[tuple[str, str], dict[str, object]] = {}
    for key, bucket in aggregate.items():
        resolved[key] = {
            "mean_session_utility": round(_mean(bucket["mean_session_utility_values"]), 6),
            "abandonment_rate": round(_mean(bucket["abandonment_rate_values"]), 6),
            "mean_trust_delta": round(_mean(bucket["mean_trust_delta_values"]), 6),
            "mean_skip_rate": round(_mean(bucket["mean_skip_rate_values"]), 6),
            "risk_level": _top_risk_level(bucket["risk_levels"]),
            "dominant_failure_mode": _top_failure_mode(bucket["failure_modes"]),
        }
    return resolved


def _aggregate_risk_flags(run_results: tuple[RunResult, ...]) -> dict[tuple[str, str], dict[str, object]]:
    """Aggregate risk-flag counts and top severities across reruns."""
    aggregate: dict[tuple[str, str], dict[str, object]] = defaultdict(
        lambda: {"count": 0, "top_severity": None}
    )
    for run_result in run_results:
        for flag in run_result.risk_flags:
            key = (flag.scenario_name, flag.archetype_label)
            aggregate[key]["count"] += 1
            current = aggregate[key]["top_severity"]
            if current is None or _risk_rank(flag.severity) > _risk_rank(current):
                aggregate[key]["top_severity"] = flag.severity
    return dict(aggregate)


def _aggregate_trace_scores(run_results: tuple[RunResult, ...]) -> dict[str, dict[str, object]]:
    """Aggregate trace-level scores across reruns by stable trace id."""
    aggregate: dict[str, dict[str, object]] = defaultdict(
        lambda: {
            "scenario_name": "",
            "archetype_label": "",
            "session_utility_values": [],
            "trace_risk_score_values": [],
            "failure_modes": Counter(),
        }
    )
    for run_result in run_results:
        for score in run_result.trace_scores:
            bucket = aggregate[score.trace_id]
            bucket["scenario_name"] = score.scenario_name
            bucket["archetype_label"] = score.archetype_label
            bucket["session_utility_values"].append(score.session_utility)
            bucket["trace_risk_score_values"].append(score.trace_risk_score)
            bucket["failure_modes"][score.dominant_failure_mode] += 1
    resolved: dict[str, dict[str, object]] = {}
    for trace_id, bucket in aggregate.items():
        resolved[trace_id] = {
            "scenario_name": bucket["scenario_name"],
            "archetype_label": bucket["archetype_label"],
            "mean_session_utility": round(_mean(bucket["session_utility_values"]), 6),
            "mean_trace_risk_score": round(_mean(bucket["trace_risk_score_values"]), 6),
            "dominant_failure_mode": _top_failure_mode(bucket["failure_modes"]),
        }
    return resolved


def _aggregate_slices(
    run_results: tuple[RunResult, ...],
) -> dict[tuple[str, ...], dict[str, object]]:
    """Aggregate discovered slices across reruns by stable feature signature."""
    aggregate: dict[tuple[str, ...], dict[str, object]] = defaultdict(
        lambda: {
            "slice_id": "",
            "trace_count_values": [],
            "mean_session_utility_values": [],
            "mean_trust_delta_values": [],
            "mean_skip_rate_values": [],
            "risk_levels": Counter(),
            "failure_modes": Counter(),
        }
    )
    for run_result in run_results:
        for slice_summary in run_result.slice_discovery.slice_summaries:
            bucket = aggregate[slice_summary.feature_signature]
            bucket["slice_id"] = slice_summary.slice_id
            bucket["trace_count_values"].append(slice_summary.trace_count)
            bucket["mean_session_utility_values"].append(slice_summary.mean_session_utility)
            bucket["mean_trust_delta_values"].append(slice_summary.mean_trust_delta)
            bucket["mean_skip_rate_values"].append(slice_summary.mean_skip_rate)
            bucket["risk_levels"][slice_summary.risk_level] += 1
            bucket["failure_modes"][slice_summary.dominant_failure_mode] += 1
    resolved: dict[tuple[str, ...], dict[str, object]] = {}
    for signature, bucket in aggregate.items():
        resolved[signature] = {
            "slice_id": bucket["slice_id"],
            "trace_count": round(_mean(bucket["trace_count_values"]), 6),
            "mean_session_utility": round(_mean(bucket["mean_session_utility_values"]), 6),
            "mean_trust_delta": round(_mean(bucket["mean_trust_delta_values"]), 6),
            "mean_skip_rate": round(_mean(bucket["mean_skip_rate_values"]), 6),
            "risk_level": _top_risk_level(bucket["risk_levels"]),
            "dominant_failure_mode": _top_failure_mode(bucket["failure_modes"]),
        }
    return resolved


def _empty_cohort_aggregate() -> dict[str, object]:
    return {
        "mean_session_utility": 0.0,
        "abandonment_rate": 0.0,
        "mean_trust_delta": 0.0,
        "mean_skip_rate": 0.0,
        "risk_level": "low",
        "dominant_failure_mode": "no_major_failure",
    }


def _empty_trace_aggregate(trace_id: str) -> dict[str, object]:
    del trace_id
    return {
        "scenario_name": "",
        "archetype_label": "",
        "mean_session_utility": 0.0,
        "mean_trace_risk_score": 0.0,
        "dominant_failure_mode": "no_major_failure",
    }


def _empty_slice_aggregate(feature_signature: tuple[str, ...]) -> dict[str, object]:
    return {
        "slice_id": "",
        "feature_signature": feature_signature,
        "trace_count": 0.0,
        "mean_session_utility": 0.0,
        "mean_trust_delta": 0.0,
        "mean_skip_rate": 0.0,
        "risk_level": None,
        "dominant_failure_mode": "no_major_failure",
    }


def _summary_metric_value(metric_summaries: tuple[MetricSummary, ...], metric_name: str) -> float:
    """Read one metric mean from a tuple of metric summaries."""
    for metric in metric_summaries:
        if metric.metric_name == metric_name:
            return metric.mean
    return 0.0


def _top_risk_level(counts: Counter[str]) -> str:
    if not counts:
        return "low"
    return max(counts, key=lambda value: (counts[value], _risk_rank(value)))


def _top_failure_mode(counts: Counter[FailureMode]) -> FailureMode:
    if not counts:
        return "no_major_failure"
    return max(counts, key=lambda value: (counts[value], value != "no_major_failure"))


def _slice_change_type(
    baseline_trace_count: float,
    candidate_trace_count: float,
) -> str:
    if baseline_trace_count == 0 and candidate_trace_count > 0:
        return "appeared"
    if baseline_trace_count > 0 and candidate_trace_count == 0:
        return "disappeared"
    if baseline_trace_count != candidate_trace_count:
        return "changed"
    return "stable"


def _risk_rank(severity: str | None) -> int:
    if severity is None:
        return -1
    return _RISK_ORDER.get(severity, -1)


def _mean(values) -> float:
    """Return the mean of an iterable, or zero when it is empty."""
    values = tuple(values)
    if not values:
        return 0.0
    return sum(values) / len(values)


def _build_regression_id(
    baseline_target: RegressionTarget,
    candidate_target: RegressionTarget,
    base_seed: int,
    rerun_count: int,
    scenario_names: tuple[str, ...] | None,
    baseline_metadata: dict[str, str | int | float],
    candidate_metadata: dict[str, str | int | float],
) -> str:
    """Build a short stable identifier for one regression comparison bundle."""
    payload = {
        "baseline_label": baseline_target.label,
        "baseline_mode": baseline_target.mode,
        "baseline_endpoint": baseline_target.adapter_base_url or "",
        "candidate_label": candidate_target.label,
        "candidate_mode": candidate_target.mode,
        "candidate_endpoint": candidate_target.adapter_base_url or "",
        "base_seed": base_seed,
        "rerun_count": rerun_count,
        "scenarios": list(scenario_names or ()),
        "baseline_artifact_id": baseline_metadata.get("artifact_id", ""),
        "candidate_artifact_id": candidate_metadata.get("artifact_id", ""),
    }
    digest = sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return f"reg-{digest}"
