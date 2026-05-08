"""Slow twin-run determinism test for schema-mapped transforms."""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import ModuleType

from evidpath.artifacts._determinism import compute_deterministic_payload_hash
from evidpath.audit import execute_domain_audit, write_run_artifacts


def test_schema_mapped_transform_audit_is_deterministic_across_twin_runs(
    tmp_path: Path,
) -> None:
    transform_module = _install_transform_module()
    server = HTTPServer(("127.0.0.1", 0), _DeterministicHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        driver_config = {
            "base_url": f"http://127.0.0.1:{server.server_port}",
            "predict": {
                "method": "POST",
                "path": "/v1/predict",
                "headers": {},
                "body": {},
            },
            "transform_request_module": transform_module,
            "transform_response_module": transform_module,
        }
        result_one = execute_domain_audit(
            domain_name="recommender",
            seed=0,
            output_dir=str(tmp_path / "run-1"),
            scenario_names=("returning-user-home-feed",),
            driver_kind="http_schema_mapped",
            driver_config=driver_config,
        )
        result_two = execute_domain_audit(
            domain_name="recommender",
            seed=0,
            output_dir=str(tmp_path / "run-2"),
            scenario_names=("returning-user-home-feed",),
            driver_kind="http_schema_mapped",
            driver_config=driver_config,
        )
        paths_one = write_run_artifacts(result_one)
        paths_two = write_run_artifacts(result_two)
        hash_one = compute_deterministic_payload_hash(
            results_path=Path(paths_one["results_path"]),
            traces_path=Path(paths_one["traces_path"]),
        )
        hash_two = compute_deterministic_payload_hash(
            results_path=Path(paths_two["results_path"]),
            traces_path=Path(paths_two["traces_path"]),
        )
        assert hash_one == hash_two
    finally:
        server.shutdown()
        sys.modules.pop(transform_module, None)


def _install_transform_module() -> str:
    name = "evidpath_test_slow_transform"
    module = ModuleType(name)

    def transform_request(adapter_request):
        return {
            "events": [
                {"type": "view", "item": item_id, "step": index}
                for index, item_id in enumerate(adapter_request.history_item_ids)
            ],
            "user_id": adapter_request.agent_id,
        }

    def transform_response(payload, adapter_request):
        from evidpath.schema import AdapterResponse, SlateItem

        items = tuple(
            SlateItem(
                item_id=str(entry["movie_id"]),
                title="",
                genre="",
                score=float(entry["confidence"]),
                rank=index + 1,
                popularity=0.0,
                novelty=0.0,
            )
            for index, entry in enumerate(payload["predictions"])
        )
        return AdapterResponse(request_id=adapter_request.request_id, items=items)

    module.transform_request = transform_request
    module.transform_response = transform_response
    sys.modules[name] = module
    return name


class _DeterministicHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        payload = {
            "predictions": [
                {"movie_id": f"m{i}", "confidence": 1.0 - 0.1 * i}
                for i in range(5)
            ]
        }
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args, **_kwargs):
        pass
