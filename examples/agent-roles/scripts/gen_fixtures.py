#!/usr/bin/env python3
"""Generate ephemeral signed Ed25519 policy + role policy, UAC contract, OPA policy, and credential fixtures."""

import argparse
import base64
import json
import os
import shutil
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


def closed_object(properties: dict) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def write_limits_contract(contracts_dir: Path, role: str) -> None:
    limits_contract = {
        "name": "my-limits",
        "version": "1.0.0",
        "tenant_id": "acme",
        "display_name": "My limits",
        "description": "Current access and remaining budgets for the calling agent",
        "classification": "H",
        "endpoints": [
            {
                "path": "/my-limits",
                "methods": ["GET"],
                "backend_url": "stoa-local://my-limits",
                "operation_id": "get_my_limits",
                "input_schema": closed_object({}),
                "output_schema": closed_object({
                    "role": closed_object({
                        "name": {"type": "string"},
                        "policy_version": {"type": "integer", "minimum": 1},
                    }),
                    "allowed_tools": {"type": "array", "items": {"type": "string"}},
                    "argument_constraints": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "object",
                            "additionalProperties": {
                                "type": "array",
                                "items": {"type": "object"},
                            },
                        },
                    },
                    "budget": closed_object({
                        "chain_remaining": {"type": "integer", "minimum": 0},
                        "root_caller_remaining": {"type": "integer", "minimum": 0},
                    }),
                    "delegation_depth": {"type": "integer", "minimum": 0, "maximum": 3},
                }),
                "llm": {
                    "summary": "Read your current access and remaining budgets",
                    "intent": "Use before choosing a tool or delegating work",
                    "tool_name": "stoa_security",
                    "side_effects": "read",
                    "safe_for_agents": True,
                    "requires_human_approval": False,
                    "examples": [
                        {"input": {}, "expected_output_contains": {"role": {"name": role}}},
                    ],
                },
            }
        ],
        "required_policies": [],
        "status": "published",
    }
    (contracts_dir / "my-limits.uac.json").write_text(
        json.dumps(limits_contract, indent=2) + "\n", encoding="utf-8"
    )


def write_jalon4_skill(
    skills_dir: Path, priv: Ed25519PrivateKey, kid: str, variant: str
) -> None:
    instructions = os.environ["STOA_POC_EXPECTED_SKILL_CONTEXT"]
    manifest = {
        "version": 1,
        "iss": "stoa-poc-policy",
        "aud": "stoa-gateway",
        "tenant_id": "acme",
        "name": "payments-guide",
        "instructions": [instructions] if variant == "manifest" else instructions,
        "tool_name": "payments_list",
        "input_schema": {"type": "object", "properties": {}},
    }
    signer = Ed25519PrivateKey.generate() if variant == "signature" else priv
    (skills_dir / "payments-guide.jws").write_text(
        sign_jws(signer, "stoa-skill+jws", kid, manifest) + "\n", encoding="utf-8"
    )


def write_jalon4_fixtures(
    runtime_dir: Path, priv: Ed25519PrivateKey, kid: str, variant: str
) -> None:
    contracts_dir = runtime_dir / "contracts"
    write_limits_contract(contracts_dir, "reader")
    skills_dir = contracts_dir / "skills"
    skills_dir.mkdir()
    write_jalon4_skill(skills_dir, priv, kid, variant)


def write_refund_demo_fixtures(
    runtime_dir: Path,
    priv: Ed25519PrivateKey,
    kid: str,
    policy_identity: dict,
    upstream_api_key: str,
) -> None:
    tool = "refunds_create"
    role = "refund_operator"
    origin = "http://upstream-mock:9000"
    contract_dir = runtime_dir / "contracts"
    write_limits_contract(contract_dir, role)

    fields = {
        "customer_id": {"type": "string"},
        "amount_eur": {"type": "integer", "minimum": 1},
        "currency": {"type": "string", "enum": ["EUR"]},
    }
    input_schema = closed_object(fields)
    output_schema = closed_object({
        **fields,
        "status": {"type": "string", "enum": ["simulated"]},
    })
    refund_contract = {
        "name": "refunds",
        "version": "1.0.0",
        "tenant_id": "acme",
        "display_name": "Simulated refunds",
        "description": "Isolated refund demonstration",
        "classification": "H",
        "endpoints": [{
            "path": "/refunds",
            "methods": ["POST"],
            "backend_url": f"{origin}/refunds",
            "operation_id": "create_refund",
            "input_schema": input_schema,
            "output_schema": output_schema,
            "llm": {
                "summary": "Create a simulated refund",
                "intent": "Demonstrate a refund in the isolated local mock",
                "tool_name": tool,
                "side_effects": "write",
                "safe_for_agents": True,
                "requires_human_approval": False,
                "examples": [{
                    "input": {"customer_id": "C-1042", "amount_eur": 50, "currency": "EUR"},
                    "expected_output_contains": {"status": "simulated"},
                }],
            },
        }],
        "required_policies": [],
        "status": "published",
    }
    (contract_dir / "refunds.uac.json").write_text(
        json.dumps(refund_contract, indent=2) + "\n", encoding="utf-8"
    )
    tool_policy = {
        **policy_identity,
        "permissions": [
            {"mcp_server": "poc-refunds", "tool": tool, "allowed": True},
            {"mcp_server": "poc-access", "tool": "stoa_security", "allowed": True},
        ],
    }
    role_policy = {
        **policy_identity,
        "roles": {
            role: {
                "allowed_tools": [tool],
                "argument_constraints": {
                    tool: {
                        "amount_eur": {"type": "max_number", "max": 500},
                        "currency": {"type": "allowed_values", "values": ["EUR"]},
                    }
                },
            }
        },
    }
    for filename, kind, payload in [
        ("policies/acme.jws", "stoa-tool-policy+jws", tool_policy),
        ("roles/acme.roles.jws", "stoa-agent-role-policy+jws", role_policy),
    ]:
        (runtime_dir / filename).write_text(
            sign_jws(priv, kind, kid, payload) + "\n", encoding="utf-8"
        )

    credentials = [{
        "route_id": f"mcp-tool:acme:{tool}",
        "auth_type": "api_key",
        "header_name": "X-API-Key",
        "header_value": upstream_api_key,
        "allowed_origin": origin,
        "shared_with_tenants": False,
    }]
    (runtime_dir / "credentials.json").write_text(
        json.dumps(credentials, indent=2) + "\n", encoding="utf-8"
    )

    # Pin the actual MCP schemas, including the required fields projected from UAC.
    skills_dir = contract_dir / "skills"
    skills_dir.mkdir()
    manifest = {
        "version": 1,
        "iss": "stoa-poc-policy",
        "aud": "stoa-gateway",
        "tenant_id": "acme",
        "name": "refunds-guide",
        "instructions": os.environ["STOA_POC_EXPECTED_SKILL_CONTEXT"],
        "tool_name": tool,
        "input_schema": {
            field: input_schema[field] for field in ("type", "properties", "required")
        },
        "output_schema": output_schema,
    }
    (skills_dir / "refunds-guide.jws").write_text(
        sign_jws(priv, "stoa-skill+jws", kid, manifest) + "\n", encoding="utf-8"
    )

    opa_policy = """package stoa.authz

import future.keywords.if

default allow := false

refund_demo_tenant if {
    input.tenant_id == "acme"
    input.resource_tenant_id == "acme"
}

allow if {
    refund_demo_tenant
    input.tool_name == "refunds_create"
    input.action == "Create"
}

allow if {
    refund_demo_tenant
    input.tool_name == "stoa_security"
    input.action == "Read"
}
"""
    (runtime_dir / "opa" / "policy.rego").write_text(opa_policy, encoding="utf-8")


def write_onboarding_demo_fixtures(
    runtime_dir: Path,
    priv: Ed25519PrivateKey,
    kid: str,
    policy_identity: dict,
) -> None:
    tool = "legacy__account_lookup"
    role = "onboarding_operator"
    contract_dir = runtime_dir / "contracts"
    write_limits_contract(contract_dir, role)

    tool_policy = {
        **policy_identity,
        "permissions": [
            {"mcp_server": "legacy", "tool": tool, "allowed": True},
            {"mcp_server": "poc-access", "tool": "stoa_security", "allowed": True},
        ],
    }
    role_policy = {
        **policy_identity,
        "roles": {
            role: {
                "allowed_tools": [tool],
                "argument_constraints": {},
            }
        },
    }
    for filename, kind, payload in [
        ("policies/acme.jws", "stoa-tool-policy+jws", tool_policy),
        ("roles/acme.roles.jws", "stoa-agent-role-policy+jws", role_policy),
    ]:
        (runtime_dir / filename).write_text(
            sign_jws(priv, kind, kid, payload) + "\n", encoding="utf-8"
        )

    (runtime_dir / "credentials.json").write_text("[]\n", encoding="utf-8")

    opa_policy = """package stoa.authz

import future.keywords.if

default allow := false

onboarding_demo_tenant if {
    input.tenant_id == "acme"
    input.resource_tenant_id == "acme"
}

allow if {
    onboarding_demo_tenant
    input.tool_name == "legacy__account_lookup"
    input.action == "Create"
}

allow if {
    onboarding_demo_tenant
    input.tool_name == "stoa_security"
    input.action == "Read"
}
"""
    (runtime_dir / "opa" / "policy.rego").write_text(opa_policy, encoding="utf-8")


def write_drift_fixture(runtime_dir: Path, admitted_dir: Path) -> None:
    # Reuse the admitted bytes and trust material; only its registered tool changes.
    shutil.copytree(admitted_dir, runtime_dir)
    path = runtime_dir / "contracts" / "payments.uac.json"
    contract = json.loads(path.read_text(encoding="utf-8"))
    contract["endpoints"][0]["input_schema"] = {
        "type": "object",
        "properties": {"reference": {"type": "string"}},
    }
    path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")


def publish_fixtures(runtime_dir: Path) -> None:
    for p in [runtime_dir, *runtime_dir.rglob("*")]:
        p.chmod(0o755 if p.is_dir() else 0o644)

    print(f"Generated signed fixtures (tool policy + role policy) in {runtime_dir}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime_dir", nargs="?", type=Path, default=Path(".runtime"))
    variants = parser.add_mutually_exclusive_group()
    variants.add_argument("--jalon4", choices=("accepted", "signature", "manifest"))
    variants.add_argument(
        "--jalon4-suite", action="store_true", help="generate all Jalon 4 cases within runtime_dir"
    )
    variants.add_argument("--refund-demo", action="store_true")
    variants.add_argument("--onboarding-demo", action="store_true")
    variants.add_argument("--role-v2-out", type=Path, help="write a second version of the signed role policy")
    variants.add_argument("--drift-from", type=Path)
    args = parser.parse_args()
    runtime_dir = args.runtime_dir / "accepted" if args.jalon4_suite else args.runtime_dir
    jalon4_variant = "accepted" if args.jalon4_suite else args.jalon4
    if args.drift_from:
        write_drift_fixture(runtime_dir, args.drift_from)
        return

    upstream_api_key = None if args.onboarding_demo else os.environ["STOA_POC_UPSTREAM_API_KEY"]

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
    policy_identity = {
        "iss": "stoa-poc-policy",
        "aud": "stoa-gateway",
        "tenant_id": "acme",
        "tenant_uuid": tenant_uuid,
        "version": 1,
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
    }
    if args.refund_demo:
        write_refund_demo_fixtures(runtime_dir, priv, kid, policy_identity, upstream_api_key)
        publish_fixtures(runtime_dir)
        return
    if args.onboarding_demo:
        write_onboarding_demo_fixtures(runtime_dir, priv, kid, policy_identity)
        publish_fixtures(runtime_dir)
        return

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
        **policy_identity,
        "permissions": [
            {"mcp_server": "poc-payments", "tool": t, "allowed": True} for t in tenant_tools
        ],
    }
    if jalon4_variant:
        tool_policy_payload["permissions"].append(
            {"mcp_server": "poc-access", "tool": "stoa_security", "allowed": True}
        )
    (runtime_dir / "policies" / "acme.jws").write_text(
        sign_jws(priv, "stoa-tool-policy+jws", kid, tool_policy_payload) + "\n",
        encoding="utf-8",
    )

    # 2. Signed role policy (stoa-agent-role-policy+jws, 10-min TTL <= 15-min max)
    role_policy_payload = {
        **policy_identity,
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
    if args.role_v2_out:
        args.role_v2_out.write_text(
            sign_jws(priv, "stoa-agent-role-policy+jws", kid, {**role_policy_payload, "version": 2}) + "\n",
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

    if jalon4_variant:
        write_jalon4_fixtures(runtime_dir, priv, kid, jalon4_variant)

    publish_fixtures(runtime_dir)
    if args.jalon4_suite:
        # Reuse the tenant identity and role artifact across tests on the same volume.
        for variant in ("signature", "manifest"):
            rejected_dir = args.runtime_dir / variant
            shutil.copytree(runtime_dir, rejected_dir)
            write_jalon4_skill(rejected_dir / "contracts" / "skills", priv, kid, variant)
        write_drift_fixture(args.runtime_dir / "drift", runtime_dir)


if __name__ == "__main__":
    main()
