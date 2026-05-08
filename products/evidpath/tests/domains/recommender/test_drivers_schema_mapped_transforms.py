"""Tests for the schema-mapped driver's transform escape hatch."""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import ModuleType

import pytest
from evidpath.domains.recommender.drivers import (
    EndpointMapping,
    HttpSchemaMappedDriverConfig,
    HttpSchemaMappedRecommenderDriver,
    ResponseMapping,
)
from evidpath.domains.recommender.drivers._transform import (
    TransformLoadError,
    load_request_transform,
    load_response_transform,
)
from evidpath.schema import (
    AdapterRequest,
    AdapterResponse,
    AgentState,
    Observation,
    ScenarioConfig,
    ScenarioContext,
    SlateItem,
)


def _make_request() -> AdapterRequest:
    return AdapterRequest(
        request_id="r1",
        agent_id="u1",
        scenario_name="s",
        scenario_profile="p",
        step_index=0,
        history_depth=0,
        history_item_ids=(),
        recent_exposure_ids=(),
        preferred_genres=(),
    )


def _install_module(name: str, module: ModuleType) -> None:
    sys.modules[name] = module


def test_load_request_transform_returns_callable() -> None:
    module = ModuleType("evidpath_test_transform_a")

    def transform_request(adapter_request):
        return {"agent_id": adapter_request.agent_id}

    module.transform_request = transform_request
    _install_module("evidpath_test_transform_a", module)
    try:
        fn = load_request_transform("evidpath_test_transform_a")
        assert fn(_make_request()) == {"agent_id": "u1"}
    finally:
        sys.modules.pop("evidpath_test_transform_a", None)


def test_load_response_transform_returns_callable() -> None:
    module = ModuleType("evidpath_test_transform_b")

    def transform_response(payload, adapter_request):
        return AdapterResponse(
            request_id=adapter_request.request_id,
            items=(
                SlateItem(
                    item_id=str(payload["x"]),
                    title="",
                    genre="",
                    score=1.0,
                    rank=1,
                    popularity=0.0,
                    novelty=0.0,
                ),
            ),
        )

    module.transform_response = transform_response
    _install_module("evidpath_test_transform_b", module)
    try:
        fn = load_response_transform("evidpath_test_transform_b")
        result = fn({"x": 7}, _make_request())
        assert result.items[0].item_id == "7"
    finally:
        sys.modules.pop("evidpath_test_transform_b", None)


def test_load_request_transform_missing_module_raises() -> None:
    with pytest.raises(TransformLoadError, match="not be imported"):
        load_request_transform("evidpath_test_transform_does_not_exist")


def test_load_request_transform_missing_function_raises() -> None:
    module = ModuleType("evidpath_test_transform_c")
    _install_module("evidpath_test_transform_c", module)
    try:
        with pytest.raises(TransformLoadError, match="transform_request"):
            load_request_transform("evidpath_test_transform_c")
    finally:
        sys.modules.pop("evidpath_test_transform_c", None)


def test_load_response_transform_missing_function_raises() -> None:
    module = ModuleType("evidpath_test_transform_d")
    _install_module("evidpath_test_transform_d", module)
    try:
        with pytest.raises(TransformLoadError, match="transform_response"):
            load_response_transform("evidpath_test_transform_d")
    finally:
        sys.modules.pop("evidpath_test_transform_d", None)


def test_config_from_dict_picks_up_transform_module_fields() -> None:
    config = HttpSchemaMappedDriverConfig.from_dict(
        {
            "base_url": "http://localhost:9999",
            "predict": {
                "method": "POST",
                "path": "/v1/predict",
                "headers": {},
                "body": {},
            },
            "transform_request_module": "evidpath_test_transform_e",
            "transform_response_module": "evidpath_test_transform_e",
        }
    )
    assert config.transform_request_module == "evidpath_test_transform_e"
    assert config.transform_response_module == "evidpath_test_transform_e"


def test_config_skips_field_validation_when_request_transform_set() -> None:
    config = HttpSchemaMappedDriverConfig.from_dict(
        {
            "base_url": "http://localhost:9999",
            "predict": {
                "method": "POST",
                "path": "/v1/predict",
                "headers": {},
                "body": {"unknown_field": "${not_a_real_adapter_field}"},
            },
            "transform_request_module": "evidpath_test_transform_e",
        }
    )
    assert config.transform_request_module == "evidpath_test_transform_e"


def test_driver_uses_request_transform_when_configured() -> None:
    module = ModuleType("evidpath_test_transform_f")

    def transform_request(adapter_request):
        return {
            "events": [
                {"type": "view", "item": item_id}
                for item_id in adapter_request.history_item_ids
            ]
        }

    module.transform_request = transform_request
    _install_module("evidpath_test_transform_f", module)
    handler_cls = type("H", (_StubHandler,), {"captured_body": None})
    server = _serve(handler_cls)
    try:
        port = server.server_address[1]
        config = HttpSchemaMappedDriverConfig(
            base_url=f"http://127.0.0.1:{port}",
            timeout_seconds=1.0,
            predict=EndpointMapping(
                method="POST",
                path="/v1/predict",
                headers={},
                body=None,
                response=ResponseMapping(
                    items_path="predictions",
                    item_id_field="movie_id",
                    score_field="confidence",
                ),
            ),
            transform_request_module="evidpath_test_transform_f",
        )
        driver = HttpSchemaMappedRecommenderDriver(config)
        state, obs, cfg = _make_state()
        slate = driver.get_slate(state, obs, cfg)
        assert handler_cls.captured_body is not None
        body = json.loads(handler_cls.captured_body)
        assert body == {
            "events": [
                {"type": "view", "item": "a"},
                {"type": "view", "item": "b"},
            ]
        }
        assert slate.items[0].item_id == "m1"
    finally:
        server.shutdown()
        sys.modules.pop("evidpath_test_transform_f", None)


def test_driver_uses_response_transform_when_configured() -> None:
    module = ModuleType("evidpath_test_transform_g")

    def transform_response(payload, adapter_request):
        return AdapterResponse(
            request_id=adapter_request.request_id,
            items=(
                SlateItem(
                    item_id="custom",
                    title="",
                    genre="",
                    score=0.42,
                    rank=1,
                    popularity=0.0,
                    novelty=0.0,
                ),
            ),
        )

    module.transform_response = transform_response
    _install_module("evidpath_test_transform_g", module)
    server = _serve(_StubHandler)
    try:
        port = server.server_address[1]
        config = HttpSchemaMappedDriverConfig(
            base_url=f"http://127.0.0.1:{port}",
            timeout_seconds=1.0,
            predict=EndpointMapping(
                method="POST",
                path="/v1/predict",
                headers={},
                body={"agent_id": "${agent_id}"},
                response=None,
            ),
            transform_response_module="evidpath_test_transform_g",
        )
        driver = HttpSchemaMappedRecommenderDriver(config)
        state, obs, cfg = _make_state()
        slate = driver.get_slate(state, obs, cfg)
        assert slate.items[0].item_id == "custom"
        assert slate.items[0].score == pytest.approx(0.42)
    finally:
        server.shutdown()
        sys.modules.pop("evidpath_test_transform_g", None)


class _StubHandler(BaseHTTPRequestHandler):
    captured_body = None

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        type(self).captured_body = body
        payload = {"predictions": [{"movie_id": "m1", "confidence": 0.9}]}
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args, **_kwargs):
        pass


def _serve(handler_cls):
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _make_state() -> tuple[AgentState, Observation, ScenarioConfig]:
    state = AgentState(
        agent_id="u1",
        archetype_label="archetype",
        step_index=0,
        click_threshold=0.5,
        preferred_genres=(),
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
        history_item_ids=("a", "b"),
        recent_exposure_ids=(),
    )
    context = ScenarioContext(
        scenario_name="s1",
        history_depth=2,
        history_item_ids=("a", "b"),
        description="",
        scenario_id="s1",
        runtime_profile="p",
    )
    obs = Observation(
        session_id="s",
        step_index=0,
        max_steps=2,
        available_actions=("click", "skip"),
        scenario_context=context,
    )
    cfg = ScenarioConfig(
        name="s1",
        max_steps=2,
        allowed_actions=("click", "skip"),
        history_depth=2,
        description="",
        scenario_id="s1",
        runtime_profile="p",
    )
    return state, obs, cfg
