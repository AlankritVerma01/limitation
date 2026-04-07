from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from interaction_harness.cli import main
from interaction_harness.domains.recommender import (
    ensure_reference_artifacts,
    project_recommender_population,
)
from interaction_harness.population_generation import (
    GeneratedPopulationCandidates,
    build_population_pack,
    generate_population_pack,
    load_population_pack,
    write_population_pack,
)
from interaction_harness.regression import run_regression_audit
from interaction_harness.schema import RegressionTarget


def test_fixture_population_generation_returns_valid_and_stable_pack() -> None:
    first = generate_population_pack(
        "test a recommender for risk-sensitive but curious viewers",
        generator_mode="fixture",
        population_size=12,
        candidate_count=18,
    )
    second = generate_population_pack(
        "test a recommender for risk-sensitive but curious viewers",
        generator_mode="fixture",
        population_size=12,
        candidate_count=18,
    )
    assert first.metadata.generator_mode == "fixture"
    assert first.metadata.brief == "test a recommender for risk-sensitive but curious viewers"
    assert first.metadata.candidate_count == 18
    assert first.metadata.selected_count == 12
    assert first.metadata.population_size_source == "explicit"
    assert len(first.personas) == 12
    assert first.metadata.pack_id == second.metadata.pack_id
    assert first.personas == second.personas


def test_fixture_population_generation_defaults_to_twelve_without_explicit_size() -> None:
    pack = generate_population_pack(
        "test a recommender for broad default swarm coverage",
        generator_mode="fixture",
        candidate_count=18,
    )
    assert pack.metadata.selected_count == 12
    assert pack.metadata.population_size_source == "default"


def test_build_population_pack_rejects_duplicate_persona_ids_and_labels() -> None:
    duplicate_payload = [
        {
            "persona_id": "dup-1",
            "display_label": "Duplicate persona",
            "persona_summary": "First persona.",
            "behavior_goal": "First goal.",
            "diversity_tags": ["dup"],
            "adapter_hints": {
                "recommender": {
                    "preferred_genres": ["action", "comedy"],
                    "popularity_preference": 0.6,
                    "novelty_preference": 0.4,
                    "repetition_tolerance": 0.5,
                    "sparse_history_confidence": 0.5,
                    "abandonment_sensitivity": 0.5,
                    "patience": 3,
                    "engagement_baseline": 0.5,
                    "quality_sensitivity": 0.5,
                    "repeat_exposure_penalty": 0.2,
                    "novelty_fatigue": 0.2,
                    "frustration_recovery": 0.2,
                    "history_reliance": 0.5,
                    "skip_tolerance": 2,
                    "abandonment_threshold": 0.6,
                },
            },
        },
        {
            "persona_id": "dup-1",
            "display_label": "Duplicate persona",
            "persona_summary": "Second persona.",
            "behavior_goal": "Second goal.",
            "diversity_tags": ["dup"],
            "adapter_hints": {
                "recommender": {
                    "preferred_genres": ["drama", "documentary"],
                    "popularity_preference": 0.3,
                    "novelty_preference": 0.8,
                    "repetition_tolerance": 0.2,
                    "sparse_history_confidence": 0.3,
                    "abandonment_sensitivity": 0.7,
                    "patience": 2,
                    "engagement_baseline": 0.4,
                    "quality_sensitivity": 0.8,
                    "repeat_exposure_penalty": 0.3,
                    "novelty_fatigue": 0.2,
                    "frustration_recovery": 0.1,
                    "history_reliance": 0.7,
                    "skip_tolerance": 1,
                    "abandonment_threshold": 0.5,
                },
            },
        },
    ]
    try:
        build_population_pack(
            duplicate_payload,
            brief="duplicate persona test",
            generator_mode="fixture",
            generated_at_utc="2026-01-01T00:00:00+00:00",
            domain_label="recommender",
            target_population_size=2,
            candidate_count=2,
        )
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("Expected duplicate generated personas to fail validation.")


def test_generated_population_pack_maps_cleanly_to_agent_seeds() -> None:
    pack = generate_population_pack(
        "evaluate reliability for a broad explicit swarm",
        generator_mode="fixture",
        population_size=12,
        candidate_count=20,
    )
    seeds = project_recommender_population(pack)
    assert len(seeds) == 12
    assert all(seed.agent_id for seed in seeds)
    assert all(seed.preferred_genres for seed in seeds)
    assert len({seed.archetype_label for seed in seeds}) == len(seeds)
    assert len({genre for seed in seeds for genre in seed.preferred_genres}) >= 6


def test_invalid_recommender_persona_hints_fail_before_runtime() -> None:
    pack = build_population_pack(
        [
            {
                "persona_id": "broken-1",
                "display_label": "Broken persona",
                "persona_summary": "Bad hints.",
                "behavior_goal": "Prove validation works.",
                "diversity_tags": ["validation"],
                "adapter_hints": {
                    "recommender": {
                        "preferred_genres": ["action"],
                        "popularity_preference": 1.4,
                        "novelty_preference": 0.5,
                        "repetition_tolerance": 0.5,
                        "sparse_history_confidence": 0.5,
                        "abandonment_sensitivity": 0.5,
                        "patience": 3,
                        "engagement_baseline": 0.5,
                        "quality_sensitivity": 0.5,
                        "repeat_exposure_penalty": 0.2,
                        "novelty_fatigue": 0.2,
                        "frustration_recovery": 0.2,
                        "history_reliance": 0.5,
                        "skip_tolerance": 2,
                        "abandonment_threshold": 0.6,
                    },
                },
            }
        ],
        brief="broken recommender persona hints",
        generator_mode="fixture",
        generated_at_utc="2026-01-01T00:00:00+00:00",
        domain_label="recommender",
        target_population_size=1,
        candidate_count=1,
    )
    try:
        project_recommender_population(pack)
    except ValueError as exc:
        assert "out-of-range recommender hint `popularity_preference`" in str(exc)
    else:
        raise AssertionError("Expected invalid recommender persona hints to fail.")


def test_population_pack_requires_full_requested_swarm_size() -> None:
    try:
        build_population_pack(
            [
                {
                    "persona_id": "only-one",
                    "display_label": "Only one",
                    "persona_summary": "Only one persona.",
                    "behavior_goal": "Prove strict population sizing.",
                    "diversity_tags": ["tiny"],
                    "adapter_hints": {
                        "recommender": {
                            "preferred_genres": ["action"],
                            "popularity_preference": 0.5,
                            "novelty_preference": 0.5,
                            "repetition_tolerance": 0.5,
                            "sparse_history_confidence": 0.5,
                            "abandonment_sensitivity": 0.5,
                            "patience": 3,
                            "engagement_baseline": 0.5,
                            "quality_sensitivity": 0.5,
                            "repeat_exposure_penalty": 0.2,
                            "novelty_fatigue": 0.2,
                            "frustration_recovery": 0.2,
                            "history_reliance": 0.5,
                            "skip_tolerance": 2,
                            "abandonment_threshold": 0.6,
                        }
                    },
                }
            ],
            brief="too small for target",
            generator_mode="fixture",
            generated_at_utc="2026-01-01T00:00:00+00:00",
            domain_label="recommender",
            target_population_size=2,
            candidate_count=1,
        )
    except ValueError as exc:
        assert "target_population_size" in str(exc)
    else:
        raise AssertionError("Expected undersized population pack to fail.")


def test_cli_population_generation_mode_requires_brief(tmp_path: Path) -> None:
    try:
        main(
            [
                "generate-population",
                "--domain",
                "recommender",
                "--output-dir",
                str(tmp_path),
            ]
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("Expected population generation without a brief to fail.")


def test_cli_population_generation_mode_writes_population_pack(tmp_path: Path) -> None:
    result = main(
        [
            "generate-population",
            "--domain",
            "recommender",
            "--mode",
            "fixture",
            "--brief",
            "test an explicit swarm of patient and impatient viewers",
            "--population-size",
            "12",
            "--population-candidate-count",
            "18",
            "--output-dir",
            str(tmp_path),
        ]
    )
    pack_path = Path(str(result["population_pack_path"]))
    assert pack_path.exists()
    payload = json.loads(pack_path.read_text(encoding="utf-8"))
    assert payload["metadata"]["generator_mode"] == "fixture"
    assert payload["metadata"]["selected_count"] == 12
    assert payload["metadata"]["population_size_source"] == "explicit"
    assert len(payload["personas"]) == 12


def test_cli_provider_population_generation_routes_through_generation_layer(tmp_path: Path) -> None:
    fake_pack = generate_population_pack(
        "provider population brief",
        generator_mode="fixture",
        population_size=12,
        candidate_count=18,
    )
    with patch("interaction_harness.cli.generate_population_pack", return_value=fake_pack) as mock_generate:
        result = main(
            [
                "generate-population",
                "--domain",
                "recommender",
                "--mode",
                "provider",
                "--model",
                "gpt-5-mini",
                "--brief",
                "provider population brief",
                "--population-pack-path",
                str(tmp_path / "provider-population.json"),
            ]
        )
    mock_generate.assert_called_once()
    assert mock_generate.call_args.kwargs["population_size"] is None
    assert Path(str(result["population_pack_path"])).exists()


def test_provider_suggestion_can_choose_population_size() -> None:
    candidates = GeneratedPopulationCandidates(
        personas=tuple(
            {
                "persona_id": f"persona-{index}",
                "display_label": f"Persona {index}",
                "persona_summary": f"Summary {index}",
                "behavior_goal": f"Goal {index}",
                "diversity_tags": [f"tag-{index % 4}"],
                "adapter_hints": {
                    "recommender": {
                        "preferred_genres": ["action", "comedy"] if index % 2 == 0 else ["drama", "documentary"],
                        "popularity_preference": 0.2 if index % 2 == 0 else 0.8,
                        "novelty_preference": 0.8 if index % 3 == 0 else 0.3,
                        "repetition_tolerance": 0.4,
                        "sparse_history_confidence": 0.5,
                        "abandonment_sensitivity": 0.4,
                        "patience": 2 + (index % 3),
                        "engagement_baseline": 0.5,
                        "quality_sensitivity": 0.6,
                        "repeat_exposure_penalty": 0.2,
                        "novelty_fatigue": 0.2,
                        "frustration_recovery": 0.2,
                        "history_reliance": 0.3 if index % 2 == 0 else 0.7,
                        "skip_tolerance": 2,
                        "abandonment_threshold": 0.6,
                    }
                },
            }
            for index in range(16)
        ),
        suggested_population_size=9,
    )
    with patch(
        "interaction_harness.population_generation.ProviderPopulationGenerator.generate",
        return_value=candidates,
    ):
        pack = generate_population_pack(
            "provider chooses the swarm size",
            generator_mode="provider",
            candidate_count=16,
        )
    assert pack.metadata.target_population_size == 9
    assert pack.metadata.selected_count == 9
    assert pack.metadata.population_size_source == "provider"


def test_fixture_generated_population_pack_can_be_reused_for_single_run(tmp_path: Path) -> None:
    pack = generate_population_pack(
        "test a richer saved swarm for a normal audit run",
        generator_mode="fixture",
        population_size=12,
        candidate_count=18,
    )
    pack_path = tmp_path / "population-pack.json"
    write_population_pack(pack, pack_path)
    loaded = load_population_pack(pack_path)
    assert loaded.metadata.pack_id == pack.metadata.pack_id

    result = main(
        [
            "audit",
            "--domain",
            "recommender",
            "--seed",
            "5",
            "--use-mock",
            "--population-pack-path",
            str(pack_path),
            "--output-dir",
            str(tmp_path / "single-run"),
        ]
    )
    payload = json.loads(Path(str(result["results_path"])).read_text(encoding="utf-8"))
    assert payload["summary"]["population_size_source"] == "explicit"
    assert payload["metadata"]["population_pack_id"] == pack.metadata.pack_id
    assert payload["metadata"]["population_source"] == "generated_pack"
    assert payload["metadata"]["population_size_source"] == "explicit"
    assert payload["metadata"]["population_pack_path"] == "<normalized>"
    assert payload["summary"]["agent_count"] == 12
    assert len(payload["traces"]) == (
        payload["summary"]["agent_count"] * payload["summary"]["scenario_count"]
    )


def test_underspecified_population_generation_brief_requests_clarification() -> None:
    try:
        generate_population_pack(
            "audience",
            generator_mode="fixture",
            domain_label="recommender",
        )
    except ValueError as exc:
        assert "more specific recommender audience" in str(exc)
    else:
        raise AssertionError("Expected a clarification-style error for vague population generation.")


def test_population_pack_can_be_reused_for_regression_runs(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)
    pack = generate_population_pack(
        "shared regression swarm",
        generator_mode="fixture",
        population_size=12,
        candidate_count=18,
    )
    pack_path = tmp_path / "shared-population-pack.json"
    write_population_pack(pack, pack_path)
    result = run_regression_audit(
        baseline_target=RegressionTarget(
            label="baseline",
            mode="reference_artifact",
            service_artifact_dir=str(artifact_dir),
        ),
        candidate_target=RegressionTarget(
            label="candidate",
            mode="reference_artifact",
            service_artifact_dir=str(artifact_dir),
        ),
        base_seed=2,
        rerun_count=1,
        output_dir=str(tmp_path / "regression"),
        population_pack_path=str(pack_path),
    )
    payload = json.loads(Path(result["regression_summary_path"]).read_text(encoding="utf-8"))
    assert payload["metadata"]["population_pack_path"] == "<normalized>"
    assert payload["baseline_summary"]["metadata"]["population_pack_id"] == pack.metadata.pack_id
    assert payload["baseline_summary"]["metadata"]["population_size_source"] == "explicit"
