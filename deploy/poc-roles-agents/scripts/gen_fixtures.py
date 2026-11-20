#!/usr/bin/env python3
"""Generate ephemeral signed Ed25519 policy + role policy, UAC contract, OPA policy, and credential fixtures."""

import base64
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def sign_jws(priv: Ed25519PrivateKey, typ: str, kid: str, payload: dict) -> str:
    header = {"alg": "EdDSA", "typ": typ, "kid": kid}
    signing_input = (
        f"{b64url(json.dumps(header, separators=(',', ':')).encode())}."
        f"{b64url(json.dumps(payload, separators=(',', ':')).encode())}"
    )
    sig = priv.sign(signing_input.encode("ascii"))
    return f"{signing_input}.{b64url(sig)}"


def main() -> None:
    runtime_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".runtime")
    upstream_api_key = os.environ["STOA_POC_UPSTREAM_API_KEY"]

    (runtime_dir / "policies").mkdir(parents=True, exist_ok=True)
    (runtime_dir / "roles").mkdir(parents=True, exist_ok=True)
    (runtime_dir / "contracts").mkdir(parents=True, exist_ok=True)
    (runtime_dir / "opa").mkdir(parents=True, exist_ok=True)

    # Generate ephemeral Ed25519 keypair in memory; private key is never written to disk.
    priv = Ed25519PrivateKey.generate()
    pub_raw = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    kid = "cp-policy-202611-1"
    tenant_uuid = str(uuid.uuid4())

    trust_jwks = {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "alg": "EdDSA",
                "use": "sig",
                "kid": kid,
                "x": b64url(pub_raw),
            }
        ]
    }
    (runtime_dir / "trust-jwks.json").write_text(
        json.dumps(trust_jwks, indent=2) + "\n", encoding="utf-8"
    )

    now = datetime.now(timezone.utc)
    tenant_tools = [
        "payments_list",
        "payments_opa_denied",
        "payments_redirect",
        "payments_outbound_blocked",
        "payments_fail",
        "payments_hidden",
    ]
    # `payments_hidden` is intentionally permitted at tenant & OPA level but omitted from the
    # `reader` role so `tools/list` filters it out and direct/sub-call execution is denied.
    reader_role_tools = [
        "payments_list",
        "payments_opa_denied",
        "payments_redirect",
        "payments_outbound_blocked",
        "payments_fail",
    ]

    # 1. Signed tenant tool policy (stoa-tool-policy+jws)
    tool_policy_payload = {
        "iss": "stoa-poc-policy",
        "aud": "stoa-gateway",
        "tenant_id": "acme",
        "tenant_uuid": tenant_uuid,
        "version": 1,
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
        "permissions": [
            {"mcp_server": "poc-payments", "tool": t, "allowed": True} for t in tenant_tools
        ],
    }
    (runtime_dir / "policies" / "acme.jws").write_text(
        sign_jws(priv, "stoa-tool-policy+jws", kid, tool_policy_payload) + "\n",
        encoding="utf-8",
    )

    # 2. Signed role policy (stoa-agent-role-policy+jws, 10-min TTL <= 15-min max)
    role_policy_payload = {
        "iss": "stoa-poc-policy",
        "aud": "stoa-gateway",
        "tenant_id": "acme",
        "tenant_uuid": tenant_uuid,
        "version": 1,
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
        "roles": {
            "reader": {
                "allowed_tools": reader_role_tools,
                "argument_constraints": {
                    "payments_list": {
                        "currency": {"type": "allowed_values", "values": ["EUR", "USD"]},
                        "account": {"type": "prefix", "prefix": "acct-"},
                        "limit": {"type": "max_number", "max": 100.0},
                    }
                },
            }
        },
    }
    (runtime_dir / "roles" / "acme.roles.jws").write_text(
        sign_jws(priv, "stoa-agent-role-policy+jws", kid, role_policy_payload) + "\n",
        encoding="utf-8",
    )

    uac_contract = {
        "name": "payments",
        "version": "1.0.0",
        "tenant_id": "acme",
        "display_name": "PoC Payments API",
        "description": "Autonomous PoC fixture contract",
        "classification": "H",
        "endpoints": [
            {
                "path": "/payments",
                "methods": ["GET"],
                "backend_url": "http://upstream-mock:9000/payments",
                "operation_id": "list_payments",
                "llm": {
                    "summary": "List tenant payments",
                    "intent": "Read payments for tenant acme",
                    "tool_name": "payments_list",
                    "side_effects": "read",
                    "safe_for_agents": True,
                    "requires_human_approval": False,
                    "examples": [],
                },
            },
            {
                "path": "/opa-denied",
                "methods": ["GET"],
                "backend_url": "http://upstream-mock:9000/payments",
                "operation_id": "opa_denied",
                "llm": {
                    "summary": "OPA denied operation",
                    "intent": "Negative OPA policy check",
                    "tool_name": "payments_opa_denied",
                    "side_effects": "read",
                    "safe_for_agents": True,
                    "requires_human_approval": False,
                    "examples": [],
                },
            },
            {
                "path": "/redirect",
                "methods": ["GET"],
                "backend_url": "http://upstream-mock:9000/redirect",
                "operation_id": "redirect_check",
                "llm": {
                    "summary": "Redirect check endpoint",
                    "intent": "Verify 3xx redirects are not followed",
                    "tool_name": "payments_redirect",
                    "side_effects": "read",
                    "safe_for_agents": True,
                    "requires_human_approval": False,
                    "examples": [],
                },
            },
            {
                "path": "/outbound-blocked",
                "methods": ["GET"],
                "backend_url": "http://169.254.169.254/latest/meta-data/",
                "operation_id": "outbound_blocked",
                "llm": {
                    "summary": "Blocked internal target",
                    "intent": "Verify outbound address policy blocks link-local IP",
                    "tool_name": "payments_outbound_blocked",
                    "side_effects": "read",
                    "safe_for_agents": True,
                    "requires_human_approval": False,
                    "examples": [],
                },
            },
            {
                "path": "/fail",
                "methods": ["GET"],
                "backend_url": "http://upstream-mock:9000/fail",
                "operation_id": "payments_fail",
                "llm": {
                    "summary": "Simulated upstream failure",
                    "intent": "Trigger fallback evaluation in poc/subcalls",
                    "tool_name": "payments_fail",
                    "side_effects": "read",
                    "safe_for_agents": True,
                    "requires_human_approval": False,
                    "examples": [],
                },
            },
            {
                "path": "/forbidden",
                "methods": ["GET"],
                "backend_url": "http://upstream-mock:9000/forbidden",
                "operation_id": "payments_hidden",
                "llm": {
                    "summary": "Tool outside reader role scope",
                    "intent": "Verify tools/list filtering and sub-call role enforcement",
                    "tool_name": "payments_hidden",
                    "side_effects": "read",
                    "safe_for_agents": True,
                    "requires_human_approval": False,
                    "examples": [],
                },
            },
        ],
        "required_policies": [],
        "status": "published",
    }
    (runtime_dir / "contracts" / "payments.uac.json").write_text(
        json.dumps(uac_contract, indent=2) + "\n", encoding="utf-8"
    )

    credentials = [
        {
            "route_id": "mcp-tool:acme:payments_list",
            "auth_type": "api_key",
            "header_name": "X-API-Key",
            "header_value": upstream_api_key,
            "allowed_origin": "http://upstream-mock:9000",
            "shared_with_tenants": False,
        }
    ]
    (runtime_dir / "credentials.json").write_text(
        json.dumps(credentials, indent=2) + "\n", encoding="utf-8"
    )

    opa_policy = """package stoa.authz

import future.keywords.if

default allow := false

allow if {
    input.tenant_id == "acme"
    input.resource_tenant_id == "acme"
    input.tool_name != "payments_opa_denied"
    input.action == "Read"
}
"""
    (runtime_dir / "opa" / "policy.rego").write_text(opa_policy, encoding="utf-8")

    for p in [runtime_dir, *runtime_dir.rglob("*")]:
        p.chmod(0o755 if p.is_dir() else 0o644)

    print(f"Generated signed fixtures (tool policy + role policy) in {runtime_dir}", flush=True)


if __name__ == "__main__":
    main()
