from __future__ import annotations

from pathlib import Path

import pytest

SLOW_TEST_NAME_PARTS = (
    "artifact_dir_produces_visible_deltas",
    "audit_progress_and_summary",
    "audit_runs_through_domain_runner",
    "audit_and_plan_run_audit_produce_equivalent",
    "audit_writes_semantic_advisory",
    "behavioral_signals_are_emitted",
    "changed_regression_surfaces_slice_changes",
    "cli_compare_mode_writes",
    "cli_runs_both_scenarios",
    "cli_runs_end_to_end",
    "compare_",
    "different_seed_changes_output",
    "discovered_slices_include",
    "execute_plan_runs_saved_audit",
    "external_url",
    "fail_level_regression",
    "fixture_generated_pack_can_be_reused_for_single_run",
    "fixture_generated_population_pack_can_be_reused_for_single_run",
    "fixture_run_semantics",
    "fixture_semantic_mode_writes",
    "generated_scenario_pack_changes",
    "http_adapter_normalizes_service_response",
    "json_output_includes_enriched_score_fields",
    "modified_candidate_artifact_produces",
    "orchestration_executor_runs_audit_plan",
    "population_pack_can_be_reused_for_regression_runs",
    "plan_run_and_execute_plan_support_compare",
    "provider_run_semantics",
    "recommender_slice_features",
    "reference_service_still_runs",
    "regression_outputs_include",
    "regression_semantics",
    "report_writers_consume_precomputed_result_only",
    "rollout_engine_is_transport_agnostic",
    "run_manifest",
    "run_swarm",
    "same_artifact_dir_regression",
    "same_seed_produces_same_json_result",
    "same_vs_same_regression",
    "semantic_mode_off_preserves",
    "semantic_mode_writes",
    "serve_reference",
    "single_run_external_url",
    "single_run_report",
    "single_run_results_include_slice",
    "trace_steps_include_decision_explanations",
)

SYSTEM_TEST_NAME_PARTS = (
    "audit",
    "compare",
    "external",
    "reference_service",
    "regression",
    "run_swarm",
    "serve_reference",
)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="Include service, subprocess, and full workflow Evidpath tests.",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    for item in items:
        _apply_derived_markers(item)

    if config.getoption("--run-slow"):
        return

    kept: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    for item in items:
        if item.get_closest_marker("slow"):
            deselected.append(item)
        else:
            kept.append(item)

    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = kept


def _apply_derived_markers(item: pytest.Item) -> None:
    path = Path(str(item.fspath))
    filename = path.name
    test_name = item.name

    if filename.endswith("_slow.py"):
        item.add_marker(pytest.mark.slow)

    if filename in {"test_examples_slow.py", "test_hf_example_slow.py"}:
        item.add_marker(pytest.mark.example)

    if filename in {
        "test_examples_slow.py",
        "test_hf_example_slow.py",
        "test_reference_service_slow.py",
        "test_system_workflows_slow.py",
    }:
        item.add_marker(pytest.mark.system)

    if any(part in test_name for part in SLOW_TEST_NAME_PARTS):
        item.add_marker(pytest.mark.slow)

    if any(part in test_name for part in SYSTEM_TEST_NAME_PARTS):
        item.add_marker(pytest.mark.system)
