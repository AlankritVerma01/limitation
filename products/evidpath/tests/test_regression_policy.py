from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest
from evidpath.cli import main
from evidpath.domains.recommender import (
    ARTIFACT_FILENAME,
    ensure_reference_artifacts,
)
from evidpath.regression import build_seed_schedule, run_regression_audit
from evidpath.regression_policy import (
    default_regression_policy,
    evaluate_regression_policy,
)
from evidpath.schema import (
    CohortDelta,
    FailureModeCount,
    MetricDelta,
    MetricSummary,
    RegressionDiff,
    RegressionPolicyOverride,
    RegressionPolicyScope,
    RegressionTarget,
    RerunSummary,
    RiskFlagDelta,
    TraceDelta,
)


def test_seed_schedule_is_deterministic() -> None:
    assert build_seed_schedule(11, 3) == (11, 12, 13)


def test_seed_schedule_rejects_non_positive_rerun_count() -> None:
    try:
        build_seed_schedule(11, 0)
    except ValueError as exc:
        assert "rerun_count must be at least 1" in str(exc)
    else:
        raise AssertionError("Expected build_seed_schedule to reject rerun_count=0.")


def test_modified_candidate_artifact_produces_visible_deltas(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline-artifacts"
    candidate_dir = tmp_path / "candidate-artifacts"
    ensure_reference_artifacts(baseline_dir)
    candidate_dir.mkdir(parents=True, exist_ok=True)
    baseline_payload = json.loads(
        (baseline_dir / ARTIFACT_FILENAME).read_text(encoding="utf-8")
    )
    candidate_payload = dict(baseline_payload)
    candidate_payload["artifact_id"] = "candidate-regression-test"
    candidate_items = []
    for item in baseline_payload["items"]:
        updated = dict(item)
        if item["genre"] in {"documentary", "horror"}:
            updated["quality"] = 0.98
            updated["popularity"] = 0.92
            updated["novelty"] = 0.88
        elif item["genre"] in {"action", "comedy"}:
            updated["quality"] = 0.18
            updated["popularity"] = 0.12
            updated["novelty"] = 0.22
        candidate_items.append(updated)
    candidate_payload["items"] = candidate_items
    (candidate_dir / ARTIFACT_FILENAME).write_text(
        json.dumps(candidate_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths = run_regression_audit(
        baseline_target=RegressionTarget(
            label="baseline",
            driver_kind="http_native_reference",
            driver_config={"artifact_dir": str(baseline_dir)},
        ),
        candidate_target=RegressionTarget(
            label="candidate",
            driver_kind="http_native_reference",
            driver_config={"artifact_dir": str(candidate_dir)},
        ),
        base_seed=6,
        rerun_count=2,
        output_dir=str(tmp_path / "regression-different"),
    )
    payload = json.loads(
        Path(paths["regression_summary_path"]).read_text(encoding="utf-8")
    )
    assert (
        payload["candidate_summary"]["metadata"]["artifact_id"]
        == "candidate-regression-test"
    )
    assert any(abs(metric["delta"]) > 0.001 for metric in payload["metric_deltas"])


def test_cli_compare_mode_writes_regression_artifacts(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    ensure_reference_artifacts(baseline_dir)
    ensure_reference_artifacts(candidate_dir)
    result = main(
        [
            "compare",
            "--domain",
            "recommender",
            "--seed",
            "7",
            "--rerun-count",
            "2",
            "--baseline-artifact-dir",
            str(baseline_dir),
            "--candidate-artifact-dir",
            str(candidate_dir),
            "--output-dir",
            str(tmp_path / "compare-output"),
        ]
    )
    assert Path(result["regression_report_path"]).exists()
    assert Path(result["regression_summary_path"]).exists()
    assert Path(result["regression_traces_path"]).exists()
    report_body = Path(result["regression_report_path"]).read_text(encoding="utf-8")
    assert "Regression Audit" in report_body
    assert "## Decision" in report_body
    assert result["decision_status"] == "pass"


def _build_regression_diff(
    *,
    metric_deltas: tuple[MetricDelta, ...] = (),
    cohort_deltas: tuple[CohortDelta, ...] = (),
    risk_flag_deltas: tuple[RiskFlagDelta, ...] = (),
    trace_deltas: tuple[TraceDelta, ...] = (),
    baseline_spread: float = 0.0,
    candidate_spread: float = 0.0,
) -> RegressionDiff:
    baseline_summary = RerunSummary(
        target=RegressionTarget(
            "baseline",
            "http_native_reference",
            {"artifact_dir": "/tmp/baseline"},
        ),
        run_count=2,
        seed_schedule=(1, 2),
        metric_summaries=(
            MetricSummary("mean_session_utility", 0.7, 0.7, 0.7, baseline_spread),
            MetricSummary("abandonment_rate", 0.1, 0.1, 0.1, baseline_spread),
        ),
        high_risk_cohort_count_mean=0.0,
        dominant_failure_mode_counts=(FailureModeCount("no_major_failure", 2),),
        metadata={"artifact_id": "baseline-artifact"},
    )
    candidate_summary = RerunSummary(
        target=RegressionTarget(
            "candidate",
            "http_native_reference",
            {"artifact_dir": "/tmp/candidate"},
        ),
        run_count=2,
        seed_schedule=(1, 2),
        metric_summaries=(
            MetricSummary("mean_session_utility", 0.7, 0.7, 0.7, candidate_spread),
            MetricSummary("abandonment_rate", 0.1, 0.1, 0.1, candidate_spread),
        ),
        high_risk_cohort_count_mean=0.0,
        dominant_failure_mode_counts=(FailureModeCount("no_major_failure", 2),),
        metadata={"artifact_id": "candidate-artifact"},
    )
    return RegressionDiff(
        gating_mode="default",
        baseline_summary=baseline_summary,
        candidate_summary=candidate_summary,
        metric_deltas=metric_deltas,
        cohort_deltas=cohort_deltas,
        risk_flag_deltas=risk_flag_deltas,
        notable_trace_deltas=trace_deltas,
        metadata={"display_name": "baseline vs candidate"},
    )


def _build_modified_candidate_artifacts(
    baseline_dir: Path, candidate_dir: Path
) -> None:
    ensure_reference_artifacts(baseline_dir)
    candidate_dir.mkdir(parents=True, exist_ok=True)
    baseline_payload = json.loads(
        (baseline_dir / ARTIFACT_FILENAME).read_text(encoding="utf-8")
    )
    candidate_payload = dict(baseline_payload)
    candidate_payload["artifact_id"] = "candidate-regression-policy"
    candidate_items = []
    for item in baseline_payload["items"]:
        updated = dict(item)
        if item["genre"] in {"documentary", "horror"}:
            updated["quality"] = 0.99
            updated["popularity"] = 0.96
            updated["novelty"] = 0.95
        else:
            updated["quality"] = 0.05
            updated["popularity"] = 0.04
            updated["novelty"] = 0.05
        candidate_items.append(updated)
    candidate_payload["items"] = candidate_items
    (candidate_dir / ARTIFACT_FILENAME).write_text(
        json.dumps(candidate_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_default_policy_passes_clean_regression() -> None:
    decision = evaluate_regression_policy(
        _build_regression_diff(
            metric_deltas=(
                MetricDelta("mean_session_utility", 0.7, 0.71, 0.01),
                MetricDelta("abandonment_rate", 0.1, 0.09, -0.01),
            ),
        ),
        default_regression_policy(),
    )
    assert decision.status == "pass"
    assert decision.exit_code == 0


def test_default_policy_warns_on_moderate_metric_regression() -> None:
    decision = evaluate_regression_policy(
        _build_regression_diff(
            metric_deltas=(MetricDelta("mean_session_utility", 0.7, 0.66, -0.04),),
        ),
        default_regression_policy(),
    )
    assert decision.status == "warn"
    assert any(
        check.check_id == "metric:mean_session_utility" for check in decision.checks
    )


def test_default_policy_fails_on_new_high_severity_risks() -> None:
    decision = evaluate_regression_policy(
        _build_regression_diff(
            risk_flag_deltas=(
                RiskFlagDelta(
                    "returning-user-home-feed",
                    "Low-patience",
                    0,
                    1,
                    1,
                    None,
                    "high",
                ),
            ),
        ),
        default_regression_policy(),
    )
    assert decision.status == "fail"
    assert decision.exit_code == 1


def test_metric_override_relaxes_one_metric_check() -> None:
    policy = default_regression_policy(
        metric_overrides=(
            RegressionPolicyOverride(
                scope=RegressionPolicyScope(metric_name="mean_session_utility"),
                warn_delta=0.08,
                fail_delta=0.16,
            ),
        ),
    )
    decision = evaluate_regression_policy(
        _build_regression_diff(
            metric_deltas=(
                MetricDelta("mean_session_utility", 0.7, 0.66, -0.04),
                MetricDelta("abandonment_rate", 0.1, 0.14, 0.04),
            ),
        ),
        policy,
    )
    metric_checks = {check.check_id: check for check in decision.checks}
    assert metric_checks["metric:mean_session_utility"].severity == "pass"
    assert metric_checks["metric:abandonment_rate"].severity == "warn"


def test_cohort_override_relaxes_matching_scope_only() -> None:
    policy = default_regression_policy(
        cohort_overrides=(
            RegressionPolicyOverride(
                scope=RegressionPolicyScope(
                    scenario_name="returning-user-home-feed",
                    archetype_label="Low-patience",
                ),
                warn_delta=0.3,
                fail_delta=0.4,
            ),
        ),
    )
    decision = evaluate_regression_policy(
        _build_regression_diff(
            cohort_deltas=(
                CohortDelta(
                    "returning-user-home-feed",
                    "Low-patience",
                    "medium",
                    "high",
                    "trust_collapse",
                    "trust_collapse",
                    0.5,
                    0.42,
                    -0.08,
                    0.06,
                    -0.04,
                    0.05,
                ),
                CohortDelta(
                    "sparse-history-home-feed",
                    "Low-patience",
                    "medium",
                    "high",
                    "trust_collapse",
                    "trust_collapse",
                    0.5,
                    0.42,
                    -0.08,
                    0.06,
                    -0.04,
                    0.05,
                ),
            ),
        ),
        policy,
    )
    cohort_checks = {
        check.check_id: check
        for check in decision.checks
        if check.check_id.startswith("cohort:")
    }
    assert (
        cohort_checks["cohort:returning-user-home-feed:Low-patience"].severity == "pass"
    )
    assert cohort_checks["cohort:sparse-history-home-feed:Low-patience"].severity in {
        "warn",
        "fail",
    }


def test_report_only_mode_suppresses_fail_exit_code() -> None:
    decision = evaluate_regression_policy(
        _build_regression_diff(
            risk_flag_deltas=(
                RiskFlagDelta(
                    "returning-user-home-feed",
                    "Low-patience",
                    0,
                    1,
                    1,
                    None,
                    "high",
                ),
            ),
        ),
        default_regression_policy(),
        gating_mode="report_only",
    )
    assert decision.status == "fail"
    assert decision.exit_code == 0


def test_same_artifact_dir_regression_passes_and_writes_decision(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)
    result = run_regression_audit(
        baseline_target=RegressionTarget(
            "baseline",
            "http_native_reference",
            {"artifact_dir": str(artifact_dir)},
        ),
        candidate_target=RegressionTarget(
            "candidate",
            "http_native_reference",
            {"artifact_dir": str(artifact_dir)},
        ),
        base_seed=4,
        rerun_count=2,
        output_dir=str(tmp_path / "regression"),
    )
    payload = json.loads(
        Path(result["regression_summary_path"]).read_text(encoding="utf-8")
    )
    assert result["decision_status"] == "pass"
    assert result["exit_code"] == 0
    assert payload["decision_status"] == "pass"
    assert "checks" in payload


def test_fail_level_regression_still_writes_artifacts(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline-artifacts"
    candidate_dir = tmp_path / "candidate-artifacts"
    _build_modified_candidate_artifacts(baseline_dir, candidate_dir)
    strict_policy = default_regression_policy(
        metric_overrides=(
            RegressionPolicyOverride(
                scope=RegressionPolicyScope(metric_name="mean_session_utility"),
                warn_delta=0.01,
                fail_delta=0.02,
            ),
        ),
    )
    result = run_regression_audit(
        baseline_target=RegressionTarget(
            "baseline",
            "http_native_reference",
            {"artifact_dir": str(baseline_dir)},
        ),
        candidate_target=RegressionTarget(
            "candidate",
            "http_native_reference",
            {"artifact_dir": str(candidate_dir)},
        ),
        base_seed=6,
        rerun_count=2,
        output_dir=str(tmp_path / "regression-fail"),
        policy=strict_policy,
    )
    assert result["decision_status"] == "fail"
    assert result["exit_code"] == 1
    assert Path(result["regression_report_path"]).exists()
    assert Path(result["regression_summary_path"]).exists()


def test_module_entrypoint_uses_main_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("evidpath.cli.main", lambda argv=None: {"exit_code": 1})
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("evidpath", run_name="__main__")
    assert exc_info.value.code == 1
