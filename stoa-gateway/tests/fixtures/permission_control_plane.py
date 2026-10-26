"""Local control-plane peer for the MCP service-account end-to-end test.

Uses the production permission router, JWT validation and a real SQLite session.
Only Keycloak is a fixture. No external service or application lifespan is used.
"""

import asyncio
import base64
import json
import os
import socket
import sys
import uuid
from pathlib import Path

# Set deterministic local-only configuration before importing the CP.
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "GIT_PROVIDER": "gitlab",
        "GITLAB_TOKEN": "fixture-only",
        "GITLAB_PROJECT_ID": "1",
        "STOA_DISABLE_AUTH": "false",
        "KEYCLOAK_CLIENT_ID": "control-plane-api",
        "KEYCLOAK_REALM": "stoa",
        "TOOL_PERMISSIONS_SERVICE_CLIENT_IDS": "stoa-mcp-gateway",
        "GATEWAY_API_KEYS": "",
        "SENDER_CONSTRAINED_ENABLED": "false",
        "LOG_DEBUG_AUTH_TOKENS": "false",
        "LOG_DEBUG_AUTH_PAYLOAD": "false",
    }
)
root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root / "control-plane-api"))
listener = socket.socket()
listener.bind(("127.0.0.1", 0))
base_url = f"http://127.0.0.1:{listener.getsockname()[1]}"
os.environ["KEYCLOAK_URL"] = base_url

import uvicorn  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from jose import jwt  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from src.database import get_db  # noqa: E402
from src.models.tenant_tool_permission import TenantToolPermission  # noqa: E402
from src.routers.tenant_tool_permissions import router  # noqa: E402

# Reuse the existing signing fixture without copying key material into this file.
source = (root / "stoa-gateway/src/auth/jwt.rs").read_text()
literal = source.split('const TEST_PEM: &str = "', 1)[1].split('";', 1)[0]
pem = "".join(line.strip().removesuffix("\\") for line in literal.splitlines()).replace("\\n", "\n")
key = serialization.load_pem_private_key(pem.encode(), password=None)
public_der = key.public_key().public_bytes(
    serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
)
# The same fixture key stands in for the gateway client key registered in Keycloak.
client_public_pem = (
    key.public_key()
    .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    .decode()
)
CLIENT_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
modulus = source.split('const TEST_N: &str = "', 1)[1].split('";', 1)[0]
issuer = f"{base_url}/realms/stoa"
app = FastAPI()
app.include_router(router)
engine = create_async_engine("sqlite+aiosqlite:///:memory:")
sessions = async_sessionmaker(engine, expire_on_commit=False)


async def database():
    async with sessions() as session:
        yield session


app.dependency_overrides[get_db] = database


@app.get("/realms/stoa")
async def realm():
    return {"public_key": base64.b64encode(public_der).decode()}


@app.get("/realms/stoa/.well-known/openid-configuration")
async def discovery():
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/auth",
        "token_endpoint": f"{issuer}/protocol/openid-connect/token",
        "jwks_uri": f"{base_url}/jwks",
    }


@app.get("/jwks")
async def jwks():
    return {
        "keys": [
            {
                "kty": "RSA",
                "kid": "test-key",
                "use": "sig",
                "alg": "RS256",
                "n": modulus,
                "e": "AQAB",
            }
        ]
    }


@app.post("/realms/stoa/protocol/openid-connect/token")
async def token(request: Request):
    import time
    from urllib.parse import parse_qs

    from fastapi import HTTPException
    from jose import JWTError

    form = parse_qs((await request.body()).decode())
    if (
        form.get("grant_type") != ["client_credentials"]
        or form.get("client_id") != ["stoa-mcp-gateway"]
        or "client_secret" in form
        or form.get("client_assertion_type") != [CLIENT_ASSERTION_TYPE]
        or len(form.get("client_assertion", [])) != 1
    ):
        raise HTTPException(400)
    # private_key_jwt: the assertion must be signed by the registered client key.
    try:
        assertion = jwt.decode(
            form["client_assertion"][0],
            client_public_pem,
            algorithms=["RS256"],
            audience=f"{issuer}/protocol/openid-connect/token",
            issuer="stoa-mcp-gateway",
        )
    except JWTError as error:
        raise HTTPException(401) from error
    if assertion.get("sub") != "stoa-mcp-gateway" or not assertion.get("jti"):
        raise HTTPException(401)
    now = int(time.time())
    access_token = jwt.encode(
        {
            "sub": "permission-reader",
            "iss": issuer,
            "aud": "control-plane-api",
            "iat": now,
            "exp": now + 300,
            "azp": "stoa-mcp-gateway",
            "preferred_username": "service-account-stoa-mcp-gateway",
            "realm_access": {"roles": []},
            "resource_access": {"control-plane-api": {"roles": ["gateway-tool-permissions-read"]}},
        },
        pem,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    return {"access_token": access_token, "expires_in": 300}


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(TenantToolPermission.__table__.create)
    async with sessions() as session:
        # Tools are denied by default: echo_tool has an explicit allow row.
        # Page two contains an explicit deny; page one cannot authorize early.
        for index in range(101):
            session.add(
                TenantToolPermission(
                    # SQLite UUID columns have numeric affinity: retain text storage.
                    id=uuid.UUID(f"a0000000-0000-0000-0000-{index + 1:012x}"),
                    tenant_id="tenant-a",
                    mcp_server_id=uuid.UUID("a0000000-0000-0000-0000-000000000001"),
                    tool_name={0: "echo_tool", 100: "blocked_tool"}.get(index, f"tool_{index}"),
                    allowed=index != 100,
                    created_by="fixture",
                )
            )
        await session.commit()
    config = uvicorn.Config(app, log_level="error", lifespan="off")
    server = uvicorn.Server(config)
    # Readiness is polled by the Rust test; this line provides the allocated URL.
    print(json.dumps({"base_url": base_url}), flush=True)
    await server.serve(sockets=[listener])
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
