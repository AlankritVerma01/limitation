from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import evidpath as ih
import pytest
from evidpath.audit import (
    execute_domain_audit,
    write_run_artifacts,
)
from evidpath.cli import main
from evidpath.domain_registry import (
    get_domain_definition,
    list_domain_definitions,
    list_public_domain_definitions,
    register_domain_definition,
)
from evidpath.domains.base import StandardDomainRunner
from evidpath.domains.stub import build_stub_domain_definition
from evidpath.regression import run_domain_regression_audit
from evidpath.reporting.base import (
    DomainReportingHooks,
    ReportBulletSection,
    ReportTableSection,
)
from evidpath.schema import RegressionTarget


def test_public_surface_exports_domain_plugin_helpers() -> None:
    assert ih.execute_domain_audit is execute_domain_audit
    assert ih.run_domain_regression_audit is run_domain_regression_audit
    assert ih.register_domain_definition is register_domain_definition
    assert ih.list_domain_definitions is list_domain_definitions


def test_register_domain_definition_requires_runner() -> None:
    incomplete = replace(build_stub_domain_definition(), runner=None)

    with pytest.raises(ValueError) as exc_info:
        register_domain_definition(incomplete)

    assert "must define a runner" in str(exc_info.value)


def test_execute_domain_audit_supports_registered_stub_domain(tmp_path: Path) -> None:
    register_domain_definition(build_stub_domain_definition())

    run_result = execute_domain_audit(
        domain_name="stub",
        seed=5,
        output_dir=str(tmp_path / "stub-audit"),
        semantic_mode="off",
    )
    artifact_paths = write_run_artifacts(run_result)
    report_text = Path(artifact_paths["report_path"]).read_text(encoding="utf-8")

    assert run_result.metadata["domain_name"] == "stub"
    assert report_text.startswith("# Evidpath Stub Audit")
    assert run_result.trace_scores[0].trace_id.startswith("stub-")


def test_domain_regression_runs_through_registered_stub_domain(tmp_path: Path) -> None:
    register_domain_definition(build_stub_domain_definition())

    result = run_domain_regression_audit(
        domain_name="stub",
        baseline_target=RegressionTarget(
            label="baseline",
            driver_kind="http_native_reference",
            driver_config={"artifact_dir": str(tmp_path / "baseline")},
        ),
        candidate_target=RegressionTarget(
            label="candidate",
            driver_kind="http_native_external",
            driver_config={"base_url": "stub://candidate"},
        ),
        base_seed=2,
        rerun_count=2,
        output_dir=str(tmp_path / "stub-regression"),
    )
    payload = json.loads(
        Path(result["regression_summary_path"]).read_text(encoding="utf-8")
    )
    report_text = Path(result["regression_report_path"]).read_text(encoding="utf-8")

    assert payload["metadata"]["domain_name"] == "stub"
    assert payload["metadata"]["baseline_target_driver_kind"] == "http_native_reference"
    assert payload["metadata"]["candidate_target_driver_kind"] == "http_native_external"
    assert report_text.startswith("# Evidpath Stub Regression")


def test_registry_lists_registered_domains() -> None:
    register_domain_definition(build_stub_domain_definition())

    assert "recommender" in list_domain_definitions()
    assert "stub" in list_domain_definitions()


def test_missing_domain_fails_clearly() -> None:
    with pytest.raises(ValueError) as exc_info:
        get_domain_definition("missing-domain")

    assert "Unsupported domain `missing-domain`" in str(exc_info.value)


def test_shared_artifact_writers_render_domain_supplied_sections(
    tmp_path: Path,
) -> None:
    register_domain_definition(_build_hooked_stub_domain_definition())

    run_result = execute_domain_audit(
        domain_name="stub",
        seed=11,
        output_dir=str(tmp_path / "stub-audit"),
        semantic_mode="off",
    )
    artifact_paths = write_run_artifacts(run_result)
    report_text = Path(artifact_paths["report_path"]).read_text(encoding="utf-8")
    payload = json.loads(
        Path(artifact_paths["results_path"]).read_text(encoding="utf-8")
    )

    assert "## Scenario Matrix" in report_text
    assert "## Cohort Signals" in report_text
    assert "## Trace Ledger" in report_text
    assert "metadata color: blue" in report_text
    assert payload["summary"]["stub_focus"] == "hooked"
    assert payload["summary"]["domain_metrics"]["mean_session_utility"] >= 0.0


def test_shared_regression_writer_renders_domain_supplied_sections(
    tmp_path: Path,
) -> None:
    register_domain_definition(_build_hooked_stub_domain_definition())

    result = run_domain_regression_audit(
        domain_name="stub",
        baseline_target=RegressionTarget(
            label="baseline",
            driver_kind="http_native_reference",
            driver_config={"artifact_dir": str(tmp_path / "baseline")},
        ),
        candidate_target=RegressionTarget(
            label="candidate",
            driver_kind="http_native_external",
            driver_config={"base_url": "stub://candidate"},
        ),
        base_seed=4,
        rerun_count=2,
        output_dir=str(tmp_path / "stub-regression"),
    )
    report_text = Path(result["regression_report_path"]).read_text(encoding="utf-8")
    payload = json.loads(
        Path(result["regression_summary_path"]).read_text(encoding="utf-8")
    )

    assert "## Delta Cohorts" in report_text
    assert "## Risk Spotlight" in report_text
    assert "## Slice Spotlight" in report_text
    assert "## Trace Spotlight" in report_text
    assert payload["summary"]["overall_direction"]


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
        build_regression_cohort_change_section=lambda regression_diff: (
            ReportTableSection(
                title="Delta Cohorts",
                columns=("Scenario", "Utility Δ"),
                rows=tuple(
                    (
                        cohort.scenario_name,
                        f"{cohort.session_utility_delta:+.3f}",
                    )
                    for cohort in regression_diff.cohort_deltas
                ),
            )
        ),
        build_regression_risk_change_section=lambda regression_diff: (
            ReportBulletSection(
                title="Risk Spotlight",
                bullets=(f"risk entries: {len(regression_diff.risk_flag_deltas)}",),
            )
        ),
        build_regression_slice_change_section=lambda regression_diff: (
            ReportBulletSection(
                title="Slice Spotlight",
                bullets=(f"slice entries: {len(regression_diff.slice_deltas)}",),
            )
        ),
        build_regression_trace_change_section=lambda regression_diff: (
            ReportTableSection(
                title="Trace Spotlight",
                columns=("Trace", "Utility Δ"),
                rows=tuple(
                    (
                        trace.trace_id,
                        f"{trace.session_utility_delta:+.3f}",
                    )
                    for trace in regression_diff.notable_trace_deltas
                ),
            )
        ),
    )
    definition = build_stub_domain_definition()
    hooked = replace(definition, reporting_hooks=hooks, runner=None)
    return replace(hooked, runner=StandardDomainRunner(definition=hooked))


def test_public_domain_list_excludes_internal_stub_domain() -> None:
    register_domain_definition(build_stub_domain_definition())

    assert "recommender" in list_public_domain_definitions()
    assert "stub" not in list_public_domain_definitions()


def test_generate_scenarios_requires_explicit_domain(tmp_path: Path) -> None:
    try:
        main(
            [
                "generate-scenarios",
                "--mode",
                "fixture",
                "--brief",
                "evaluate recommendation quality for brand new users",
                "--output-dir",
                str(tmp_path),
            ]
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("Expected missing --domain to be rejected.")
