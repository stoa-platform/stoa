"""YAML catalog loader — reads catalog entries from YAML files (CAB-1639).

Catalog YAML files live in this directory. Each file defines one category
with its API entries. Files are loaded once at startup and cached.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

CATALOG_DIR = Path(__file__).parent

# ---------- Schemas ----------


class CatalogTool(BaseModel):
    """A tool exposed by a catalog API entry."""

    name: str
    description: str | None = None


class CatalogEntry(BaseModel):
    """A single API/MCP connector in the curated catalog."""

    id: str
    name: str
    display_name: str
    description: str
    category: str
    country: str = Field(description="ISO 3166-1 alpha-2 or 'EU' for pan-European")
    region: str = "EU"
    spec_url: str | None = None
    mcp_endpoint: str | None = None
    protocol: str = Field(description="openapi | mcp | graphql")
    auth_type: str = Field(
        default="none",
        description="none | api_key | oauth2 | basic",
    )
    tools: list[CatalogTool] = []
    status: str = Field(
        default="community",
        description="verified | community | experimental",
    )
    tags: list[str] = []
    documentation_url: str | None = None
    icon: str | None = None


class CatalogCategory(BaseModel):
    """A category grouping catalog entries."""

    id: str
    name: str
    icon: str | None = None
    entries: list[CatalogEntry]


class CatalogResponse(BaseModel):
    """Full catalog response with categories and flat entry list."""

    entries: list[CatalogEntry]
    total: int
    categories: list[str]


class SearchResult(BaseModel):
    """Search result response."""

    entries: list[CatalogEntry]
    total: int
    query: str


# ---------- Cache ----------

_catalog_cache: list[CatalogEntry] | None = None


def _load_yaml_files() -> list[CatalogEntry]:
    """Load all YAML catalog files from the catalog directory."""
    entries: list[CatalogEntry] = []

    for yaml_path in sorted(CATALOG_DIR.glob("*.yaml")):
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        if not data or "entries" not in data:
            continue

        category_id = data.get("category_id", yaml_path.stem)

        for entry_data in data["entries"]:
            # Inherit category from file if not set on entry
            entry_data.setdefault("category", category_id)
            # Parse tools if they're simple strings
            if "tools" in entry_data:
                entry_data["tools"] = [{"name": t} if isinstance(t, str) else t for t in entry_data["tools"]]
            entries.append(CatalogEntry(**entry_data))

    return entries


def get_catalog() -> list[CatalogEntry]:
    """Return cached catalog entries, loading from YAML on first call."""
    global _catalog_cache
    if _catalog_cache is None:
        _catalog_cache = _load_yaml_files()
    return _catalog_cache


def get_categories() -> list[str]:
    """Return sorted unique category names."""
    return sorted({e.category for e in get_catalog()})


def reload_catalog() -> list[CatalogEntry]:
    """Force reload catalog from YAML files. Useful for testing."""
    global _catalog_cache
    _catalog_cache = None
    return get_catalog()
