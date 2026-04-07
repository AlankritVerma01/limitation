from __future__ import annotations

import json
from pathlib import Path
from urllib import request
from urllib.error import HTTPError

import pytest
from interaction_harness.audit import run_recommender_audit
from interaction_harness.domains.recommender import (
    ARTIFACT_FILENAME,
    HttpRecommenderAdapter,
    RecommenderAgentPolicy,
    build_recommender_run_config,
    build_reference_artifacts,
    build_scenarios,
    initial_state_from_seed,
    load_reference_artifacts,
    run_reference_recommender_service,
)
from interaction_harness.rollout.engine import run_rollouts


@pytest.fixture()
def reference_artifact_dir(tmp_path: Path) -> Path:
    artifact_dir = tmp_path / "reference-artifacts"
    build_reference_artifacts(artifact_dir)
    return artifact_dir


def test_reference_artifact_build_writes_expected_bundle(reference_artifact_dir: Path) -> None:
    artifact_path = reference_artifact_dir / ARTIFACT_FILENAME
    assert artifact_path.exists()
    payload = load_reference_artifacts(reference_artifact_dir)
    assert payload["artifact_id"].startswith("movielens-100k-reference-")
    assert payload["dataset"] == "MovieLens 100K"
    assert payload["item_count"] > 1000


def test_reference_service_answers_health_and_metadata(reference_artifact_dir: Path) -> None:
    with run_reference_recommender_service(str(reference_artifact_dir)) as (base_url, metadata):
        assert metadata["service_kind"] == "reference"
        with request.urlopen(f"{base_url}/health", timeout=2.0) as response:
            health = json.loads(response.read().decode("utf-8"))
        with request.urlopen(f"{base_url}/metadata", timeout=2.0) as response:
            remote_metadata = json.loads(response.read().decode("utf-8"))
    assert health["status"] == "ok"
    assert remote_metadata["artifact_id"] == metadata["artifact_id"]


def test_reference_service_rejects_malformed_requests(reference_artifact_dir: Path) -> None:
    with run_reference_recommender_service(str(reference_artifact_dir)) as (base_url, _metadata):
        req = request.Request(
            f"{base_url}/recommendations",
            data=json.dumps({"bad": "payload"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as exc_info:
            request.urlopen(req, timeout=2.0)
    assert exc_info.value.code == 400


def test_http_adapter_works_against_reference_service(reference_artifact_dir: Path) -> None:
    run_config, _resolved_inputs = build_recommender_run_config(
        seed=4,
        scenario_names=("returning-user-home-feed",),
        service_artifact_dir=str(reference_artifact_dir),
    )
    scenario = build_scenarios(run_config.scenarios)[0]
    agent_seed = run_config.agent_seeds[0]
    observation = scenario.initialize(agent_seed, run_config)
    state = initial_state_from_seed(agent_seed, observation.scenario_context)
    with run_reference_recommender_service(str(reference_artifact_dir)) as (base_url, _metadata):
        adapter = HttpRecommenderAdapter(base_url, timeout_seconds=2.0)
        slate = adapter.get_slate(state, observation, run_config.scenarios[0])
        metadata = adapter.get_service_metadata()
    assert len(slate.items) == 5
    assert slate.items[0].rank == 1
    assert metadata["service_kind"] == "reference"


def test_rollout_runs_against_reference_service(reference_artifact_dir: Path) -> None:
    run_config, _resolved_inputs = build_recommender_run_config(
        seed=6,
        scenario_names=("returning-user-home-feed",),
        service_artifact_dir=str(reference_artifact_dir),
    )
    scenarios = build_scenarios(run_config.scenarios)
    with run_reference_recommender_service(str(reference_artifact_dir)) as (base_url, _metadata):
        traces = run_rollouts(
            HttpRecommenderAdapter(base_url, timeout_seconds=2.0),
            scenarios,
            RecommenderAgentPolicy(),
            run_config,
        )
    assert traces
    assert all(trace.steps for trace in traces)


def test_reference_service_is_default_for_audit_runs(reference_artifact_dir: Path, tmp_path: Path) -> None:
    paths = run_recommender_audit(
        seed=3,
        output_dir=str(tmp_path / "audit"),
        service_artifact_dir=str(reference_artifact_dir),
    )
    payload = json.loads(Path(paths["results_path"]).read_text(encoding="utf-8"))
    assert payload["metadata"]["service_kind"] == "reference"
    assert payload["metadata"]["service_mode"] == "reference"


def test_mock_service_can_still_be_requested_explicitly(tmp_path: Path) -> None:
    paths = run_recommender_audit(
        seed=3,
        output_dir=str(tmp_path / "audit"),
        service_mode="mock",
    )
    payload = json.loads(Path(paths["results_path"]).read_text(encoding="utf-8"))
    assert payload["metadata"]["service_kind"] == "mock"
    assert payload["metadata"]["service_mode"] == "mock"
