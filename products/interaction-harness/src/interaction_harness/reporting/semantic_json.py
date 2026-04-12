"""Dedicated advisory semantic JSON artifacts."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from ..schema import RegressionDiff, RunResult


def _serialize(value: Any) -> Any:
    if is_dataclass(value):
        return _serialize(asdict(value))
    if isinstance(value, dict):
        return {key: _serialize(inner) for key, inner in value.items()}
    if isinstance(value, tuple | list):
        return [_serialize(inner) for inner in value]
    return value


def write_run_semantic_artifact(run_result: RunResult, output_dir: Path) -> str | None:
    """Write a dedicated single-run semantic advisory sidecar when enabled."""
    interpretation = run_result.semantic_interpretation
    if interpretation is None:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    semantic_path = output_dir / "semantic_advisory.json"
    payload = {
        "workflow_type": "run-swarm" if run_result.metadata.get("run_plan_id") else "audit",
        "advisory_only": True,
        "run_id": str(run_result.metadata.get("run_id", "")),
        "run_plan_id": str(run_result.metadata.get("run_plan_id", "")),
        "run_plan_path": str(run_result.metadata.get("run_plan_path", "")),
        "run_manifest_path": str(run_result.metadata.get("run_manifest_path", "")),
        "semantic_mode": interpretation.mode,
        "provider_name": interpretation.provider_name,
        "model_name": interpretation.model_name,
        "model_profile": interpretation.model_profile,
        "generated_at_utc": interpretation.generated_at_utc,
        "advisory_summary": interpretation.advisory_summary,
        "trace_explanations": _serialize(interpretation.trace_explanations),
    }
    semantic_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return str(semantic_path)


def write_regression_semantic_artifact(
    regression_diff: RegressionDiff,
    output_dir: Path,
) -> str | None:
    """Write a dedicated compare semantic advisory sidecar when enabled."""
    interpretation = regression_diff.semantic_interpretation
    if interpretation is None:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    semantic_path = output_dir / "semantic_regression_advisory.json"
    payload = {
        "workflow_type": "compare",
        "advisory_only": True,
        "regression_id": str(regression_diff.metadata.get("regression_id", "")),
        "run_plan_id": str(regression_diff.metadata.get("run_plan_id", "")),
        "run_plan_path": str(regression_diff.metadata.get("run_plan_path", "")),
        "run_manifest_path": str(regression_diff.metadata.get("run_manifest_path", "")),
        "semantic_mode": interpretation.mode,
        "provider_name": interpretation.provider_name,
        "model_name": interpretation.model_name,
        "model_profile": interpretation.model_profile,
        "generated_at_utc": interpretation.generated_at_utc,
        "advisory_summary": interpretation.advisory_summary,
        "trace_explanations": _serialize(interpretation.trace_explanations),
    }
    semantic_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return str(semantic_path)
