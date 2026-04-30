from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from evidpath.cli import main
from evidpath.generation_support import (
    DEFAULT_POPULATION_PROVIDER_MODEL,
    DEFAULT_SCENARIO_PROVIDER_MODEL,
    DEFAULT_SEMANTIC_PROVIDER_MODEL,
    build_responses_endpoint,
    load_dotenv_if_present,
    read_retry_count,
    read_retry_count_with_fallback,
    read_timeout_seconds,
    read_timeout_seconds_with_fallback,
    resolve_provider_model,
)
from evidpath.population_generation import (
    GeneratedPopulationCandidates,
    generate_population_pack,
)
from evidpath.scenario_generation import (
    generate_scenario_pack,
)


def test_provider_helpers_normalize_endpoint_and_env_values(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("OPENAI_RETRY_COUNT", raising=False)
    assert build_responses_endpoint(None) == "https://api.openai.com/v1/responses"
    assert (
        build_responses_endpoint("https://example.com/v1")
        == "https://example.com/v1/responses"
    )
    assert (
        build_responses_endpoint("https://example.com/v1/responses")
        == "https://example.com/v1/responses"
    )
    assert read_timeout_seconds("OPENAI_TIMEOUT_SECONDS") == 45.0
    assert read_retry_count("OPENAI_RETRY_COUNT") == 1
    assert (
        read_timeout_seconds_with_fallback(
            "OPENAI_SCENARIO_TIMEOUT_SECONDS", "OPENAI_TIMEOUT_SECONDS"
        )
        == 45.0
    )
    assert (
        read_retry_count_with_fallback(
            "OPENAI_SCENARIO_RETRY_COUNT", "OPENAI_RETRY_COUNT"
        )
        == 1
    )


def test_provider_model_profiles_resolve_expected_defaults() -> None:
    scenario_model, scenario_profile = resolve_provider_model(
        purpose="scenario_generation"
    )
    population_model, population_profile = resolve_provider_model(
        purpose="population_generation"
    )
    semantic_model, semantic_profile = resolve_provider_model(
        purpose="semantic_interpretation"
    )

    assert (scenario_model, scenario_profile) == (
        DEFAULT_SCENARIO_PROVIDER_MODEL,
        "fast",
    )
    assert (population_model, population_profile) == (
        DEFAULT_POPULATION_PROVIDER_MODEL,
        "fast",
    )
    assert (semantic_model, semantic_profile) == (
        DEFAULT_SEMANTIC_PROVIDER_MODEL,
        "fast",
    )

    balanced_model, balanced_profile = resolve_provider_model(
        purpose="semantic_interpretation",
        profile_name="balanced",
    )
    assert (balanced_model, balanced_profile) == ("gpt-5.4-mini", "balanced")

    custom_model, custom_profile = resolve_provider_model(
        purpose="population_generation",
        explicit_model_name="gpt-5-mini",
        profile_name="deep",
    )
    assert (custom_model, custom_profile) == ("gpt-5-mini", "custom")


def test_provider_helpers_reject_invalid_env_values(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "abc")
    try:
        read_timeout_seconds("OPENAI_TIMEOUT_SECONDS")
    except ValueError as exc:
        assert "must be a number of seconds" in str(exc)
    else:
        raise AssertionError("Expected invalid timeout to fail.")

    monkeypatch.setenv("OPENAI_RETRY_COUNT", "-1")
    try:
        read_retry_count("OPENAI_RETRY_COUNT")
    except ValueError as exc:
        assert "must be 0 or greater" in str(exc)
    else:
        raise AssertionError("Expected invalid retry count to fail.")


def test_provider_helpers_use_purpose_specific_env_first(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("OPENAI_POPULATION_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("OPENAI_RETRY_COUNT", "1")
    monkeypatch.setenv("OPENAI_POPULATION_RETRY_COUNT", "3")

    assert (
        read_timeout_seconds_with_fallback(
            "OPENAI_POPULATION_TIMEOUT_SECONDS",
            "OPENAI_TIMEOUT_SECONDS",
        )
        == 120.0
    )
    assert (
        read_retry_count_with_fallback(
            "OPENAI_POPULATION_RETRY_COUNT",
            "OPENAI_RETRY_COUNT",
        )
        == 3
    )


def test_dotenv_loader_populates_missing_provider_key(
    tmp_path: Path, monkeypatch
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        'OPENAI_API_KEY="test-key"\nOPENAI_BASE_URL=https://example.com/v1\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    load_dotenv_if_present()
    assert os.getenv("OPENAI_API_KEY") == "test-key"
    assert os.getenv("OPENAI_BASE_URL") == "https://example.com/v1"


def test_cli_provider_generation_mode_routes_through_generation_layer(
    tmp_path: Path,
) -> None:
    fake_pack = generate_scenario_pack("provider brief", generator_mode="fixture")
    with patch(
        "evidpath.cli_app.handlers.generate_scenario_pack",
        return_value=fake_pack,
    ) as mock_generate:
        result = main(
            [
                "generate-scenarios",
                "--domain",
                "recommender",
                "--mode",
                "provider",
                "--model",
                "gpt-5",
                "--brief",
                "provider brief",
                "--scenario-pack-path",
                str(tmp_path / "provider-pack.json"),
            ]
        )
    mock_generate.assert_called_once()
    assert mock_generate.call_args.kwargs["model_profile"] == "fast"
    assert Path(str(result["scenario_pack_path"])).exists()


def test_cli_provider_population_generation_routes_through_generation_layer(
    tmp_path: Path,
) -> None:
    fake_pack = generate_population_pack(
        "provider population brief",
        generator_mode="fixture",
        population_size=12,
        candidate_count=18,
    )
    with patch(
        "evidpath.cli_app.handlers.generate_population_pack",
        return_value=fake_pack,
    ) as mock_generate:
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
    assert mock_generate.call_args.kwargs["model_profile"] == "fast"
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
                        "preferred_genres": ["action", "comedy"]
                        if index % 2 == 0
                        else ["drama", "documentary"],
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
        "evidpath.population_generation.ProviderPopulationGenerator.generate",
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
