"""Lightweight DTOs for Portal list endpoints (CAB-1113 Phase 5).

List endpoints use these minimal schemas to avoid loading relationships
and reduce payload size. Detail endpoints keep full response models.
"""

from datetime import datetime

from pydantic import BaseModel


class MCPServerListItem(BaseModel):
    """Lightweight MCP server for list views — no relations loaded.

    tools_count is computed via SQL subquery instead of loading the tools relationship.
    """

    id: str
    name: str
    display_name: str
    status: str
    tools_count: int = 0
    category: str | None = None
    icon: str | None = None
    description: str = ""
    tenant_id: str | None = None
    version: str | None = None
    documentation_url: str | None = None
    requires_approval: bool = False
    created_at: datetime | None = None


class APIListItem(BaseModel):
    """Lightweight API for list views — no deployments/backend_url."""

    id: str
    name: str
    display_name: str
    version: str
    status: str
    description: str = ""
    tenant_id: str
    tenant_name: str | None = None
    category: str | None = None
    tags: list[str] = []
    is_promoted: bool = True
