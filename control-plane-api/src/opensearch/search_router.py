"""
STOA Platform - Search API
==========================

FastAPI endpoints for full-text search of tools catalog.

Features:
- Full-text search with relevance scoring
- Faceted search (category, tags)
- Auto-complete suggestions
- Multi-tenant filtering
- Search analytics

Endpoints:
    GET  /search/tools           - Search tools catalog
    GET  /search/tools/suggest   - Auto-complete suggestions
    GET  /search/tools/facets    - Get available facets
    GET  /search/analytics       - Search analytics (admin)
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from opensearchpy import AsyncOpenSearch
from pydantic import BaseModel, Field

logger = logging.getLogger("stoa.search")

router = APIRouter(prefix="/search", tags=["search"])


# =============================================================================
# Models
# =============================================================================

class SortOrder(str, Enum):
    """Sort order options."""
    RELEVANCE = "relevance"
    NAME_ASC = "name_asc"
    NAME_DESC = "name_desc"
    UPDATED_DESC = "updated_desc"
    POPULARITY = "popularity"


class ToolSearchResult(BaseModel):
    """Single tool search result."""
    id: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    version: str = "1.0.0"
    visibility: str = "private"
    stats: dict = Field(default_factory=dict)
    score: float = 0.0
    highlights: dict = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """Search response model."""
    query: str
    total: int
    page: int
    page_size: int
    results: list[ToolSearchResult]
    facets: dict = Field(default_factory=dict)
    took_ms: float = 0.0


class SuggestResponse(BaseModel):
    """Auto-complete suggestion response."""
    query: str
    suggestions: list[dict]
    took_ms: float = 0.0


class FacetsResponse(BaseModel):
    """Facets response model."""
    categories: list[dict]
    tags: list[dict]
    visibility: list[dict]


# =============================================================================
# Dependencies
# =============================================================================

async def get_opensearch() -> AsyncOpenSearch:
    """Get OpenSearch client (placeholder - replace with actual dependency)."""
    from .opensearch_integration import get_opensearch_client
    return await get_opensearch_client()


async def get_current_tenant(
    # In real app, extract from JWT
) -> str:
    """Get current tenant ID from request context."""
    return "default"  # Placeholder


# =============================================================================
# Search Service
# =============================================================================

class SearchService:
    """OpenSearch search service."""
    
    def __init__(self, client: AsyncOpenSearch):
        self.client = client
        self.index = "tools"
    
    async def search_tools(
        self,
        query: str,
        tenant_id: str,
        category: Optional[str] = None,
        tags: Optional[list[str]] = None,
        visibility: Optional[str] = None,
        sort: SortOrder = SortOrder.RELEVANCE,
        page: int = 1,
        page_size: int = 20,
        include_facets: bool = True,
    ) -> SearchResponse:
        """Search tools catalog with full-text search."""
        
        # Build query
        must_clauses = []
        filter_clauses = []
        
        # Full-text search
        if query and query.strip():
            must_clauses.append({
                "multi_match": {
                    "query": query,
                    "fields": [
                        "name^3",
                        "name.keyword^4",
                        "description^2",
                        "tags^1.5",
                        "category",
                    ],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                    "prefix_length": 2,
                }
            })
        else:
            must_clauses.append({"match_all": {}})
        
        # Tenant filter (mandatory)
        filter_clauses.append({
            "bool": {
                "should": [
                    {"term": {"tenant_id": tenant_id}},
                    {"term": {"visibility": "public"}},
                ],
                "minimum_should_match": 1,
            }
        })
        
        # Category filter
        if category:
            filter_clauses.append({"term": {"category": category}})
        
        # Tags filter
        if tags:
            for tag in tags:
                filter_clauses.append({"term": {"tags": tag}})
        
        # Visibility filter
        if visibility:
            filter_clauses.append({"term": {"visibility": visibility}})
        
        # Build sort
        sort_config = self._build_sort(sort)
        
        # Build aggregations for facets
        aggs = {}
        if include_facets:
            aggs = {
                "categories": {
                    "terms": {"field": "category", "size": 20}
                },
                "tags": {
                    "terms": {"field": "tags", "size": 50}
                },
                "visibility": {
                    "terms": {"field": "visibility", "size": 5}
                },
            }
        
        # Execute search
        body = {
            "query": {
                "bool": {
                    "must": must_clauses,
                    "filter": filter_clauses,
                }
            },
            "sort": sort_config,
            "from": (page - 1) * page_size,
            "size": page_size,
            "highlight": {
                "fields": {
                    "name": {"number_of_fragments": 0},
                    "description": {"number_of_fragments": 3, "fragment_size": 150},
                    "tags": {"number_of_fragments": 0},
                }
            },
            "aggs": aggs,
        }
        
        response = await self.client.search(
            index=self.index,
            body=body,
        )
        
        # Parse results
        results = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            result = ToolSearchResult(
                id=source["id"],
                name=source["name"],
                description=source.get("description"),
                category=source.get("category"),
                tags=source.get("tags", []),
                version=source.get("version", "1.0.0"),
                visibility=source.get("visibility", "private"),
                stats=source.get("stats", {}),
                score=hit["_score"] or 0.0,
                highlights=hit.get("highlight", {}),
            )
            results.append(result)
        
        # Parse facets
        facets = {}
        if include_facets and "aggregations" in response:
            for agg_name, agg_data in response["aggregations"].items():
                facets[agg_name] = [
                    {"key": bucket["key"], "count": bucket["doc_count"]}
                    for bucket in agg_data.get("buckets", [])
                ]
        
        return SearchResponse(
            query=query,
            total=response["hits"]["total"]["value"],
            page=page,
            page_size=page_size,
            results=results,
            facets=facets,
            took_ms=response["took"],
        )
    
    async def suggest(
        self,
        query: str,
        tenant_id: str,
        limit: int = 10,
    ) -> SuggestResponse:
        """Get auto-complete suggestions."""
        
        body = {
            "suggest": {
                "tool-suggest": {
                    "prefix": query,
                    "completion": {
                        "field": "name.suggest",
                        "size": limit,
                        "skip_duplicates": True,
                        "fuzzy": {
                            "fuzziness": "AUTO",
                        },
                        "contexts": {
                            "tenant": [tenant_id, "public"],
                        },
                    }
                }
            }
        }
        
        response = await self.client.search(
            index=self.index,
            body=body,
        )
        
        suggestions = []
        for option in response["suggest"]["tool-suggest"][0]["options"]:
            suggestions.append({
                "id": option["_id"],
                "name": option["text"],
                "score": option["_score"],
            })
        
        return SuggestResponse(
            query=query,
            suggestions=suggestions,
            took_ms=response["took"],
        )
    
    async def get_facets(
        self,
        tenant_id: str,
    ) -> FacetsResponse:
        """Get all available facets for filtering."""
        
        body = {
            "size": 0,
            "query": {
                "bool": {
                    "should": [
                        {"term": {"tenant_id": tenant_id}},
                        {"term": {"visibility": "public"}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            "aggs": {
                "categories": {
                    "terms": {"field": "category", "size": 100}
                },
                "tags": {
                    "terms": {"field": "tags", "size": 200}
                },
                "visibility": {
                    "terms": {"field": "visibility", "size": 10}
                },
            },
        }
        
        response = await self.client.search(
            index=self.index,
            body=body,
        )
        
        return FacetsResponse(
            categories=[
                {"key": b["key"], "count": b["doc_count"]}
                for b in response["aggregations"]["categories"]["buckets"]
            ],
            tags=[
                {"key": b["key"], "count": b["doc_count"]}
                for b in response["aggregations"]["tags"]["buckets"]
            ],
            visibility=[
                {"key": b["key"], "count": b["doc_count"]}
                for b in response["aggregations"]["visibility"]["buckets"]
            ],
        )
    
    def _build_sort(self, sort: SortOrder) -> list:
        """Build sort configuration."""
        if sort == SortOrder.RELEVANCE:
            return ["_score", {"updated_at": "desc"}]
        elif sort == SortOrder.NAME_ASC:
            return [{"name.keyword": "asc"}]
        elif sort == SortOrder.NAME_DESC:
            return [{"name.keyword": "desc"}]
        elif sort == SortOrder.UPDATED_DESC:
            return [{"updated_at": "desc"}]
        elif sort == SortOrder.POPULARITY:
            return [{"stats.call_count": "desc"}, "_score"]
        return ["_score"]


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/tools", response_model=SearchResponse)
async def search_tools(
    q: str = Query("", description="Search query"),
    category: Optional[str] = Query(None, description="Filter by category"),
    tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)"),
    visibility: Optional[str] = Query(None, description="Filter by visibility"),
    sort: SortOrder = Query(SortOrder.RELEVANCE, description="Sort order"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page"),
    facets: bool = Query(True, description="Include facets in response"),
    client: AsyncOpenSearch = Depends(get_opensearch),
    tenant_id: str = Depends(get_current_tenant),
):
    """
    Search tools catalog with full-text search.
    
    Supports:
    - Full-text search across name, description, and tags
    - Fuzzy matching for typo tolerance
    - Faceted filtering by category, tags, and visibility
    - Relevance scoring with boosted fields
    - Pagination and sorting
    """
    service = SearchService(client)
    
    # Parse tags
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    
    return await service.search_tools(
        query=q,
        tenant_id=tenant_id,
        category=category,
        tags=tag_list,
        visibility=visibility,
        sort=sort,
        page=page,
        page_size=page_size,
        include_facets=facets,
    )


@router.get("/tools/suggest", response_model=SuggestResponse)
async def suggest_tools(
    q: str = Query(..., min_length=1, description="Query prefix"),
    limit: int = Query(10, ge=1, le=50, description="Max suggestions"),
    client: AsyncOpenSearch = Depends(get_opensearch),
    tenant_id: str = Depends(get_current_tenant),
):
    """
    Get auto-complete suggestions for tool names.
    
    Returns matching tool names as the user types,
    with fuzzy matching for typo tolerance.
    """
    service = SearchService(client)
    return await service.suggest(
        query=q,
        tenant_id=tenant_id,
        limit=limit,
    )


@router.get("/tools/facets", response_model=FacetsResponse)
async def get_tool_facets(
    client: AsyncOpenSearch = Depends(get_opensearch),
    tenant_id: str = Depends(get_current_tenant),
):
    """
    Get all available facets for filtering tools.
    
    Returns counts for each category, tag, and visibility level.
    """
    service = SearchService(client)
    return await service.get_facets(tenant_id=tenant_id)


@router.get("/analytics")
async def get_search_analytics(
    period: str = Query("7d", description="Time period (1d, 7d, 30d)"),
    client: AsyncOpenSearch = Depends(get_opensearch),
    tenant_id: str = Depends(get_current_tenant),
):
    """
    Get search analytics (admin only).
    
    Returns:
    - Top search queries
    - Popular tools
    - Search volume over time
    """
    # Parse period
    period_map = {"1d": 1, "7d": 7, "30d": 30}
    days = period_map.get(period, 7)
    
    body = {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"tenant_id": tenant_id}},
                    {"range": {"@timestamp": {"gte": f"now-{days}d"}}},
                ],
            }
        },
        "aggs": {
            "top_tools": {
                "terms": {"field": "tool.id", "size": 10}
            },
            "calls_over_time": {
                "date_histogram": {
                    "field": "@timestamp",
                    "calendar_interval": "day",
                }
            },
            "total_calls": {
                "sum": {"field": "metrics.call_count"}
            },
        },
    }
    
    response = await client.search(
        index="analytics-*",
        body=body,
    )
    
    return {
        "period": period,
        "top_tools": response["aggregations"]["top_tools"]["buckets"],
        "calls_over_time": response["aggregations"]["calls_over_time"]["buckets"],
        "total_calls": response["aggregations"]["total_calls"]["value"],
    }
