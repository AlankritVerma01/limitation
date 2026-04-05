"""Deterministic regression policy evaluation for compare-mode audits."""

from __future__ import annotations

from .schema import (
    CohortDelta,
    RegressionCheckResult,
    RegressionDecision,
    RegressionDecisionStatus,
    RegressionDiff,
    RegressionMetricPolicy,
    RegressionPolicy,
    RegressionPolicyOverride,
    RegressionPolicyScope,
)

_SEVERITY_ORDER: dict[RegressionDecisionStatus, int] = {
    "pass": 0,
    "warn": 1,
    "fail": 2,
}
_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def default_regression_policy(
    *,
    metric_overrides: tuple[RegressionPolicyOverride, ...] = (),
    cohort_overrides: tuple[RegressionPolicyOverride, ...] = (),
) -> RegressionPolicy:
    """Return the default portable regression gating policy."""
    return RegressionPolicy(
        name="default",
        metric_policies=(
            RegressionMetricPolicy("mean_session_utility", "lower", 0.03, 0.07),
            RegressionMetricPolicy("abandonment_rate", "higher", 0.03, 0.07),
            RegressionMetricPolicy("mean_engagement", "lower", 0.03, 0.07),
            RegressionMetricPolicy("mean_frustration", "higher", 0.03, 0.07),
            RegressionMetricPolicy("mean_trust_delta", "lower", 0.04, 0.1),
            RegressionMetricPolicy("mean_skip_rate", "higher", 0.03, 0.07),
            RegressionMetricPolicy("high_risk_cohort_count", "higher", 1.0, 2.0),
        ),
        metric_overrides=metric_overrides,
        cohort_overrides=cohort_overrides,
    )


def evaluate_regression_policy(
    regression_diff: RegressionDiff,
    policy: RegressionPolicy,
    *,
    gating_mode: str = "default",
) -> RegressionDecision:
    """Evaluate one regression diff against a deterministic policy."""
    checks = list(_metric_checks(regression_diff, policy))
    cohort_checks = tuple(_cohort_checks(regression_diff, policy))
    checks.extend(cohort_checks)
    checks.extend(_aggregate_cohort_checks(regression_diff, policy, cohort_checks))
    checks.extend(_risk_flag_checks(regression_diff, policy))
    checks.extend(_trace_checks(regression_diff, policy))
    checks.extend(_variance_checks(regression_diff, policy, tuple(checks)))
    checks.sort(key=_check_sort_key, reverse=True)

    triggered = [check for check in checks if check.severity != "pass"]
    status = max((check.severity for check in checks), key=_severity_rank, default="pass")
    reasons = tuple(check.message for check in triggered[:5])
    exit_code = 0 if gating_mode == "report_only" or status != "fail" else 1
    return RegressionDecision(
        status=status,
        reasons=reasons,
        checks=tuple(checks),
        exit_code=exit_code,
    )


def cohort_regression_score(cohort: CohortDelta) -> float:
    """Return a portable cohort regression score where negative means worse."""
    return round(
        cohort.session_utility_delta
        - (0.6 * cohort.abandonment_rate_delta)
        + (0.4 * cohort.trust_delta_delta)
        - (0.3 * cohort.skip_rate_delta)
        + (
            0.08
            * (
                _risk_rank(cohort.baseline_risk_level)
                - _risk_rank(cohort.candidate_risk_level)
            )
        ),
        6,
    )


def _metric_checks(
    regression_diff: RegressionDiff,
    policy: RegressionPolicy,
) -> tuple[RegressionCheckResult, ...]:
    metric_policy_by_name = {
        metric_policy.metric_name: metric_policy for metric_policy in policy.metric_policies
    }
    checks: list[RegressionCheckResult] = []
    for metric in regression_diff.metric_deltas:
        metric_policy = metric_policy_by_name.get(metric.metric_name)
        if metric_policy is None:
            continue
        warn_delta, fail_delta = _metric_thresholds(metric.metric_name, policy, metric_policy)
        severity, worse_magnitude = _metric_severity(metric.delta, metric_policy, warn_delta, fail_delta)
        checks.append(
            RegressionCheckResult(
                check_id=f"metric:{metric.metric_name}",
                severity=severity,
                scope=RegressionPolicyScope(metric_name=metric.metric_name),
                message=(
                    f"Metric `{metric.metric_name}` shifted by {metric.delta:+.3f} "
                    f"against a {severity} threshold."
                ),
                value=f"{metric.delta:+.3f}",
                threshold=_threshold_text(
                    warn=warn_delta,
                    fail=fail_delta,
                    direction=metric_policy.worse_direction,
                ),
                details={
                    "baseline_mean": metric.baseline_mean,
                    "candidate_mean": metric.candidate_mean,
                    "worse_magnitude": worse_magnitude,
                },
            )
        )
    return tuple(checks)


def _cohort_checks(
    regression_diff: RegressionDiff,
    policy: RegressionPolicy,
) -> tuple[RegressionCheckResult, ...]:
    checks: list[RegressionCheckResult] = []
    for cohort in regression_diff.cohort_deltas:
        score = cohort_regression_score(cohort)
        warn_delta, fail_delta = _cohort_thresholds(cohort, policy)
        worse_magnitude = max(0.0, -score)
        severity = _delta_severity(worse_magnitude, warn_delta, fail_delta)
        checks.append(
            RegressionCheckResult(
                check_id=f"cohort:{cohort.scenario_name}:{cohort.archetype_label}",
                severity=severity,
                scope=RegressionPolicyScope(
                    scenario_name=cohort.scenario_name,
                    archetype_label=cohort.archetype_label,
                ),
                message=(
                    f"Cohort `{cohort.scenario_name}` / `{cohort.archetype_label}` "
                    f"scored {score:+.3f}."
                ),
                value=f"{score:+.3f}",
                threshold=f"warn <= -{warn_delta:.3f}, fail <= -{fail_delta:.3f}",
                details={
                    "session_utility_delta": cohort.session_utility_delta,
                    "abandonment_rate_delta": cohort.abandonment_rate_delta,
                    "trust_delta_delta": cohort.trust_delta_delta,
                    "skip_rate_delta": cohort.skip_rate_delta,
                    "baseline_risk_level": cohort.baseline_risk_level,
                    "candidate_risk_level": cohort.candidate_risk_level,
                },
            )
        )
    return tuple(checks)


def _aggregate_cohort_checks(
    regression_diff: RegressionDiff,
    policy: RegressionPolicy,
    cohort_checks: tuple[RegressionCheckResult, ...],
) -> tuple[RegressionCheckResult, ...]:
    regressed_count = sum(check.severity != "pass" for check in cohort_checks)
    added_high_risk_count = sum(
        cohort.baseline_risk_level != "high" and cohort.candidate_risk_level == "high"
        for cohort in regression_diff.cohort_deltas
    )
    checks = [
        RegressionCheckResult(
            check_id="aggregate:regressed_cohorts",
            severity=_count_severity(
                regressed_count,
                policy.warn_regressed_cohort_count,
                policy.fail_regressed_cohort_count,
            ),
            scope=RegressionPolicyScope(),
            message=f"Regressed cohort count is {regressed_count}.",
            value=str(regressed_count),
            threshold=(
                f"warn >= {policy.warn_regressed_cohort_count}, "
                f"fail >= {policy.fail_regressed_cohort_count}"
            ),
        ),
        RegressionCheckResult(
            check_id="aggregate:added_high_risk_cohorts",
            severity=_count_severity(
                added_high_risk_count,
                policy.warn_added_high_risk_cohort_count,
                policy.fail_added_high_risk_cohort_count,
            ),
            scope=RegressionPolicyScope(),
            message=f"New high-risk cohort count is {added_high_risk_count}.",
            value=str(added_high_risk_count),
            threshold=(
                f"warn >= {policy.warn_added_high_risk_cohort_count}, "
                f"fail >= {policy.fail_added_high_risk_cohort_count}"
            ),
        ),
    ]
    return tuple(checks)


def _risk_flag_checks(
    regression_diff: RegressionDiff,
    policy: RegressionPolicy,
) -> tuple[RegressionCheckResult, ...]:
    added_risk_flag_count = sum(
        risk.baseline_count == 0 and risk.candidate_count > 0
        for risk in regression_diff.risk_flag_deltas
    )
    new_high_severity_count = sum(
        (risk.baseline_top_severity != "high") and (risk.candidate_top_severity == "high")
        for risk in regression_diff.risk_flag_deltas
    )
    escalated_risk_count = sum(
        _risk_rank(risk.candidate_top_severity) > _risk_rank(risk.baseline_top_severity)
        for risk in regression_diff.risk_flag_deltas
    )
    checks = [
        RegressionCheckResult(
            check_id="aggregate:added_risk_flags",
            severity=_count_severity(
                added_risk_flag_count,
                policy.warn_added_risk_flag_count,
                policy.fail_added_risk_flag_count,
            ),
            scope=RegressionPolicyScope(),
            message=f"Added risk flag count is {added_risk_flag_count}.",
            value=str(added_risk_flag_count),
            threshold=(
                f"warn >= {policy.warn_added_risk_flag_count}, "
                f"fail >= {policy.fail_added_risk_flag_count}"
            ),
        ),
        RegressionCheckResult(
            check_id="aggregate:new_high_severity_risks",
            severity=_count_severity(
                new_high_severity_count,
                policy.fail_new_high_severity_risk_flag_count,
                policy.fail_new_high_severity_risk_flag_count,
            ),
            scope=RegressionPolicyScope(),
            message=f"New high-severity risk flag count is {new_high_severity_count}.",
            value=str(new_high_severity_count),
            threshold=f"fail >= {policy.fail_new_high_severity_risk_flag_count}",
            details={"escalated_risk_count": escalated_risk_count},
        ),
    ]
    if checks[-1].severity == "pass" and escalated_risk_count > 0:
        checks[-1] = RegressionCheckResult(
            check_id="aggregate:new_high_severity_risks",
            severity="warn",
            scope=RegressionPolicyScope(),
            message=f"Risk severity escalated for {escalated_risk_count} cohort(s).",
            value=str(escalated_risk_count),
            threshold=f"warn when severity increases; fail >= {policy.fail_new_high_severity_risk_flag_count} new high risk(s)",
        )
    return tuple(checks)


def _trace_checks(
    regression_diff: RegressionDiff,
    policy: RegressionPolicy,
) -> tuple[RegressionCheckResult, ...]:
    count = sum(
        trace.session_utility_delta <= -policy.trace_utility_drop_threshold
        and trace.trace_risk_score_delta >= policy.trace_risk_increase_threshold
        for trace in regression_diff.notable_trace_deltas
    )
    return (
        RegressionCheckResult(
            check_id="aggregate:trace_regressions",
            severity=_count_severity(
                count,
                policy.warn_trace_regression_count,
                policy.fail_trace_regression_count,
            ),
            scope=RegressionPolicyScope(),
            message=f"Trace regression count is {count}.",
            value=str(count),
            threshold=(
                f"warn >= {policy.warn_trace_regression_count}, "
                f"fail >= {policy.fail_trace_regression_count}"
            ),
            details={
                "trace_utility_drop_threshold": policy.trace_utility_drop_threshold,
                "trace_risk_increase_threshold": policy.trace_risk_increase_threshold,
            },
        ),
    )


def _variance_checks(
    regression_diff: RegressionDiff,
    policy: RegressionPolicy,
    prior_checks: tuple[RegressionCheckResult, ...],
) -> tuple[RegressionCheckResult, ...]:
    max_spread = max(
        [metric.spread for metric in regression_diff.baseline_summary.metric_summaries]
        + [metric.spread for metric in regression_diff.candidate_summary.metric_summaries],
        default=0.0,
    )
    prior_severity = max((check.severity for check in prior_checks), key=_severity_rank, default="pass")
    severity: RegressionDecisionStatus = "pass"
    if max_spread >= policy.fail_variance_spread and prior_severity in {"warn", "fail"}:
        severity = "fail"
    elif max_spread >= policy.warn_variance_spread and prior_severity in {"warn", "fail"}:
        severity = "warn"
    return (
        RegressionCheckResult(
            check_id="aggregate:variance",
            severity=severity,
            scope=RegressionPolicyScope(),
            message=f"Observed max rerun spread is {max_spread:.3f}.",
            value=f"{max_spread:.3f}",
            threshold=(
                f"warn >= {policy.warn_variance_spread:.3f}, "
                f"fail >= {policy.fail_variance_spread:.3f} when regressions are also present"
            ),
        ),
    )


def _metric_thresholds(
    metric_name: str,
    policy: RegressionPolicy,
    metric_policy: RegressionMetricPolicy,
) -> tuple[float, float]:
    warn_delta = metric_policy.warn_delta
    fail_delta = metric_policy.fail_delta
    for override in policy.metric_overrides:
        if override.scope.metric_name == metric_name:
            warn_delta = override.warn_delta
            fail_delta = override.fail_delta
    return warn_delta, fail_delta


def _cohort_thresholds(
    cohort: CohortDelta,
    policy: RegressionPolicy,
) -> tuple[float, float]:
    warn_delta = policy.cohort_warn_delta
    fail_delta = policy.cohort_fail_delta
    for override in policy.cohort_overrides:
        if _scope_matches_cohort(override.scope, cohort):
            warn_delta = override.warn_delta
            fail_delta = override.fail_delta
    return warn_delta, fail_delta


def _metric_severity(
    delta: float,
    metric_policy: RegressionMetricPolicy,
    warn_delta: float,
    fail_delta: float,
) -> tuple[RegressionDecisionStatus, float]:
    worse_magnitude = delta if metric_policy.worse_direction == "higher" else -delta
    worse_magnitude = max(0.0, worse_magnitude)
    return _delta_severity(worse_magnitude, warn_delta, fail_delta), worse_magnitude


def _delta_severity(
    worse_magnitude: float,
    warn_delta: float,
    fail_delta: float,
) -> RegressionDecisionStatus:
    if worse_magnitude >= fail_delta:
        return "fail"
    if worse_magnitude >= warn_delta:
        return "warn"
    return "pass"


def _count_severity(value: int, warn_count: int, fail_count: int) -> RegressionDecisionStatus:
    if fail_count > 0 and value >= fail_count:
        return "fail"
    if warn_count > 0 and value >= warn_count:
        return "warn"
    return "pass"


def _scope_matches_cohort(scope: RegressionPolicyScope, cohort: CohortDelta) -> bool:
    if scope.metric_name is not None:
        return False
    if scope.scenario_name is not None and scope.scenario_name != cohort.scenario_name:
        return False
    if scope.archetype_label is not None and scope.archetype_label != cohort.archetype_label:
        return False
    return scope.scenario_name is not None or scope.archetype_label is not None


def _threshold_text(*, warn: float, fail: float, direction: str) -> str:
    comparator = ">=" if direction == "higher" else "<="
    sign = "" if direction == "higher" else "-"
    return f"warn {comparator} {sign}{warn:.3f}, fail {comparator} {sign}{fail:.3f}"


def _check_sort_key(check: RegressionCheckResult) -> tuple[int, int, str]:
    scoped = 1 if check.scope.metric_name or check.scope.scenario_name or check.scope.archetype_label else 0
    return (_severity_rank(check.severity), scoped, check.check_id)


def _severity_rank(severity: RegressionDecisionStatus) -> int:
    return _SEVERITY_ORDER[severity]


def _risk_rank(severity: str | None) -> int:
    if severity is None:
        return -1
    return _RISK_ORDER.get(severity, -1)
