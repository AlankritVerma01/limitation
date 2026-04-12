"""Recommender-owned helpers used by the shared reporting pipeline."""

from __future__ import annotations

from ...contracts.core import RegressionDiff, RunResult
from ...reporting.base import (
    DomainReportingHooks,
    ReportBulletSection,
    ReportTableSection,
)

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


RECOMMENDER_REPORTING_HOOKS = DomainReportingHooks(
    build_scenario_coverage_section=lambda run_result: build_recommender_scenario_coverage_section(
        run_result
    ),
    build_cohort_summary_section=lambda run_result: build_recommender_cohort_summary_section(
        run_result
    ),
    build_trace_score_section=lambda run_result: build_recommender_trace_score_section(run_result),
    build_metadata_highlights_section=lambda run_result: build_recommender_metadata_highlights_section(
        run_result
    ),
    build_run_summary_fields=lambda run_result: build_recommender_run_summary_fields(run_result),
    build_regression_cohort_change_section=lambda regression_diff: build_recommender_regression_cohort_change_section(
        regression_diff
    ),
    build_regression_risk_change_section=lambda regression_diff: build_recommender_regression_risk_change_section(
        regression_diff
    ),
    build_regression_slice_change_section=lambda regression_diff: build_recommender_regression_slice_change_section(
        regression_diff
    ),
    build_regression_trace_change_section=lambda regression_diff: build_recommender_regression_trace_change_section(
        regression_diff
    ),
)


def build_recommender_run_executive_summary(run_result: RunResult) -> list[str]:
    """Return the short top-of-report summary lines for recommender audits."""
    high_risk = [cohort for cohort in run_result.cohort_summaries if cohort.risk_level == "high"]
    medium_risk = [cohort for cohort in run_result.cohort_summaries if cohort.risk_level == "medium"]
    strongest = max(
        run_result.cohort_summaries,
        key=lambda cohort: cohort.mean_session_utility,
        default=None,
    )
    weakest = min(
        run_result.cohort_summaries,
        key=lambda cohort: cohort.mean_session_utility,
        default=None,
    )
    lines: list[str] = []
    if high_risk:
        lines.append(
            f"Overall status is `mixed`: {len(high_risk)} high-risk cohort(s) and {len(medium_risk)} medium-risk cohort(s) were detected."
        )
    elif medium_risk:
        lines.append(
            f"Overall status is `watch`: no high-risk cohorts were detected, but {len(medium_risk)} medium-risk cohort(s) need follow-up."
        )
    else:
        lines.append("Overall status is `healthy`: no medium or high-risk cohorts were detected in this run.")
    if strongest is not None:
        lines.append(
            f"Strongest cohort: `{strongest.scenario_name}` / `{strongest.archetype_label}` with utility `{strongest.mean_session_utility:.3f}`."
        )
    if weakest is not None:
        lines.append(
            f"Main concern: `{weakest.scenario_name}` / `{weakest.archetype_label}` with failure mode `{weakest.dominant_failure_mode}` and utility `{weakest.mean_session_utility:.3f}`."
        )
        lines.append(
            f"Behavioral signal watch: first impression `{weakest.mean_first_impression_score:.3f}`, abandonment pressure `{weakest.mean_abandonment_pressure:.3f}`."
        )
    if high_risk:
        inspect = ", ".join(
            f"{cohort.scenario_name} / {cohort.archetype_label}" for cohort in high_risk[:2]
        )
        lines.append(f"Inspect next: representative failure traces for {inspect}.")
    elif strongest is not None:
        lines.append(
            f"Inspect next: compare the strongest trace from `{strongest.archetype_label}` against lower-utility cohorts for hidden failure patterns."
        )
    return lines[:4]


def select_recommender_representative_cohorts(run_result: RunResult):
    """Choose the small set of recommender cohorts worth showing in the report body."""
    failure_cohorts = [
        cohort
        for cohort in run_result.cohort_summaries
        if cohort.representative_failure_trace_id is not None
    ]
    failure_cohorts.sort(
        key=lambda cohort: (
            -_RISK_ORDER.get(cohort.risk_level, -1),
            cohort.mean_session_utility,
        )
    )
    success_cohorts = [
        cohort
        for cohort in run_result.cohort_summaries
        if cohort.representative_success_trace_id is not None
    ]
    success_cohorts.sort(
        key=lambda cohort: (
            _RISK_ORDER.get(cohort.risk_level, -1),
            -cohort.mean_session_utility,
        )
    )
    return tuple(failure_cohorts[:2]), tuple(success_cohorts[:2])


def build_recommender_regression_summary(regression_diff: RegressionDiff) -> dict[str, object]:
    """Build the compact recommender regression status summary."""
    improved = 0
    regressed = 0
    for cohort in regression_diff.cohort_deltas:
        score = (
            cohort.session_utility_delta
            - (0.6 * cohort.abandonment_rate_delta)
            + (0.4 * cohort.trust_delta_delta)
            - (0.3 * cohort.skip_rate_delta)
            + (0.08 * (_risk_rank(cohort.baseline_risk_level) - _risk_rank(cohort.candidate_risk_level)))
        )
        if score > 0.05:
            improved += 1
        elif score < -0.05:
            regressed += 1
    added_risks = sum(
        1
        for risk in regression_diff.risk_flag_deltas
        if risk.baseline_count == 0 and risk.candidate_count > 0
    )
    removed_risks = sum(
        1
        for risk in regression_diff.risk_flag_deltas
        if risk.baseline_count > 0 and risk.candidate_count == 0
    )
    changed_slices = sum(
        1 for slice_delta in regression_diff.slice_deltas if slice_delta.change_type == "changed"
    )
    appeared_slices = sum(
        1 for slice_delta in regression_diff.slice_deltas if slice_delta.change_type == "appeared"
    )
    disappeared_slices = sum(
        1 for slice_delta in regression_diff.slice_deltas if slice_delta.change_type == "disappeared"
    )
    spreads = [metric.spread for metric in regression_diff.baseline_summary.metric_summaries] + [
        metric.spread for metric in regression_diff.candidate_summary.metric_summaries
    ]
    max_spread = max(spreads, default=0.0)
    if regressed == 0 and improved > 0 and added_risks == 0:
        overall_direction = "candidate improved"
    elif improved == 0 and (regressed > 0 or added_risks > removed_risks):
        overall_direction = "candidate regressed"
    elif improved == 0 and regressed == 0 and added_risks == 0 and removed_risks == 0:
        overall_direction = "no material change"
    else:
        overall_direction = "mixed"
    return {
        "overall_direction": overall_direction,
        "improved_cohort_count": improved,
        "regressed_cohort_count": regressed,
        "added_risk_flag_count": added_risks,
        "removed_risk_flag_count": removed_risks,
        "changed_slice_count": changed_slices,
        "appeared_slice_count": appeared_slices,
        "disappeared_slice_count": disappeared_slices,
        "variance_note": (
            "low observed variance across reruns"
            if max_spread <= 0.01
            else "visible rerun variance; interpret small deltas carefully"
        ),
        "candidate_target_identity": str(
            regression_diff.metadata.get("candidate_target_identity", "")
        ),
        "baseline_target_identity": str(
            regression_diff.metadata.get("baseline_target_identity", "")
        ),
    }


def build_recommender_regression_important_changes(
    regression_diff: RegressionDiff,
) -> list[str]:
    """Select the small set of recommender deltas worth highlighting first."""
    changes: list[str] = []
    for cohort in regression_diff.cohort_deltas[:3]:
        magnitude = (
            abs(cohort.session_utility_delta)
            + abs(cohort.abandonment_rate_delta)
            + abs(cohort.trust_delta_delta)
            + abs(cohort.skip_rate_delta)
        )
        if magnitude < 0.01:
            continue
        changes.append(
            f"{cohort.scenario_name} / {cohort.archetype_label}: utility {cohort.session_utility_delta:+.3f}, "
            f"abandonment {cohort.abandonment_rate_delta:+.3f}, trust {cohort.trust_delta_delta:+.3f}"
        )
    for risk in regression_diff.risk_flag_deltas:
        if risk.delta != 0:
            direction = "added" if risk.delta > 0 else "removed"
            changes.append(
                f"{risk.scenario_name} / {risk.archetype_label}: {direction} {abs(risk.delta)} risk flag(s)"
            )
        if len(changes) >= 3:
            break
    for slice_delta in regression_diff.slice_deltas:
        if slice_delta.change_type != "stable":
            signature = ", ".join(slice_delta.feature_signature)
            changes.append(
                f"{signature}: {slice_delta.change_type}, utility {slice_delta.session_utility_delta:+.3f}, trust {slice_delta.trust_delta_delta:+.3f}"
            )
        if len(changes) >= 3:
            break
    for trace in regression_diff.notable_trace_deltas:
        if abs(trace.session_utility_delta) >= 0.02 or abs(trace.trace_risk_score_delta) >= 0.02:
            changes.append(
                f"{trace.trace_id}: utility {trace.session_utility_delta:+.3f}, risk {trace.trace_risk_score_delta:+.3f}"
            )
        if len(changes) >= 3:
            break
    return changes[:3]


def build_recommender_scenario_coverage_section(run_result: RunResult) -> ReportBulletSection:
    """Build the recommender scenario coverage section for shared markdown rendering."""
    bullets = []
    for scenario in run_result.run_config.scenarios:
        risk_tags = ", ".join(scenario.risk_focus_tags) or "n/a"
        context_hint = scenario.context_hint or "n/a"
        bullets.append(
            f"`{scenario.name}`: {scenario.description} "
            f"(history depth `{scenario.history_depth}`, max steps `{scenario.max_steps}`, "
            f"goal `{scenario.test_goal or 'n/a'}`, risk tags `{risk_tags}`, "
            f"context hint `{context_hint}`)"
        )
    return ReportBulletSection(
        title="Scenario Coverage",
        bullets=tuple(bullets),
    )


def build_recommender_cohort_summary_section(run_result: RunResult) -> ReportTableSection:
    """Build the recommender cohort summary table for shared markdown rendering."""
    return ReportTableSection(
        title="Cohort Summary",
        columns=(
            "Scenario",
            "Archetype",
            "Risk",
            "Failure Mode",
            "Utility",
            "First Impression",
            "Abandon Pressure",
            "Trust Δ",
        ),
        rows=tuple(
            (
                cohort.scenario_name,
                cohort.archetype_label,
                cohort.risk_level,
                cohort.dominant_failure_mode,
                f"{cohort.mean_session_utility:.3f}",
                f"{cohort.mean_first_impression_score:.3f}",
                f"{cohort.mean_abandonment_pressure:.3f}",
                f"{cohort.mean_trust_delta:.3f}",
            )
            for cohort in run_result.cohort_summaries
        ),
    )


def build_recommender_trace_score_section(run_result: RunResult) -> ReportTableSection:
    """Build the recommender trace-score table for shared markdown rendering."""
    return ReportTableSection(
        title="Trace Scores",
        columns=(
            "Trace",
            "Scenario",
            "Archetype",
            "Utility",
            "First Impression",
            "Abandon Pressure",
            "Failure Mode",
            "Trust Δ",
            "Abandoned",
        ),
        rows=tuple(
            (
                score.trace_id,
                score.scenario_name,
                score.archetype_label,
                f"{score.session_utility:.3f}",
                f"{score.first_impression_score:.3f}",
                f"{score.abandonment_pressure:.3f}",
                score.dominant_failure_mode,
                f"{score.trust_delta:.3f}",
                str(score.abandoned),
            )
            for score in run_result.trace_scores
        ),
    )


def build_recommender_metadata_highlights_section(run_result: RunResult) -> ReportBulletSection:
    """Build recommender-specific metadata highlights for the shared metadata section."""
    bullets = [
        f"Target identity: `{run_result.metadata.get('target_identity', 'unknown')}`",
        f"Target endpoint host: `{run_result.metadata.get('target_endpoint_host', 'n/a')}`",
        f"Service metadata status: `{run_result.metadata.get('service_metadata_status', 'unknown')}`",
        f"Contract version: `{run_result.metadata.get('artifact_contract_version', 'v1')}`",
    ]
    if run_result.metadata.get("dataset"):
        bullets.append(f"Dataset: `{run_result.metadata.get('dataset', '')}`")
    if run_result.metadata.get("data_source"):
        bullets.append(f"Data source: `{run_result.metadata.get('data_source', '')}`")
    if run_result.metadata.get("model_kind"):
        bullets.append(f"Model kind: `{run_result.metadata.get('model_kind', '')}`")
    if run_result.metadata.get("model_id"):
        bullets.append(f"Model ID: `{run_result.metadata.get('model_id', '')}`")
    return ReportBulletSection(
        title="Metadata Highlights",
        bullets=tuple(bullets),
    )


def build_recommender_run_summary_fields(run_result: RunResult) -> dict[str, object]:
    """Build additive recommender summary fields for results.json."""
    strongest = max(
        run_result.cohort_summaries,
        key=lambda cohort: cohort.mean_session_utility,
        default=None,
    )
    return {
        "mean_first_impression_score": (
            sum(score.first_impression_score for score in run_result.trace_scores)
            / len(run_result.trace_scores)
            if run_result.trace_scores
            else 0.0
        ),
        "mean_abandonment_pressure": (
            sum(score.abandonment_pressure for score in run_result.trace_scores)
            / len(run_result.trace_scores)
            if run_result.trace_scores
            else 0.0
        ),
        "strongest_cohort": (
            {
                "scenario_name": strongest.scenario_name,
                "archetype_label": strongest.archetype_label,
                "mean_session_utility": strongest.mean_session_utility,
            }
            if strongest is not None
            else None
        ),
    }


def build_recommender_regression_cohort_change_section(
    regression_diff: RegressionDiff,
) -> ReportTableSection:
    """Build the recommender cohort-change table for shared regression rendering."""
    return ReportTableSection(
        title="Cohort Changes",
        columns=(
            "Scenario",
            "Archetype",
            "Baseline Risk",
            "Candidate Risk",
            "Failure Mode",
            "Utility Δ",
            "Abandon Δ",
            "Trust Δ",
            "Skip Δ",
        ),
        rows=tuple(
            (
                cohort.scenario_name,
                cohort.archetype_label,
                cohort.baseline_risk_level,
                cohort.candidate_risk_level,
                (
                    cohort.candidate_failure_mode
                    if cohort.candidate_failure_mode != "no_major_failure"
                    else cohort.baseline_failure_mode
                ),
                f"{cohort.session_utility_delta:+.3f}",
                f"{cohort.abandonment_rate_delta:+.3f}",
                f"{cohort.trust_delta_delta:+.3f}",
                f"{cohort.skip_rate_delta:+.3f}",
            )
            for cohort in regression_diff.cohort_deltas
        ),
    )


def build_recommender_regression_risk_change_section(
    regression_diff: RegressionDiff,
) -> ReportBulletSection:
    """Build the recommender risk-change section for shared regression rendering."""
    visible_risks = [
        risk
        for risk in regression_diff.risk_flag_deltas
        if risk.baseline_count != 0 or risk.candidate_count != 0
    ]
    bullets = (
        tuple(
            f"{risk.scenario_name} / {risk.archetype_label}: "
            f"baseline `{risk.baseline_count}` ({risk.baseline_top_severity or 'none'}) -> "
            f"candidate `{risk.candidate_count}` ({risk.candidate_top_severity or 'none'})"
            for risk in visible_risks
        )
        if visible_risks
        else ("No risk flag changes were detected.",)
    )
    return ReportBulletSection(title="Risk Changes", bullets=bullets)


def build_recommender_regression_slice_change_section(
    regression_diff: RegressionDiff,
) -> ReportTableSection | ReportBulletSection:
    """Build the recommender slice-change section for shared regression rendering."""
    visible_slices = [
        slice_delta
        for slice_delta in regression_diff.slice_deltas
        if slice_delta.change_type != "stable"
        or abs(slice_delta.session_utility_delta) >= 0.01
        or abs(slice_delta.trust_delta_delta) >= 0.01
        or abs(slice_delta.skip_rate_delta) >= 0.01
    ]
    if not visible_slices:
        return ReportBulletSection(
            title="Discovered Slice Changes",
            bullets=("No material discovered-slice changes were detected.",),
        )
    return ReportTableSection(
        title="Discovered Slice Changes",
        columns=(
            "Signature",
            "Change",
            "Baseline Count",
            "Candidate Count",
            "Risk",
            "Failure Mode",
            "Utility Δ",
            "Trust Δ",
            "Skip Δ",
        ),
        rows=tuple(
            (
                ", ".join(slice_delta.feature_signature),
                slice_delta.change_type,
                str(slice_delta.baseline_trace_count),
                str(slice_delta.candidate_trace_count),
                f"{slice_delta.baseline_risk_level or 'none'} -> {slice_delta.candidate_risk_level or 'none'}",
                (
                    slice_delta.candidate_failure_mode
                    if slice_delta.candidate_failure_mode != "no_major_failure"
                    else slice_delta.baseline_failure_mode
                ),
                f"{slice_delta.session_utility_delta:+.3f}",
                f"{slice_delta.trust_delta_delta:+.3f}",
                f"{slice_delta.skip_rate_delta:+.3f}",
            )
            for slice_delta in visible_slices
        ),
    )


def build_recommender_regression_trace_change_section(
    regression_diff: RegressionDiff,
) -> ReportTableSection:
    """Build the recommender trace-change table for shared regression rendering."""
    return ReportTableSection(
        title="Notable Trace Changes",
        columns=(
            "Trace",
            "Scenario",
            "Archetype",
            "Utility Δ",
            "Risk Δ",
            "Baseline Failure",
            "Candidate Failure",
        ),
        rows=tuple(
            (
                trace.trace_id,
                trace.scenario_name,
                trace.archetype_label,
                f"{trace.session_utility_delta:+.3f}",
                f"{trace.trace_risk_score_delta:+.3f}",
                trace.baseline_failure_mode,
                trace.candidate_failure_mode,
            )
            for trace in regression_diff.notable_trace_deltas
        ),
    )


def _risk_rank(severity: str | None) -> int:
    if severity is None:
        return -1
    return _RISK_ORDER.get(severity, -1)
