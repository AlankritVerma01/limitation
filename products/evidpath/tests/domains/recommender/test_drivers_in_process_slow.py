"""Slow end-to-end tests for the in-process recommender driver."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from evidpath.artifacts.run_manifest import write_run_manifest
from evidpath.audit import execute_domain_audit, write_run_artifacts


def test_in_process_audit_end_to_end_via_example_recsys(tmp_path: Path) -> None:
    examples_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(examples_root))
    try:
        run_result = execute_domain_audit(
            domain_name="recommender",
            seed=11,
            output_dir=str(tmp_path / "in-process-audit"),
            scenario_names=("returning-user-home-feed",),
            driver_kind="in_process",
            driver_config={
                "import_path": "examples.recommender_in_process.recsys:predict",
                "backend_name": "popularity-baseline-v1",
            },
        )
    finally:
        sys.path.remove(str(examples_root))
    paths = write_run_artifacts(run_result)
    manifest_path = write_run_manifest(
        run_result,
        artifact_paths=paths,
        workflow_type="audit",
    )
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))

    assert manifest["service"]["target_driver_kind"] == "in_process"
    assert manifest["service"]["target_driver_config"]["import_path"].endswith(":predict")
    assert run_result.trace_scores


def test_in_process_audit_is_deterministic_across_twin_runs(tmp_path: Path) -> None:
    examples_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(examples_root))
    try:
        first = execute_domain_audit(
            domain_name="recommender",
            seed=11,
            output_dir=str(tmp_path / "first"),
            scenario_names=("returning-user-home-feed",),
            driver_kind="in_process",
            driver_config={
                "import_path": "examples.recommender_in_process.recsys:predict",
            },
        )
        second = execute_domain_audit(
            domain_name="recommender",
            seed=11,
            output_dir=str(tmp_path / "second"),
            scenario_names=("returning-user-home-feed",),
            driver_kind="in_process",
            driver_config={
                "import_path": "examples.recommender_in_process.recsys:predict",
            },
        )
    finally:
        sys.path.remove(str(examples_root))
    first_paths = write_run_artifacts(first)
    second_paths = write_run_artifacts(second)
    first_manifest_path = write_run_manifest(
        first,
        artifact_paths=first_paths,
        workflow_type="audit",
    )
    second_manifest_path = write_run_manifest(
        second,
        artifact_paths=second_paths,
        workflow_type="audit",
    )
    first_manifest = json.loads(Path(first_manifest_path).read_text(encoding="utf-8"))
    second_manifest = json.loads(Path(second_manifest_path).read_text(encoding="utf-8"))

    assert (
        first_manifest["outputs"]["deterministic_payload_hash"]
        == second_manifest["outputs"]["deterministic_payload_hash"]
    )
