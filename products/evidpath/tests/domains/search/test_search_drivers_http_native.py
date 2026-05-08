"""Tests for the native HTTP search driver."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from evidpath.domains.search.drivers import (
    HttpNativeSearchDriver,
    HttpNativeSearchDriverConfig,
)
from evidpath.schema import AgentState, Observation, ScenarioConfig, ScenarioContext


def test_http_native_search_driver_calls_search_endpoint() -> None:
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
                        "request_id": captured["body"]["request_id"],
                        "results": [
                            {
                                "result_id": "r1",
                                "title": "Weather Alerts",
                                "snippet": "Current warnings.",
                                "url": "https://example.com/weather",
                                "result_type": "news",
                                "relevance_score": 0.93,
                                "rank": 1,
                                "freshness_score": 0.97,
                            }
                        ],
                    }
                ).encode("utf-8")
            )

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "model_id": "native"}).encode("utf-8"))

        def log_message(self, *args):
            pass

    server, base_url = _start_mock_server(Handler)
    try:
        driver = HttpNativeSearchDriver(
            HttpNativeSearchDriverConfig(base_url=base_url, timeout_seconds=2.0)
        )
        ranked_list = driver.get_ranked_list(
            _dummy_state(),
            _dummy_observation(),
            _dummy_scenario(),
        )

        assert captured["path"] == "/search"
        assert captured["body"]["query"] == "weather alerts"
        assert ranked_list.items[0].item_type == "news"
        assert driver.check_health()["status"] == "ok"
    finally:
        server.shutdown()


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
