"""Tests for docs search endpoint (CAB-1327)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.routers.docs_search import (
    DocsSearchResponse,
    DocsSearchResult,
    DocsSearchService,
    get_docs_search_service,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service():
    """Fresh DocsSearchService instance."""
    return DocsSearchService()


@pytest.fixture
def sample_algolia_hits():
    """Sample Algolia API response hits."""
    return [
        {
            "title": "Quick Start Guide",
            "url": "https://docs.gostoa.dev/docs/guides/quick-start",
            "content": "Get started with STOA in 5 minutes...",
            "_snippetResult": {"content": {"value": "Get started with <em>STOA</em> in 5 minutes..."}},
        },
        {
            "title": "MCP Gateway Overview",
            "url": "https://docs.gostoa.dev/blog/what-is-mcp-gateway",
            "content": "The MCP Gateway bridges AI agents to APIs...",
            "_snippetResult": {"content": {"value": "The <em>MCP Gateway</em> bridges AI agents to APIs..."}},
        },
    ]


@pytest.fixture
def sample_llms_entries():
    """Sample parsed llms-full.txt entries."""
    return [
        {
            "title": "Quick Start Guide",
            "url": "https://docs.gostoa.dev/docs/guides/quick-start",
            "description": "Get started with STOA in 5 minutes",
        },
        {
            "title": "API Security Checklist",
            "url": "https://docs.gostoa.dev/blog/api-security-checklist",
            "description": "Essential security checklist for API developers",
        },
    ]


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


class TestDocsSearchResult:
    def test_minimal(self):
        r = DocsSearchResult(title="T", url="https://x.com", snippet="S", score=1.0)
        assert r.title == "T"
        assert r.category is None
        assert r.boosted is False

    def test_full(self):
        r = DocsSearchResult(
            title="T",
            url="https://x.com",
            snippet="S",
            score=1.2,
            category="docs",
            boosted=True,
        )
        assert r.category == "docs"
        assert r.boosted is True


class TestDocsSearchResponse:
    def test_serialization(self):
        r = DocsSearchResponse(
            query="test",
            total=1,
            results=[DocsSearchResult(title="T", url="https://x.com", snippet="S", score=1.0)],
            took_ms=12.3,
        )
        data = r.model_dump()
        assert data["query"] == "test"
        assert data["total"] == 1
        assert len(data["results"]) == 1
        assert data["took_ms"] == 12.3

    def test_empty_results(self):
        r = DocsSearchResponse(query="nothing", total=0, results=[])
        assert r.total == 0
        assert r.results == []


# ---------------------------------------------------------------------------
# llms-full.txt Parsing Tests
# ---------------------------------------------------------------------------


class TestLlmsTxtParsing:
    def test_basic_parsing(self, service):
        text = """## Quick Start
> Get started with STOA
- URL: https://docs.gostoa.dev/quick-start

## Migration Guide
> Migrate from Kong to STOA
https://docs.gostoa.dev/migration
"""
        entries = service._parse_llms_txt(text)
        assert len(entries) == 2
        assert entries[0]["title"] == "Quick Start"
        assert entries[0]["url"] == "https://docs.gostoa.dev/quick-start"
        assert "Get started" in entries[0]["description"]

    def test_empty_text(self, service):
        entries = service._parse_llms_txt("")
        assert entries == []

    def test_no_url(self, service):
        text = """## Title Only
> Just a description
"""
        entries = service._parse_llms_txt(text)
        assert len(entries) == 1
        assert entries[0]["url"] == ""

    def test_plain_text_description(self, service):
        text = """## My Title
This is a plain text description.
It spans multiple lines.
https://example.com
"""
        entries = service._parse_llms_txt(text)
        assert len(entries) == 1
        assert "plain text description" in entries[0]["description"]
        assert entries[0]["url"] == "https://example.com"

    def test_link_prefix(self, service):
        text = """## Entry
- Link: https://example.com/page
"""
        entries = service._parse_llms_txt(text)
        assert entries[0]["url"] == "https://example.com/page"


# ---------------------------------------------------------------------------
# Boost Logic Tests
# ---------------------------------------------------------------------------


class TestBoostLogic:
    def test_algolia_result_boosted_when_in_llms(self, service, sample_llms_entries):
        algolia_results = [
            DocsSearchResult(
                title="Quick Start Guide",
                url="https://docs.gostoa.dev/docs/guides/quick-start",
                snippet="...",
                score=1.0,
            )
        ]
        boosted = service._boost_results(algolia_results, sample_llms_entries, "quick start")
        assert boosted[0].boosted is True
        assert boosted[0].score == 1.2  # 1.0 + 0.2

    def test_llms_only_entry_appended(self, service, sample_llms_entries):
        algolia_results = []
        boosted = service._boost_results(algolia_results, sample_llms_entries, "security checklist")
        assert len(boosted) == 1
        assert boosted[0].category == "llms-txt"
        assert boosted[0].boosted is True

    def test_no_duplicate_urls(self, service, sample_llms_entries):
        algolia_results = [
            DocsSearchResult(
                title="Quick Start",
                url="https://docs.gostoa.dev/docs/guides/quick-start",
                snippet="...",
                score=1.0,
            )
        ]
        boosted = service._boost_results(algolia_results, sample_llms_entries, "quick start")
        urls = [r.url for r in boosted]
        assert len(urls) == len(set(urls))

    def test_results_sorted_by_score(self, service, sample_llms_entries):
        algolia_results = [
            DocsSearchResult(
                title="Low Score",
                url="https://example.com/low",
                snippet="...",
                score=0.5,
            ),
            DocsSearchResult(
                title="Quick Start Guide",
                url="https://docs.gostoa.dev/docs/guides/quick-start",
                snippet="...",
                score=1.0,
            ),
        ]
        boosted = service._boost_results(algolia_results, sample_llms_entries, "quick start")
        scores = [r.score for r in boosted]
        assert scores == sorted(scores, reverse=True)

    def test_short_query_words_ignored(self, service, sample_llms_entries):
        """Words <= 2 chars should not trigger llms-txt matches."""
        algolia_results = []
        boosted = service._boost_results(algolia_results, sample_llms_entries, "is a")
        # "is" and "a" are <= 2 chars, should not match
        assert len(boosted) == 0

    def test_trailing_slash_normalization(self, service):
        llms = [
            {
                "title": "Test",
                "url": "https://example.com/page/",
                "description": "test page",
            }
        ]
        algolia_results = [
            DocsSearchResult(
                title="Test",
                url="https://example.com/page",
                snippet="...",
                score=1.0,
            )
        ]
        boosted = service._boost_results(algolia_results, llms, "test")
        assert boosted[0].boosted is True


# ---------------------------------------------------------------------------
# Algolia Search Tests
# ---------------------------------------------------------------------------


class TestAlgoliaSearch:
    @pytest.mark.asyncio
    async def test_algolia_returns_hits(self, service):
        mock_response = MagicMock()
        mock_response.json.return_value = {"hits": [{"title": "Test", "url": "https://example.com"}]}
        mock_response.raise_for_status = MagicMock()

        with patch("src.routers.docs_search.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            hits = await service._algolia_search("test", 5)
            assert len(hits) == 1
            assert hits[0]["title"] == "Test"

    @pytest.mark.asyncio
    async def test_algolia_empty_response(self, service):
        mock_response = MagicMock()
        mock_response.json.return_value = {"hits": []}
        mock_response.raise_for_status = MagicMock()

        with patch("src.routers.docs_search.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            hits = await service._algolia_search("nonexistent", 5)
            assert hits == []


# ---------------------------------------------------------------------------
# Search Method Tests
# ---------------------------------------------------------------------------


class TestSearchMethod:
    @pytest.mark.asyncio
    async def test_search_combines_algolia_and_llms(self, service):
        with (
            patch.object(
                service,
                "_algolia_search",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "title": "Result",
                        "url": "https://docs.gostoa.dev/docs/test",
                        "content": "Test content",
                        "_snippetResult": {"content": {"value": "Test <em>content</em>"}},
                    }
                ],
            ),
            patch.object(service, "_load_llms_txt", new_callable=AsyncMock, return_value=[]),
        ):
            response = await service.search("test", limit=5)
            assert isinstance(response, DocsSearchResponse)
            assert response.query == "test"
            assert response.total == 1
            assert response.took_ms >= 0

    @pytest.mark.asyncio
    async def test_search_algolia_failure_graceful(self, service):
        with (
            patch.object(
                service,
                "_algolia_search",
                new_callable=AsyncMock,
                side_effect=httpx.HTTPError("Connection failed"),
            ),
            patch.object(
                service,
                "_load_llms_txt",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "title": "Fallback",
                        "url": "https://example.com/fb",
                        "description": "fallback result for test query",
                    }
                ],
            ),
        ):
            response = await service.search("test", limit=5)
            assert response.total >= 0  # Should not crash

    @pytest.mark.asyncio
    async def test_search_respects_limit(self, service):
        hits = [
            {
                "title": f"Result {i}",
                "url": f"https://example.com/{i}",
                "content": f"Content {i}",
                "_snippetResult": {"content": {"value": f"Snippet {i}"}},
            }
            for i in range(10)
        ]
        with (
            patch.object(
                service,
                "_algolia_search",
                new_callable=AsyncMock,
                return_value=hits,
            ),
            patch.object(service, "_load_llms_txt", new_callable=AsyncMock, return_value=[]),
        ):
            response = await service.search("test", limit=3)
            assert response.total <= 3


# ---------------------------------------------------------------------------
# Category Detection Tests
# ---------------------------------------------------------------------------


class TestCategoryDetection:
    @pytest.mark.asyncio
    async def test_blog_category(self, service):
        with (
            patch.object(
                service,
                "_algolia_search",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "title": "Blog Post",
                        "url": "https://docs.gostoa.dev/blog/my-post",
                        "content": "...",
                        "_snippetResult": {"content": {"value": "..."}},
                    }
                ],
            ),
            patch.object(service, "_load_llms_txt", new_callable=AsyncMock, return_value=[]),
        ):
            response = await service.search("blog", limit=5)
            assert response.results[0].category == "blog"

    @pytest.mark.asyncio
    async def test_adr_category(self, service):
        with (
            patch.object(
                service,
                "_algolia_search",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "title": "ADR-024",
                        "url": "https://docs.gostoa.dev/adr/adr-024",
                        "content": "...",
                        "_snippetResult": {"content": {"value": "..."}},
                    }
                ],
            ),
            patch.object(service, "_load_llms_txt", new_callable=AsyncMock, return_value=[]),
        ):
            response = await service.search("adr", limit=5)
            assert response.results[0].category == "adr"

    @pytest.mark.asyncio
    async def test_guide_category(self, service):
        with (
            patch.object(
                service,
                "_algolia_search",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "title": "Guide",
                        "url": "https://docs.gostoa.dev/guides/quick-start",
                        "content": "...",
                        "_snippetResult": {"content": {"value": "..."}},
                    }
                ],
            ),
            patch.object(service, "_load_llms_txt", new_callable=AsyncMock, return_value=[]),
        ):
            response = await service.search("guide", limit=5)
            assert response.results[0].category == "guide"

    @pytest.mark.asyncio
    async def test_docs_category(self, service):
        with (
            patch.object(
                service,
                "_algolia_search",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "title": "Docs",
                        "url": "https://docs.gostoa.dev/docs/overview",
                        "content": "...",
                        "_snippetResult": {"content": {"value": "..."}},
                    }
                ],
            ),
            patch.object(service, "_load_llms_txt", new_callable=AsyncMock, return_value=[]),
        ):
            response = await service.search("docs", limit=5)
            assert response.results[0].category == "docs"


# ---------------------------------------------------------------------------
# Cache Tests
# ---------------------------------------------------------------------------


class TestLlmsCache:
    @pytest.mark.asyncio
    async def test_cache_hit(self, service):
        """Second call within TTL should use cache."""
        service._llms_entries = [{"title": "Cached", "url": "", "description": ""}]
        import time

        service._llms_loaded_at = time.monotonic()  # Just loaded

        result = await service._load_llms_txt()
        assert len(result) == 1
        assert result[0]["title"] == "Cached"


# ---------------------------------------------------------------------------
# Endpoint Tests
# ---------------------------------------------------------------------------


class TestEndpoint:
    def setup_method(self):
        """Set up mock service for endpoint tests."""
        self.mock_service = MagicMock(spec=DocsSearchService)
        self.mock_service.search = AsyncMock(
            return_value=DocsSearchResponse(
                query="test",
                total=1,
                results=[
                    DocsSearchResult(
                        title="Test Result",
                        url="https://docs.gostoa.dev/test",
                        snippet="A test result",
                        score=1.0,
                    )
                ],
                took_ms=5.0,
            )
        )
        app.dependency_overrides[get_docs_search_service] = lambda: self.mock_service
        self.client = TestClient(app)

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_search_endpoint_success(self):
        resp = self.client.get("/v1/docs/search?q=test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "test"
        assert data["total"] == 1
        assert len(data["results"]) == 1

    def test_search_endpoint_with_limit(self):
        resp = self.client.get("/v1/docs/search?q=gateway&limit=10")
        assert resp.status_code == 200

    def test_search_endpoint_missing_query(self):
        resp = self.client.get("/v1/docs/search")
        assert resp.status_code == 422

    def test_search_endpoint_empty_query(self):
        resp = self.client.get("/v1/docs/search?q=")
        assert resp.status_code == 422

    def test_search_endpoint_limit_too_high(self):
        resp = self.client.get("/v1/docs/search?q=test&limit=100")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Singleton Tests
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_docs_search_service_returns_instance(self):
        import src.routers.docs_search as mod

        mod._service = None
        svc = get_docs_search_service()
        assert isinstance(svc, DocsSearchService)

    def test_get_docs_search_service_returns_same_instance(self):
        import src.routers.docs_search as mod

        mod._service = None
        svc1 = get_docs_search_service()
        svc2 = get_docs_search_service()
        assert svc1 is svc2


# ---------------------------------------------------------------------------
# Title Fallback Tests
# ---------------------------------------------------------------------------


class TestTitleFallback:
    @pytest.mark.asyncio
    async def test_title_from_hierarchy(self, service):
        """When title is empty, should fall back to hierarchy."""
        with (
            patch.object(
                service,
                "_algolia_search",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "title": "",
                        "url": "https://docs.gostoa.dev/docs/test",
                        "hierarchy": {"lvl1": "Section Title", "lvl0": "Top"},
                        "content": "...",
                        "_snippetResult": {"content": {"value": "..."}},
                    }
                ],
            ),
            patch.object(service, "_load_llms_txt", new_callable=AsyncMock, return_value=[]),
        ):
            response = await service.search("test", limit=5)
            assert response.results[0].title == "Section Title"

    @pytest.mark.asyncio
    async def test_untitled_fallback(self, service):
        """When no title and no hierarchy, should use 'Untitled'."""
        with (
            patch.object(
                service,
                "_algolia_search",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "url": "https://docs.gostoa.dev/docs/test",
                        "content": "...",
                        "_snippetResult": {"content": {"value": "..."}},
                    }
                ],
            ),
            patch.object(service, "_load_llms_txt", new_callable=AsyncMock, return_value=[]),
        ):
            response = await service.search("test", limit=5)
            assert response.results[0].title == "Untitled"
