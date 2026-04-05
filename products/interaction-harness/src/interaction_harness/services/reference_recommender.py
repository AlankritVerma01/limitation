"""Reference recommender service backed by offline-built artifacts."""

from __future__ import annotations

import json
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from ..schema import AdapterRequest
from .reference_artifacts import ensure_reference_artifacts
from .reference_backend import ReferenceRecommendationBackend


def _handler_for_backend(backend: ReferenceRecommendationBackend):
    class _ReferenceRecommenderHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._write_json(200, {"status": "ok", "service_kind": "reference"})
                return
            if self.path == "/metadata":
                self._write_json(200, backend.metadata())
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/recommendations":
                self.send_error(404)
                return
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0:
                self._write_json(400, {"error": "empty_request"})
                return
            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                adapter_request = AdapterRequest(
                    request_id=str(payload["request_id"]),
                    agent_id=str(payload["agent_id"]),
                    scenario_name=str(payload["scenario_name"]),
                    scenario_profile=str(payload.get("scenario_profile", payload["scenario_name"])),
                    step_index=int(payload["step_index"]),
                    history_depth=int(payload["history_depth"]),
                    history_item_ids=tuple(payload["history_item_ids"]),
                    recent_exposure_ids=tuple(payload["recent_exposure_ids"]),
                    preferred_genres=tuple(payload["preferred_genres"]),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                self._write_json(400, {"error": "invalid_request"})
                return
            self._write_json(200, backend.get_recommendations(adapter_request))

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            del format, args

        def _write_json(self, status_code: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return _ReferenceRecommenderHandler


@contextmanager
def run_reference_recommender_service(artifact_dir: str | None = None):
    """Start the artifact-backed reference service and yield its base URL."""
    artifact_path = ensure_reference_artifacts(artifact_dir)
    backend = ReferenceRecommendationBackend(artifact_path.parent)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        _handler_for_backend(backend),
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", backend.metadata()
    finally:
        server.shutdown()
        thread.join(timeout=2.0)
        server.server_close()
