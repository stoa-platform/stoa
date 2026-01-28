# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Sanctions Screening API router.

CAB-1018: Mock APIs for Central Bank Demo
Demonstrates semantic cache pattern with normalized entity matching.
"""

import time
from datetime import datetime

from fastapi import APIRouter
from prometheus_client import Counter, Gauge

from src.config import settings
from src.logging_config import get_logger
from src.schemas.sanctions import (
    ScreeningRequest,
    ScreeningResponse,
    ScreeningResult,
    ListVersionResponse,
    ListInfo,
)
from src.services.semantic_cache import get_semantic_cache, normalize
from src.services.sanctions_lists import get_sanctions_database

logger = get_logger(__name__)

router = APIRouter(tags=["Sanctions Screening"])

# Prometheus metrics
SANCTIONS_REQUESTS_TOTAL = Counter(
    f"{settings.metrics_prefix}_sanctions_requests_total",
    "Total sanctions screening requests",
    ["result", "cache_hit"],
)

SANCTIONS_MATCHES_TOTAL = Counter(
    f"{settings.metrics_prefix}_sanctions_matches_total",
    "Total sanctions matches found",
    ["list_name"],
)

SANCTIONS_CACHE_HIT_RATIO = Gauge(
    f"{settings.metrics_prefix}_sanctions_cache_hit_ratio",
    "Semantic cache hit ratio (0.0-1.0)",
)


def _determine_result(max_score: int) -> ScreeningResult:
    """Determine screening result from max match score.

    - score >= 90 → HIT
    - score 60-89 → PARTIAL_MATCH
    - score < 60 → NO_HIT
    """
    if max_score >= 90:
        return ScreeningResult.HIT
    elif max_score >= 60:
        return ScreeningResult.PARTIAL_MATCH
    else:
        return ScreeningResult.NO_HIT


@router.post(
    "/screening/check",
    response_model=ScreeningResponse,
    summary="Screen entity against sanctions lists",
    description="""
Screen an entity (person or organization) against multiple sanctions lists.

**Lists Checked:**
- OFAC (US Treasury)
- EU_SANCTIONS (European Union)
- UN_CONSOLIDATED (United Nations)

**Semantic Cache:**
Results are cached based on normalized entity name + type + country.
Normalization: lowercase, strip whitespace, replace hyphens with spaces.

Example: "IVAN PETROV" and "ivan-petrov" produce the same cache key.

**Result Classification:**
- **HIT**: Match score >= 90% (exact or alias match)
- **PARTIAL_MATCH**: Match score 60-89% (partial name match)
- **NO_HIT**: Match score < 60% (no significant match)

**Demo:**
Use `POST /demo/trigger/cache-clear` to clear the cache.
    """,
)
async def screen_entity(request: ScreeningRequest) -> ScreeningResponse:
    """Screen an entity against sanctions lists."""
    start_time = time.perf_counter()
    cache = get_semantic_cache()
    database = get_sanctions_database()

    normalized_name = normalize(request.entity_name)

    logger.info(
        "Sanctions screening request",
        entity_name=request.entity_name,
        normalized_name=normalized_name,
        entity_type=request.entity_type.value,
        country=request.country,
    )

    # Check cache
    cached_response = cache.get(
        request.entity_name, request.entity_type.value, request.country
    )

    if cached_response is not None:
        # Cache hit - update cached flag and return
        cached_response.cached = True
        cached_response.processing_time_ms = int(
            (time.perf_counter() - start_time) * 1000
        )
        cached_response.timestamp = datetime.utcnow().isoformat() + "Z"

        SANCTIONS_REQUESTS_TOTAL.labels(
            result=cached_response.result.value,
            cache_hit="true",
        ).inc()

        # Update cache hit ratio metric
        stats = cache.get_stats()
        SANCTIONS_CACHE_HIT_RATIO.set(stats["hit_ratio"])

        logger.info(
            "Sanctions screening cache hit",
            entity_name=request.entity_name,
            result=cached_response.result.value,
        )

        return cached_response

    # Cache miss - perform actual screening
    matches = database.search(
        entity_name=request.entity_name,
        entity_type=request.entity_type,
        country=request.country,
    )

    # Determine result based on best match
    max_score = max((m.match_score for m in matches), default=0)
    result = _determine_result(max_score)

    # Calculate processing time
    processing_time_ms = int((time.perf_counter() - start_time) * 1000)

    # Build response
    response = ScreeningResponse(
        result=result,
        matches=matches,
        confidence=max_score,
        list_sources=database.get_list_names(),
        entity_name=request.entity_name,
        entity_name_normalized=normalized_name,
        entity_type=request.entity_type,
        country=request.country,
        cached=False,
        processing_time_ms=processing_time_ms,
        timestamp=datetime.utcnow().isoformat() + "Z",
    )

    # Store in cache
    cache.set(request.entity_name, request.entity_type.value, request.country, response)

    # Update metrics
    SANCTIONS_REQUESTS_TOTAL.labels(
        result=result.value,
        cache_hit="false",
    ).inc()

    for match in matches:
        SANCTIONS_MATCHES_TOTAL.labels(list_name=match.list_name).inc()

    # Update cache hit ratio metric
    stats = cache.get_stats()
    SANCTIONS_CACHE_HIT_RATIO.set(stats["hit_ratio"])

    logger.info(
        "Sanctions screening completed",
        entity_name=request.entity_name,
        result=result.value,
        matches_found=len(matches),
        max_score=max_score,
        processing_time_ms=processing_time_ms,
    )

    return response


@router.get(
    "/screening/lists/version",
    response_model=ListVersionResponse,
    summary="Get sanctions list versions",
    description="""
Get version information for all sanctions lists.

Returns:
- List name
- Version string
- Last update date
- Entry count
    """,
)
async def get_list_versions() -> ListVersionResponse:
    """Get version information for all sanctions lists."""
    database = get_sanctions_database()
    versions = database.get_list_versions()

    return ListVersionResponse(
        lists=[
            ListInfo(
                name=v["name"],
                version=v["version"],
                last_updated=v["last_updated"],
                entry_count=v["entry_count"],
            )
            for v in versions
        ],
        timestamp=datetime.utcnow().isoformat() + "Z",
    )
