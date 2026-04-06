"""JSON and trace artifact writer for the recommender audit."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from ..schema import RunResult


def _serialize(value: Any) -> Any:
    """Convert nested dataclasses into plain JSON-friendly Python objects."""
    if is_dataclass(value):
        return _serialize(asdict(value))
    if isinstance(value, dict):
        return {key: _serialize(inner) for key, inner in value.items()}
    if isinstance(value, tuple | list):
        return [_serialize(inner) for inner in value]
    return value


class JsonReportWriter:
    """Writes machine-readable run results and a trace bundle."""

    def __init__(self, *, include_slice_membership: bool = False) -> None:
        self.include_slice_membership = include_slice_membership

    def write(self, run_result: RunResult, output_dir: Path) -> dict[str, str]:
        """Write normalized JSON summaries plus the raw trace bundle."""
        output_dir.mkdir(parents=True, exist_ok=True)
        results_path = output_dir / "results.json"
        traces_path = output_dir / "traces.jsonl"
        payload = self._normalize_payload(run_result)
        results_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with traces_path.open("w", encoding="utf-8") as handle:
            for trace in run_result.traces:
                handle.write(json.dumps(_serialize(trace), sort_keys=True) + "\n")
        return {
            "results_path": str(results_path),
            "traces_path": str(traces_path),
        }

    def _normalize_payload(self, run_result: RunResult) -> dict[str, Any]:
        """Normalize volatile paths and timestamps so snapshots stay stable."""
        payload = _serialize(run_result)
        if payload.get("semantic_interpretation") is None:
            payload.pop("semantic_interpretation", None)
        if not self.include_slice_membership:
            payload["slice_discovery"]["memberships"] = []
        payload["summary"] = self._build_summary(run_result)
        payload["run_config"]["rollout"]["output_dir"] = "<normalized>"
        payload["run_config"]["rollout"]["adapter_base_url"] = "<normalized>"
        if "service_artifact_dir" in payload["run_config"]["rollout"]:
            payload["run_config"]["rollout"]["service_artifact_dir"] = "<normalized>"
        if "adapter_base_url" in payload["metadata"]:
            payload["metadata"]["adapter_base_url"] = "<normalized>"
        if "service_artifact_dir" in payload["metadata"]:
            payload["metadata"]["service_artifact_dir"] = "<normalized>"
        if "scenario_pack_path" in payload["metadata"]:
            payload["metadata"]["scenario_pack_path"] = "<normalized>"
        if "population_pack_path" in payload["metadata"]:
            payload["metadata"]["population_pack_path"] = "<normalized>"
        if "generated_at_utc" in payload["metadata"]:
            payload["metadata"]["generated_at_utc"] = "<normalized>"
        semantic = payload.get("semantic_interpretation")
        if isinstance(semantic, dict) and "generated_at_utc" in semantic:
            semantic["generated_at_utc"] = "<normalized>"
        if "generated_at_utc" in payload["summary"]:
            payload["summary"]["generated_at_utc"] = "<normalized>"
        return payload

    def _build_summary(self, run_result: RunResult) -> dict[str, object]:
        """Build the compact summary block shown at the top of results.json."""
        high_risk = [
            cohort for cohort in run_result.cohort_summaries if cohort.risk_level == "high"
        ]
        medium_risk = [
            cohort for cohort in run_result.cohort_summaries if cohort.risk_level == "medium"
        ]
        strongest = max(
            run_result.cohort_summaries,
            key=lambda cohort: cohort.mean_session_utility,
            default=None,
        )
        return {
            "display_name": str(run_result.metadata.get("display_name", run_result.run_config.run_name)),
            "run_id": str(run_result.metadata.get("run_id", "")),
            "generated_at_utc": str(run_result.metadata.get("generated_at_utc", "")),
            "service_kind": str(run_result.metadata.get("service_kind", "unknown")),
            "target_mode": str(run_result.metadata.get("target_mode", "reference_artifact")),
            "target_identity": str(run_result.metadata.get("target_identity", "")),
            "scenario_source": str(run_result.metadata.get("scenario_source", "built_in")),
            "scenario_count": int(run_result.metadata.get("scenario_count", len(run_result.run_config.scenarios))),
            "trace_count": len(run_result.traces),
            "agent_count": int(run_result.metadata.get("agent_count", len(run_result.run_config.agent_seeds))),
            "population_source": str(run_result.metadata.get("population_source", "built_in_seeds")),
            "population_size_source": str(run_result.metadata.get("population_size_source", "built_in")),
            "semantic_mode": str(run_result.metadata.get("semantic_mode", "off")),
            "slice_count": int(
                run_result.metadata.get(
                    "slice_count",
                    len(run_result.slice_discovery.slice_summaries),
                )
            ),
            "high_risk_cohort_count": len(high_risk),
            "medium_risk_cohort_count": len(medium_risk),
            "risk_flag_count": len(run_result.risk_flags),
            "strongest_cohort": (
                {
                    "scenario_name": strongest.scenario_name,
                    "archetype_label": strongest.archetype_label,
                    "mean_session_utility": strongest.mean_session_utility,
                }
                if strongest is not None
                else None
            ),
        }
