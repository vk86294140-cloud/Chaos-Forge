"""A tiny demo service to run experiments against.

Run it with:  python examples/demo_target.py  (listens on :8000)
Then point an experiment's `target` at http://localhost:8000.

Uses only the standard library so the examples work without extra installs.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:
        pass

    def do_GET(self) -> None:
        if self.path.startswith("/health"):
            body = json.dumps({"status": "ok"}).encode()
            self.send_response(200)
        else:
            body = json.dumps({"message": "hello from demo service"}).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("demo target listening on http://127.0.0.1:8000 (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
