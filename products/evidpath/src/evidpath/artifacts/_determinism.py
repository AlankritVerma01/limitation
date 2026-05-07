"""Hash and normalization helpers for deterministic-payload comparisons."""

from __future__ import annotations

import json
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from ..schema import AgentSeed, ScenarioConfig

_VOLATILE_KEYS: frozenset[str] = frozenset(
    {
        "generated_at_utc",
        "report_path",
        "results_path",
        "traces_path",
        "chart_path",
        "semantic_advisory_path",
        "run_manifest_path",
        "run_plan_path",
        "service_artifact_dir",
        "run_plan_id",
        "regression_id",
    }
)


def hash_scenarios(scenarios: tuple[ScenarioConfig, ...]) -> str:
    """Return a stable sha256 over a tuple of scenario configs."""
    payload = [asdict(scenario) for scenario in scenarios]
    return _sha256(json.dumps(payload, sort_keys=True))


def hash_population(seeds: tuple[AgentSeed, ...]) -> str:
    """Return a stable sha256 over a tuple of agent seeds."""
    payload = [asdict(seed) for seed in seeds]
    return _sha256(json.dumps(payload, sort_keys=True))


def normalize_for_diff(payload: object) -> object:
    """Recursively strip volatile keys from a JSON-shaped payload."""
    if isinstance(payload, dict):
        return {
            key: normalize_for_diff(value)
            for key, value in payload.items()
            if key not in _VOLATILE_KEYS
        }
    if isinstance(payload, list):
        return [normalize_for_diff(item) for item in payload]
    return payload


def compute_deterministic_payload_hash(
    *,
    results_path: Path,
    traces_path: Path,
) -> str:
    """Compute the sha256 of normalized results plus traces."""
    results_payload = json.loads(results_path.read_text(encoding="utf-8"))
    normalized_results = normalize_for_diff(results_payload)
    trace_lines = [
        json.loads(line)
        for line in traces_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    normalized_traces = normalize_for_diff(trace_lines)
    combined = {"results": normalized_results, "traces": normalized_traces}
    return _sha256(json.dumps(combined, sort_keys=True))


def _sha256(data: str) -> str:
    return sha256(data.encode("utf-8")).hexdigest()
