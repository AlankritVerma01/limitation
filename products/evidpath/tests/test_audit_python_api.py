"""Tests for evidpath.audit() Python API."""

from __future__ import annotations

from pathlib import Path

import pytest
from evidpath import AdapterRequest, AdapterResponse, RunResult, SlateItem, audit


def _stub_predict(request: AdapterRequest) -> AdapterResponse:
    return AdapterResponse(
        request_id=request.request_id,
        items=(
            SlateItem(
                item_id="m1",
                title="Heat",
                genre="thriller",
                score=0.9,
                rank=1,
                popularity=0.5,
                novelty=0.3,
            ),
        ),
    )


def test_audit_callable_returns_run_result(tmp_path: Path) -> None:
    result = audit(
        callable=_stub_predict,
        seed=0,
        scenario_names=("returning-user-home-feed",),
        output_dir=str(tmp_path),
    )
    assert isinstance(result, RunResult)
    assert result.metadata["target_driver_kind"] == "in_process"
    assert result.metadata["target_driver_config"]["import_path"] == "<inline>"
    assert result.metadata["backend_name"] == "_stub_predict"


def test_audit_callable_accepts_class_instance(tmp_path: Path) -> None:
    class Recsys:
        service_metadata = {"model_kind": "popularity"}

        def predict(self, request: AdapterRequest) -> AdapterResponse:
            return _stub_predict(request)

    result = audit(
        callable=Recsys(),
        seed=0,
        scenario_names=("returning-user-home-feed",),
        output_dir=str(tmp_path),
    )
    assert result.metadata["target_driver_kind"] == "in_process"
    assert result.metadata["model_kind"] == "popularity"


def test_audit_rejects_non_callable() -> None:
    with pytest.raises(TypeError, match="callable"):
        audit(callable=42, seed=0, scenario_names=("returning-user-home-feed",))


def test_audit_passes_backend_name(tmp_path: Path) -> None:
    result = audit(
        callable=_stub_predict,
        seed=0,
        scenario_names=("returning-user-home-feed",),
        output_dir=str(tmp_path),
        backend_name="my-experimental-v3",
    )
    assert result.metadata["backend_name"] == "my-experimental-v3"
