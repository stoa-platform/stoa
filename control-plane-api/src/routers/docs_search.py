"""Docs search endpoint backed by Algolia + llms-full.txt boost (CAB-1327).

Public, read-only endpoint that searches STOA documentation (docs, blog, ADRs, guides).
Uses httpx to call Algolia REST API directly (avoids pydantic version conflict with SDK).
"""

import asyncio
import re
import time

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..config import settings
from ..logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class DocsSearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    score: float
    category: str | None = None
    boosted: bool = False


class DocsSearchResponse(BaseModel):
    query: str
    total: int
    results: list[DocsSearchResult]
    took_ms: float = 0.0


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

_ALGOLIA_SEARCH_URL = "https://{app_id}-dsn.algolia.net/1/indexes/{index}/query"
_LLMS_CACHE_TTL = 3600  # 1 hour


class DocsSearchService:
    """Searches Algolia + llms-full.txt and merges results."""

    def __init__(self) -> None:
        self._llms_entries: list[dict[str, str]] = []
        self._llms_loaded_at: float = 0.0

    # -- Algolia ----------------------------------------------------------

    async def _algolia_search(self, query: str, limit: int) -> list[dict]:
        """Call Algolia REST API and return raw hits."""
        url = _ALGOLIA_SEARCH_URL.format(
            app_id=settings.ALGOLIA_APP_ID,
            index=settings.ALGOLIA_INDEX_NAME.replace(" ", "%20"),
        )
        headers = {
            "X-Algolia-Application-Id": settings.ALGOLIA_APP_ID,
            "X-Algolia-API-Key": settings.ALGOLIA_SEARCH_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {
            "query": query,
            "hitsPerPage": limit,
            "attributesToRetrieve": [
                "title",
                "url",
                "content",
                "hierarchy",
                "type",
            ],
            "attributesToSnippet": ["content:40"],
            "snippetEllipsisText": "...",
        }

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data.get("hits", [])

    # -- llms-full.txt ----------------------------------------------------

    async def _load_llms_txt(self) -> list[dict[str, str]]:
        """Fetch and parse llms-full.txt. Cached for 1 hour."""
        now = time.monotonic()
        if self._llms_entries and (now - self._llms_loaded_at) < _LLMS_CACHE_TTL:
            return self._llms_entries

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(settings.LLMS_FULL_TXT_URL)
                resp.raise_for_status()
                text = resp.text
        except httpx.HTTPError:
            logger.warning("Failed to fetch llms-full.txt, using cached or empty")
            return self._llms_entries

        entries = self._parse_llms_txt(text)
        self._llms_entries = entries
        self._llms_loaded_at = now
        logger.info("Loaded llms-full.txt", entry_count=len(entries))
        return entries

    @staticmethod
    def _parse_llms_txt(text: str) -> list[dict[str, str]]:
        """Parse llms-full.txt into structured entries.

        Expected format (Markdown-ish):
            ## Title
            > description or summary
            - URL: https://...
        Or simpler sections with headings + content.
        """
        entries: list[dict[str, str]] = []
        current_title = ""
        current_url = ""
        current_desc_lines: list[str] = []

        for line in text.splitlines():
            stripped = line.strip()

            # Heading → start new entry
            if stripped.startswith("## "):
                # Flush previous
                if current_title:
                    entries.append(
                        {
                            "title": current_title,
                            "url": current_url,
                            "description": " ".join(current_desc_lines).strip(),
                        }
                    )
                current_title = stripped[3:].strip()
                current_url = ""
                current_desc_lines = []
                continue

            # URL line
            url_match = re.match(r"^-?\s*(?:URL:\s*)?(?:Link:\s*)?(https?://\S+)", stripped)
            if url_match and not current_url:
                current_url = url_match.group(1)
                continue

            # Description lines (blockquote or plain text)
            if stripped.startswith("> "):
                current_desc_lines.append(stripped[2:])
            elif stripped and current_title and not stripped.startswith("#"):
                current_desc_lines.append(stripped)

        # Flush last entry
        if current_title:
            entries.append(
                {
                    "title": current_title,
                    "url": current_url,
                    "description": " ".join(current_desc_lines).strip(),
                }
            )

        return entries

    # -- Merge + boost ----------------------------------------------------

    def _boost_results(
        self,
        algolia_results: list[DocsSearchResult],
        llms_entries: list[dict[str, str]],
        query: str,
    ) -> list[DocsSearchResult]:
        """Boost Algolia results that appear in llms-full.txt; append llms-only matches."""
        query_lower = query.lower()
        query_words = set(query_lower.split())

        # Index llms entries by URL for quick lookup
        llms_by_url: dict[str, dict[str, str]] = {}
        for entry in llms_entries:
            if entry.get("url"):
                llms_by_url[entry["url"].rstrip("/")] = entry

        # Boost Algolia hits that are also in llms-full.txt
        algolia_urls: set[str] = set()
        for result in algolia_results:
            norm_url = result.url.rstrip("/")
            algolia_urls.add(norm_url)
            if norm_url in llms_by_url:
                result.boosted = True
                result.score = result.score + 0.2

        # Append llms-full.txt entries matching the query but not in Algolia
        for entry in llms_entries:
            entry_url = entry.get("url", "").rstrip("/")
            if entry_url in algolia_urls or not entry_url:
                continue

            searchable = f"{entry.get('title', '')} {entry.get('description', '')}".lower()
            if query_lower in searchable or any(w in searchable for w in query_words if len(w) > 2):
                algolia_results.append(
                    DocsSearchResult(
                        title=entry.get("title", ""),
                        url=entry_url,
                        snippet=entry.get("description", "")[:200],
                        score=0.1,
                        category="llms-txt",
                        boosted=True,
                    )
                )

        # Re-sort by score descending
        algolia_results.sort(key=lambda r: r.score, reverse=True)
        return algolia_results

    # -- Public API -------------------------------------------------------

    async def search(self, query: str, limit: int = 5) -> DocsSearchResponse:
        """Search docs via Algolia + llms-full.txt boost."""
        t0 = time.monotonic()

        # Run Algolia + llms fetch in parallel
        algolia_task = asyncio.create_task(self._algolia_search(query, limit))
        llms_task = asyncio.create_task(self._load_llms_txt())

        try:
            hits = await algolia_task
        except httpx.HTTPError:
            logger.warning("Algolia search failed, falling back to llms-full.txt only")
            hits = []

        llms_entries = await llms_task

        # Convert Algolia hits to results
        results: list[DocsSearchResult] = []
        for hit in hits:
            # Build URL from Algolia hit
            url = hit.get("url", "")
            if not url:
                # Docusaurus Algolia plugin stores url directly
                url = hit.get("objectID", "")

            # Build title from hierarchy or title field
            title = hit.get("title", "")
            if not title:
                hierarchy = hit.get("hierarchy", {})
                for lvl in ("lvl1", "lvl2", "lvl3", "lvl0"):
                    if hierarchy.get(lvl):
                        title = hierarchy[lvl]
                        break

            # Snippet from highlighted content
            snippet_result = hit.get("_snippetResult", {})
            content_snippet = snippet_result.get("content", {})
            snippet = content_snippet.get("value", "") if isinstance(content_snippet, dict) else ""
            if not snippet:
                snippet = (hit.get("content", "") or "")[:200]

            # Determine category from URL path
            category = None
            if "/blog/" in url:
                category = "blog"
            elif "/adr/" in url:
                category = "adr"
            elif "/guides/" in url:
                category = "guide"
            elif "/docs/" in url:
                category = "docs"

            results.append(
                DocsSearchResult(
                    title=title or "Untitled",
                    url=url,
                    snippet=snippet,
                    score=1.0,  # Algolia results get base score 1.0
                    category=category,
                    boosted=False,
                )
            )

        # Apply llms-full.txt boost
        results = self._boost_results(results, llms_entries, query)

        # Trim to requested limit
        results = results[:limit]

        took_ms = round((time.monotonic() - t0) * 1000, 1)
        return DocsSearchResponse(
            query=query,
            total=len(results),
            results=results,
            took_ms=took_ms,
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_service: DocsSearchService | None = None


def get_docs_search_service() -> DocsSearchService:
    global _service
    if _service is None:
        _service = DocsSearchService()
    return _service


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/v1/docs", tags=["Docs Search"])


@router.get("/search", response_model=DocsSearchResponse)
async def search_docs(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    limit: int = Query(5, ge=1, le=20, description="Max results"),
    service: DocsSearchService = Depends(get_docs_search_service),
) -> DocsSearchResponse:
    """Search STOA documentation, guides, ADRs, and blog posts.

    Public endpoint — no authentication required.
    Combines Algolia full-text search with llms-full.txt boosting.
    """
    return await service.search(query=q, limit=limit)
