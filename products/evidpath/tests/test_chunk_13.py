from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import evidpath as ih
import pytest
from evidpath.audit import execute_domain_audit, write_run_artifacts
from evidpath.domain_registry import (
    get_domain_definition,
    list_domain_definitions,
    register_domain_definition,
)
from evidpath.domains.recommender import (
    HttpRecommenderAdapter,
    RecommenderAgentPolicy,
    resolve_built_in_recommender_scenarios,
)
from evidpath.domains.stub import build_stub_domain_definition
from evidpath.regression import run_domain_regression_audit
from evidpath.schema import RegressionTarget


def test_public_surface_exports_domain_plugin_helpers() -> None:
    assert ih.execute_domain_audit is execute_domain_audit
    assert ih.run_domain_regression_audit is run_domain_regression_audit
    assert ih.register_domain_definition is register_domain_definition
    assert ih.list_domain_definitions is list_domain_definitions


def test_recommender_domain_package_is_the_primary_import_surface() -> None:
    assert RecommenderAgentPolicy.__module__.startswith("evidpath.domains.recommender")
    assert HttpRecommenderAdapter.__module__.startswith("evidpath.domains.recommender")
    assert callable(resolve_built_in_recommender_scenarios)


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
            mode="reference_artifact",
            service_artifact_dir=str(tmp_path / "baseline"),
        ),
        candidate_target=RegressionTarget(
            label="candidate",
            mode="external_url",
            adapter_base_url="stub://candidate",
        ),
        base_seed=2,
        rerun_count=2,
        output_dir=str(tmp_path / "stub-regression"),
    )
    payload = json.loads(Path(result["regression_summary_path"]).read_text(encoding="utf-8"))
    report_text = Path(result["regression_report_path"]).read_text(encoding="utf-8")

    assert payload["metadata"]["domain_name"] == "stub"
    assert payload["metadata"]["baseline_target_mode"] == "reference_artifact"
    assert payload["metadata"]["candidate_target_mode"] == "external_url"
    assert report_text.startswith("# Evidpath Stub Regression")


def test_registry_lists_registered_domains() -> None:
    register_domain_definition(build_stub_domain_definition())

    assert "recommender" in list_domain_definitions()
    assert "stub" in list_domain_definitions()


def test_missing_domain_fails_clearly() -> None:
    with pytest.raises(ValueError) as exc_info:
        get_domain_definition("missing-domain")

    assert "Unsupported domain `missing-domain`" in str(exc_info.value)
