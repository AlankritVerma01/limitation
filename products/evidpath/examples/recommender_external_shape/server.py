"""Mock recommender with a non-native request and response shape."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from evidpath.domains.recommender import CATALOG


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/v1/predict":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers["Content-Length"])
        request_body = json.loads(self.rfile.read(length).decode("utf-8"))
        limit = int(request_body.get("n", 5))
        sorted_items = sorted(CATALOG, key=lambda item: item.popularity, reverse=True)[
            :limit
        ]
        self._json(
            {
                "predictions": [
                    {
                        "movie_id": item.item_id,
                        "confidence": 0.9 - 0.05 * index,
                        "title": item.title,
                    }
                    for index, item in enumerate(sorted_items)
                ]
            }
        )

    def do_GET(self):
        if self.path == "/healthz":
            self._json({"status": "ok"})
        elif self.path == "/v1/info":
            self._json({"model": {"name": "popularity"}, "version": "v1"})
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass

    def _json(self, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(host: str = "127.0.0.1", port: int = 8071) -> None:
    """Serve the external-shape example."""
    HTTPServer((host, port), _Handler).serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8071)
    args = parser.parse_args()
    serve(host=args.host, port=args.port)
