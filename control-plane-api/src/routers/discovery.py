"""
API/MCP Discovery — Smart Connector Catalog (CAB-1637, CAB-1639)

Three levels of discovery:
1. Curated catalog of pre-configured EU public APIs/MCP endpoints (YAML-driven)
2. Discovery by URL (auto-detect OpenAPI/MCP from pasted URL)
3. Search across catalog by keyword/domain
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.auth.dependencies import User, get_current_user
from src.catalog.loader import (
    CatalogResponse,
    SearchResult,
    get_catalog,
    get_categories,
)
from src.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/discovery", tags=["Discovery"])


# ---------- Schemas (detect only — catalog schemas moved to catalog.loader) ----------


class DetectRequest(BaseModel):
    url: str = Field(description="URL to probe for OpenAPI/MCP endpoints")


class DetectedSpec(BaseModel):
    url: str
    protocol: str = Field(description="openapi | mcp | unknown")
    title: str | None = None
    version: str | None = None
    description: str | None = None
    endpoints_count: int = 0
    tools_count: int = 0


# ---------- Endpoints ----------


@router.get(
    "/catalog",
    response_model=CatalogResponse,
    summary="List curated API/MCP catalog",
)
async def list_catalog(
    category: str | None = Query(None, description="Filter by category"),
    region: str | None = Query(None, description="Filter by region"),
    protocol: str | None = Query(None, description="Filter by protocol: openapi | mcp"),
    country: str | None = Query(None, description="Filter by country (ISO 3166-1 alpha-2)"),
    status: str | None = Query(None, description="Filter by status: verified | community | experimental"),
    _user: User = Depends(get_current_user),
) -> CatalogResponse:
    """Return curated catalog of pre-configured EU public APIs and MCP endpoints."""
    entries = list(get_catalog())

    if category:
        entries = [e for e in entries if e.category == category]
    if region:
        entries = [e for e in entries if region.lower() in e.region.lower()]
    if protocol:
        entries = [e for e in entries if e.protocol == protocol]
    if country:
        entries = [e for e in entries if e.country.upper() == country.upper()]
    if status:
        entries = [e for e in entries if e.status == status]

    categories = get_categories()

    return CatalogResponse(entries=entries, total=len(entries), categories=categories)


@router.post(
    "/detect",
    response_model=DetectedSpec,
    summary="Auto-detect API/MCP from URL",
)
async def detect_from_url(
    request: DetectRequest,
    _user: User = Depends(get_current_user),
) -> DetectedSpec:
    """Probe a URL to auto-detect OpenAPI spec or MCP endpoint."""
    url = request.url.rstrip("/")

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        # Try MCP capabilities first
        for mcp_path in ["/mcp/capabilities", "/.well-known/mcp.json", "/mcp"]:
            try:
                resp = await client.get(f"{url}{mcp_path}")
                if resp.status_code == 200:
                    data = resp.json()
                    tools_count = 0
                    if "tools" in data:
                        tools_count = len(data.get("tools", []))
                    elif "capabilities" in data and "tools" in data.get("capabilities", {}):
                        tools_count = len(data.get("capabilities", {}).get("tools", {}).get("listChanged", []))
                    return DetectedSpec(
                        url=f"{url}{mcp_path}",
                        protocol="mcp",
                        title=data.get("serverInfo", {}).get("name"),
                        version=data.get("serverInfo", {}).get("version"),
                        description=data.get("serverInfo", {}).get("description"),
                        tools_count=tools_count,
                    )
            except (httpx.HTTPError, ValueError):
                continue

        # Try OpenAPI spec endpoints
        for spec_path in [
            "/openapi.json",
            "/swagger.json",
            "/api-docs",
            "/v3/api-docs",
            "/docs/openapi.json",
            "",
        ]:
            try:
                target = f"{url}{spec_path}" if spec_path else url
                resp = await client.get(target)
                if resp.status_code == 200:
                    data = resp.json()
                    if "openapi" in data or "swagger" in data:
                        paths = data.get("paths", {})
                        return DetectedSpec(
                            url=target,
                            protocol="openapi",
                            title=data.get("info", {}).get("title"),
                            version=data.get("info", {}).get("version"),
                            description=data.get("info", {}).get("description"),
                            endpoints_count=len(paths),
                        )
            except (httpx.HTTPError, ValueError):
                continue

    raise HTTPException(
        status_code=422,
        detail="Could not detect OpenAPI or MCP endpoint at the given URL",
    )


@router.get(
    "/search",
    response_model=SearchResult,
    summary="Search catalog by keyword",
)
async def search_catalog(
    q: str = Query(..., min_length=2, description="Search query"),
    _user: User = Depends(get_current_user),
) -> SearchResult:
    """Search the curated catalog by keyword (name, description, tags)."""
    query_lower = q.lower()
    entries = get_catalog()

    matches = [
        e
        for e in entries
        if query_lower in e.name.lower()
        or query_lower in e.display_name.lower()
        or query_lower in e.description.lower()
        or any(query_lower in tag for tag in e.tags)
        or query_lower in e.category.lower()
    ]

    return SearchResult(entries=matches, total=len(matches), query=q)
