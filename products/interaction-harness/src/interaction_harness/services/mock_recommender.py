"""Local mock recommender service used to prove the adapter boundary."""

from __future__ import annotations

import json
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from ..catalog import CATALOG


def build_recommendation(payload: dict) -> dict:
    """Produce a deterministic recommendation slate from the request payload."""
    preferred_genres = tuple(payload["preferred_genres"])
    history_ids = set(payload["history_item_ids"])
    recent_exposure_ids = set(payload["recent_exposure_ids"])
    scenario_name = payload["scenario_name"]
    step_index = payload["step_index"]

    ranked_items = []
    for item in CATALOG:
        genre_match = 1.0 if item.genre in preferred_genres else 0.15
        popularity_weight = 0.48 if scenario_name == "sparse-history-home-feed" else 0.28
        novelty_weight = 0.07 if scenario_name == "sparse-history-home-feed" else 0.18
        history_bonus = 0.08 if item.item_id in history_ids else 0.0
        exposure_penalty = 0.12 if item.item_id in recent_exposure_ids else 0.0
        score = (
            (popularity_weight * item.popularity)
            + (0.32 * genre_match)
            + (novelty_weight * item.novelty)
            + (0.25 * item.quality)
            + history_bonus
            - exposure_penalty
            - (0.03 * step_index)
        )
        ranked_items.append((score, item))

    ranked_items.sort(key=lambda entry: entry[0], reverse=True)
    items = []
    for rank, (score, item) in enumerate(ranked_items[:5], start=1):
        items.append(
            {
                "item_id": item.item_id,
                "title": item.title,
                "genre": item.genre,
                "score": round(score, 6),
                "rank": rank,
                "popularity": item.popularity,
                "novelty": item.novelty,
            }
        )
    return {"request_id": payload["request_id"], "items": items}


class _MockRecommenderHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            body = json.dumps({"status": "ok", "service_kind": "mock"}).encode("utf-8")
        elif self.path == "/metadata":
            body = json.dumps(
                {
                    "service_kind": "mock",
                    "backend_name": "MockRecommenderFixture",
                    "artifact_id": "mock-catalog-v1",
                    "dataset": "in-package-mock-catalog",
                    "item_count": len(CATALOG),
                }
            ).encode("utf-8")
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/recommendations":
            self.send_error(404)
            return
        content_length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        response_payload = build_recommendation(payload)
        body = json.dumps(response_payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        del format, args


@contextmanager
def run_mock_recommender_service():
    """Start a tiny local HTTP service and yield its base URL."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockRecommenderHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=2.0)
        server.server_close()
