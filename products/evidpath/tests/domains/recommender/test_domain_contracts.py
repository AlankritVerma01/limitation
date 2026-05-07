from __future__ import annotations

import json
from pathlib import Path

from evidpath.audit import run_recommender_audit
from evidpath.domain_registry import get_domain_definition
from evidpath.domains.recommender import (
    CATALOG,
    HttpNativeRecommenderDriver,
    RecommenderAgentPolicy,
    ensure_reference_artifacts,
    history_for_genres,
    resolve_built_in_recommender_scenarios,
    run_mock_recommender_service,
    run_reference_recommender_service,
)


def test_recommender_domain_package_is_the_primary_import_surface() -> None:
    assert RecommenderAgentPolicy.__module__.startswith("evidpath.domains.recommender")
    assert HttpNativeRecommenderDriver.__module__.startswith("evidpath.domains.recommender")
    assert callable(resolve_built_in_recommender_scenarios)


def test_default_reference_audit_smoke(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "reference-artifacts"
    ensure_reference_artifacts(artifact_dir)

    paths = run_recommender_audit(
        seed=3,
        scenario_names=("returning-user-home-feed",),
        service_artifact_dir=str(artifact_dir),
        output_dir=str(tmp_path / "audit"),
    )
    payload = json.loads(Path(paths["results_path"]).read_text(encoding="utf-8"))

    assert payload["metadata"]["service_kind"] == "reference"
    assert payload["metadata"]["target_mode"] == "reference_artifact"
    assert payload["summary"]["trace_count"] > 0


def test_recommender_domain_package_exposes_primary_owned_helpers() -> None:
    assert CATALOG
    assert history_for_genres(("action", "comedy"), 3)
    assert callable(run_reference_recommender_service)
    assert callable(run_mock_recommender_service)


def test_recommender_domain_exposes_generation_hooks() -> None:
    definition = get_domain_definition("recommender")

    assert definition.generation_hooks is not None
    assert definition.generation_hooks.build_fixture_scenarios is not None
    assert definition.generation_hooks.build_population_prompt is not None
    assert definition.run_reference_service is not None


def test_reference_service_still_runs_through_preserved_public_path(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "reference-artifacts"
    ensure_reference_artifacts(artifact_dir)

    with run_reference_recommender_service(str(artifact_dir)) as (base_url, metadata):
        assert base_url.startswith("http://")
        assert metadata["service_kind"] == "reference"
