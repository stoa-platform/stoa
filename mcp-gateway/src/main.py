# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""STOA MCP Gateway - Main Application Entry Point.

Model Context Protocol Gateway for AI-Native API Management.
Exposes APIs as MCP Tools for LLM consumption.
"""

import asyncio
import ipaddress
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
import uvicorn
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from .config import get_settings
from .handlers import mcp_router, subscriptions_router, mcp_sse_router, sse_alias_router, servers_router, policy_router
from .middleware import MetricsMiddleware, ShadowMiddleware
from .services import get_tool_registry, shutdown_tool_registry, init_database, shutdown_database
from .services.tool_handlers import init_tool_handlers, shutdown_tool_handlers
from .services.external_server_loader import get_external_server_loader, shutdown_external_server_loader
from .k8s import get_tool_watcher, shutdown_tool_watcher
from .clients import init_core_api_client, shutdown_core_api_client
from .features.error_snapshots import (
    MCPErrorSnapshotMiddleware,
    get_mcp_snapshot_settings,
    snapshots_router,
)
from .features.error_snapshots.publisher import setup_snapshot_publisher, shutdown_snapshot_publisher

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger(__name__)

# Application state
app_state: dict[str, Any] = {
    "ready": False,
    "started_at": None,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    settings = get_settings()
    logger.info(
        "Starting STOA MCP Gateway",
        version=settings.app_version,
        environment=settings.environment,
    )

    # Startup
    app_state["started_at"] = datetime.now(timezone.utc)

    # Initialize Core API client (ADR-001 compliance)
    init_core_api_client(
        base_url=settings.control_plane_api_url,
        timeout=30.0
    )
    logger.info("Core API client initialized", base_url=settings.control_plane_api_url)

    # CAB-672/ADR-001: Initialize tool handlers (uses CoreAPIClient, no DB)
    try:
        init_tool_handlers()
        logger.info("Tool handlers initialized (ADR-001 compliant)")
    except Exception as e:
        logger.warning("Tool handlers initialization failed", error=str(e))

    # Initialize database (still needed for error snapshots and legacy features)
    try:
        await init_database()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning("Database initialization failed, using in-memory storage", error=str(e))

    # Initialize tool registry
    registry = await get_tool_registry()

    # Initialize MCP error snapshot publisher (Phase 3)
    snapshot_settings = get_mcp_snapshot_settings()
    if snapshot_settings.enabled:
        try:
            await setup_snapshot_publisher()
            logger.info("MCP error snapshot publisher initialized")
        except Exception as e:
            logger.warning("MCP error snapshot publisher failed to start", error=str(e))

    # Initialize K8s watcher and connect to registry
    if settings.k8s_watcher_enabled:
        # Get watcher without starting (to set callbacks first)
        watcher = await get_tool_watcher(start=False)

        # CAB-605: Define callbacks to connect watcher to registry
        # Use register_proxied_tool for ProxiedTool instances from K8s CRDs
        async def on_proxied_added(tool):
            """Register ProxiedTool from K8s CRD."""
            registry.register_proxied_tool(tool)
            logger.info(
                "K8s proxied tool registered",
                tool_name=tool.name,
                namespaced_name=tool.namespaced_name,
                internal_key=tool.internal_key,
                tenant_id=tool.tenant_id,
            )

        async def on_proxied_removed(tool_key):
            """Unregister ProxiedTool by key."""
            removed = registry.unregister_proxied_tool(tool_key)
            if removed:
                logger.info("K8s proxied tool unregistered", tool_key=tool_key)
            else:
                logger.warning("K8s proxied tool not found for removal", tool_key=tool_key)

        # Legacy callbacks for backward compatibility (non-ProxiedTool)
        async def on_tool_added(tool):
            registry.register(tool)
            logger.info("K8s tool registered", tool_name=tool.name)

        async def on_tool_removed(tool_name):
            registry.unregister(tool_name)
            logger.info("K8s tool unregistered", tool_name=tool_name)

        async def on_tool_modified(tool):
            registry.register(tool)  # Register overwrites existing
            logger.info("K8s tool updated", tool_name=tool.name)

        # Set callbacks BEFORE starting to catch initial events
        # CAB-605: Use dedicated proxied tool callbacks for CRD-sourced tools
        watcher.set_callbacks(
            on_added=on_tool_added,
            on_removed=on_tool_removed,
            on_modified=on_tool_modified,
            on_proxied_added=on_proxied_added,
            on_proxied_removed=on_proxied_removed,
        )

        # Now start the watcher
        await watcher.startup()

        logger.info("K8s watcher connected to tool registry")

    # Initialize external MCP server loader (Linear, GitHub, Slack, etc.)
    if settings.external_servers_enabled:
        try:
            external_loader = await get_external_server_loader()
            await external_loader.startup()
            logger.info(
                "External MCP server loader started",
                poll_interval=settings.external_server_poll_interval,
            )
        except Exception as e:
            logger.warning("External server loader failed to start", error=str(e))

    app_state["ready"] = True

    logger.info(
        "STOA MCP Gateway ready",
        base_domain=settings.base_domain,
        keycloak_url=settings.keycloak_url,
    )

    yield

    # Shutdown
    logger.info("Shutting down STOA MCP Gateway")
    app_state["ready"] = False

    # Cleanup MCP error snapshot publisher
    await shutdown_snapshot_publisher()

    # Cleanup external server loader
    await shutdown_external_server_loader()

    # Cleanup K8s watcher
    await shutdown_tool_watcher()

    # Cleanup tool registry
    await shutdown_tool_registry()

    # CAB-660: Cleanup tool handlers
    shutdown_tool_handlers()

    # Cleanup database
    await shutdown_database()

    # Cleanup Core API client
    shutdown_core_api_client()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Model Context Protocol Gateway for AI-Native API Management",
        version=settings.app_version,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    # Shadow mode middleware for Python → Rust migration
    if settings.shadow_mode_enabled:
        app.add_middleware(
            ShadowMiddleware,
            rust_gateway_url=settings.shadow_rust_gateway_url,
            timeout=settings.shadow_timeout_seconds,
        )
        logger.info(
            "Shadow mode ENABLED",
            rust_gateway_url=settings.shadow_rust_gateway_url,
        )

    # MCP Error Snapshot middleware (captures errors for debugging)
    snapshot_settings = get_mcp_snapshot_settings()
    if snapshot_settings.enabled:
        app.add_middleware(MCPErrorSnapshotMiddleware)
        logger.info("MCP error snapshot middleware enabled")

    # Metrics middleware (must be added first to capture all requests)
    if settings.enable_metrics:
        app.add_middleware(MetricsMiddleware)

    # CAB-950: Secured CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=settings.cors_allow_methods.split(","),
        allow_headers=settings.cors_allow_headers.split(","),
        expose_headers=settings.cors_expose_headers.split(","),
        max_age=settings.cors_max_age,
    )

    # Register routes
    register_routes(app)

    # Register MCP router
    app.include_router(mcp_router)

    # Register policy management router (CAB-875)
    app.include_router(policy_router)

    # Register subscriptions router
    app.include_router(subscriptions_router)

    # Register MCP SSE router for native Claude Desktop support
    app.include_router(mcp_sse_router)

    # Register servers router for server-based subscriptions
    app.include_router(servers_router)

    # Register SSE alias router for /sse endpoint (Phase 2)
    app.include_router(sse_alias_router)

    # Register error snapshots router (Phase 4)
    snapshot_settings = get_mcp_snapshot_settings()
    if snapshot_settings.enabled:
        app.include_router(snapshots_router)
        logger.info("Error snapshots API enabled")

    # Serve favicon - try multiple paths for Docker and local dev
    @app.get("/favicon.ico", include_in_schema=False)
    @app.get("/favicon.svg", include_in_schema=False)
    async def favicon():
        """Serve STOA favicon."""
        import os
        # Try multiple paths: Docker (/app/static), relative from src
        possible_paths = [
            "/app/static/favicon.svg",  # Docker container path
            os.path.join(os.path.dirname(__file__), "..", "static", "favicon.svg"),  # Local dev
            os.path.join(os.getcwd(), "static", "favicon.svg"),  # CWD based
        ]
        for favicon_path in possible_paths:
            if os.path.exists(favicon_path):
                return FileResponse(favicon_path, media_type="image/svg+xml")
        # Return empty response if file not found
        return Response(status_code=204)

    return app


def _is_internal_request(request: Request) -> bool:
    """Check if request comes from internal network (K8s cluster).

    Detection strategy:
    Kubernetes probes access the pod directly via the service,
    while external requests go through the ingress (ALB -> nginx -> pod).

    We detect external requests by checking if the request went through
    the ingress, which sets the X-Request-ID header (nginx adds this).

    Internal networks (for direct connections):
    - 10.0.0.0/8 (K8s pod network)
    - 172.16.0.0/12 (K8s service network)
    - 192.168.0.0/16 (Private networks)
    - 127.0.0.0/8 (Localhost)
    """
    # Check direct client IP
    client_ip = request.client.host if request.client else "0.0.0.0"

    # Check if request came through ingress by looking for typical ingress headers
    # X-Request-ID is added by nginx-ingress for all requests
    has_request_id = bool(request.headers.get("X-Request-ID", "").strip())
    # X-Forwarded headers are added by ALB/nginx for external requests
    has_forwarded = bool(request.headers.get("X-Forwarded-For", "").strip())
    has_forwarded_proto = bool(request.headers.get("X-Forwarded-Proto", "").strip())

    # If request has typical ingress headers, it's likely external
    # unless the original IP is also internal (rare case)
    if has_request_id or has_forwarded or has_forwarded_proto:
        # Request likely came through ingress - assume external
        return False

    # No ingress headers - direct connection from within cluster
    try:
        ip = ipaddress.ip_address(client_ip)
        internal_networks = [
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
            ipaddress.ip_network("127.0.0.0/8"),
        ]
        return any(ip in network for network in internal_networks)
    except ValueError:
        return False


def register_routes(app: FastAPI) -> None:
    """Register all application routes."""

    # K8s-standard health endpoints (CAB-308)
    @app.get("/health/live", tags=["Health"])
    async def health_live(request: Request) -> dict[str, Any]:
        """Liveness probe - process is alive (CAB-308).

        K8s will restart the pod if this fails.
        Only accessible from internal cluster network.
        """
        if not _is_internal_request(request):
            raise HTTPException(status_code=403, detail="Forbidden - internal only")

        settings = get_settings()
        return {
            "status": "healthy",
            "version": settings.app_version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/health/ready", tags=["Health"])
    async def health_ready(request: Request) -> JSONResponse:
        """Readiness probe - ready to accept traffic (CAB-308).

        K8s will remove pod from service if this fails.
        Only accessible from internal cluster network.
        """
        if not _is_internal_request(request):
            raise HTTPException(status_code=403, detail="Forbidden - internal only")

        settings = get_settings()

        checks: dict[str, Any] = {
            "app_ready": app_state["ready"],
        }

        is_ready = all(checks.values())

        response = {
            "status": "healthy" if is_ready else "unhealthy",
            "version": settings.app_version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": checks,
        }

        return JSONResponse(
            content=response,
            status_code=200 if is_ready else 503,
        )

    @app.get("/health/startup", tags=["Health"])
    async def health_startup(request: Request) -> dict[str, Any]:
        """Startup probe - initial boot complete (CAB-308).

        K8s uses this during pod startup.
        Only accessible from internal cluster network.
        """
        if not _is_internal_request(request):
            raise HTTPException(status_code=403, detail="Forbidden - internal only")

        settings = get_settings()
        return {
            "status": "healthy",
            "version": settings.app_version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # Legacy endpoints (backward compatibility)
    @app.get("/health", tags=["Health"], include_in_schema=False)
    async def health_check(request: Request) -> dict[str, Any]:
        """Legacy health check endpoint (deprecated, use /health/live)."""
        if not _is_internal_request(request):
            client = request.client.host if request.client else "unknown"
            logger.info("Blocked external health check request", client_ip=client)
            raise HTTPException(status_code=403, detail="Forbidden - internal only")

        settings = get_settings()
        return {
            "status": "healthy",
            "service": "stoa-mcp-gateway",
            "version": settings.app_version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/ready", tags=["Health"], include_in_schema=False)
    async def readiness_check(request: Request) -> JSONResponse:
        """Legacy readiness endpoint (deprecated, use /health/ready)."""
        if not _is_internal_request(request):
            raise HTTPException(status_code=403, detail="Forbidden - internal only")

        settings = get_settings()

        checks: dict[str, Any] = {
            "service": "stoa-mcp-gateway",
            "version": settings.app_version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": {
                "app_ready": app_state["ready"],
            },
        }

        is_ready = all(checks["checks"].values())
        checks["status"] = "ready" if is_ready else "not_ready"

        return JSONResponse(
            content=checks,
            status_code=200 if is_ready else 503,
        )

    @app.get("/live", tags=["Health"], include_in_schema=False)
    async def liveness_check(request: Request) -> dict[str, str]:
        """Legacy liveness endpoint (deprecated, use /health/live)."""
        if not _is_internal_request(request):
            raise HTTPException(status_code=403, detail="Forbidden - internal only")

        return {"status": "alive"}

    @app.get("/metrics", tags=["Observability"])
    async def metrics(request: Request) -> Response:
        """Prometheus metrics endpoint.

        Only accessible from internal cluster network.
        """
        if not _is_internal_request(request):
            raise HTTPException(status_code=403, detail="Forbidden - internal only")

        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    @app.get("/", tags=["Info"])
    async def root() -> dict[str, Any]:
        """Root endpoint with service information."""
        settings = get_settings()
        return {
            "service": "stoa-mcp-gateway",
            "description": "Model Context Protocol Gateway for AI-Native API Management",
            "version": settings.app_version,
            "mcp": {
                "tools": "/mcp/v1/tools",
                "sse": "/mcp/sse",
                "docs": "https://modelcontextprotocol.io",
            },
        }

    # ============================================
    # PUBLIC HEALTH/STATUS ENDPOINTS (Phase 2)
    # These are public alternatives to the internal-only /health endpoints
    # ============================================

    @app.get("/healthz", tags=["Health"])
    async def healthz_public() -> dict[str, Any]:
        """Public health endpoint.

        Unlike /health (internal-only for K8s probes), this is accessible externally.
        """
        settings = get_settings()
        return {
            "status": "healthy",
            "service": "stoa-mcp-gateway",
            "version": settings.app_version,
        }

    @app.get("/status", tags=["Health"])
    async def status_public() -> dict[str, Any]:
        """Public detailed status endpoint."""
        settings = get_settings()
        return {
            "status": "healthy" if app_state["ready"] else "starting",
            "service": "stoa-mcp-gateway",
            "version": settings.app_version,
            "environment": settings.environment,
            "started_at": app_state["started_at"].isoformat() if app_state["started_at"] else None,
        }

    @app.get("/api/health", tags=["Health"])
    async def api_health() -> dict[str, Any]:
        """API health endpoint (public)."""
        return await healthz_public()

    @app.get("/api/status", tags=["Health"])
    async def api_status() -> dict[str, Any]:
        """API status endpoint (public)."""
        return await status_public()

    # ============================================
    # ADMIN ENDPOINTS
    # ============================================

    @app.post("/admin/reload-external-servers", tags=["Admin"])
    async def reload_external_servers(request: Request) -> dict[str, Any]:
        """Force reload external MCP server configurations.

        Only accessible from internal cluster network.
        Triggers immediate sync instead of waiting for next poll interval.
        """
        if not _is_internal_request(request):
            raise HTTPException(status_code=403, detail="Forbidden - internal only")

        settings = get_settings()
        if not settings.external_servers_enabled:
            return {"status": "disabled", "message": "External servers feature is disabled"}

        loader = await get_external_server_loader()
        result = await loader.reload()
        return result

    @app.get("/admin/external-servers/status", tags=["Admin"])
    async def external_servers_status(request: Request) -> dict[str, Any]:
        """Get external MCP server loader status.

        Only accessible from internal cluster network.
        """
        if not _is_internal_request(request):
            raise HTTPException(status_code=403, detail="Forbidden - internal only")

        settings = get_settings()
        if not settings.external_servers_enabled:
            return {"enabled": False}

        loader = await get_external_server_loader()
        return loader.get_status()

    # ============================================
    # API DISCOVERY ENDPOINTS (Phase 2)
    # ============================================

    @app.get("/api", tags=["Info"])
    async def api_info() -> dict[str, Any]:
        """API root information."""
        settings = get_settings()
        return {
            "service": "stoa-mcp-gateway",
            "version": settings.app_version,
            "api_version": "v1",
            "endpoints": {
                "tools": "/api/tools",
                "info": "/api/info",
                "health": "/api/health",
                "status": "/api/status",
                "apis": "/api/apis",
            },
        }

    @app.get("/api/v1", tags=["Info"])
    async def api_v1_info() -> dict[str, Any]:
        """API v1 information."""
        return await api_info()

    @app.get("/api/info", tags=["Info"])
    async def api_info_detailed() -> dict[str, Any]:
        """STOA MCP Gateway detailed info."""
        settings = get_settings()
        registry = await get_tool_registry()
        result = registry.list_tools(limit=1000)
        return {
            "service": "stoa-mcp-gateway",
            "version": settings.app_version,
            "environment": settings.environment,
            "tools_count": len(result.tools),
            "mcp": {
                "protocol_version": "2025-11-25",
                "transport": "Streamable HTTP (SSE)",
                "endpoints": {
                    "sse": "/mcp/sse",
                    "tools": "/tools",
                },
            },
        }

    @app.get("/api/apis", tags=["Info"])
    async def api_apis() -> dict[str, Any]:
        """List available STOA APIs."""
        settings = get_settings()
        return {
            "apis": [
                {"name": "MCP Gateway", "url": f"https://mcp.{settings.base_domain}", "description": "AI-Native API access via MCP"},
                {"name": "Control Plane API", "url": f"https://api.{settings.base_domain}", "description": "Platform management API"},
                {"name": "Developer Portal", "url": f"https://portal.{settings.base_domain}", "description": "API documentation and testing"},
                {"name": "API Gateway Runtime", "url": f"https://apis.{settings.base_domain}", "description": "Runtime API gateway"},
            ],
        }

    @app.get("/api/tools", tags=["MCP REST"])
    async def api_tools() -> dict[str, Any]:
        """List MCP tools (alias for /tools)."""
        return await list_tools_rest()

    # ============================================
    # OPENAPI/DOCS ENDPOINTS (Phase 2)
    # Enable OpenAPI spec access even when debug=False
    # ============================================

    @app.get("/openapi.json", tags=["Docs"], include_in_schema=False)
    async def openapi_json() -> dict[str, Any]:
        """OpenAPI specification."""
        return app.openapi()

    @app.get("/api/openapi.json", tags=["Docs"], include_in_schema=False)
    async def api_openapi_json() -> dict[str, Any]:
        """OpenAPI specification (alias)."""
        return app.openapi()

    # ============================================
    # MCP REST ENDPOINTS (existing)
    # ============================================

    # Claude.ai REST endpoints for MCP tools (hybrid mode)
    @app.get("/tools", tags=["MCP REST"])
    async def list_tools_rest() -> dict[str, Any]:
        """List available MCP tools (REST endpoint for Claude.ai hybrid mode)."""
        from .services import get_tool_registry

        print("[MCP REST] GET /tools called", flush=True)
        registry = await get_tool_registry()
        result = registry.list_tools(limit=1000)

        tools = []
        for tool in result.tools:
            schema = tool.input_schema
            if schema:
                input_schema = schema.model_dump() if hasattr(schema, 'model_dump') else dict(schema)
            else:
                input_schema = {"type": "object", "properties": {}}

            tools.append({
                "name": tool.name,
                "description": tool.description or "",
                "inputSchema": input_schema,
            })

        print(f"[MCP REST] Returning {len(tools)} tools", flush=True)
        return {"tools": tools}

    @app.get("/subscriptions", tags=["MCP REST"])
    async def list_subscriptions_rest() -> dict[str, Any]:
        """List subscriptions (REST endpoint for Claude.ai hybrid mode)."""
        print("[MCP REST] GET /subscriptions called", flush=True)
        # Return empty subscriptions - Claude.ai checks this endpoint
        return {"subscriptions": []}

    @app.post("/tools/{tool_name}", tags=["MCP REST"])
    async def call_tool_rest(tool_name: str, request: Request) -> dict[str, Any]:
        """Call an MCP tool (REST endpoint for Claude.ai hybrid mode)."""
        import json
        from .services import get_tool_registry
        from .models.mcp import ToolInvocation

        body = await request.json()
        arguments = body.get("arguments", {})

        print(f"[MCP REST] POST /tools/{tool_name} called with args: {arguments}", flush=True)

        registry = await get_tool_registry()
        tool = registry.get(tool_name)

        if not tool:
            return JSONResponse(
                content={"error": f"Tool not found: {tool_name}"},
                status_code=404,
            )

        try:
            invocation = ToolInvocation(
                name=tool_name,
                arguments=arguments,
            )
            result = await registry.invoke(invocation)

            content = []
            for item in result.content:
                if hasattr(item, 'text'):
                    content.append({"type": "text", "text": item.text})
                else:
                    content.append({"type": "text", "text": str(item)})

            print(f"[MCP REST] Tool {tool_name} result: is_error={result.is_error}", flush=True)
            return {
                "content": content,
                "isError": result.is_error,
            }
        except Exception as e:
            print(f"[MCP REST] Tool {tool_name} error: {e}", flush=True)
            return {
                "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                "isError": True,
            }

    # OAuth Authorization Server Metadata (RFC 8414) for Claude.ai integration
    @app.get("/.well-known/oauth-authorization-server", tags=["OAuth"])
    async def oauth_authorization_server_metadata() -> dict[str, Any]:
        """OAuth 2.0 Authorization Server Metadata (RFC 8414).

        Required by Claude.ai for OAuth integration with remote MCP servers.
        Points to local proxy endpoints for token/registration to handle network issues.
        """
        settings = get_settings()
        keycloak_issuer = settings.keycloak_issuer
        mcp_gateway_url = f"https://mcp.{settings.base_domain}"

        return {
            "issuer": keycloak_issuer,
            "authorization_endpoint": f"{keycloak_issuer}/protocol/openid-connect/auth",
            # Use our proxy for token endpoint (Claude.ai may not reach auth.gostoa.dev)
            "token_endpoint": f"{mcp_gateway_url}/oauth/token",
            "userinfo_endpoint": f"{keycloak_issuer}/protocol/openid-connect/userinfo",
            "jwks_uri": f"{keycloak_issuer}/protocol/openid-connect/certs",
            # Use our proxy for registration endpoint
            "registration_endpoint": f"{mcp_gateway_url}/oauth/register",
            "scopes_supported": ["openid", "profile", "email", "offline_access"],
            "response_types_supported": ["code", "token", "id_token", "code token", "code id_token", "token id_token", "code token id_token"],
            "grant_types_supported": ["authorization_code", "refresh_token", "client_credentials", "password"],
            "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post", "private_key_jwt", "none"],
            "code_challenge_methods_supported": ["S256", "plain"],
            "introspection_endpoint": f"{keycloak_issuer}/protocol/openid-connect/token/introspect",
            "revocation_endpoint": f"{keycloak_issuer}/protocol/openid-connect/revoke",
            "end_session_endpoint": f"{keycloak_issuer}/protocol/openid-connect/logout",
        }

    @app.get("/.well-known/openid-configuration", tags=["OAuth"])
    async def openid_configuration() -> dict[str, Any]:
        """OpenID Connect Discovery (RFC 8414).

        Points to local proxy endpoints for token/registration.
        """
        settings = get_settings()
        keycloak_issuer = settings.keycloak_issuer
        mcp_gateway_url = f"https://mcp.{settings.base_domain}"

        return {
            "issuer": keycloak_issuer,
            "authorization_endpoint": f"{keycloak_issuer}/protocol/openid-connect/auth",
            # Use our proxy for token endpoint
            "token_endpoint": f"{mcp_gateway_url}/oauth/token",
            "userinfo_endpoint": f"{keycloak_issuer}/protocol/openid-connect/userinfo",
            "jwks_uri": f"{keycloak_issuer}/protocol/openid-connect/certs",
            "end_session_endpoint": f"{keycloak_issuer}/protocol/openid-connect/logout",
            "check_session_iframe": f"{keycloak_issuer}/protocol/openid-connect/login-status-iframe.html",
            "introspection_endpoint": f"{keycloak_issuer}/protocol/openid-connect/token/introspect",
            "revocation_endpoint": f"{keycloak_issuer}/protocol/openid-connect/revoke",
            # Use our proxy for registration endpoint
            "registration_endpoint": f"{mcp_gateway_url}/oauth/register",
            "scopes_supported": ["openid", "profile", "email", "offline_access", "address", "phone"],
            "response_types_supported": ["code", "token", "id_token", "code token", "code id_token", "token id_token", "code token id_token"],
            "grant_types_supported": ["authorization_code", "refresh_token", "client_credentials", "password", "urn:ietf:params:oauth:grant-type:device_code"],
            "subject_types_supported": ["public", "pairwise"],
            "id_token_signing_alg_values_supported": ["RS256", "ES256"],
            "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post", "private_key_jwt", "none"],
            "code_challenge_methods_supported": ["S256", "plain"],
            "claims_supported": ["sub", "iss", "aud", "exp", "iat", "name", "email", "preferred_username", "given_name", "family_name"],
        }

    # OAuth Protected Resource Metadata (RFC 9449) for Claude.ai MCP integration
    @app.get("/.well-known/oauth-protected-resource", tags=["OAuth"])
    @app.get("/.well-known/oauth-protected-resource/{path:path}", tags=["OAuth"])
    async def oauth_protected_resource_metadata(path: str = "") -> dict[str, Any]:
        """OAuth 2.0 Protected Resource Metadata (RFC 9449).

        Required by Claude.ai for MCP OAuth integration.
        Points to the authorization server metadata.
        """
        settings = get_settings()
        keycloak_issuer = settings.keycloak_issuer
        mcp_gateway_url = f"https://mcp.{settings.base_domain}"

        return {
            "resource": mcp_gateway_url,
            "authorization_servers": [keycloak_issuer],
            "scopes_supported": ["openid", "profile", "email"],
            "bearer_methods_supported": ["header"],
            "resource_documentation": "https://docs.gostoa.dev/mcp",
        }

    # OAuth Token Proxy - Proxies token requests to Keycloak
    # This is needed because Claude.ai servers may not be able to reach auth.gostoa.dev directly
    @app.post("/oauth/token", tags=["OAuth"])
    async def oauth_token_proxy(request: Request) -> JSONResponse:
        """Proxy OAuth token requests to Keycloak.

        This endpoint proxies token exchange requests to Keycloak's token endpoint.
        Required because Claude.ai's backend servers may not have direct access to auth.gostoa.dev.
        """
        settings = get_settings()
        keycloak_token_url = f"{settings.keycloak_issuer}/protocol/openid-connect/token"

        # Get the form data from the request
        form_data = await request.form()
        form_dict = {key: value for key, value in form_data.items()}

        logger.info(
            "Proxying token request to Keycloak",
            grant_type=form_dict.get("grant_type"),
            client_id=form_dict.get("client_id"),
        )

        # Forward headers (especially Authorization for client credentials)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if "Authorization" in request.headers:
            headers["Authorization"] = request.headers["Authorization"]

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    keycloak_token_url,
                    data=form_dict,
                    headers=headers,
                )

                logger.info(
                    "Keycloak token response",
                    status_code=response.status_code,
                    client_id=form_dict.get("client_id"),
                )

                # Return the response from Keycloak
                return JSONResponse(
                    content=response.json(),
                    status_code=response.status_code,
                    headers={
                        "Cache-Control": "no-store",
                        "Pragma": "no-cache",
                    },
                )

        except httpx.HTTPError as e:
            logger.error("Failed to proxy token request to Keycloak", error=str(e))
            return JSONResponse(
                content={"error": "server_error", "error_description": "Failed to contact authorization server"},
                status_code=502,
            )

    # OAuth Registration Proxy - Proxies DCR requests to Keycloak
    # Forces public client creation for MCP OAuth (PKCE-based authentication)
    @app.post("/oauth/register", tags=["OAuth"])
    async def oauth_register_proxy(request: Request) -> JSONResponse:
        """Proxy OAuth Dynamic Client Registration to Keycloak.

        This endpoint:
        1. Creates the client via standard DCR
        2. Modifies the client via Admin API to make it public (PKCE-only)

        Claude.ai uses PKCE for MCP OAuth and doesn't have client secrets.
        Keycloak DCR doesn't properly support token_endpoint_auth_method: none,
        so we patch the client after creation.
        """
        import json

        settings = get_settings()
        keycloak_register_url = f"{settings.keycloak_issuer}/clients-registrations/openid-connect"
        keycloak_admin_url = f"{settings.keycloak_url}/admin/realms/{settings.keycloak_realm}"
        keycloak_token_url = f"{settings.keycloak_url}/realms/master/protocol/openid-connect/token"

        body = await request.body()

        # Parse DCR request for logging
        try:
            dcr_request = json.loads(body)
            logger.info(
                "DCR request received",
                client_name=dcr_request.get("client_name"),
                token_endpoint_auth_method=dcr_request.get("token_endpoint_auth_method"),
                redirect_uris=dcr_request.get("redirect_uris"),
            )
        except json.JSONDecodeError:
            dcr_request = {}

        headers = {
            "Content-Type": "application/json",
        }
        if "Authorization" in request.headers:
            headers["Authorization"] = request.headers["Authorization"]

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Step 1: Create client via DCR
                response = await client.post(
                    keycloak_register_url,
                    content=body,
                    headers=headers,
                )

                if response.status_code != 201:
                    logger.warning("DCR failed", status_code=response.status_code)
                    return JSONResponse(
                        content=response.json(),
                        status_code=response.status_code,
                    )

                response_data = response.json()
                client_id = response_data.get("client_id")

                logger.info(
                    "DCR client created, now patching to public",
                    client_id=client_id,
                )

                # Step 2: Get admin token to modify the client
                admin_token_response = await client.post(
                    keycloak_token_url,
                    data={
                        "grant_type": "password",
                        "client_id": "admin-cli",
                        "username": "admin",
                        "password": settings.keycloak_admin_password,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                if admin_token_response.status_code != 200:
                    logger.warning(
                        "Failed to get admin token, client will be confidential",
                        status_code=admin_token_response.status_code,
                    )
                    return JSONResponse(content=response_data, status_code=201)

                admin_token = admin_token_response.json().get("access_token")

                # Step 3: Get the full client configuration first
                # Keycloak Admin API PUT replaces the entire resource, so we need the full config
                get_client_response = await client.get(
                    f"{keycloak_admin_url}/clients/{client_id}",
                    headers={
                        "Authorization": f"Bearer {admin_token}",
                    },
                )

                if get_client_response.status_code != 200:
                    logger.warning(
                        "Failed to get client for patching",
                        client_id=client_id,
                        status_code=get_client_response.status_code,
                    )
                    return JSONResponse(content=response_data, status_code=201)

                # Step 4: Modify the client to make it public with PKCE
                full_client = get_client_response.json()
                full_client["publicClient"] = True
                # Ensure attributes dict exists
                if "attributes" not in full_client or full_client["attributes"] is None:
                    full_client["attributes"] = {}
                full_client["attributes"]["pkce.code.challenge.method"] = "S256"

                logger.info(
                    "Updating client to public with PKCE",
                    client_id=client_id,
                    current_public=full_client.get("publicClient"),
                )

                # Step 5: PUT the modified client back
                patch_response = await client.put(
                    f"{keycloak_admin_url}/clients/{client_id}",
                    json=full_client,
                    headers={
                        "Authorization": f"Bearer {admin_token}",
                        "Content-Type": "application/json",
                    },
                )

                if patch_response.status_code in (200, 204):
                    logger.info(
                        "Client patched to public successfully",
                        client_id=client_id,
                    )
                    # Update response to reflect public client
                    response_data["token_endpoint_auth_method"] = "none"
                    response_data.pop("client_secret", None)
                else:
                    logger.warning(
                        "Failed to patch client to public",
                        client_id=client_id,
                        status_code=patch_response.status_code,
                        response=patch_response.text[:500],
                    )

                return JSONResponse(
                    content=response_data,
                    status_code=201,
                )

        except httpx.HTTPError as e:
            logger.error("Failed to proxy DCR request to Keycloak", error=str(e))
            return JSONResponse(
                content={"error": "server_error", "error_description": "Failed to contact authorization server"},
                status_code=502,
            )



# Create the application instance
app = create_app()


def main() -> None:
    """Run the application with uvicorn."""
    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
