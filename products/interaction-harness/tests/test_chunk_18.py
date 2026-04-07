from __future__ import annotations

from pathlib import Path

from interaction_harness.cli import main
from interaction_harness.domain_registry import (
    get_domain_definition,
    list_public_domain_definitions,
    register_domain_definition,
)
from interaction_harness.domains.stub import build_stub_domain_definition


def test_recommender_domain_exposes_generation_hooks() -> None:
    definition = get_domain_definition("recommender")

    assert definition.generation_hooks is not None
    assert definition.generation_hooks.build_fixture_scenarios is not None
    assert definition.generation_hooks.build_population_prompt is not None
    assert definition.run_reference_service is not None


def test_public_domain_list_excludes_internal_stub_domain() -> None:
    register_domain_definition(build_stub_domain_definition())

    assert "recommender" in list_public_domain_definitions()
    assert "stub" not in list_public_domain_definitions()


def test_generate_scenarios_compatibility_without_domain_still_works(tmp_path: Path) -> None:
    result = main(
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

    assert Path(str(result["scenario_pack_path"])).exists()
