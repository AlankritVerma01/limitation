"""Slow twin-run determinism test for evidpath.audit() Python API."""

from __future__ import annotations

from pathlib import Path

from evidpath import AdapterRequest, AdapterResponse, SlateItem, audit
from evidpath.artifacts._determinism import compute_deterministic_payload_hash
from evidpath.audit import write_run_artifacts


def test_python_api_audit_is_deterministic_across_twin_runs(tmp_path: Path) -> None:
    first = audit(
        callable=_deterministic_predict,
        seed=0,
        output_dir=str(tmp_path / "run-1"),
    )
    second = audit(
        callable=_deterministic_predict,
        seed=0,
        output_dir=str(tmp_path / "run-2"),
    )
    paths_one = write_run_artifacts(first)
    paths_two = write_run_artifacts(second)
    hash_one = compute_deterministic_payload_hash(
        results_path=Path(paths_one["results_path"]),
        traces_path=Path(paths_one["traces_path"]),
    )
    hash_two = compute_deterministic_payload_hash(
        results_path=Path(paths_two["results_path"]),
        traces_path=Path(paths_two["traces_path"]),
    )
    assert hash_one == hash_two


def _deterministic_predict(request: AdapterRequest) -> AdapterResponse:
    items = tuple(
        SlateItem(
            item_id=f"m{i}",
            title=f"item-{i}",
            genre="g",
            score=1.0 - 0.05 * i,
            rank=i + 1,
            popularity=0.5,
            novelty=0.3,
        )
        for i in range(5)
    )
    return AdapterResponse(request_id=request.request_id, items=items)
