"""Server that expects an event-derived request shape."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        if "events" not in body:
            self.send_response(400)
            self.end_headers()
            return
        ranked = [
            {"movie_id": f"m{i}", "confidence": 1.0 - 0.05 * i}
            for i in range(5)
        ]
        encoded = json.dumps({"predictions": ranked}).encode("utf-8")
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
    parser.add_argument("--port", type=int, default=8074)
    args = parser.parse_args()
    server = HTTPServer(("127.0.0.1", args.port), _Handler)
    print(f"serving on http://127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
