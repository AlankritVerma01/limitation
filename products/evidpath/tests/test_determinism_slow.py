"""End-to-end determinism check that runs the same audit twice."""

from __future__ import annotations

import json
from pathlib import Path

from evidpath.cli import main


def test_determinism_byte_stable_across_repeated_runs(tmp_path: Path) -> None:
    paths_a = _run_audit(tmp_path / "run-a")
    paths_b = _run_audit(tmp_path / "run-b")
    manifest_a = _read_manifest(paths_a)
    manifest_b = _read_manifest(paths_b)
    hash_a = manifest_a["outputs"]["deterministic_payload_hash"]
    hash_b = manifest_b["outputs"]["deterministic_payload_hash"]
    assert hash_a != ""
    assert hash_a == hash_b


def _run_audit(output_dir: Path) -> dict[str, str | int]:
    return main(
        [
            "audit",
            "--domain",
            "recommender",
            "--seed",
            "7",
            "--use-mock",
            "--output-dir",
            str(output_dir),
        ]
    )


def _read_manifest(paths: dict[str, str | int]) -> dict:
    return json.loads(
        Path(str(paths["run_manifest_path"])).read_text(encoding="utf-8")
    )
