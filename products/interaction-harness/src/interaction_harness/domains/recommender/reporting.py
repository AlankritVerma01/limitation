"""Recommender-owned helpers used by the shared reporting pipeline."""

from __future__ import annotations

from ...contracts.core import RegressionDiff, RunResult

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


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


def _risk_rank(severity: str | None) -> int:
    if severity is None:
        return -1
    return _RISK_ORDER.get(severity, -1)
