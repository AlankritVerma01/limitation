"""Unit tests for environment and determinism helpers."""

from __future__ import annotations

import json
from pathlib import Path

from evidpath.artifacts._determinism import (
    compute_deterministic_payload_hash,
    hash_population,
    hash_scenarios,
    normalize_for_diff,
)
from evidpath.artifacts._environment import collect_environment_fingerprint
from evidpath.domains.recommender.policy import build_seeded_archetypes
from evidpath.domains.recommender.scenarios import (
    resolve_built_in_recommender_scenarios,
)


def test_collect_environment_fingerprint_has_expected_keys() -> None:
    fingerprint = collect_environment_fingerprint(cli_invocation=["evidpath", "audit"])
    assert set(fingerprint) == {
        "evidpath_version",
        "python_version",
        "platform",
        "git_sha",
        "cli_invocation",
    }
    assert all(isinstance(value, str) for value in fingerprint.values())
    assert fingerprint["cli_invocation"] == "evidpath audit"
    assert fingerprint["python_version"].count(".") >= 1


def test_collect_environment_fingerprint_strips_argv_path_prefix() -> None:
    fingerprint = collect_environment_fingerprint(
        cli_invocation=["/usr/local/bin/evidpath", "audit", "--seed", "7"],
    )
    assert fingerprint["cli_invocation"] == "evidpath audit --seed 7"


def test_hash_scenarios_is_stable_for_same_input() -> None:
    scenarios = resolve_built_in_recommender_scenarios(("returning-user-home-feed",))
    assert hash_scenarios(scenarios) == hash_scenarios(scenarios)


def test_hash_scenarios_differs_for_different_input() -> None:
    one = resolve_built_in_recommender_scenarios(("returning-user-home-feed",))
    two = resolve_built_in_recommender_scenarios(("sparse-history-home-feed",))
    assert hash_scenarios(one) != hash_scenarios(two)


def test_hash_population_is_stable_for_same_seeds() -> None:
    seeds = build_seeded_archetypes()
    assert hash_population(seeds) == hash_population(seeds)


def test_normalize_for_diff_strips_volatile_keys() -> None:
    payload = {
        "stable": "keep",
        "generated_at_utc": "2026-05-06T12:00:00+00:00",
        "nested": {
            "results_path": "/tmp/run-a/results.json",
            "score": 0.42,
        },
        "list_of_dicts": [
            {"run_manifest_path": "/tmp/run-a/run_manifest.json", "value": 1},
        ],
    }
    assert normalize_for_diff(payload) == {
        "stable": "keep",
        "nested": {"score": 0.42},
        "list_of_dicts": [{"value": 1}],
    }


def test_compute_deterministic_payload_hash_is_stable_across_paths(
    tmp_path: Path,
) -> None:
    results_a = tmp_path / "a" / "results.json"
    traces_a = tmp_path / "a" / "traces.jsonl"
    results_b = tmp_path / "b" / "results.json"
    traces_b = tmp_path / "b" / "traces.jsonl"
    for results_path, traces_path in ((results_a, traces_a), (results_b, traces_b)):
        results_path.parent.mkdir(parents=True)
        results_path.write_text(
            json.dumps(
                {
                    "metadata": {
                        "run_id": "run-deadbeef",
                        "generated_at_utc": str(results_path),
                        "report_path": str(results_path.parent / "report.md"),
                    },
                    "score": 0.5,
                }
            ),
            encoding="utf-8",
        )
        traces_path.write_text(
            json.dumps({"trace_id": "t-1", "value": 1}) + "\n",
            encoding="utf-8",
        )
    hash_a = compute_deterministic_payload_hash(
        results_path=results_a, traces_path=traces_a
    )
    hash_b = compute_deterministic_payload_hash(
        results_path=results_b, traces_path=traces_b
    )
    assert hash_a == hash_b
    assert len(hash_a) == 64


def test_run_manifest_includes_environment_inputs_outputs(tmp_path: Path) -> None:
    from evidpath.cli import main

    paths = main(
        [
            "audit",
            "--domain",
            "recommender",
            "--seed",
            "11",
            "--use-mock",
            "--output-dir",
            str(tmp_path / "single"),
        ]
    )
    manifest = json.loads(
        Path(str(paths["run_manifest_path"])).read_text(encoding="utf-8")
    )
    assert set(manifest["environment"]) == {
        "evidpath_version",
        "python_version",
        "platform",
        "git_sha",
        "cli_invocation",
    }
    assert set(manifest["inputs"]) == {"scenario_hash", "population_hash"}
    assert len(manifest["inputs"]["scenario_hash"]) == 64
    assert isinstance(manifest["outputs"]["deterministic_payload_hash"], str)
    assert len(manifest["outputs"]["deterministic_payload_hash"]) == 64
