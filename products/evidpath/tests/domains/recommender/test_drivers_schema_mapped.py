"""Tests for schema-mapped HTTP driver internals."""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from evidpath.artifacts.run_manifest import write_run_manifest
from evidpath.audit import execute_domain_audit, write_run_artifacts
from evidpath.domains.recommender.drivers import (
    HttpSchemaMappedDriverConfig,
    HttpSchemaMappedRecommenderDriver,
    ResponseMapping,
)
from evidpath.domains.recommender.drivers._extraction import (
    ResponseExtractionError,
    extract_items,
    resolve_dot_path,
)
from evidpath.domains.recommender.drivers._templating import (
    EnvVarMissingError,
    TemplateValidationError,
    discover_field_references,
    substitute,
)
from evidpath.schema import (
    AgentState,
    Observation,
    ScenarioConfig,
    ScenarioContext,
)


def test_substitute_preserves_pure_marker_type() -> None:
    assert substitute(
        {"history": "${history_item_ids}"},
        {"history_item_ids": ["m1", "m2"]},
    ) == {"history": ["m1", "m2"]}


def test_substitute_mixed_marker_and_env_marker() -> None:
    os.environ["EVIDPATH_TEST_API_KEY"] = "secret-xyz"
    try:
        assert substitute("/users/${agent_id}", {"agent_id": "u123"}) == "/users/u123"
        assert substitute("Bearer ${env:EVIDPATH_TEST_API_KEY}", {}) == "Bearer secret-xyz"
    finally:
        del os.environ["EVIDPATH_TEST_API_KEY"]


def test_substitute_raises_for_missing_env_and_unknown_field() -> None:
    with pytest.raises(EnvVarMissingError, match="EVIDPATH_TEST_NEVER_SET"):
        substitute("${env:EVIDPATH_TEST_NEVER_SET}", {})
    with pytest.raises(TemplateValidationError, match="missing"):
        substitute("${missing}", {"agent_id": "u123"})


def test_discover_field_references_ignores_env_markers() -> None:
    template = {"x": "${agent_id}", "y": "/${step_index}", "z": "${env:KEY}"}
    assert discover_field_references(template) == {"agent_id", "step_index"}


def test_resolve_dot_path_and_extract_items() -> None:
    payload = {
        "predictions": [
            {"movie_id": "m1", "confidence": 0.91, "title": "Heat"},
            {"movie_id": "m2", "confidence": 0.85, "title": "Drive"},
        ]
    }
    mapping = ResponseMapping(
        items_path="predictions",
        item_id_field="movie_id",
        score_field="confidence",
        title_field="title",
    )

    assert resolve_dot_path(payload, "predictions.1.movie_id") == "m2"
    assert extract_items(payload, mapping)[0].title == "Heat"


def test_extract_items_uses_jsonpath_when_path_starts_with_dollar() -> None:
    payload = {
        "buckets": [
            {"name": "main", "items": [{"movie_id": "m1", "confidence": 0.9}]},
            {"name": "fallback", "items": [{"movie_id": "m2", "confidence": 0.5}]},
        ]
    }
    mapping = ResponseMapping(
        items_path="$.buckets[?(@.name=='main')].items[*]",
        item_id_field="movie_id",
        score_field="confidence",
    )
    items = extract_items(payload, mapping)
    assert len(items) == 1
    assert items[0].item_id == "m1"
    assert items[0].score == pytest.approx(0.9)


def test_extract_items_dot_path_unchanged_for_non_dollar_paths() -> None:
    payload = {"predictions": [{"movie_id": "m1", "confidence": 0.91}]}
    mapping = ResponseMapping(
        items_path="predictions",
        item_id_field="movie_id",
        score_field="confidence",
    )
    items = extract_items(payload, mapping)
    assert items[0].item_id == "m1"


def test_extract_items_jsonpath_parse_error_surfaces() -> None:
    mapping = ResponseMapping(
        items_path="$.items[?(@.name!='x')]",
        item_id_field="id",
        score_field="s",
    )
    with pytest.raises(ResponseExtractionError, match="JSONPath"):
        extract_items({"items": []}, mapping)


def test_resolve_dot_path_missing_segment_raises_with_path() -> None:
    with pytest.raises(ResponseExtractionError, match="items.5"):
        resolve_dot_path({"items": [{"id": "x"}]}, "items.5.id")


def test_http_schema_mapped_config_validates_template_references() -> None:
    with pytest.raises(ValueError, match="unknown_field"):
        HttpSchemaMappedDriverConfig.from_dict(
            {
                "base_url": "http://x",
                "predict": {
                    "method": "POST",
                    "path": "/predict",
                    "body": {"x": "${unknown_field}"},
                },
            }
        )


def test_schema_mapped_driver_calls_endpoint_and_extracts_items() -> None:
    captured = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            captured["body"] = json.loads(self.rfile.read(length).decode("utf-8"))
            captured["path"] = self.path
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "predictions": [
                            {"movie_id": "m1", "confidence": 0.91, "title": "Heat"},
                            {"movie_id": "m2", "confidence": 0.85, "title": "Drive"},
                        ]
                    }
                ).encode("utf-8")
            )

        def log_message(self, *args):
            pass

    server, base_url = _start_mock_server(Handler)
    try:
        driver = HttpSchemaMappedRecommenderDriver(
            HttpSchemaMappedDriverConfig.from_dict(
                {
                    "base_url": base_url,
                    "predict": {
                        "method": "POST",
                        "path": "/v1/predict",
                        "body": {
                            "user_id": "${agent_id}",
                            "history": "${history_item_ids}",
                            "n": 10,
                        },
                        "response": {
                            "items_path": "predictions",
                            "item_id_field": "movie_id",
                            "score_field": "confidence",
                            "title_field": "title",
                        },
                    },
                }
            )
        )
        slate = driver.get_slate(_dummy_state(), _dummy_observation(), _dummy_scenario())

        assert captured["path"] == "/v1/predict"
        assert captured["body"]["user_id"] == "agent-1"
        assert slate.items[0].item_id == "m1"
    finally:
        server.shutdown()


def test_schema_mapped_driver_runs_through_audit(tmp_path: Path) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            self.rfile.read(length)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "predictions": [
                            {"movie_id": "m1", "confidence": 0.91, "title": "Heat"},
                            {"movie_id": "m2", "confidence": 0.85, "title": "Drive"},
                            {"movie_id": "m3", "confidence": 0.80, "title": "Collateral"},
                        ]
                    }
                ).encode("utf-8")
            )

        def log_message(self, *args):
            pass

    server, base_url = _start_mock_server(Handler)
    try:
        run_result = execute_domain_audit(
            domain_name="recommender",
            seed=11,
            output_dir=str(tmp_path / "schema-mapped-audit"),
            scenario_names=("returning-user-home-feed",),
            driver_kind="http_schema_mapped",
            driver_config={
                "base_url": base_url,
                "predict": {
                    "method": "POST",
                    "path": "/v1/predict",
                    "body": {
                        "user_id": "${agent_id}",
                        "history": "${history_item_ids}",
                        "n": 5,
                    },
                    "response": {
                        "items_path": "predictions",
                        "item_id_field": "movie_id",
                        "score_field": "confidence",
                        "title_field": "title",
                    },
                },
            },
        )
        paths = write_run_artifacts(run_result)
        manifest_path = write_run_manifest(
            run_result,
            artifact_paths=paths,
            workflow_type="audit",
        )
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))

        assert manifest["service"]["target_driver_kind"] == "http_schema_mapped"
        assert manifest["service"]["target_driver_config"]["base_url"] == base_url
        assert run_result.trace_scores
    finally:
        server.shutdown()


def _start_mock_server(handler_cls):
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}"


def _dummy_state() -> AgentState:
    return AgentState(
        agent_id="agent-1",
        archetype_label="archetype",
        step_index=0,
        click_threshold=0.5,
        preferred_genres=("action",),
        popularity_preference=0.5,
        novelty_preference=0.4,
        repetition_tolerance=0.6,
        sparse_history_confidence=0.5,
        abandonment_sensitivity=0.2,
        engagement_baseline=0.5,
        quality_sensitivity=0.6,
        repeat_exposure_penalty=0.1,
        novelty_fatigue=0.1,
        frustration_recovery=0.3,
        history_reliance=0.4,
        skip_tolerance=1,
        abandonment_threshold=0.85,
        patience_remaining=2,
        last_action="start",
        history_item_ids=(),
    )


def _dummy_observation() -> Observation:
    return Observation(
        session_id="s",
        step_index=0,
        max_steps=2,
        available_actions=("click", "skip"),
        scenario_context=ScenarioContext(
            scenario_name="scenario-1",
            history_depth=0,
            history_item_ids=(),
            description="",
            scenario_id="scenario-1",
            runtime_profile="",
            context_hint="",
        ),
    )


def _dummy_scenario() -> ScenarioConfig:
    return ScenarioConfig(
        name="scenario-1",
        max_steps=2,
        allowed_actions=("click", "skip"),
        history_depth=0,
        description="",
        scenario_id="scenario-1",
        test_goal="",
        runtime_profile="",
        context_hint="",
    )
