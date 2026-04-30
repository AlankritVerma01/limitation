from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import zipfile
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
from pathlib import Path
from threading import Thread
from unittest.mock import patch
from urllib import request

from evidpath.cli import main
from evidpath.domains.recommender import ensure_reference_artifacts
from evidpath.domains.recommender.generation import (
    normalize_recommender_persona_profile,
    project_recommender_persona_to_agent_seed,
)
from evidpath.population_generation import (
    GeneratedPopulationCandidates,
    generate_population_pack,
    write_population_pack,
)
from evidpath.scenario_generation import (
    generate_scenario_pack,
    write_scenario_pack,
)
from evidpath.schema import GeneratedPersona

EXAMPLE_SERVICE_DIR = (
    Path(__file__).resolve().parents[3] / "examples" / "recommender_http_service"
)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@contextmanager
def _run_example_service(
    *,
    model_kind: str,
    artifact_dir: Path,
):
    port = _free_port()
    env = os.environ.copy()
    env["IH_EXAMPLE_MODEL_KIND"] = model_kind
    env["IH_EXAMPLE_ARTIFACT_DIR"] = str(artifact_dir)
    process = subprocess.Popen(
        [
            sys.executable,
            str(EXAMPLE_SERVICE_DIR / "run.py"),
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
    for _ in range(80):
        try:
            with request.urlopen(f"{base_url}/health", timeout=0.5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("status") == "ok":
                return
        except Exception as exc:  # pragma: no cover - polling fallback
            last_error = exc
        time.sleep(0.1)
    raise RuntimeError(f"Example service did not become ready: {last_error}")


@contextmanager
def _run_malformed_service() -> str:
    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A003
            return

        def _write_json(self, code: int, payload: str) -> None:
            encoded = payload.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):  # noqa: N802
            if self.path == "/health":
                self._write_json(200, '{"status":"ok","service_kind":"external"}')
            elif self.path == "/metadata":
                self._write_json(
                    200, '{"service_kind":"external","model_kind":"broken"}'
                )
            else:
                self._write_json(404, '{"detail":"not_found"}')

        def do_POST(self):  # noqa: N802
            if self.path == "/recommendations":
                self._write_json(
                    200,
                    '{"request_id":"broken","items":[{"item_id":"1","title":"Broken"}]}',
                )
            else:
                self._write_json(404, '{"detail":"not_found"}')

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_demo_audit_flow_surfaces_risky_and_healthy_cohorts(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "reference-artifacts"
    ensure_reference_artifacts(artifact_dir)

    result = main(
        [
            "audit",
            "--domain",
            "recommender",
            "--seed",
            "7",
            "--reference-artifact-dir",
            str(artifact_dir),
            "--output-dir",
            str(tmp_path / "demo-audit"),
        ]
    )

    report = Path(str(result["report_path"])).read_text(encoding="utf-8")
    assert "## Executive Summary" in report
    assert "## Launch Risks" in report
    assert "## Representative Traces To Inspect" in report
    assert "Main concern:" in report
    assert "Strongest cohort:" in report
    assert "trust_collapse" in report


def test_demo_compare_flow_writes_buyer_readable_regression_summary(
    tmp_path: Path,
) -> None:
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    ensure_reference_artifacts(baseline_dir)
    ensure_reference_artifacts(candidate_dir)

    result = main(
        [
            "compare",
            "--domain",
            "recommender",
            "--baseline-artifact-dir",
            str(baseline_dir),
            "--candidate-artifact-dir",
            str(candidate_dir),
            "--baseline-label",
            "current-prod",
            "--candidate-label",
            "current-prod-copy",
            "--rerun-count",
            "2",
            "--output-dir",
            str(tmp_path / "demo-compare"),
        ]
    )

    report = Path(str(result["regression_report_path"])).read_text(encoding="utf-8")
    assert "## Decision" in report
    assert "## Executive Summary" in report
    assert "## Most Important Changes" in report
    assert "Comparison: `current-prod` -> `current-prod-copy`" in report
    assert "Overall direction:" in report


def test_example_external_service_health_and_metadata_for_both_models(
    tmp_path: Path,
) -> None:
    for model_kind in ("popularity", "item-item-cf", "genre-history-blend"):
        with _run_example_service(
            model_kind=model_kind,
            artifact_dir=tmp_path / f"{model_kind}-artifacts",
        ) as base_url:
            with request.urlopen(f"{base_url}/metadata", timeout=2.0) as response:
                metadata = json.loads(response.read().decode("utf-8"))

        assert metadata["service_kind"] == "external"
        assert metadata["dataset"] == "MovieLens 100K"
        assert metadata["data_source"] in {"repo_copy", "downloaded"}
        assert metadata["model_kind"] == model_kind
        assert metadata["item_count"] > 1000


def test_example_service_can_build_artifacts_from_downloaded_source_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sys.path.insert(0, str(EXAMPLE_SERVICE_DIR.parent))
    try:
        from recommender_http_service import artifacts as service_artifacts
    finally:
        sys.path.pop(0)

    monkeypatch.setattr(
        service_artifacts, "DEFAULT_DATA_DIR", tmp_path / "missing-ml-100k"
    )

    archive_bytes = BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as zipped:
        zipped.writestr(
            "ml-100k/u.item",
            (
                "1|Toy Story (1995)|01-Jan-1995||http://example|0|0|0|0|0|1|0|0|0|0|0|0|0|0|0|0|0|0|0\n"
                "2|GoldenEye (1995)|01-Jan-1995||http://example|0|1|0|0|0|0|0|0|0|0|0|0|0|0|0|0|1|0|0\n"
            ),
        )
        zipped.writestr(
            "ml-100k/u.data",
            "1\t1\t5\t874965758\n1\t2\t4\t874965759\n2\t2\t5\t874965760\n",
        )
    archive_payload = archive_bytes.getvalue()

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return archive_payload

    monkeypatch.setattr(
        service_artifacts.request, "urlopen", lambda *args, **kwargs: _Response()
    )

    artifact_path = service_artifacts.ensure_example_artifacts(
        tmp_path / "downloaded-artifacts"
    )
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["dataset"] == "MovieLens 100K"
    assert payload["item_count"] == 2


def test_example_external_service_recommendation_contract_for_both_models(
    tmp_path: Path,
) -> None:
    payload = {
        "request_id": "demo-request",
        "agent_id": "agent-demo",
        "scenario_name": "returning-user-home-feed",
        "scenario_profile": "returning-user-home-feed",
        "step_index": 0,
        "history_depth": 4,
        "history_item_ids": ["50", "181", "172", "174"],
        "recent_exposure_ids": ["50"],
        "preferred_genres": ["action", "thriller"],
    }
    for model_kind in ("popularity", "item-item-cf", "genre-history-blend"):
        with _run_example_service(
            model_kind=model_kind,
            artifact_dir=tmp_path / f"{model_kind}-artifacts",
        ) as base_url:
            req = request.Request(
                f"{base_url}/recommendations",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(req, timeout=2.0) as response:
                body = json.loads(response.read().decode("utf-8"))

        assert body["request_id"] == "demo-request"
        assert len(body["items"]) == 5
        assert body["items"][0]["rank"] == 1
        assert {
            "item_id",
            "title",
            "genre",
            "score",
            "rank",
            "popularity",
            "novelty",
        } <= set(body["items"][0])


def test_check_target_command_validates_a_healthy_external_service(
    tmp_path: Path, capsys
) -> None:
    with _run_example_service(
        model_kind="genre-history-blend",
        artifact_dir=tmp_path / "genre-history-artifacts",
    ) as base_url:
        result = main(
            [
                "check-target",
                "--domain",
                "recommender",
                "--target-url",
                base_url,
            ]
        )

    captured = capsys.readouterr()
    assert result["probe_status"] == "ok"
    assert result["model_kind"] == "genre-history-blend"
    assert "Target check complete:" in captured.out
    assert "Probe scenario" in captured.out


def test_check_target_rejects_malformed_recommendation_payload() -> None:
    with _run_malformed_service() as base_url:
        try:
            main(
                [
                    "check-target",
                    "--domain",
                    "recommender",
                    "--target-url",
                    base_url,
                ]
            )
        except RuntimeError as exc:
            assert "invalid response payload" in str(exc).lower()
        else:
            raise AssertionError(
                "Expected malformed recommendation payload to fail target check."
            )


def test_check_target_rejects_unreachable_target() -> None:
    try:
        main(
            [
                "check-target",
                "--domain",
                "recommender",
                "--target-url",
                "http://127.0.0.1:1",
                "--timeout-seconds",
                "0.1",
            ]
        )
    except RuntimeError as exc:
        assert "unreachable" in str(exc).lower() or "health check" in str(exc).lower()
    else:
        raise AssertionError("Expected unreachable target to fail target check.")


def test_external_audit_flow_captures_service_metadata(tmp_path: Path) -> None:
    with _run_example_service(
        model_kind="popularity",
        artifact_dir=tmp_path / "popularity-artifacts",
    ) as base_url:
        result = main(
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
                str(tmp_path / "external-audit"),
            ]
        )

    payload = json.loads(Path(str(result["results_path"])).read_text(encoding="utf-8"))
    report = Path(str(result["report_path"])).read_text(encoding="utf-8")
    assert payload["metadata"]["service_kind"] == "external"
    assert payload["metadata"]["model_kind"] == "popularity"
    assert payload["metadata"]["data_source"] in {"repo_copy", "downloaded"}
    assert payload["summary"]["target_mode"] == "external_url"
    assert "Model kind: `popularity`" in report
    assert "Dataset: `MovieLens 100K`" in report


def test_external_compare_flow_supports_two_model_variants(tmp_path: Path) -> None:
    with (
        _run_example_service(
            model_kind="popularity",
            artifact_dir=tmp_path / "popularity-artifacts",
        ) as baseline_url,
        _run_example_service(
            model_kind="item-item-cf",
            artifact_dir=tmp_path / "cf-artifacts",
        ) as candidate_url,
    ):
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
                "popularity",
                "--candidate-label",
                "item-item-cf",
                "--rerun-count",
                "1",
                "--output-dir",
                str(tmp_path / "external-compare"),
            ]
        )

    payload = json.loads(
        Path(str(result["regression_summary_path"])).read_text(encoding="utf-8")
    )
    assert payload["baseline_summary"]["target"]["mode"] == "external_url"
    assert payload["candidate_summary"]["target"]["mode"] == "external_url"
    assert payload["baseline_summary"]["metadata"]["model_kind"] == "popularity"
    assert payload["candidate_summary"]["metadata"]["model_kind"] == "item-item-cf"


def test_external_audit_supports_scenario_and_population_pack_reuse(
    tmp_path: Path,
) -> None:
    scenario_pack = generate_scenario_pack(
        "test trust and exploration balance for returning users",
        generator_mode="fixture",
    )
    scenario_pack_path = tmp_path / "scenario-pack.json"
    write_scenario_pack(scenario_pack, scenario_pack_path)
    population_pack = generate_population_pack(
        "test a broad swarm of novelty-seeking and low-patience viewers",
        generator_mode="fixture",
        population_size=8,
    )
    population_pack_path = tmp_path / "population-pack.json"
    write_population_pack(population_pack, population_pack_path)

    with _run_example_service(
        model_kind="item-item-cf",
        artifact_dir=tmp_path / "cf-artifacts",
    ) as base_url:
        result = main(
            [
                "audit",
                "--domain",
                "recommender",
                "--target-url",
                base_url,
                "--scenario-pack-path",
                str(scenario_pack_path),
                "--population-pack-path",
                str(population_pack_path),
                "--output-dir",
                str(tmp_path / "external-pack-audit"),
            ]
        )

    payload = json.loads(Path(str(result["results_path"])).read_text(encoding="utf-8"))
    assert payload["metadata"]["scenario_pack_id"] == scenario_pack.metadata.pack_id
    assert payload["metadata"]["population_pack_id"] == population_pack.metadata.pack_id
    assert payload["summary"]["target_mode"] == "external_url"


def test_provider_generated_packs_can_be_reused_against_external_targets(
    tmp_path: Path,
) -> None:
    provider_scenarios = [
        {
            "scenario_id": "provider-taste-recovery",
            "name": "Provider Taste Recovery",
            "description": "Provider-authored re-engagement session.",
            "test_goal": "Check trust rebuild with richer simulation focus.",
            "risk_focus_tags": ["trust-drop", "weak-first-impression"],
            "max_steps": 5,
            "allowed_actions": ["click", "skip", "abandon"],
            "adapter_hints": {
                "recommender": {
                    "runtime_profile": "re-engagement-home-feed",
                    "history_depth": 2,
                    "context_hint": "rebuild trust after drift",
                    "simulation_focus": ["trust-rebuild", "first-two-slates-matter"],
                }
            },
        }
    ]
    provider_personas = GeneratedPopulationCandidates(
        personas=(
            {
                "persona_id": "provider-first-hit",
                "display_label": "Provider First Hit",
                "persona_summary": "Needs early confidence and a clean first slate.",
                "behavior_goal": "Reward quality once trust is earned.",
                "diversity_tags": ["provider", "ai-authored"],
                "adapter_hints": {
                    "recommender": {
                        "preferred_genres": ["action", "thriller"],
                        "popularity_preference": 0.44,
                        "novelty_preference": 0.61,
                        "repetition_tolerance": 0.28,
                        "sparse_history_confidence": 0.34,
                        "abandonment_sensitivity": 0.72,
                        "patience": 3,
                        "engagement_baseline": 0.55,
                        "quality_sensitivity": 0.71,
                        "repeat_exposure_penalty": 0.33,
                        "novelty_fatigue": 0.21,
                        "frustration_recovery": 0.22,
                        "history_reliance": 0.46,
                        "skip_tolerance": 2,
                        "abandonment_threshold": 0.58,
                        "behavior_plan": [
                            "first-hit-or-leave",
                            "trust-before-explore",
                        ],
                    }
                },
            },
        ),
        suggested_population_size=1,
    )
    with (
        patch(
            "evidpath.scenario_generation.ProviderScenarioGenerator.generate",
            return_value=provider_scenarios,
        ),
        patch(
            "evidpath.population_generation.ProviderPopulationGenerator.generate",
            return_value=provider_personas,
        ),
    ):
        scenario_pack = generate_scenario_pack(
            "provider-authored trust rebuild coverage",
            generator_mode="provider",
            scenario_count=1,
        )
        population_pack = generate_population_pack(
            "provider-authored early trust and exploration coverage",
            generator_mode="provider",
            candidate_count=1,
        )

    scenario_pack_path = tmp_path / "provider-scenario-pack.json"
    population_pack_path = tmp_path / "provider-population-pack.json"
    write_scenario_pack(scenario_pack, scenario_pack_path)
    write_population_pack(population_pack, population_pack_path)

    with _run_example_service(
        model_kind="genre-history-blend",
        artifact_dir=tmp_path / "provider-external-artifacts",
    ) as base_url:
        first = main(
            [
                "audit",
                "--domain",
                "recommender",
                "--target-url",
                base_url,
                "--scenario-pack-path",
                str(scenario_pack_path),
                "--population-pack-path",
                str(population_pack_path),
                "--seed",
                "11",
                "--output-dir",
                str(tmp_path / "provider-external-first"),
            ]
        )
        second = main(
            [
                "audit",
                "--domain",
                "recommender",
                "--target-url",
                base_url,
                "--scenario-pack-path",
                str(scenario_pack_path),
                "--population-pack-path",
                str(population_pack_path),
                "--seed",
                "11",
                "--output-dir",
                str(tmp_path / "provider-external-second"),
            ]
        )

    first_payload = json.loads(
        Path(str(first["results_path"])).read_text(encoding="utf-8")
    )
    second_payload = json.loads(
        Path(str(second["results_path"])).read_text(encoding="utf-8")
    )
    assert first_payload["metadata"]["scenario_pack_mode"] == "provider"
    assert first_payload["metadata"]["population_pack_mode"] == "provider"
    assert first_payload["traces"] == second_payload["traces"]
    first_summary = dict(first_payload["summary"])
    second_summary = dict(second_payload["summary"])
    first_summary.pop("run_plan_id", None)
    second_summary.pop("run_plan_id", None)
    assert first_summary == second_summary


def test_ai_behavior_plan_projects_into_structured_runtime_seed() -> None:
    persona = GeneratedPersona(
        persona_id="provider-plan-persona",
        display_label="Provider plan persona",
        persona_summary="AI-authored persona with a concrete behavior plan.",
        behavior_goal="Stay open to exploration once quality is proven.",
        diversity_tags=("provider", "plan-driven"),
        adapter_hints={
            "recommender": {
                "preferred_genres": ["sci-fi", "thriller"],
                "popularity_preference": 0.45,
                "novelty_preference": 0.62,
                "repetition_tolerance": 0.31,
                "sparse_history_confidence": 0.42,
                "abandonment_sensitivity": 0.58,
                "patience": 3,
                "engagement_baseline": 0.57,
                "quality_sensitivity": 0.63,
                "repeat_exposure_penalty": 0.24,
                "novelty_fatigue": 0.27,
                "frustration_recovery": 0.16,
                "history_reliance": 0.39,
                "skip_tolerance": 2,
                "abandonment_threshold": 0.64,
                "behavior_plan": [
                    "first-hit-or-leave",
                    "trust-before-explore",
                    "quickly-bored-by-repetition",
                ],
            }
        },
    )
    projected = project_recommender_persona_to_agent_seed(persona)
    projected_profile = normalize_recommender_persona_profile(persona)

    assert "first-hit-or-leave" in projected.diversity_tags
    assert "trust-before-explore" in projected.behavior_goal
    assert projected_profile.abandonment_sensitivity > 0.58
    assert projected_profile.repetition_tolerance < 0.31
    assert projected_profile.quality_sensitivity > 0.63


def test_external_cli_example_flow_writes_artifacts(tmp_path: Path) -> None:
    with _run_example_service(
        model_kind="popularity",
        artifact_dir=tmp_path / "popularity-artifacts",
    ) as base_url:
        result = main(
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
                str(tmp_path / "docs-aligned-external-audit"),
            ]
        )

    assert Path(str(result["report_path"])).exists()
    assert Path(str(result["results_path"])).exists()
