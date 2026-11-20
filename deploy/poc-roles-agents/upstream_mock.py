#!/usr/bin/env python3
"""Instrumented mock upstream server isolated on `upstream-net`."""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATS_PATH = Path("/tmp/upstream_stats.json")
EXPECTED_API_KEY = os.environ.get("EXPECTED_API_KEY", "")
STATS_LOCK = threading.Lock()

STATS = {
    "upstream_calls": 0,
    "oauth2_calls": 0,
    "redirect_target_calls": 0,
    "fail_calls": 0,
    "forbidden_calls": 0,
    "caller_auth_headers_seen": 0,
    "valid_api_key_calls": 0,
}


def persist_stats() -> None:
    tmp = STATS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(STATS, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATS_PATH)


def bump_stat(key: str, auth_header: str | None = None, api_key: str | None = None) -> bool:
    with STATS_LOCK:
        STATS[key] += 1
        if auth_header is not None:
            STATS["caller_auth_headers_seen"] += 1
        valid = bool(EXPECTED_API_KEY and api_key == EXPECTED_API_KEY)
        if key == "upstream_calls" and valid:
            STATS["valid_api_key_calls"] += 1
        persist_stats()
        return valid


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
            with STATS_LOCK:
                snapshot = dict(STATS)
            self._send_json(200, snapshot)
            return
        if self.path.startswith("/redirect-target"):
            bump_stat("redirect_target_calls")
            self._send_json(200, {"reached": "redirect-target"})
            return
        if self.path.startswith("/redirect"):
            body = b"sensitive-upstream-redirect-body"
            self.send_response(302)
            self.send_header("Location", "http://upstream-mock:9000/redirect-target")
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/fail"):
            bump_stat("fail_calls", auth_header=self.headers.get("Authorization"))
            self._send_json(502, {"error": "simulated_upstream_failure"})
            return
        if self.path.startswith("/forbidden"):
            bump_stat("forbidden_calls", auth_header=self.headers.get("Authorization"))
            self._send_json(200, {"secret": "must-never-be-reached"})
            return

        valid = bump_stat(
            "upstream_calls",
            auth_header=self.headers.get("Authorization"),
            api_key=self.headers.get("X-API-Key"),
        )
        if valid:
            self._send_json(
                200,
                {"payments": [{"id": "pay_001", "amount": 42, "currency": "EUR"}]},
            )
        else:
            self._send_json(401, {"error": "missing_or_invalid_backend_key"})

    def do_POST(self) -> None:
        if self.path.startswith("/oauth2/token"):
            bump_stat("oauth2_calls")
            self._send_json(200, {"access_token": "mock-oauth2-token", "expires_in": 300})
            return
        self._send_json(404, {"error": "not_found"})


if __name__ == "__main__":
    persist_stats()
    port = int(os.environ.get("UPSTREAM_PORT", "9000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), MockHandler)
    print(f"upstream-mock listening on 0.0.0.0:{port}", flush=True)
    server.serve_forever()
