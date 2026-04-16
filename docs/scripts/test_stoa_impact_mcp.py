"""Tests for stoa_impact_mcp.

Run: python3 -m pytest docs/scripts/test_stoa_impact_mcp.py -q
(or: python3 docs/scripts/test_stoa_impact_mcp.py for a lightweight self-runner)
"""

from __future__ import annotations

import io
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import stoa_impact_mcp as srv  # noqa: E402


def _fixture_db() -> sqlite3.Connection:
    """Build an in-memory DB matching the schema used by the real file."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    conn.executescript(schema_path.read_text())
    conn.executescript("""
        INSERT INTO components (id, name, type, tech_stack, repo_path, status) VALUES
            ('svc-a', 'Service A', 'service', 'python', 'svc-a/', 'active'),
            ('svc-b', 'Service B', 'service', 'rust', 'svc-b/', 'active'),
            ('fe-x',  'Frontend X', 'frontend', 'react', 'fe-x/', 'active');
        INSERT INTO contracts (id, source_component, target_component, type,
                               contract_ref, schema_type, schema_path, typed)
        VALUES
            ('c1', 'svc-a', 'svc-b', 'rest-api', 'GET /b/items', 'openapi', 'b.yaml', 1),
            ('c2', 'svc-b', 'svc-a', 'kafka-event', 'evt.updated', 'avro', 'evt.avsc', 1),
            ('c3', 'fe-x',  'svc-a', 'rest-api', 'POST /a/login', 'none', NULL, 0);
        INSERT INTO scenarios (id, name, description, actor, priority, test_level, test_in_ci)
        VALUES
            ('sc-login', 'User login', 'OIDC flow', 'user', 'P0', 'e2e', 1),
            ('sc-report', 'Report fetch', 'Data read', 'user', 'P1', 'unit', 0);
        INSERT INTO scenario_steps (scenario_id, step_order, component_id, action, contract_id)
        VALUES
            ('sc-login', 1, 'fe-x',  'POST login', 'c3'),
            ('sc-login', 2, 'svc-a', 'verify',     NULL),
            ('sc-report', 1, 'svc-a', 'query',     'c1');
        INSERT INTO risks (id, severity, title, status, impacted_components, ticket_ref)
        VALUES
            ('r1', 'HIGH', 'Untyped login contract', 'open', 'svc-a,fe-x', 'CAB-1'),
            ('r2', 'LOW',  'Dormant risk',           'mitigated', 'svc-b', 'CAB-2');
        """)
    return conn


def call_tool(conn, name, args=None):
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": args or {}},
    }
    resp = srv.handle_request(conn, req)
    assert resp is not None, f"no response for {name}"
    assert "result" in resp, f"error response: {resp}"
    result = resp["result"]
    if result.get("isError"):
        return {"error": result["content"][0]["text"]}
    payload = result["content"][0]["text"]
    return json.loads(payload)


# --- Tests ---


def test_initialize():
    conn = _fixture_db()
    resp = srv.handle_request(conn, {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert resp["result"]["protocolVersion"] == srv.PROTOCOL_VERSION
    assert resp["result"]["serverInfo"]["name"] == "stoa-impact"
    assert "tools" in resp["result"]["capabilities"]


def test_tools_list_shapes():
    conn = _fixture_db()
    resp = srv.handle_request(conn, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = resp["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {
        "list_components",
        "get_component",
        "get_contracts",
        "get_impacted_scenarios",
        "get_risks",
        "get_dependency_matrix",
        "get_untyped_contracts",
        "get_component_risk_score",
    } <= names
    for t in tools:
        assert "description" in t and t["description"]
        assert t["inputSchema"]["type"] == "object"
        assert t["inputSchema"].get("additionalProperties") is False


def test_list_components_filter():
    conn = _fixture_db()
    svcs = call_tool(conn, "list_components", {"type": "service"})
    assert {c["id"] for c in svcs} == {"svc-a", "svc-b"}
    fes = call_tool(conn, "list_components", {"type": "frontend"})
    assert [c["id"] for c in fes] == ["fe-x"]


def test_get_component_unknown():
    conn = _fixture_db()
    err = call_tool(conn, "get_component", {"component_id": "nope"})
    assert "error" in err and "Unknown component_id" in err["error"]


def test_get_contracts_direction():
    conn = _fixture_db()
    both = call_tool(conn, "get_contracts", {"component_id": "svc-a"})
    assert {c["id"] for c in both["outgoing"]} == {"c1"}
    assert {c["id"] for c in both["incoming"]} == {"c2", "c3"}
    out_only = call_tool(conn, "get_contracts", {"component_id": "svc-a", "direction": "out"})
    assert out_only["incoming"] == []


def test_get_contracts_bad_direction():
    conn = _fixture_db()
    err = call_tool(conn, "get_contracts", {"component_id": "svc-a", "direction": "sideways"})
    assert "direction must be" in err["error"]


def test_impacted_scenarios_p0_first():
    conn = _fixture_db()
    scenarios = call_tool(conn, "get_impacted_scenarios", {"component_id": "svc-a"})
    assert [s["id"] for s in scenarios] == ["sc-login", "sc-report"]
    assert scenarios[0]["priority"] == "P0"


def test_get_risks_filters():
    conn = _fixture_db()
    high = call_tool(conn, "get_risks", {"severity": "HIGH"})
    assert [r["id"] for r in high] == ["r1"]
    open_only = call_tool(conn, "get_risks", {"status": "open"})
    assert [r["id"] for r in open_only] == ["r1"]
    by_comp = call_tool(conn, "get_risks", {"component_id": "svc-b"})
    assert [r["id"] for r in by_comp] == ["r2"]


def test_get_risks_unknown_component_rejected():
    """Prevents LIKE-wildcard enumeration by validating component existence first."""
    conn = _fixture_db()
    err = call_tool(conn, "get_risks", {"component_id": "../../etc/passwd"})
    assert "Unknown component_id" in err["error"]


def test_get_risks_enum_validation():
    conn = _fixture_db()
    err = call_tool(conn, "get_risks", {"severity": "EXTINCTION"})
    assert "severity must be" in err["error"]


def test_dependency_matrix():
    conn = _fixture_db()
    rows = call_tool(conn, "get_dependency_matrix", {"source_component": "svc-a"})
    assert [(r["source_component"], r["target_component"]) for r in rows] == [("svc-a", "svc-b")]


def test_untyped_contracts():
    conn = _fixture_db()
    rows = call_tool(conn, "get_untyped_contracts")
    assert {r["id"] for r in rows} == {"c3"}


def test_component_risk_score_scope():
    conn = _fixture_db()
    one = call_tool(conn, "get_component_risk_score", {"component_id": "svc-a"})
    assert len(one) == 1
    assert one[0]["id"] == "svc-a"
    assert one[0]["outgoing_contracts"] == 1


def test_unknown_tool():
    conn = _fixture_db()
    req = {
        "jsonrpc": "2.0",
        "id": 99,
        "method": "tools/call",
        "params": {"name": "drop_table", "arguments": {}},
    }
    resp = srv.handle_request(conn, req)
    assert resp["result"]["isError"] is True
    assert "Unknown tool" in resp["result"]["content"][0]["text"]


def test_parse_error_yields_rpc_error(monkeypatch):
    conn = _fixture_db()
    monkeypatch.setattr(sys, "stdin", io.StringIO("{ not json\n"))
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    srv.serve_stdio(conn)
    out = json.loads(buf.getvalue().strip())
    assert out["error"]["code"] == -32700


def test_notification_no_response():
    conn = _fixture_db()
    resp = srv.handle_request(conn, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert resp is None


def test_read_only_enforced(tmp_path):
    """Opening in URI ro mode must reject writes even if the handler tried."""
    db_path = tmp_path / "ro.db"
    seed = sqlite3.connect(db_path)
    seed.execute("CREATE TABLE t (x INTEGER)")
    seed.execute("INSERT INTO t VALUES (1)")
    seed.commit()
    seed.close()
    conn = srv.open_db(db_path)
    try:
        conn.execute("INSERT INTO t VALUES (2)")
    except sqlite3.OperationalError as exc:
        assert "readonly" in str(exc).lower() or "read-only" in str(exc).lower()
    else:
        raise AssertionError("Write should have failed in ro mode")


if __name__ == "__main__":
    # Lightweight self-runner (no pytest dep required).
    import traceback

    failures = 0
    tests = [
        (name, obj) for name, obj in globals().items() if name.startswith("test_") and callable(obj)
    ]
    for name, fn in tests:
        try:
            if "tmp_path" in fn.__code__.co_varnames or "monkeypatch" in fn.__code__.co_varnames:
                # Skip pytest-fixture tests in self-run mode.
                print(f"SKIP {name} (needs pytest fixtures)")
                continue
            fn()
            print(f"PASS {name}")
        except Exception:
            failures += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    sys.exit(1 if failures else 0)
