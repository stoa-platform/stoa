"""Explicit opt-in: real CP HTTP/SSE + local database + real Envoy container.

Only authentication of the test operator and fault injection are fixture code.
Production routers, repositories, bus, Go transports, adapters and ADS are used.
"""

import asyncio
import ipaddress
import json
import os
import re
import socket
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
import uvicorn
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.auth.dependencies import User, get_current_user
from src.config import settings
from src.database import get_db
from src.events.event_bus import event_bus
from src.models.catalog import APICatalog
from src.models.gateway_deployment import GatewayDeployment
from src.models.gateway_instance import GatewayInstance, GatewayType
from src.models.gateway_policy import GatewayPolicy, GatewayPolicyBinding, PolicyScope, PolicyType
from src.routers import gateway_deployments, gateway_internal
from tests.o1_support import compile_jsonb_sqlite  # registers the SQLite JSON projection

ENVOY = "envoyproxy/envoy@sha256:29d778ba078e0404d18fa45ffb834c062071b0f81dc0a6a41501ce8e23a0059f"
pytestmark = pytest.mark.skipif(os.getenv("O1_RUN_ENVOY") != "1", reason="local Envoy opt-in required")


async def command(*args: str, env: dict | None = None) -> str:
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    output, _ = await process.communicate()
    safe = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[local address]", output.decode(errors="replace"))
    safe = safe.replace(str(ipaddress.IPv6Address(1)), "[loopback]")
    if process.returncode:
        evidence = os.getenv("O1_EVIDENCE_DIR")
        if evidence:
            Path(evidence).mkdir(parents=True, exist_ok=True)
            (Path(evidence) / "o1-last-failure.log").write_text(safe)
    assert process.returncode == 0, safe[:6000] + safe[-6000:]
    return safe


@pytest.mark.asyncio
async def test_o1_offline_envoy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started_at = datetime.now(ZoneInfo("Europe/Paris")).isoformat()
    assert compile_jsonb_sqlite is not None
    monkeypatch.setattr(settings, "DEPLOY_MODE", "sse_only")
    monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "o1-local-test-key")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cp.sqlite'}")
    async with engine.begin() as connection:
        await connection.execute(text("PRAGMA journal_mode=WAL"))
        for model in (APICatalog, GatewayInstance, GatewayDeployment, GatewayPolicy, GatewayPolicyBinding):
            await connection.run_sync(model.__table__.create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    own, foreign = uuid4(), uuid4()
    async with sessions() as db:
        for identity, name in ((own, "own"), (foreign, "foreign")):
            db.add(
                GatewayInstance(
                    id=identity,
                    name=name,
                    display_name=name,
                    gateway_type=GatewayType.STOA,
                    base_url="http://gateway.test",
                    environment="dev",
                    tenant_id="o1-test",
                )
            )
        await db.commit()

    async def database():
        async with sessions() as db:
            yield db

    async def operator() -> User:
        return User(id="local-operator", email="operator@example.test", username="local", roles=["cpi-admin"])

    app = FastAPI()
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = operator
    app.include_router(gateway_deployments.router)
    app.include_router(gateway_internal.router)
    fault = {"empty": False}
    acknowledgements: list[dict] = []

    @app.middleware("http")
    async def observations(request: Request, call_next):
        if request.url.path.endswith("/config") and fault["empty"]:
            return JSONResponse({"pending_deployments": [], "pending_policies": []})
        payload = await request.json() if request.url.path.endswith("/sync-ack") else None
        response = await call_next(request)
        if payload is not None and response.status_code == 200:
            acknowledgements.extend(payload.get("synced_policies", []))
        return response

    @app.get("/o1/identity")
    async def identity():
        return {"own": str(own), "foreign": str(foreign)}

    @app.get("/o1/acks")
    async def acks():
        return acknowledgements[-100:]

    @app.post("/o1/fault")
    async def inject_fault(request: Request):
        fault["empty"] = bool((await request.json())["empty"])
        return {"ok": True}

    @app.post("/o1/catalog")
    async def catalog(request: Request, db: AsyncSession = Depends(database)):
        value = await request.json()
        entry = APICatalog(
            id=uuid4(),
            tenant_id="o1-test",
            api_id=value["api_id"],
            api_name=value["api_id"],
            version="1",
            api_metadata={"backend_url": value["backend_url"]},
            openapi_spec={"openapi": "3.0.0", "paths": {"/ping": {"get": {}}}},
        )
        db.add(entry)
        await db.commit()
        return {"id": str(entry.id)}

    @app.post("/o1/policy")
    async def policy(request: Request, db: AsyncSession = Depends(database)):
        value = await request.json()
        if value.get("id"):
            entry = await db.get(GatewayPolicy, UUID(value["id"]))
            assert entry is not None
            entry.config = value["config"]
        else:
            entry = GatewayPolicy(
                id=uuid4(),
                name=str(uuid4()),
                tenant_id="o1-test",
                policy_type=PolicyType(value["type"]),
                scope=PolicyScope.API,
                config=value["config"],
                enabled=True,
            )
            entry.bindings = [
                GatewayPolicyBinding(
                    api_catalog_id=UUID(value["target"]),
                    gateway_instance_id=own,
                    enabled=True,
                )
            ]
            db.add(entry)
        await db.commit()
        await event_bus.publish("o1-test", "sync-policy", {}, gateway_id=str(own))
        return {"id": str(entry.id)}

    @app.delete("/o1/policy/{policy_id}")
    async def remove_policy(policy_id: UUID, db: AsyncSession = Depends(database)):
        await db.execute(delete(GatewayPolicyBinding).where(GatewayPolicyBinding.policy_id == policy_id))
        await db.execute(delete(GatewayPolicy).where(GatewayPolicy.id == policy_id))
        await db.commit()
        await event_bus.publish("o1-test", "sync-policy", {}, gateway_id=str(own))
        return {"ok": True}

    listener = socket.socket()
    listener.bind(("localhost", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False, lifespan="off"))
    serving = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                await asyncio.sleep(0.01)
        repo = Path(__file__).resolve().parents[2]
        architecture = (await command("docker", "image", "inspect", ENVOY, "--format", "{{.Architecture}}")).strip()
        env = {
            **os.environ,
            "GOOS": "linux",
            "GOARCH": architecture,
            "CGO_ENABLED": "0",
            "GOPROXY": "off",
            "GOSUMDB": "off",
            "GOTOOLCHAIN": "local",
        }
        build = await command(
            "go",
            "-C",
            str(repo / "stoa-go"),
            "test",
            "-tags=o1integration",
            "-c",
            "-o",
            str(tmp_path / "o1.test"),
            "./internal/connect",
            env=env,
        )
        sha = (await command("git", "-C", str(repo), "rev-parse", "HEAD")).strip()
        output = await command(
            "docker",
            "run",
            "--rm",
            "--pull=never",
            "--name",
            f"o1-soiree-{uuid4().hex[:10]}",
            "--add-host=host.docker.internal:host-gateway",
            "--mount",
            f"type=bind,src={tmp_path},dst=/work",
            "--env",
            f"O1_CP_URL=http://host.docker.internal:{port}",
            "--env",
            "O1_RESULT=/work/result.json",
            "--env",
            f"O1_CANDIDATE_SHA={sha}",
            "--env",
            f"O1_ENVOY_IMAGE={ENVOY}",
            "--entrypoint",
            "/work/o1.test",
            ENVOY,
            "-test.run=^TestO1OfflineEnvoy$",
            "-test.v",
            "-test.timeout=120s",
        )
        result = json.loads((tmp_path / "result.json").read_text())
        assert result["verdict"] == "OK"
        result["started_at_paris"] = started_at
        result["finished_at_paris"] = datetime.now(ZoneInfo("Europe/Paris")).isoformat()
        result["platform"] = f"linux/{architecture}"
        evidence = Path(os.getenv("O1_EVIDENCE_DIR", str(tmp_path)))
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "o1-result.json").write_text(json.dumps(result, indent=2) + "\n")
        (evidence / "o1-envoy.log").write_text(build + output)
    finally:
        server.should_exit = True
        await serving
        await engine.dispose()
