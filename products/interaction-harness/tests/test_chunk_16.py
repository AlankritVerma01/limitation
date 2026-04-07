from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from interaction_harness.audit import execute_domain_audit, write_run_artifacts
from interaction_harness.domain_registry import register_domain_definition
from interaction_harness.domains.base import StandardDomainRunner
from interaction_harness.domains.recommender import (
    CATALOG,
    ensure_reference_artifacts,
    history_for_genres,
    run_mock_recommender_service,
    run_reference_recommender_service,
)
from interaction_harness.domains.stub import build_stub_domain_definition
from interaction_harness.regression import run_domain_regression_audit
from interaction_harness.reporting.base import (
    DomainReportingHooks,
    ReportBulletSection,
    ReportTableSection,
)
from interaction_harness.schema import RegressionTarget


def test_recommender_domain_package_exposes_primary_owned_helpers() -> None:
    assert CATALOG
    assert history_for_genres(("action", "comedy"), 3)
    assert callable(run_reference_recommender_service)
    assert callable(run_mock_recommender_service)


def test_shared_artifact_writers_render_domain_supplied_sections(tmp_path: Path) -> None:
    register_domain_definition(_build_hooked_stub_domain_definition())

    run_result = execute_domain_audit(
        domain_name="stub",
        seed=11,
        output_dir=str(tmp_path / "stub-audit"),
        semantic_mode="off",
    )
    artifact_paths = write_run_artifacts(run_result)
    report_text = Path(artifact_paths["report_path"]).read_text(encoding="utf-8")
    payload = json.loads(Path(artifact_paths["results_path"]).read_text(encoding="utf-8"))

    assert "## Scenario Matrix" in report_text
    assert "## Cohort Signals" in report_text
    assert "## Trace Ledger" in report_text
    assert "metadata color: blue" in report_text
    assert payload["summary"]["stub_focus"] == "hooked"
    assert payload["summary"]["domain_metrics"]["mean_session_utility"] >= 0.0


def test_shared_regression_writer_renders_domain_supplied_sections(tmp_path: Path) -> None:
    register_domain_definition(_build_hooked_stub_domain_definition())

    result = run_domain_regression_audit(
        domain_name="stub",
        baseline_target=RegressionTarget(
            label="baseline",
            mode="reference_artifact",
            service_artifact_dir=str(tmp_path / "baseline"),
        ),
        candidate_target=RegressionTarget(
            label="candidate",
            mode="external_url",
            adapter_base_url="stub://candidate",
        ),
        base_seed=4,
        rerun_count=2,
        output_dir=str(tmp_path / "stub-regression"),
    )
    report_text = Path(result["regression_report_path"]).read_text(encoding="utf-8")
    payload = json.loads(Path(result["regression_summary_path"]).read_text(encoding="utf-8"))

    assert "## Delta Cohorts" in report_text
    assert "## Risk Spotlight" in report_text
    assert "## Slice Spotlight" in report_text
    assert "## Trace Spotlight" in report_text
    assert payload["summary"]["overall_direction"]


def test_reference_service_still_runs_through_preserved_public_path(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "reference-artifacts"
    ensure_reference_artifacts(artifact_dir)

    with run_reference_recommender_service(str(artifact_dir)) as (base_url, metadata):
        assert base_url.startswith("http://")
        assert metadata["service_kind"] == "reference"


def _build_hooked_stub_domain_definition():
    hooks = DomainReportingHooks(
        build_scenario_coverage_section=lambda run_result: ReportBulletSection(
            title="Scenario Matrix",
            bullets=tuple(
                f"{scenario.name} / {scenario.max_steps} steps"
                for scenario in run_result.run_config.scenarios
            ),
        ),
        build_cohort_summary_section=lambda run_result: ReportTableSection(
            title="Cohort Signals",
            columns=("Scenario", "Archetype", "Utility"),
            rows=tuple(
                (
                    cohort.scenario_name,
                    cohort.archetype_label,
                    f"{cohort.mean_session_utility:.3f}",
                )
                for cohort in run_result.cohort_summaries
            ),
        ),
        build_trace_score_section=lambda run_result: ReportTableSection(
            title="Trace Ledger",
            columns=("Trace", "Utility", "Risk"),
            rows=tuple(
                (
                    trace_score.trace_id,
                    f"{trace_score.session_utility:.3f}",
                    f"{trace_score.trace_risk_score:.3f}",
                )
                for trace_score in run_result.trace_scores
            ),
        ),
        build_metadata_highlights_section=lambda _run_result: ReportBulletSection(
            title="Metadata Highlights",
            bullets=("metadata color: blue",),
        ),
        build_run_summary_fields=lambda _run_result: {"stub_focus": "hooked"},
        build_regression_cohort_change_section=lambda regression_diff: ReportTableSection(
            title="Delta Cohorts",
            columns=("Scenario", "Utility Δ"),
            rows=tuple(
                (
                    cohort.scenario_name,
                    f"{cohort.session_utility_delta:+.3f}",
                )
                for cohort in regression_diff.cohort_deltas
            ),
        ),
        build_regression_risk_change_section=lambda regression_diff: ReportBulletSection(
            title="Risk Spotlight",
            bullets=(
                f"risk entries: {len(regression_diff.risk_flag_deltas)}",
            ),
        ),
        build_regression_slice_change_section=lambda regression_diff: ReportBulletSection(
            title="Slice Spotlight",
            bullets=(
                f"slice entries: {len(regression_diff.slice_deltas)}",
            ),
        ),
        build_regression_trace_change_section=lambda regression_diff: ReportTableSection(
            title="Trace Spotlight",
            columns=("Trace", "Utility Δ"),
            rows=tuple(
                (
                    trace.trace_id,
                    f"{trace.session_utility_delta:+.3f}",
                )
                for trace in regression_diff.notable_trace_deltas
            ),
        ),
    )
    definition = build_stub_domain_definition()
    hooked = replace(definition, reporting_hooks=hooks, runner=None)
    return replace(hooked, runner=StandardDomainRunner(definition=hooked))
