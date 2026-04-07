from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from interaction_harness.cli import main
from interaction_harness.domains.recommender import project_recommender_scenarios
from interaction_harness.generation_support import (
    build_responses_endpoint,
    load_dotenv_if_present,
    read_retry_count,
    read_timeout_seconds,
)
from interaction_harness.scenario_generation import (
    build_scenario_pack,
    generate_scenario_pack,
    load_scenario_pack,
    write_scenario_pack,
)


def test_fixture_generation_returns_valid_and_stable_pack() -> None:
    first = generate_scenario_pack(
        "test a recommender for novelty-seeking movie fans",
        generator_mode="fixture",
    )
    second = generate_scenario_pack(
        "test a recommender for novelty-seeking movie fans",
        generator_mode="fixture",
    )
    assert first.metadata.generator_mode == "fixture"
    assert first.metadata.brief == "test a recommender for novelty-seeking movie fans"
    assert len(first.scenarios) == 3
    assert first.metadata.pack_id == second.metadata.pack_id
    assert first.scenarios == second.scenarios


def test_provider_helpers_normalize_endpoint_and_env_values(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("OPENAI_RETRY_COUNT", raising=False)
    assert build_responses_endpoint(None) == "https://api.openai.com/v1/responses"
    assert build_responses_endpoint("https://example.com/v1") == "https://example.com/v1/responses"
    assert build_responses_endpoint("https://example.com/v1/responses") == "https://example.com/v1/responses"
    assert read_timeout_seconds("OPENAI_TIMEOUT_SECONDS") == 45.0
    assert read_retry_count("OPENAI_RETRY_COUNT") == 1


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


def test_dotenv_loader_populates_missing_provider_key(tmp_path: Path, monkeypatch) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text('OPENAI_API_KEY="test-key"\nOPENAI_BASE_URL=https://example.com/v1\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    load_dotenv_if_present()
    assert os.getenv("OPENAI_API_KEY") == "test-key"
    assert os.getenv("OPENAI_BASE_URL") == "https://example.com/v1"


def test_build_scenario_pack_rejects_malformed_provider_output() -> None:
    try:
        build_scenario_pack(
            [{"name": "Broken scenario"}],
            brief="broken",
            generator_mode="provider",
            generated_at_utc="2026-01-01T00:00:00+00:00",
            domain_label="recommender",
            provider_name="openai",
            model_name="gpt-5",
        )
    except ValueError as exc:
        assert "scenario_id" in str(exc)
    else:
        raise AssertionError("Expected malformed scenario output to be rejected.")


def test_build_scenario_pack_rejects_duplicate_scenario_names_and_ids() -> None:
    duplicate_payload = [
        {
            "scenario_id": "dup-1",
            "name": "Duplicate name",
            "description": "First scenario.",
            "test_goal": "First goal.",
            "risk_focus_tags": ["dup"],
            "max_steps": 5,
            "allowed_actions": ["click", "skip", "abandon"],
            "adapter_hints": {
                "recommender": {
                    "runtime_profile": "returning-user-home-feed",
                    "history_depth": 1,
                }
            },
        },
        {
            "scenario_id": "dup-1",
            "name": "Duplicate name",
            "description": "Second scenario.",
            "test_goal": "Second goal.",
            "risk_focus_tags": ["dup"],
            "max_steps": 5,
            "allowed_actions": ["click", "skip", "abandon"],
            "adapter_hints": {
                "recommender": {
                    "runtime_profile": "sparse-history-home-feed",
                    "history_depth": 1,
                }
            },
        },
    ]
    try:
        build_scenario_pack(
            duplicate_payload,
            brief="duplicate scenario test",
            generator_mode="fixture",
            generated_at_utc="2026-01-01T00:00:00+00:00",
            domain_label="recommender",
        )
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("Expected duplicate generated scenarios to fail validation.")


def test_generated_pack_maps_cleanly_to_recommender_scenarios() -> None:
    pack = generate_scenario_pack(
        "evaluate trust and novelty balance for home feed sessions",
        generator_mode="fixture",
    )
    configs = project_recommender_scenarios(pack)
    assert len(configs) == 3
    assert all(config.scenario_id for config in configs)
    assert all(config.runtime_profile for config in configs)
    assert all(config.test_goal for config in configs)
    assert all(config.allowed_actions == ("click", "skip", "abandon") for config in configs)


def test_invalid_recommender_adapter_hints_fail_before_runtime() -> None:
    pack = build_scenario_pack(
        [
            {
                "scenario_id": "broken-1",
                "name": "Broken scenario",
                "description": "Bad hints.",
                "test_goal": "Prove validation works.",
                "risk_focus_tags": ["validation"],
                "max_steps": 5,
                "allowed_actions": ["click", "skip", "abandon"],
                "adapter_hints": {
                    "recommender": {
                        "runtime_profile": "unsupported-profile",
                        "history_depth": 2,
                    }
                },
            }
        ],
        brief="broken recommender hints",
        generator_mode="fixture",
        generated_at_utc="2026-01-01T00:00:00+00:00",
        domain_label="recommender",
    )
    try:
        project_recommender_scenarios(pack)
    except ValueError as exc:
        assert "unsupported recommender runtime profile" in str(exc)
    else:
        raise AssertionError("Expected invalid recommender adapter hints to fail.")


def test_cli_generation_mode_requires_brief(tmp_path: Path) -> None:
    try:
        main(
            [
                "generate-scenarios",
                "--domain",
                "recommender",
                "--output-dir",
                str(tmp_path),
            ]
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("Expected generation mode without a brief to fail.")


def test_cli_generation_mode_writes_scenario_pack(tmp_path: Path) -> None:
    result = main(
        [
            "generate-scenarios",
            "--domain",
            "recommender",
            "--mode",
            "fixture",
            "--brief",
            "test robustness for sparse history users",
            "--output-dir",
            str(tmp_path),
        ]
    )
    pack_path = Path(str(result["scenario_pack_path"]))
    assert pack_path.exists()
    payload = json.loads(pack_path.read_text(encoding="utf-8"))
    assert payload["metadata"]["generator_mode"] == "fixture"
    assert len(payload["scenarios"]) == 3


def test_write_scenario_pack_avoids_overwriting_different_pack(tmp_path: Path) -> None:
    first = generate_scenario_pack("first brief for generated pack", generator_mode="fixture")
    second = generate_scenario_pack("second brief for generated pack", generator_mode="fixture")
    target = tmp_path / "scenario-pack.json"
    first_path = Path(write_scenario_pack(first, target))
    second_path = Path(write_scenario_pack(second, target))
    assert first_path.exists()
    assert second_path.exists()
    assert first_path != second_path
    assert second.metadata.pack_id in second_path.name


def test_cli_provider_generation_mode_routes_through_generation_layer(tmp_path: Path) -> None:
    fake_pack = generate_scenario_pack("provider brief", generator_mode="fixture")
    with patch("interaction_harness.cli.generate_scenario_pack", return_value=fake_pack) as mock_generate:
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
    assert Path(str(result["scenario_pack_path"])).exists()


def test_fixture_generated_pack_can_be_reused_for_single_run(tmp_path: Path) -> None:
    pack = generate_scenario_pack(
        "test recommendation quality for new sessions with light history",
        generator_mode="fixture",
    )
    pack_path = tmp_path / "scenario-pack.json"
    write_scenario_pack(pack, pack_path)
    loaded = load_scenario_pack(pack_path)
    assert loaded.metadata.pack_id == pack.metadata.pack_id

    result = main(
        [
            "audit",
            "--domain",
            "recommender",
            "--seed",
            "5",
            "--use-mock",
            "--scenario-pack-path",
            str(pack_path),
            "--output-dir",
            str(tmp_path / "single-run"),
        ]
    )
    payload = json.loads(Path(str(result["results_path"])).read_text(encoding="utf-8"))
    assert payload["summary"]["scenario_source"] == "generated_pack"
    assert payload["metadata"]["scenario_pack_id"] == pack.metadata.pack_id
    assert payload["metadata"]["scenario_pack_mode"] == "fixture"
    assert payload["metadata"]["scenario_pack_path"] == "<normalized>"
    assert all(trace["scenario_id"] for trace in payload["traces"])


def test_underspecified_scenario_generation_brief_requests_clarification() -> None:
    try:
        generate_scenario_pack(
            "users",
            generator_mode="fixture",
            domain_label="recommender",
        )
    except ValueError as exc:
        assert "more specific recommender goal" in str(exc)
    else:
        raise AssertionError("Expected a clarification-style error for vague scenario generation.")
