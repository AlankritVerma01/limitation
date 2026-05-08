"""Tests for public search domain wiring."""

from __future__ import annotations

from pathlib import Path

from evidpath.audit import execute_domain_audit
from evidpath.domain_registry import (
    get_domain_definition,
    list_public_domain_definitions,
)
from evidpath.domains.search import build_search_domain_definition
from evidpath.domains.search.services import open_search_service_context
from evidpath.regression import run_domain_regression_audit
from evidpath.schema import (
    RegressionTarget,
    RolloutConfig,
    RunConfig,
    ScoringConfig,
    trace_metric,
)


def test_search_domain_is_registered_publicly() -> None:
    assert "search" in list_public_domain_definitions()
    assert get_domain_definition("search").name == "search"


def test_search_domain_definition_builds_default_reference_audit(tmp_path: Path) -> None:
    run_result = execute_domain_audit(
        domain_name="search",
        seed=11,
        output_dir=str(tmp_path / "search-audit"),
        scenario_names=("time-sensitive-query",),
    )

    assert run_result.metadata["domain_name"] == "search"
    assert run_result.metadata["target_driver_kind"] == "http_native_reference"
    assert run_result.trace_scores
    assert trace_metric(run_result.trace_scores[0], "freshness_percentile") >= 0.0


def test_search_domain_summarizes_run_metrics(tmp_path: Path) -> None:
    definition = build_search_domain_definition()
    run_result = execute_domain_audit(
        domain_name="search",
        seed=12,
        output_dir=str(tmp_path / "search-summary"),
        scenario_names=("navigational-query",),
    )

    metrics = definition.summarize_run_metrics(run_result)

    assert "mean_top_bucket_relevance" in metrics
    assert "mean_snippet_query_overlap" in metrics


def test_search_domain_compare_runs_against_reference(tmp_path: Path) -> None:
    diff = run_domain_regression_audit(
        domain_name="search",
        baseline=RegressionTarget("baseline", "http_native_reference", {}),
        candidate=RegressionTarget("candidate", "http_native_reference", {}),
        output_dir=str(tmp_path / "search-compare"),
        scenario_names=("navigational-query",),
        rerun_count=1,
    )

    assert diff.baseline_summary.run_count == 1
    assert diff.candidate_summary.run_count == 1
    assert diff.decision is not None
    assert diff.decision.status == "pass"


def test_search_http_native_driver_config_is_external_context() -> None:
    run_config = RunConfig(
        run_name="search-driver-config",
        scenarios=(),
        rollout=RolloutConfig(
            seed=0,
            output_dir="tmp",
            service_mode="reference",
            service_artifact_dir=None,
            adapter_base_url=None,
            service_timeout_seconds=2.0,
            driver_kind="http_native_external",
            driver_config={"base_url": "http://127.0.0.1:8123/"},
        ),
        scoring=ScoringConfig(),
        agent_seeds=(),
    )

    with open_search_service_context(run_config) as (base_url, metadata):
        assert base_url == "http://127.0.0.1:8123"
        assert metadata["service_kind"] == "external"
        assert metadata["target_endpoint_host"] == "127.0.0.1:8123"
