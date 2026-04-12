from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib import request

import pytest
from evidpath.cli import main

pytest.importorskip("torch")
pytest.importorskip("transformers")

HF_SERVICE_DIR = (
    Path(__file__).resolve().parents[1] / "examples" / "hf_recommender_service"
)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@contextmanager
def _run_hf_service(
    *,
    model_kind: str,
    artifact_dir: Path,
):
    port = _free_port()
    env = os.environ.copy()
    env["IH_HF_MODEL_KIND"] = model_kind
    env["IH_HF_ARTIFACT_DIR"] = str(artifact_dir)
    process = subprocess.Popen(
        [
            sys.executable,
            str(HF_SERVICE_DIR / "run.py"),
            "--model-kind",
            model_kind,
            "--artifact-dir",
            str(artifact_dir),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_health(base_url)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _wait_for_health(base_url: str) -> None:
    last_error: Exception | None = None
    for _ in range(240):
        try:
            with request.urlopen(f"{base_url}/health", timeout=0.5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("status") == "ok":
                return
        except Exception as exc:  # pragma: no cover - polling fallback
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"HF example service did not become ready: {last_error}")


def test_hf_wrapper_supports_health_metadata_recommendations_and_public_checks(
    tmp_path: Path,
) -> None:
    with _run_hf_service(
        model_kind="hf-semantic",
        artifact_dir=tmp_path / "hf-service-artifacts",
    ) as base_url:
        with request.urlopen(f"{base_url}/metadata", timeout=2.0) as response:
            metadata = json.loads(response.read().decode("utf-8"))
        recommendation_request = {
            "request_id": "demo-request",
            "agent_id": "demo-agent",
            "scenario_name": "returning-user-home-feed",
            "scenario_profile": "returning-user-home-feed",
            "step_index": 1,
            "history_depth": 2,
            "history_item_ids": ["50", "181"],
            "recent_exposure_ids": [],
            "preferred_genres": ["drama", "thriller"],
        }
        req = request.Request(
            f"{base_url}/recommendations",
            data=json.dumps(recommendation_request).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=5.0) as response:
            payload = json.loads(response.read().decode("utf-8"))

        check_result = main(
            [
                "check-target",
                "--domain",
                "recommender",
                "--target-url",
                base_url,
            ]
        )
        audit_result = main(
            [
                "audit",
                "--domain",
                "recommender",
                "--target-url",
                base_url,
                "--scenario",
                "returning-user-home-feed",
                "--seed",
                "7",
                "--output-dir",
                str(tmp_path / "hf-audit"),
            ]
        )

    assert metadata["backend_name"] == "HFExternalRecommenderService"
    assert metadata["model_kind"] == "hf-semantic"
    assert metadata["embedding_model_name"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert len(payload["items"]) == 5
    assert payload["items"][0]["rank"] == 1
    assert check_result["probe_status"] == "ok"
    assert check_result["model_kind"] == "hf-semantic"
    audit_payload = json.loads(Path(str(audit_result["results_path"])).read_text(encoding="utf-8"))
    assert audit_payload["metadata"]["service_kind"] == "external"
    assert audit_payload["metadata"]["model_kind"] == "hf-semantic"
    assert audit_payload["metadata"]["backend_name"] == "HFExternalRecommenderService"


def test_compare_runs_against_two_hf_wrapper_modes(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "hf-shared-artifacts"
    with _run_hf_service(
        model_kind="hf-semantic",
        artifact_dir=artifact_dir,
    ) as baseline_url:
        with _run_hf_service(
            model_kind="hf-semantic-popularity-blend",
            artifact_dir=artifact_dir,
        ) as candidate_url:
            result = main(
                [
                    "compare",
                    "--domain",
                    "recommender",
                    "--baseline-url",
                    baseline_url,
                    "--candidate-url",
                    candidate_url,
                    "--baseline-label",
                    "hf-semantic",
                    "--candidate-label",
                    "hf-semantic-popularity-blend",
                    "--rerun-count",
                    "2",
                    "--output-dir",
                    str(tmp_path / "hf-compare"),
                ]
            )

    report = Path(str(result["regression_report_path"])).read_text(encoding="utf-8")
    assert "hf-semantic" in report
    assert "hf-semantic-popularity-blend" in report
    assert Path(str(result["run_manifest_path"])).exists()
