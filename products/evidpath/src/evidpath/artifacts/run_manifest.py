"""Durable run-manifest writers for audit, swarm, and compare workflows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..schema import RegressionDiff, RunResult
from ._determinism import (
    compute_deterministic_payload_hash,
    hash_population,
    hash_scenarios,
)
from ._environment import collect_environment_fingerprint


def write_run_manifest(
    run_result: RunResult,
    *,
    artifact_paths: dict[str, str],
    workflow_type: str,
    workflow_metadata: dict[str, Any] | None = None,
) -> str:
    """Write one durable manifest for a single-run workflow."""
    manifest_path = Path(
        str(
            run_result.metadata.get(
                "run_manifest_path",
                Path(run_result.run_config.rollout.output_dir) / "run_manifest.json",
            )
        )
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "workflow_type": workflow_type,
        "domain": str(run_result.metadata.get("domain_name", "")),
        "run_id": str(run_result.metadata.get("run_id", "")),
        "generated_at_utc": str(run_result.metadata.get("generated_at_utc", "")),
        "display_name": str(
            run_result.metadata.get("display_name", run_result.run_config.run_name)
        ),
        "run_name": run_result.run_config.run_name,
        "run_plan": {
            "run_plan_id": str(run_result.metadata.get("run_plan_id", "")),
            "run_plan_path": str(run_result.metadata.get("run_plan_path", "")),
            "planner_mode": str(run_result.metadata.get("planner_mode", "")),
            "planner_provider_name": str(
                run_result.metadata.get("planner_provider_name", "")
            ),
            "planner_model_name": str(
                run_result.metadata.get("planner_model_name", "")
            ),
            "planner_model_profile": str(
                run_result.metadata.get("planner_model_profile", "")
            ),
            "planner_summary": str(run_result.metadata.get("planner_summary", "")),
        },
        "seed": run_result.run_config.rollout.seed,
        "semantic_mode": str(run_result.metadata.get("semantic_mode", "off")),
        "semantic_advisory": {
            "enabled": bool(run_result.semantic_interpretation is not None),
            "advisory_only": True,
            "artifact_path": str(artifact_paths.get("semantic_advisory_path", "")),
            "mode": str(run_result.metadata.get("semantic_mode", "off")),
            "provider_name": str(run_result.metadata.get("semantic_provider_name", "")),
            "model_name": str(run_result.metadata.get("semantic_model", "")),
            "model_profile": str(
                run_result.metadata.get("semantic_model_profile", "")
            ),
            "decision_origin": str(
                run_result.metadata.get("semantic_advisory_origin", "")
            ),
            "gating": str(run_result.metadata.get("semantic_advisory_gating", "advisory_only")),
            "rationale": str(
                run_result.metadata.get("semantic_advisory_rationale", "")
            ),
            "execution_status": "completed"
            if run_result.semantic_interpretation is not None
            else "skipped",
        },
        "service": {
            "service_kind": str(run_result.metadata.get("service_kind", "")),
            "target_driver_kind": str(run_result.metadata.get("target_driver_kind", "")),
            "target_identity": str(run_result.metadata.get("target_identity", "")),
            "target_endpoint_host": str(
                run_result.metadata.get("target_endpoint_host", "")
            ),
            "dataset": str(run_result.metadata.get("dataset", "")),
            "data_source": str(run_result.metadata.get("data_source", "")),
            "backend_name": str(run_result.metadata.get("backend_name", "")),
            "model_kind": str(run_result.metadata.get("model_kind", "")),
            "model_id": str(run_result.metadata.get("model_id", "")),
            "artifact_id": str(run_result.metadata.get("artifact_id", "")),
            "service_metadata_status": str(
                run_result.metadata.get("service_metadata_status", "")
            ),
        },
        "coverage": {
            "scenario_source": str(run_result.metadata.get("scenario_source", "")),
            "scenario_pack_id": str(run_result.metadata.get("scenario_pack_id", "")),
            "scenario_pack_mode": str(
                run_result.metadata.get("scenario_pack_mode", "")
            ),
            "scenario_pack_model_name": str(
                run_result.metadata.get("scenario_pack_model_name", "")
            ),
            "scenario_pack_model_profile": str(
                run_result.metadata.get("scenario_pack_model_profile", "")
            ),
            "population_source": str(run_result.metadata.get("population_source", "")),
            "population_pack_id": str(
                run_result.metadata.get("population_pack_id", "")
            ),
            "population_pack_mode": str(
                run_result.metadata.get("population_pack_mode", "")
            ),
            "population_pack_model_name": str(
                run_result.metadata.get("population_pack_model_name", "")
            ),
            "population_pack_model_profile": str(
                run_result.metadata.get("population_pack_model_profile", "")
            ),
            "population_size_source": str(
                run_result.metadata.get("population_size_source", "")
            ),
        },
        "artifacts": dict(sorted(artifact_paths.items())),
        "workflow_metadata": dict(sorted((workflow_metadata or {}).items())),
        "environment": collect_environment_fingerprint(),
        "inputs": {
            "scenario_hash": hash_scenarios(run_result.run_config.scenarios),
            "population_hash": hash_population(run_result.run_config.agent_seeds),
        },
        "outputs": {
            "deterministic_payload_hash": compute_deterministic_payload_hash(
                results_path=Path(artifact_paths["results_path"]),
                traces_path=Path(artifact_paths["traces_path"]),
            ),
        },
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return str(manifest_path)


def write_regression_manifest(
    regression_diff: RegressionDiff,
    *,
    artifact_paths: dict[str, str | int],
) -> str:
    """Write one durable manifest for a compare workflow."""
    manifest_path = Path(
        str(
            regression_diff.metadata.get(
                "run_manifest_path",
                Path(str(artifact_paths["regression_report_path"])).parent
                / "run_manifest.json",
            )
        )
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    decision = regression_diff.decision
    payload = {
        "workflow_type": "compare",
        "domain": str(regression_diff.metadata.get("domain_name", "")),
        "regression_id": str(regression_diff.metadata.get("regression_id", "")),
        "generated_at_utc": str(regression_diff.metadata.get("generated_at_utc", "")),
        "display_name": str(regression_diff.metadata.get("display_name", "")),
        "run_plan": {
            "run_plan_id": str(regression_diff.metadata.get("run_plan_id", "")),
            "run_plan_path": str(regression_diff.metadata.get("run_plan_path", "")),
            "planner_mode": str(regression_diff.metadata.get("planner_mode", "")),
            "planner_provider_name": str(
                regression_diff.metadata.get("planner_provider_name", "")
            ),
            "planner_model_name": str(
                regression_diff.metadata.get("planner_model_name", "")
            ),
            "planner_model_profile": str(
                regression_diff.metadata.get("planner_model_profile", "")
            ),
            "planner_summary": str(regression_diff.metadata.get("planner_summary", "")),
        },
        "base_seed": int(regression_diff.metadata.get("base_seed", 0)),
        "rerun_count": int(regression_diff.metadata.get("rerun_count", 0)),
        "semantic_advisory": {
            "enabled": bool(regression_diff.semantic_interpretation is not None),
            "advisory_only": True,
            "artifact_path": str(
                artifact_paths.get("semantic_regression_advisory_path", "")
            ),
            "mode": str(regression_diff.metadata.get("semantic_mode", "off")),
            "provider_name": str(
                regression_diff.metadata.get("semantic_provider_name", "")
            ),
            "model_name": str(regression_diff.metadata.get("semantic_model", "")),
            "model_profile": str(
                regression_diff.metadata.get("semantic_model_profile", "")
            ),
            "decision_origin": str(
                regression_diff.metadata.get("semantic_advisory_origin", "")
            ),
            "gating": str(
                regression_diff.metadata.get("semantic_advisory_gating", "advisory_only")
            ),
            "rationale": str(
                regression_diff.metadata.get("semantic_advisory_rationale", "")
            ),
            "execution_status": "completed"
            if regression_diff.semantic_interpretation is not None
            else "skipped",
        },
        "policy_name": str(regression_diff.metadata.get("policy_name", "")),
        "policy_mode": str(regression_diff.metadata.get("policy_mode", "")),
        "baseline": {
            "label": regression_diff.baseline_summary.target.label,
            "target_driver_kind": regression_diff.baseline_summary.target.driver_kind,
            "target_identity": str(
                regression_diff.metadata.get("baseline_target_identity", "")
            ),
            "target_endpoint_host": str(
                regression_diff.metadata.get("baseline_target_endpoint_host", "")
            ),
            "service_kind": str(
                regression_diff.baseline_summary.metadata.get("service_kind", "")
            ),
            "dataset": str(
                regression_diff.baseline_summary.metadata.get("dataset", "")
            ),
            "model_kind": str(
                regression_diff.baseline_summary.metadata.get("model_kind", "")
            ),
            "model_id": str(
                regression_diff.baseline_summary.metadata.get("model_id", "")
            ),
        },
        "candidate": {
            "label": regression_diff.candidate_summary.target.label,
            "target_driver_kind": regression_diff.candidate_summary.target.driver_kind,
            "target_identity": str(
                regression_diff.metadata.get("candidate_target_identity", "")
            ),
            "target_endpoint_host": str(
                regression_diff.metadata.get("candidate_target_endpoint_host", "")
            ),
            "service_kind": str(
                regression_diff.candidate_summary.metadata.get("service_kind", "")
            ),
            "dataset": str(
                regression_diff.candidate_summary.metadata.get("dataset", "")
            ),
            "model_kind": str(
                regression_diff.candidate_summary.metadata.get("model_kind", "")
            ),
            "model_id": str(
                regression_diff.candidate_summary.metadata.get("model_id", "")
            ),
        },
        "coverage": {
            "scenario_pack_path": str(
                regression_diff.metadata.get("scenario_pack_path", "")
            ),
            "population_pack_path": str(
                regression_diff.metadata.get("population_pack_path", "")
            ),
        },
        "decision": {
            "status": decision.status if decision is not None else "pass",
            "exit_code": decision.exit_code if decision is not None else 0,
        },
        "artifacts": dict(sorted((key, str(value)) for key, value in artifact_paths.items())),
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return str(manifest_path)
