#!/usr/bin/env python3
"""Instrumented mock upstream server isolated on `upstream-net`."""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

STATS_PATH = Path("/tmp/upstream_stats.json")
EXPECTED_API_KEY = os.environ.get("EXPECTED_API_KEY", "")

STATS = {
    "upstream_calls": 0,
    "oauth2_calls": 0,
    "redirect_target_calls": 0,
    "caller_auth_headers_seen": 0,
    "valid_api_key_calls": 0,
}


def persist_stats() -> None:
    tmp = STATS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(STATS, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATS_PATH)


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/_health":
            self._send_json(200, {"status": "ok"})
            return
        if self.path == "/_stats":
            self._send_json(200, STATS)
            return
        if self.path.startswith("/redirect-target"):
            STATS["redirect_target_calls"] += 1
            persist_stats()
            self._send_json(200, {"reached": "redirect-target"})
            return

        STATS["upstream_calls"] += 1
        if self.headers.get("Authorization") is not None:
            STATS["caller_auth_headers_seen"] += 1
        if EXPECTED_API_KEY and self.headers.get("X-API-Key") == EXPECTED_API_KEY:
            STATS["valid_api_key_calls"] += 1
            persist_stats()
            self._send_json(
                200,
                {"payments": [{"id": "pay_001", "amount": 42, "currency": "EUR"}]},
            )
        else:
            persist_stats()
            self._send_json(401, {"error": "missing_or_invalid_backend_key"})

    def do_POST(self) -> None:
        if self.path.startswith("/oauth2/token"):
            STATS["oauth2_calls"] += 1
            persist_stats()
            self._send_json(200, {"access_token": "mock-oauth2-token", "expires_in": 300})
            return
        self._send_json(404, {"error": "not_found"})


if __name__ == "__main__":
    persist_stats()
    port = int(os.environ.get("UPSTREAM_PORT", "9000"))
    server = HTTPServer(("0.0.0.0", port), MockHandler)
    print(f"upstream-mock listening on 0.0.0.0:{port}", flush=True)
    server.serve_forever()
