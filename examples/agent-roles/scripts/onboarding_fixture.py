#!/usr/bin/env python3
"""Stdlib-only mock servers (MCP Streamable HTTP and Vault KV v2) for local onboarding smoke fixtures."""

from __future__ import annotations

import argparse
from collections import OrderedDict
import copy
from datetime import datetime, timezone
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import secrets
import ssl
import sys
import threading
from urllib.parse import parse_qs, urlsplit
import uuid

MCP_PROTOCOL_VERSION = "2025-03-26"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_MCP_PORT = 9100
DEFAULT_VAULT_PORT = 8200
DEFAULT_TENANT = "acme"
DEFAULT_VAULT_ENV = "fixture-local"
DEFAULT_MAX_SESSIONS = 64
DEFAULT_MAX_SECRETS = 256
DEFAULT_MCP_BEARER_ENV = "ONBOARDING_MCP_BEARER_TOKEN"
DEFAULT_VAULT_OPERATOR_ENV = "ONBOARDING_VAULT_OPERATOR_TOKEN"
DEFAULT_VAULT_GATEWAY_ENV = "ONBOARDING_VAULT_GATEWAY_TOKEN"
MAX_BODY_BYTES = 65536

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
CUSTOMER_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

MCP_TOOL_DEFINITION = {
    "name": "account_lookup",
    "description": "Look up a synthetic customer account by customer_id",
    "inputSchema": {
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
            }
        },
        "required": ["customer_id"],
    },
    "annotations": {
        "readOnlyHint": True,
    },
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def is_valid_jsonrpc_id(value: object) -> bool:
    return isinstance(value, (str, int)) and not isinstance(value, bool)


def is_valid_vault_secret_data(data: object) -> bool:
    """Strictly require data: {allowed_origin: string, headers: {string: string}}."""
    if not isinstance(data, dict) or set(data.keys()) != {"allowed_origin", "headers"}:
        return False
    origin = data["allowed_origin"]
    if not isinstance(origin, str) or not origin or len(origin) > 256:
        return False
    if any(ch.isspace() for ch in origin):
        return False
    parsed = urlsplit(origin)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        return False
    headers = data["headers"]
    if not isinstance(headers, dict) or not headers:
        return False
    for key, val in headers.items():
        if not isinstance(key, str) or not key or any(c in key for c in ("\r", "\n")):
            return False
        if not isinstance(val, str) or not val or any(c in val for c in ("\r", "\n")):
            return False
    return True


def read_required_env(env_name: str) -> str:
    value = os.environ.get(env_name, "")
    if not value:
        print(f"error: required environment variable is unset or empty: {env_name}", file=sys.stderr)
        sys.exit(2)
    return value


class _FixtureHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class _BaseJsonHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        # Suppress default request logging to avoid leaking paths, headers, or tokens.
        return

    def _send_json(
        self,
        code: int,
        payload: dict,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for key, val in extra_headers.items():
                self.send_header(key, val)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_empty(self, code: int) -> None:
        self.send_response(code)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _read_json_object(self) -> tuple[dict | None, str | None]:
        raw_len = self.headers.get("Content-Length")
        if raw_len is None:
            return None, "missing_content_length"
        try:
            length = int(raw_len)
        except ValueError:
            return None, "invalid_content_length"
        if not 1 <= length <= MAX_BODY_BYTES:
            return None, "invalid_content_length"
        raw = self.rfile.read(length)
        if len(raw) != length:
            return None, "truncated_body"
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None, "invalid_json"
        if not isinstance(parsed, dict):
            return None, "invalid_json_object"
        return parsed, None


class McpState:
    def __init__(
        self,
        bearer_token: str,
        *,
        tenant: str = DEFAULT_TENANT,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
    ) -> None:
        if not bearer_token:
            raise ValueError("bearer_token must be non-empty")
        if max_sessions < 1:
            raise ValueError("max_sessions must be >= 1")
        self._bearer_token = bearer_token
        self.tenant = tenant
        self._max_sessions = max_sessions
        self._lock = threading.Lock()
        self._sessions: OrderedDict[str, dict[str, bool]] = OrderedDict()
        self._stats = {
            "initialize_ok": 0,
            "notifications_initialized_ok": 0,
            "tools_list_ok": 0,
            "tools_call_ok": 0,
            "auth_denied": 0,
            "input_denied": 0,
            "session_denied": 0,
            "protocol_denied": 0,
            "forwarded_auth_caller": 0,
        }

    def verify_bearer(self, token: str) -> bool:
        return hmac.compare_digest(token, self._bearer_token)

    def bump(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._stats[key] += 1

    def create_session(self) -> str:
        session_id = secrets.token_urlsafe(24)
        with self._lock:
            while len(self._sessions) >= self._max_sessions:
                self._sessions.popitem(last=False)
            self._sessions[session_id] = {"initialized": False}
            self._stats["initialize_ok"] += 1
        return session_id

    def has_session(self, session_id: str) -> bool:
        with self._lock:
            if session_id not in self._sessions:
                return False
            self._sessions.move_to_end(session_id)
            return True

    def mark_initialized(self, session_id: str) -> bool:
        with self._lock:
            if session_id not in self._sessions:
                return False
            self._sessions.move_to_end(session_id)
            self._sessions[session_id]["initialized"] = True
            self._stats["notifications_initialized_ok"] += 1
            return True

    def stats_snapshot(self) -> dict:
        with self._lock:
            return {
                "mode": "mcp",
                **self._stats,
                "active_sessions": len(self._sessions),
            }


def _make_mcp_handler(state: McpState) -> type[_BaseJsonHandler]:
    class McpHandler(_BaseJsonHandler):
        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path in ("/health", "/_health"):
                self._send_json(200, {"status": "ok", "mode": "mcp"})
                return
            if path in ("/stats", "/_stats"):
                self._send_json(200, state.stats_snapshot())
                return
            if path == "/mcp":
                self._send_json(405, {"error": "method_not_allowed"})
                return
            self._send_json(404, {"error": "not_found"})

        def do_POST(self) -> None:
            path = urlsplit(self.path).path
            if path != "/mcp":
                self._send_json(404, {"error": "not_found"})
                return
            self._handle_mcp_post()

        def do_DELETE(self) -> None:
            self._send_json(405, {"error": "method_not_allowed"})

        def do_PUT(self) -> None:
            self._send_json(405, {"error": "method_not_allowed"})

        def _check_auth(self) -> bool:
            auth_headers = self.headers.get_all("Authorization") or []
            dpop_headers = self.headers.get_all("DPoP") or []
            fwd_auth_headers = self.headers.get_all("X-Forwarded-Authorization") or []

            has_dpop_header = any(v.strip() for v in dpop_headers)
            has_dpop_scheme = any(
                v.strip().lower().startswith("dpop ") or v.strip().lower() == "dpop"
                for v in auth_headers
            )
            has_fwd_auth = any(v.strip() for v in fwd_auth_headers)
            has_multi_auth = len(auth_headers) > 1

            if has_dpop_header or has_dpop_scheme or has_fwd_auth or has_multi_auth:
                state.bump("forwarded_auth_caller", "auth_denied")
                self._send_json(401, {"error": "unauthorized"})
                return False

            if len(auth_headers) != 1:
                state.bump("auth_denied")
                self._send_json(401, {"error": "unauthorized"})
                return False

            raw = auth_headers[0]
            if not raw.startswith("Bearer ") or len(raw) <= 7:
                state.bump("auth_denied")
                self._send_json(401, {"error": "unauthorized"})
                return False

            token = raw[7:]
            if not state.verify_bearer(token):
                state.bump("auth_denied")
                self._send_json(401, {"error": "unauthorized"})
                return False
            return True

        def _handle_mcp_post(self) -> None:
            if not self._check_auth():
                return

            content_type = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                state.bump("input_denied")
                self._send_json(415, {"error": "unsupported_media_type"})
                return

            payload, err = self._read_json_object()
            if err is not None or payload is None:
                state.bump("input_denied")
                self._send_json(
                    400,
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32600, "message": "Invalid Request"},
                    },
                )
                return

            if payload.get("jsonrpc") != "2.0" or not isinstance(payload.get("method"), str):
                state.bump("input_denied")
                self._send_json(
                    400,
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32600, "message": "Invalid Request"},
                    },
                )
                return

            proto_hdr = self.headers.get("MCP-Protocol-Version")
            if proto_hdr is not None and proto_hdr.strip() != MCP_PROTOCOL_VERSION:
                state.bump("protocol_denied", "input_denied")
                self._send_json(400, {"error": "unsupported_protocol_version"})
                return

            method = payload["method"]
            req_id = payload.get("id")

            if method == "initialize":
                self._handle_initialize(req_id, payload.get("params"))
                return

            session_id = self.headers.get("Mcp-Session-Id")
            if not session_id:
                state.bump("session_denied", "input_denied")
                self._send_json(400, {"error": "missing_session_id"})
                return
            if not state.has_session(session_id):
                state.bump("session_denied", "input_denied")
                self._send_json(404, {"error": "invalid_session"})
                return

            if method == "notifications/initialized":
                if "id" in payload and payload["id"] is not None:
                    state.bump("input_denied")
                    self._send_json(
                        400,
                        {
                            "jsonrpc": "2.0",
                            "id": None,
                            "error": {"code": -32600, "message": "Invalid Request"},
                        },
                    )
                    return
                if not state.mark_initialized(session_id):
                    state.bump("session_denied", "input_denied")
                    self._send_json(404, {"error": "invalid_session"})
                    return
                self._send_empty(202)
                return

            if not is_valid_jsonrpc_id(req_id):
                state.bump("input_denied")
                self._send_json(
                    400,
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32600, "message": "Invalid Request"},
                    },
                )
                return

            if method == "tools/list":
                params = payload.get("params", {})
                if params is not None and not isinstance(params, dict):
                    state.bump("input_denied")
                    self._send_json(
                        200,
                        {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "error": {"code": -32602, "message": "Invalid params"},
                        },
                    )
                    return
                state.bump("tools_list_ok")
                self._send_json(
                    200,
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"tools": [MCP_TOOL_DEFINITION]},
                    },
                )
                return

            if method == "tools/call":
                self._handle_tools_call(req_id, payload.get("params"))
                return

            state.bump("input_denied")
            self._send_json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": "Method not found"},
                },
            )

        def _handle_initialize(self, req_id: object, params: object) -> None:
            if not is_valid_jsonrpc_id(req_id):
                state.bump("input_denied")
                self._send_json(
                    400,
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32600, "message": "Invalid Request"},
                    },
                )
                return
            if params is None:
                params = {}
            if not isinstance(params, dict):
                state.bump("input_denied")
                self._send_json(
                    400,
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32602, "message": "Invalid params"},
                    },
                )
                return
            proto_ver = params.get("protocolVersion")
            if proto_ver is not None and proto_ver != MCP_PROTOCOL_VERSION:
                state.bump("protocol_denied", "input_denied")
                self._send_json(
                    400,
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32602, "message": "Unsupported protocol version"},
                    },
                )
                return

            session_id = state.create_session()
            self._send_json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {
                            "name": "stoa-onboarding-mcp-mock",
                            "version": "1.0.0",
                        },
                    },
                },
                extra_headers={
                    "Mcp-Session-Id": session_id,
                    "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
                },
            )

        def _handle_tools_call(self, req_id: object, params: object) -> None:
            if not isinstance(params, dict):
                state.bump("input_denied")
                self._send_json(
                    200,
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32602, "message": "Invalid params"},
                    },
                )
                return
            name = params.get("name")
            arguments = params.get("arguments")
            if name != "account_lookup" or not isinstance(arguments, dict):
                state.bump("input_denied")
                self._send_json(
                    200,
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32602, "message": "Invalid tool or arguments"},
                    },
                )
                return
            if "customer_id" not in arguments:
                state.bump("input_denied")
                self._send_json(
                    200,
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32602, "message": "Invalid arguments"},
                    },
                )
                return
            customer_id = arguments["customer_id"]
            if not isinstance(customer_id, str) or not CUSTOMER_ID_RE.fullmatch(customer_id):
                state.bump("input_denied")
                self._send_json(
                    200,
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32602, "message": "Invalid customer_id"},
                    },
                )
                return

            state.bump("tools_call_ok")
            synthetic = {
                "customer_id": customer_id,
                "status": "active",
                "tier": "synthetic",
                "tenant": state.tenant,
            }
            self._send_json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(synthetic, separators=(",", ":")),
                            }
                        ],
                        "isError": False,
                    },
                },
            )

    return McpHandler


class VaultState:
    def __init__(
        self,
        operator_token: str,
        gateway_token: str,
        *,
        tenant: str = DEFAULT_TENANT,
        env: str = DEFAULT_VAULT_ENV,
        max_secrets: int = DEFAULT_MAX_SECRETS,
    ) -> None:
        if not operator_token or not gateway_token:
            raise ValueError("operator_token and gateway_token must be non-empty")
        if hmac.compare_digest(operator_token, gateway_token):
            raise ValueError("operator_token and gateway_token must be distinct")
        if max_secrets < 1:
            raise ValueError("max_secrets must be >= 1")
        self._operator_token = operator_token
        self._gateway_token = gateway_token
        self.tenant = tenant
        self.env = env
        self._max_secrets = max_secrets
        self._lock = threading.Lock()
        self._secrets: dict[tuple[str, str], dict] = {}
        self._stats = {
            "cas_writes_ok": 0,
            "cas_conflicts": 0,
            "cas_violations": 0,
            "readbacks_ok": 0,
            "readbacks_by_actor": {"operator": 0, "gateway": 0},
            "soft_deletes_ok": 0,
            "auth_denied": 0,
            "role_violations": 0,
            "path_violations": 0,
            "violations": 0,
        }

    def resolve_actor(self, token: str) -> str | None:
        if hmac.compare_digest(token, self._operator_token):
            return "operator"
        if hmac.compare_digest(token, self._gateway_token):
            return "gateway"
        return None

    def bump_violation(self, detail_key: str | None = None) -> None:
        with self._lock:
            self._stats["violations"] += 1
            if detail_key is not None:
                self._stats[detail_key] += 1

    def write_secret_cas0(self, key: tuple[str, str], data: dict) -> tuple[int, dict]:
        with self._lock:
            if key in self._secrets:
                self._stats["cas_conflicts"] += 1
                self._stats["violations"] += 1
                return 400, {"errors": ["check-and-set parameter did not match the current version"]}
            if len(self._secrets) >= self._max_secrets:
                self._stats["violations"] += 1
                return 429, {"errors": ["fixture secret capacity reached"]}
            created_time = utc_now_iso()
            record = {
                "version": 1,
                "data": copy.deepcopy(data),
                "created_time": created_time,
                "deletion_time": "",
                "destroyed": False,
            }
            self._secrets[key] = record
            self._stats["cas_writes_ok"] += 1
            return 200, {
                "request_id": str(uuid.uuid4()),
                "data": {
                    "created_time": created_time,
                    "custom_metadata": None,
                    "deletion_time": "",
                    "destroyed": False,
                    "version": 1,
                },
            }

    def read_secret_v1(self, key: tuple[str, str], actor: str) -> tuple[int, dict]:
        with self._lock:
            record = self._secrets.get(key)
            if record is None:
                return 404, {"errors": []}
            metadata = {
                "created_time": record["created_time"],
                "custom_metadata": None,
                "deletion_time": record["deletion_time"],
                "destroyed": record["destroyed"],
                "version": record["version"],
            }
            if record["deletion_time"]:
                return 404, {
                    "request_id": str(uuid.uuid4()),
                    "data": {
                        "data": None,
                        "metadata": metadata,
                    },
                }
            self._stats["readbacks_ok"] += 1
            self._stats["readbacks_by_actor"][actor] += 1
            return 200, {
                "request_id": str(uuid.uuid4()),
                "data": {
                    "data": copy.deepcopy(record["data"]),
                    "metadata": metadata,
                },
            }

    def soft_delete_v1(self, key: tuple[str, str]) -> int:
        with self._lock:
            record = self._secrets.get(key)
            if record is None:
                return 404
            if not record["deletion_time"]:
                record["deletion_time"] = utc_now_iso()
                record["data"] = None
                self._stats["soft_deletes_ok"] += 1
            return 204

    def parse_secret_path(self, path: str, expected_action: str) -> tuple[str, str] | None:
        parts = path.split("/")
        # Expected: ["", "v1", "secret", expected_action, "stoa", "mcp", tenant, env, uuid, alias]
        if len(parts) != 10:
            return None
        if (
            parts[0] != ""
            or parts[1] != "v1"
            or parts[2] != "secret"
            or parts[3] != expected_action
            or parts[4] != "stoa"
            or parts[5] != "mcp"
            or parts[6] != self.tenant
            or parts[7] != self.env
        ):
            return None
        uuid_part, alias_part = parts[8], parts[9]
        if not UUID_RE.fullmatch(uuid_part) or not ALIAS_RE.fullmatch(alias_part):
            return None
        return uuid_part, alias_part

    def stats_snapshot(self) -> dict:
        with self._lock:
            active = sum(1 for rec in self._secrets.values() if not rec["deletion_time"])
            deleted = len(self._secrets) - active
            return {
                "mode": "vault",
                "cas_writes_ok": self._stats["cas_writes_ok"],
                "cas_conflicts": self._stats["cas_conflicts"],
                "cas_violations": self._stats["cas_violations"],
                "readbacks_ok": self._stats["readbacks_ok"],
                "readbacks_by_actor": dict(self._stats["readbacks_by_actor"]),
                "soft_deletes_ok": self._stats["soft_deletes_ok"],
                "auth_denied": self._stats["auth_denied"],
                "role_violations": self._stats["role_violations"],
                "path_violations": self._stats["path_violations"],
                "violations": self._stats["violations"],
                "active_secrets": active,
                "deleted_secrets": deleted,
            }


def _make_vault_handler(state: VaultState) -> type[_BaseJsonHandler]:
    class VaultHandler(_BaseJsonHandler):
        def _authenticate(self) -> str | None:
            vault_tokens = self.headers.get_all("X-Vault-Token") or []
            auth_headers = self.headers.get_all("Authorization") or []

            token: str | None = None
            if len(vault_tokens) > 1 or len(auth_headers) > 1:
                state.bump_violation("auth_denied")
                self._send_json(403, {"errors": ["permission denied"]})
                return None

            if vault_tokens:
                token = vault_tokens[0]
            if auth_headers:
                raw_auth = auth_headers[0]
                if not raw_auth.startswith("Bearer ") or len(raw_auth) <= 7:
                    state.bump_violation("auth_denied")
                    self._send_json(403, {"errors": ["permission denied"]})
                    return None
                bearer = raw_auth[7:]
                if token is not None and not hmac.compare_digest(token, bearer):
                    state.bump_violation("auth_denied")
                    self._send_json(403, {"errors": ["permission denied"]})
                    return None
                token = bearer

            if not token:
                state.bump_violation("auth_denied")
                self._send_json(403, {"errors": ["permission denied"]})
                return None

            actor = state.resolve_actor(token)
            if actor is None:
                state.bump_violation("auth_denied")
                self._send_json(403, {"errors": ["permission denied"]})
                return None
            return actor

        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            path = parsed.path
            if path in ("/health", "/_health", "/v1/sys/health"):
                self._send_json(
                    200,
                    {"status": "ok", "mode": "vault", "initialized": True, "sealed": False},
                )
                return
            if path in ("/stats", "/_stats"):
                self._send_json(200, state.stats_snapshot())
                return
            if not path.startswith("/v1/secret/"):
                self._send_json(404, {"errors": []})
                return

            actor = self._authenticate()
            if actor is None:
                return

            key = state.parse_secret_path(path, "data")
            if key is None:
                state.bump_violation("path_violations")
                self._send_json(403, {"errors": ["permission denied"]})
                return

            query = parse_qs(parsed.query, keep_blank_values=True)
            if query:
                if set(query.keys()) != {"version"} or query["version"] != ["1"]:
                    state.bump_violation()
                    self._send_json(400, {"errors": ["invalid version parameter"]})
                    return

            code, payload = state.read_secret_v1(key, actor)
            self._send_json(code, payload)

        def do_POST(self) -> None:
            parsed = urlsplit(self.path)
            path = parsed.path
            if not path.startswith("/v1/secret/"):
                self._send_json(404, {"errors": []})
                return

            actor = self._authenticate()
            if actor is None:
                return

            data_key = state.parse_secret_path(path, "data")
            if data_key is not None:
                if actor != "operator":
                    state.bump_violation("role_violations")
                    self._send_json(403, {"errors": ["permission denied"]})
                    return
                self._handle_write(data_key)
                return

            delete_key = state.parse_secret_path(path, "delete")
            if delete_key is not None:
                if actor != "operator":
                    state.bump_violation("role_violations")
                    self._send_json(403, {"errors": ["permission denied"]})
                    return
                self._handle_delete(delete_key)
                return

            state.bump_violation("path_violations")
            self._send_json(403, {"errors": ["permission denied"]})

        def do_DELETE(self) -> None:
            state.bump_violation()
            self._send_json(405, {"errors": ["method not allowed"]})

        def do_PUT(self) -> None:
            state.bump_violation()
            self._send_json(405, {"errors": ["method not allowed"]})

        def _handle_write(self, key: tuple[str, str]) -> None:
            body, err = self._read_json_object()
            if err is not None or body is None:
                state.bump_violation()
                self._send_json(400, {"errors": ["invalid request body"]})
                return
            options = body.get("options")
            if (
                not isinstance(options, dict)
                or type(options.get("cas")) is not int
                or options.get("cas") != 0
            ):
                state.bump_violation("cas_violations")
                self._send_json(400, {"errors": ["check-and-set parameter required"]})
                return
            data = body.get("data")
            if not is_valid_vault_secret_data(data):
                state.bump_violation()
                self._send_json(400, {"errors": ["invalid secret data schema"]})
                return

            code, payload = state.write_secret_cas0(key, data)
            self._send_json(code, payload)

        def _handle_delete(self, key: tuple[str, str]) -> None:
            body, err = self._read_json_object()
            if err is not None or body is None:
                state.bump_violation()
                self._send_json(400, {"errors": ["invalid request body"]})
                return
            versions = body.get("versions")
            if (
                set(body.keys()) != {"versions"}
                or not isinstance(versions, list)
                or len(versions) != 1
                or type(versions[0]) is not int
                or versions[0] != 1
            ):
                state.bump_violation()
                self._send_json(400, {"errors": ["invalid versions parameter"]})
                return

            code = state.soft_delete_v1(key)
            if code == 204:
                self._send_empty(204)
            else:
                self._send_json(404, {"errors": []})

    return VaultHandler


def create_mcp_server(
    host: str,
    port: int,
    bearer_token: str,
    *,
    tenant: str = DEFAULT_TENANT,
    max_sessions: int = DEFAULT_MAX_SESSIONS,
) -> tuple[_FixtureHTTPServer, McpState]:
    state = McpState(bearer_token, tenant=tenant, max_sessions=max_sessions)
    server = _FixtureHTTPServer((host, port), _make_mcp_handler(state))
    return server, state


def create_vault_server(
    host: str,
    port: int,
    operator_token: str,
    gateway_token: str,
    *,
    tenant: str = DEFAULT_TENANT,
    env: str = DEFAULT_VAULT_ENV,
    max_secrets: int = DEFAULT_MAX_SECRETS,
) -> tuple[_FixtureHTTPServer, VaultState]:
    state = VaultState(
        operator_token,
        gateway_token,
        tenant=tenant,
        env=env,
        max_secrets=max_secrets,
    )
    server = _FixtureHTTPServer((host, port), _make_vault_handler(state))
    return server, state


def create_vault_tls_server(
    host: str,
    tls_port: int,
    state: VaultState,
    *,
    certfile: str,
    keyfile: str,
) -> _FixtureHTTPServer:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certfile=certfile, keyfile=keyfile)
    server = _FixtureHTTPServer((host, tls_port), _make_vault_handler(state))
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    return server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("mcp", "vault"), required=True)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Listen port (default: {DEFAULT_MCP_PORT} for mcp, {DEFAULT_VAULT_PORT} for vault)",
    )
    parser.add_argument("--tls-port", type=int, default=None, help="Optional TLS port for vault mode")
    parser.add_argument("--tls-cert", default=None, help="PEM certificate path for vault TLS listener")
    parser.add_argument("--tls-key", default=None, help="PEM private key path for vault TLS listener")
    parser.add_argument("--tenant", default=DEFAULT_TENANT)
    parser.add_argument("--vault-env", default=DEFAULT_VAULT_ENV)
    parser.add_argument("--max-sessions", type=int, default=DEFAULT_MAX_SESSIONS)
    parser.add_argument("--max-secrets", type=int, default=DEFAULT_MAX_SECRETS)
    parser.add_argument("--mcp-bearer-env", default=DEFAULT_MCP_BEARER_ENV)
    parser.add_argument("--vault-operator-token-env", default=DEFAULT_VAULT_OPERATOR_ENV)
    parser.add_argument("--vault-gateway-token-env", default=DEFAULT_VAULT_GATEWAY_ENV)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    tls_server: _FixtureHTTPServer | None = None
    tls_thread: threading.Thread | None = None

    if args.mode == "mcp":
        port = DEFAULT_MCP_PORT if args.port is None else args.port
        bearer = read_required_env(args.mcp_bearer_env)
        server, _ = create_mcp_server(
            args.host,
            port,
            bearer,
            tenant=args.tenant,
            max_sessions=args.max_sessions,
        )
    else:
        port = DEFAULT_VAULT_PORT if args.port is None else args.port
        tls_opts = (args.tls_port is not None, bool(args.tls_cert), bool(args.tls_key))
        if any(tls_opts) and not all(tls_opts):
            print(
                "error: --tls-port, --tls-cert, and --tls-key must all be provided together",
                file=sys.stderr,
            )
            sys.exit(2)
        operator_token = read_required_env(args.vault_operator_token_env)
        gateway_token = read_required_env(args.vault_gateway_token_env)
        if hmac.compare_digest(operator_token, gateway_token):
            print(
                "error: operator and gateway tokens must be distinct",
                file=sys.stderr,
            )
            sys.exit(2)
        server, state = create_vault_server(
            args.host,
            port,
            operator_token,
            gateway_token,
            tenant=args.tenant,
            env=args.vault_env,
            max_secrets=args.max_secrets,
        )
        if args.tls_port is not None:
            tls_server = create_vault_tls_server(
                args.host,
                args.tls_port,
                state,
                certfile=args.tls_cert,
                keyfile=args.tls_key,
            )
            tls_thread = threading.Thread(target=tls_server.serve_forever, daemon=True)
            tls_thread.start()

    actual_host, actual_port = server.server_address[:2]
    if tls_server is not None:
        tls_host, tls_port = tls_server.server_address[:2]
        print(
            f"onboarding-fixture mode={args.mode} listening on {actual_host}:{actual_port} "
            f"tls={tls_host}:{tls_port}",
            flush=True,
        )
    else:
        print(
            f"onboarding-fixture mode={args.mode} listening on {actual_host}:{actual_port}",
            flush=True,
        )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if tls_server is not None:
            tls_server.shutdown()
            tls_server.server_close()
        if tls_thread is not None:
            tls_thread.join(timeout=2)


if __name__ == "__main__":
    main()
