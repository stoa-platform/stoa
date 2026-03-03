"""
API/MCP Discovery — Smart Connector Catalog (CAB-1637)

Three levels of discovery:
1. Curated catalog of pre-configured EU public APIs/MCP endpoints
2. Discovery by URL (auto-detect OpenAPI/MCP from pasted URL)
3. Search across catalog by keyword/domain
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.auth.dependencies import User, get_current_user
from src.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/discovery", tags=["Discovery"])


# ---------- Schemas ----------


class CatalogEntry(BaseModel):
    id: str
    name: str
    display_name: str
    description: str
    category: str
    region: str = "EU"
    spec_url: str | None = None
    mcp_endpoint: str | None = None
    protocol: str = Field(description="openapi | mcp | graphql")
    tags: list[str] = []
    documentation_url: str | None = None
    icon: str | None = None


class CatalogResponse(BaseModel):
    entries: list[CatalogEntry]
    total: int
    categories: list[str]


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


class SearchResult(BaseModel):
    entries: list[CatalogEntry]
    total: int
    query: str


# ---------- Curated Catalog Data ----------

CURATED_CATALOG: list[dict] = [
    {
        "id": "eu-inpi-fr",
        "name": "inpi-fr",
        "display_name": "INPI (France)",
        "description": "Institut National de la Propriété Industrielle — French business registry (RNCS/RNE)",
        "category": "business-registry",
        "region": "EU-FR",
        "spec_url": "https://data.inpi.fr/api/docs",
        "protocol": "openapi",
        "tags": ["business", "registry", "france", "rncs"],
        "documentation_url": "https://data.inpi.fr/",
        "icon": "building-2",
    },
    {
        "id": "eu-handelsregister-de",
        "name": "handelsregister-de",
        "display_name": "Handelsregister (Germany)",
        "description": "German Commercial Register — company registration and business data",
        "category": "business-registry",
        "region": "EU-DE",
        "spec_url": "https://www.handelsregister.de/rp_web/api",
        "protocol": "openapi",
        "tags": ["business", "registry", "germany"],
        "documentation_url": "https://www.handelsregister.de/",
        "icon": "building-2",
    },
    {
        "id": "eu-vies",
        "name": "vies",
        "display_name": "VIES VAT Validation (EU)",
        "description": "EU VAT Information Exchange System — validate VAT numbers across member states",
        "category": "tax-compliance",
        "region": "EU",
        "spec_url": "https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number",
        "protocol": "openapi",
        "tags": ["tax", "vat", "compliance", "eu"],
        "documentation_url": "https://ec.europa.eu/taxation_customs/vies/",
        "icon": "receipt",
    },
    {
        "id": "eu-ted",
        "name": "ted-europa",
        "display_name": "TED (Tenders Electronic Daily)",
        "description": "EU public procurement notices — search and access tender documents",
        "category": "procurement",
        "region": "EU",
        "spec_url": "https://ted.europa.eu/api/v3/notices",
        "protocol": "openapi",
        "tags": ["procurement", "tenders", "eu", "public"],
        "documentation_url": "https://ted.europa.eu/",
        "icon": "gavel",
    },
    {
        "id": "eu-eurostat",
        "name": "eurostat",
        "display_name": "Eurostat Data API",
        "description": "European statistics — economic, social, environmental indicators",
        "category": "statistics",
        "region": "EU",
        "spec_url": "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1",
        "protocol": "openapi",
        "tags": ["statistics", "data", "eu", "economics"],
        "documentation_url": "https://ec.europa.eu/eurostat/",
        "icon": "bar-chart-3",
    },
    {
        "id": "eu-epo",
        "name": "epo-ops",
        "display_name": "EPO Open Patent Services",
        "description": "European Patent Office — patent search and full-text retrieval",
        "category": "intellectual-property",
        "region": "EU",
        "spec_url": "https://ops.epo.org/3.2/rest-services",
        "protocol": "openapi",
        "tags": ["patents", "ip", "eu"],
        "documentation_url": "https://www.epo.org/searching-for-patents/data/web-services/ops.html",
        "icon": "file-badge",
    },
    {
        "id": "eu-echa",
        "name": "echa-chemicals",
        "display_name": "ECHA Chemicals Database",
        "description": "European Chemicals Agency — REACH, CLP chemical substance data",
        "category": "chemicals-compliance",
        "region": "EU",
        "spec_url": "https://echa.europa.eu/api",
        "protocol": "openapi",
        "tags": ["chemicals", "reach", "compliance", "eu"],
        "documentation_url": "https://echa.europa.eu/",
        "icon": "flask-conical",
    },
    {
        "id": "eu-bris",
        "name": "bris",
        "display_name": "BRIS (Business Registers Interconnection)",
        "description": "Interconnection of EU business registers — cross-border company search",
        "category": "business-registry",
        "region": "EU",
        "protocol": "openapi",
        "tags": ["business", "registry", "eu", "cross-border"],
        "documentation_url": "https://e-justice.europa.eu/content_find_a_company-489-en.do",
        "icon": "globe",
    },
    {
        "id": "eu-ecb-sdw",
        "name": "ecb-sdw",
        "display_name": "ECB Statistical Data Warehouse",
        "description": "European Central Bank — exchange rates, monetary statistics, banking data",
        "category": "finance",
        "region": "EU",
        "spec_url": "https://data-api.ecb.europa.eu/service",
        "protocol": "openapi",
        "tags": ["finance", "ecb", "exchange-rates", "eu"],
        "documentation_url": "https://data.ecb.europa.eu/",
        "icon": "landmark",
    },
    {
        "id": "eu-inspire",
        "name": "inspire-geoportal",
        "display_name": "INSPIRE Geoportal",
        "description": "EU spatial data infrastructure — cross-border geospatial datasets",
        "category": "geospatial",
        "region": "EU",
        "spec_url": "https://inspire-geoportal.ec.europa.eu/",
        "protocol": "openapi",
        "tags": ["geospatial", "maps", "eu", "infrastructure"],
        "documentation_url": "https://inspire.ec.europa.eu/",
        "icon": "map",
    },
    {
        "id": "mcp-anthropic",
        "name": "anthropic-mcp",
        "display_name": "Anthropic Claude (MCP)",
        "description": "Anthropic Claude AI via Model Context Protocol — tool use, analysis, generation",
        "category": "ai-services",
        "region": "global",
        "mcp_endpoint": "https://api.anthropic.com/v1/mcp",
        "protocol": "mcp",
        "tags": ["ai", "llm", "mcp", "anthropic"],
        "documentation_url": "https://docs.anthropic.com/",
        "icon": "brain",
    },
    {
        "id": "mcp-openai",
        "name": "openai-mcp",
        "display_name": "OpenAI (MCP)",
        "description": "OpenAI GPT models via MCP-compatible endpoint",
        "category": "ai-services",
        "region": "global",
        "protocol": "mcp",
        "tags": ["ai", "llm", "mcp", "openai"],
        "documentation_url": "https://platform.openai.com/docs",
        "icon": "brain",
    },
]


def _get_catalog() -> list[CatalogEntry]:
    return [CatalogEntry(**entry) for entry in CURATED_CATALOG]


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
    _user: User = Depends(get_current_user),
) -> CatalogResponse:
    """Return curated catalog of pre-configured EU public APIs and MCP endpoints."""
    entries = _get_catalog()

    if category:
        entries = [e for e in entries if e.category == category]
    if region:
        entries = [e for e in entries if region.lower() in e.region.lower()]
    if protocol:
        entries = [e for e in entries if e.protocol == protocol]

    categories = sorted({e.category for e in _get_catalog()})

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
    entries = _get_catalog()

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
