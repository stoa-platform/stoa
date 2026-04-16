#!/usr/bin/env python3
"""stoa-impact MCP server — read-only SQLite bridge for Claude Code teammates.

Exposes docs/stoa-impact.db via Model Context Protocol (stdio transport).
All queries are parameterized; no raw SQL surface. Database is opened in
SQLite read-only URI mode. No external dependencies.

Register in .mcp.json:
    "stoa-impact": {
      "command": "python3",
      "args": ["docs/scripts/stoa_impact_mcp.py"]
    }

CAB-2066 Phase 3.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "stoa-impact"
SERVER_VERSION = "0.1.0"

DEFAULT_DB = Path(__file__).resolve().parent.parent / "stoa-impact.db"

SEVERITY_ENUM = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
RISK_STATUS_ENUM = ["open", "mitigated", "accepted", "resolved"]
DIRECTION_ENUM = ["in", "out", "both"]


class ToolError(Exception):
    """Raised when a tool call fails with a user-visible message."""


def open_db(path: Path) -> sqlite3.Connection:
    """Open the impact DB read-only. Fails fast if the file is missing."""
    if not path.exists():
        raise ToolError(f"Database not found at {path}")
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def rows_to_list(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def q_list_components(conn: sqlite3.Connection, args: dict[str, Any]) -> Any:
    type_filter = args.get("type")
    sql = "SELECT id, name, type, tech_stack, repo_path, status FROM components"
    params: tuple[Any, ...] = ()
    if type_filter:
        sql += " WHERE type = ?"
        params = (type_filter,)
    sql += " ORDER BY id"
    return rows_to_list(conn.execute(sql, params).fetchall())


def q_get_component(conn: sqlite3.Connection, args: dict[str, Any]) -> Any:
    component_id = require_str(args, "component_id")
    row = conn.execute(
        "SELECT id, name, type, tech_stack, repo_path, status, description "
        "FROM components WHERE id = ?",
        (component_id,),
    ).fetchone()
    if not row:
        raise ToolError(f"Unknown component_id: {component_id}")
    return dict(row)


def q_get_contracts(conn: sqlite3.Connection, args: dict[str, Any]) -> Any:
    component_id = require_str(args, "component_id")
    direction = args.get("direction", "both")
    if direction not in DIRECTION_ENUM:
        raise ToolError(f"direction must be one of {DIRECTION_ENUM}")
    out_rows: list[sqlite3.Row] = []
    in_rows: list[sqlite3.Row] = []
    if direction in ("out", "both"):
        out_rows = conn.execute(
            "SELECT id, contract_ref, target_component AS target, type, typed, "
            "schema_type, description "
            "FROM contracts WHERE source_component = ? ORDER BY target_component",
            (component_id,),
        ).fetchall()
    if direction in ("in", "both"):
        in_rows = conn.execute(
            "SELECT id, contract_ref, source_component AS source, type, typed, "
            "schema_type, description "
            "FROM contracts WHERE target_component = ? ORDER BY source_component",
            (component_id,),
        ).fetchall()
    return {
        "outgoing": rows_to_list(out_rows),
        "incoming": rows_to_list(in_rows),
    }


def q_get_impacted_scenarios(conn: sqlite3.Connection, args: dict[str, Any]) -> Any:
    component_id = require_str(args, "component_id")
    rows = conn.execute(
        "SELECT DISTINCT s.id, s.name, s.priority, s.test_level, s.test_in_ci, s.actor "
        "FROM scenarios s JOIN scenario_steps ss ON s.id = ss.scenario_id "
        "WHERE ss.component_id = ? "
        "ORDER BY s.priority, s.id",
        (component_id,),
    ).fetchall()
    return rows_to_list(rows)


def q_get_risks(conn: sqlite3.Connection, args: dict[str, Any]) -> Any:
    component_id = args.get("component_id")
    severity = args.get("severity")
    status = args.get("status")
    if severity and severity not in SEVERITY_ENUM:
        raise ToolError(f"severity must be one of {SEVERITY_ENUM}")
    if status and status not in RISK_STATUS_ENUM:
        raise ToolError(f"status must be one of {RISK_STATUS_ENUM}")

    where: list[str] = []
    params: list[Any] = []
    if component_id:
        # Validate component exists to avoid leaking via LIKE wildcards.
        exists = conn.execute("SELECT 1 FROM components WHERE id = ?", (component_id,)).fetchone()
        if not exists:
            raise ToolError(f"Unknown component_id: {component_id}")
        where.append("impacted_components LIKE ?")
        params.append(f"%{component_id}%")
    if severity:
        where.append("severity = ?")
        params.append(severity)
    if status:
        where.append("status = ?")
        params.append(status)
    sql = (
        "SELECT id, severity, title, status, ticket_ref, impacted_components, "
        "recommendation, description FROM risks"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += (
        " ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 "
        "WHEN 'MEDIUM' THEN 3 ELSE 4 END, id"
    )
    return rows_to_list(conn.execute(sql, params).fetchall())


def q_get_dependency_matrix(conn: sqlite3.Connection, args: dict[str, Any]) -> Any:
    source = args.get("source_component")
    sql = (
        "SELECT source_component, target_component, contract_types, contract_count "
        "FROM dependency_matrix"
    )
    params: tuple[Any, ...] = ()
    if source:
        sql += " WHERE source_component = ?"
        params = (source,)
    sql += " ORDER BY source_component, target_component"
    return rows_to_list(conn.execute(sql, params).fetchall())


def q_get_untyped_contracts(conn: sqlite3.Connection, args: dict[str, Any]) -> Any:
    rows = conn.execute(
        "SELECT id, contract_ref, source_component, target_component, type "
        "FROM untyped_contracts"
    ).fetchall()
    return rows_to_list(rows)


def q_get_component_risk_score(conn: sqlite3.Connection, args: dict[str, Any]) -> Any:
    component_id = args.get("component_id")
    sql = (
        "SELECT id, name, outgoing_contracts, incoming_contracts, "
        "scenarios_involved, untyped_outgoing FROM component_risk_score"
    )
    params: tuple[Any, ...] = ()
    if component_id:
        sql += " WHERE id = ?"
        params = (component_id,)
    sql += " ORDER BY id"
    return rows_to_list(conn.execute(sql, params).fetchall())


def require_str(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise ToolError(f"Missing or invalid '{key}'")
    return value


TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_components",
        "description": (
            "List all registered components (services, frontends, gateways, infra, "
            "externals). Optional filter by type."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": [
                        "service",
                        "frontend",
                        "gateway",
                        "infra",
                        "external",
                        "cli",
                    ],
                }
            },
            "additionalProperties": False,
        },
        "handler": q_list_components,
    },
    {
        "name": "get_component",
        "description": "Return metadata for a single component by id.",
        "inputSchema": {
            "type": "object",
            "properties": {"component_id": {"type": "string"}},
            "required": ["component_id"],
            "additionalProperties": False,
        },
        "handler": q_get_component,
    },
    {
        "name": "get_contracts",
        "description": (
            "Return contracts (API, gRPC, Kafka, DB, OIDC, etc.) for a component. "
            "direction=out returns outgoing, in=incoming, both=both (default)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "component_id": {"type": "string"},
                "direction": {"type": "string", "enum": DIRECTION_ENUM},
            },
            "required": ["component_id"],
            "additionalProperties": False,
        },
        "handler": q_get_contracts,
    },
    {
        "name": "get_impacted_scenarios",
        "description": (
            "Return P0/P1/P2 scenarios that traverse a component. Use to assess "
            "blast radius before modifying a component."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"component_id": {"type": "string"}},
            "required": ["component_id"],
            "additionalProperties": False,
        },
        "handler": q_get_impacted_scenarios,
    },
    {
        "name": "get_risks",
        "description": (
            "Return known risks, optionally filtered by component_id, severity "
            "(CRITICAL/HIGH/MEDIUM/LOW), or status (open/mitigated/accepted/resolved)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "component_id": {"type": "string"},
                "severity": {"type": "string", "enum": SEVERITY_ENUM},
                "status": {"type": "string", "enum": RISK_STATUS_ENUM},
            },
            "additionalProperties": False,
        },
        "handler": q_get_risks,
    },
    {
        "name": "get_dependency_matrix",
        "description": (
            "Return source->target dependency edges with aggregated contract types "
            "and counts. Optionally filter by source_component."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"source_component": {"type": "string"}},
            "additionalProperties": False,
        },
        "handler": q_get_dependency_matrix,
    },
    {
        "name": "get_untyped_contracts",
        "description": (
            "Return contracts missing a schema (typed=0). Useful to spot missing "
            "Pydantic/TS/Rust definitions on critical paths."
        ),
        "inputSchema": {"type": "object", "additionalProperties": False},
        "handler": q_get_untyped_contracts,
    },
    {
        "name": "get_component_risk_score",
        "description": (
            "Return per-component risk score (outgoing/incoming contracts, "
            "scenarios, untyped_outgoing). Optionally scope to one component."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"component_id": {"type": "string"}},
            "additionalProperties": False,
        },
        "handler": q_get_component_risk_score,
    },
]


def tool_spec(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": tool["name"],
        "description": tool["description"],
        "inputSchema": tool["inputSchema"],
    }


def find_tool(name: str) -> dict[str, Any]:
    for t in TOOLS:
        if t["name"] == name:
            return t
    raise ToolError(f"Unknown tool: {name}")


def handle_request(conn: sqlite3.Connection, request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    req_id = request.get("id")
    params = request.get("params") or {}

    if method is None:
        return error_response(req_id, -32600, "Invalid request: missing method")

    # Notifications (no id) — no response required by JSON-RPC spec.
    if req_id is None:
        return None

    try:
        if method == "initialize":
            return ok_response(
                req_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "capabilities": {"tools": {"listChanged": False}},
                },
            )
        if method == "tools/list":
            return ok_response(req_id, {"tools": [tool_spec(t) for t in TOOLS]})
        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            if not isinstance(name, str):
                raise ToolError("tools/call: missing 'name'")
            if not isinstance(args, dict):
                raise ToolError("tools/call: 'arguments' must be an object")
            tool = find_tool(name)
            result = tool["handler"](conn, args)
            text = json.dumps(result, indent=2, default=str)
            return ok_response(
                req_id,
                {"content": [{"type": "text", "text": text}], "isError": False},
            )
        if method in ("ping",):
            return ok_response(req_id, {})
        return error_response(req_id, -32601, f"Method not found: {method}")
    except ToolError as exc:
        if method == "tools/call":
            return ok_response(
                req_id,
                {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            )
        return error_response(req_id, -32602, str(exc))
    except sqlite3.Error as exc:
        # Log details to stderr; return a generic message so schema/column names
        # from constraint errors do not leak to the MCP client.
        print(f"[stoa-impact-mcp] sqlite error: {exc}", file=sys.stderr)
        return error_response(req_id, -32000, "Database error (see server stderr)")
    except Exception as exc:  # noqa: BLE001 - keep server alive, surface generic
        print(f"[stoa-impact-mcp] internal error: {exc!r}", file=sys.stderr)
        return error_response(req_id, -32603, "Internal server error")


def ok_response(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def error_response(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def serve_stdio(conn: sqlite3.Connection) -> None:
    """Blocking loop: read JSON-RPC messages line-by-line from stdin, write to stdout."""
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            sys.stdout.write(json.dumps(error_response(None, -32700, f"Parse error: {exc}")) + "\n")
            sys.stdout.flush()
            continue
        response = handle_request(conn, request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="stoa-impact MCP server (read-only)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to stoa-impact.db")
    args = parser.parse_args(argv)
    try:
        conn = open_db(args.db)
    except ToolError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    try:
        serve_stdio(conn)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
