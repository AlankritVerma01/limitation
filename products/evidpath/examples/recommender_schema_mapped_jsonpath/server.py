"""Tiny HTTP server returning a multi-bucket recsys response."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

_PAYLOAD = {
    "buckets": [
        {
            "name": "main",
            "items": [
                {"movie_id": "m1", "confidence": 0.91, "title": "Heat"},
                {"movie_id": "m2", "confidence": 0.85, "title": "Drive"},
                {"movie_id": "m3", "confidence": 0.71, "title": "Collateral"},
            ],
        },
        {
            "name": "fallback",
            "items": [
                {"movie_id": "m9", "confidence": 0.20, "title": "Cats"},
            ],
        },
    ]
}


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        encoded = json.dumps(_PAYLOAD).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args, **_kwargs):
        pass


def main() -> None:
    """Run the example HTTP server."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8073)
    args = parser.parse_args()
    server = HTTPServer(("127.0.0.1", args.port), _Handler)
    print(f"serving on http://127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
