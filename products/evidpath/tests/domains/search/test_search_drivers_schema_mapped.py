"""Tests for the schema-mapped HTTP search driver."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from evidpath.domains.search.drivers import (
    HttpSchemaMappedSearchDriver,
    HttpSchemaMappedSearchDriverConfig,
    SearchResponseMapping,
)
from evidpath.domains.search.drivers._extraction import (
    extract_results,
    resolve_dot_path,
)
from evidpath.domains.search.drivers._templating import substitute
from evidpath.schema import AgentState, Observation, ScenarioConfig, ScenarioContext


def test_search_schema_mapped_config_validates_template_references() -> None:
    with pytest.raises(ValueError, match="unknown_field"):
        HttpSchemaMappedSearchDriverConfig.from_dict(
            {
                "base_url": "http://x",
                "search": {
                    "method": "POST",
                    "path": "/search",
                    "body": {"x": "${unknown_field}"},
                },
            }
        )


def test_search_schema_mapping_extracts_results() -> None:
    payload = {
        "hits": [
            {
                "id": "r1",
                "headline": "Weather Alerts",
                "summary": "Current warnings.",
                "link": "https://example.com/weather",
                "kind": "news",
                "score": 0.92,
                "freshness": 0.97,
            }
        ]
    }
    mapping = SearchResponseMapping(
        results_path="hits",
        result_id_field="id",
        title_field="headline",
        snippet_field="summary",
        url_field="link",
        type_field="kind",
        relevance_score_field="score",
        freshness_score_field="freshness",
    )

    assert resolve_dot_path(payload, "hits.0.id") == "r1"
    assert extract_results(payload, mapping)[0].freshness_score == 0.97


def test_search_schema_mapped_driver_calls_endpoint_and_extracts_results() -> None:
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
                        "hits": [
                            {
                                "id": "r1",
                                "headline": "Weather Alerts",
                                "summary": "Current warnings.",
                                "link": "https://example.com/weather",
                                "kind": "news",
                                "score": 0.92,
                            }
                        ]
                    }
                ).encode("utf-8")
            )

        def log_message(self, *args):
            pass

    server, base_url = _start_mock_server(Handler)
    try:
        driver = HttpSchemaMappedSearchDriver(
            HttpSchemaMappedSearchDriverConfig.from_dict(
                {
                    "base_url": base_url,
                    "search": {
                        "method": "POST",
                        "path": "/v1/search",
                        "body": {"q": "${query}", "user": "${user_id}", "n": 10},
                        "response": {
                            "results_path": "hits",
                            "result_id_field": "id",
                            "title_field": "headline",
                            "snippet_field": "summary",
                            "url_field": "link",
                            "type_field": "kind",
                            "relevance_score_field": "score",
                        },
                    },
                }
            )
        )
        ranked_list = driver.get_ranked_list(
            _dummy_state(),
            _dummy_observation(),
            _dummy_scenario(),
        )

        assert captured["path"] == "/v1/search"
        assert captured["body"] == {"q": "weather alerts", "user": "agent-1", "n": 10}
        assert ranked_list.items[0].item_id == "r1"
    finally:
        server.shutdown()


def test_search_schema_mapped_driver_percent_encodes_get_query_path() -> None:
    captured = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            captured["path"] = self.path
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "hits": [
                            {
                                "id": "r1",
                                "headline": "Weather Alerts",
                                "summary": "Current warnings.",
                                "link": "https://example.com/weather",
                                "kind": "news",
                                "score": 0.92,
                            }
                        ]
                    }
                ).encode("utf-8")
            )

        def log_message(self, *args):
            pass

    server, base_url = _start_mock_server(Handler)
    try:
        driver = HttpSchemaMappedSearchDriver(
            HttpSchemaMappedSearchDriverConfig.from_dict(
                {
                    "base_url": base_url,
                    "search": {
                        "method": "GET",
                        "path": "/v1/search?q=${query}",
                        "response": {
                            "results_path": "hits",
                            "result_id_field": "id",
                            "title_field": "headline",
                            "snippet_field": "summary",
                            "url_field": "link",
                            "type_field": "kind",
                            "relevance_score_field": "score",
                        },
                    },
                }
            )
        )

        ranked_list = driver.get_ranked_list(
            _dummy_state(),
            _dummy_observation(),
            _dummy_scenario(),
        )

        assert captured["path"] == "/v1/search?q=weather%20alerts"
        assert ranked_list.items[0].item_id == "r1"
    finally:
        server.shutdown()


def test_search_template_substitute_preserves_pure_marker_type() -> None:
    assert substitute({"query": "${query}"}, {"query": "weather alerts"}) == {
        "query": "weather alerts"
    }


def _start_mock_server(handler_cls):
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def _dummy_state() -> AgentState:
    return AgentState(
        agent_id="agent-1",
        archetype_label="archetype",
        step_index=0,
        click_threshold=0.5,
        preferred_genres=("news",),
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
        session_id="session-1",
        step_index=0,
        max_steps=2,
        available_actions=("click", "skip"),
        scenario_context=ScenarioContext(
            scenario_name="search-scenario",
            history_depth=0,
            history_item_ids=(),
            description="",
            scenario_id="search-scenario",
            runtime_profile="",
            context_hint="weather alerts",
        ),
    )


def _dummy_scenario() -> ScenarioConfig:
    return ScenarioConfig(
        name="search-scenario",
        max_steps=2,
        allowed_actions=("click", "skip"),
        history_depth=0,
        description="",
        scenario_id="search-scenario",
        test_goal="",
        runtime_profile="",
        context_hint="",
    )
