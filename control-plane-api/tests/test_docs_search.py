"""Tests for docs search endpoint (CAB-1327).

Phase 1: Algolia keyword search + llms-full.txt boost.
Phase 2: Semantic search (embeddings + k-NN), hybrid mode (RRF), reindex endpoint.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.routers.docs_search import (
    DocsSearchResponse,
    DocsSearchResult,
    DocsSearchService,
    _categorize_url,
    get_docs_search_service,
)
from src.services.docs_embedding_service import (
    DocsEmbeddingService,
    get_docs_embedding_service,
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
            "url": "https://docs.gostoa.dev/docs/guides/quickstart",
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
            "url": "https://docs.gostoa.dev/docs/guides/quickstart",
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
                url="https://docs.gostoa.dev/docs/guides/quickstart",
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
                url="https://docs.gostoa.dev/docs/guides/quickstart",
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
                url="https://docs.gostoa.dev/docs/guides/quickstart",
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
                        "url": "https://docs.gostoa.dev/guides/quickstart",
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
        self.mock_embed_svc = MagicMock(spec=DocsEmbeddingService)
        app.dependency_overrides[get_docs_search_service] = lambda: self.mock_service
        app.dependency_overrides[get_docs_embedding_service] = lambda: self.mock_embed_svc
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


# ===========================================================================
# Phase 2 Tests — Semantic Search, Hybrid, Reindex (CAB-1327)
# ===========================================================================


# ---------------------------------------------------------------------------
# Chunking Tests
# ---------------------------------------------------------------------------


class TestChunking:
    def setup_method(self):
        self.svc = DocsEmbeddingService()

    def test_h2_splitting(self):
        """Split on H2 boundaries."""
        content = "Intro text\n## Section A\nContent A\n## Section B\nContent B"
        chunks = self.svc.chunk_markdown(content, title="Doc", url="https://example.com")
        assert len(chunks) >= 2
        headings = [c.heading for c in chunks]
        assert "Section A" in headings
        assert "Section B" in headings

    def test_overlap_on_large_section(self):
        """Oversized sections get character-based windowing with overlap."""
        big_text = "## Big\n" + "x" * 5000
        chunks = self.svc.chunk_markdown(big_text, max_chars=2048, overlap=200)
        assert len(chunks) >= 2
        # Second chunk should overlap with first
        if len(chunks) >= 2:
            first_end = chunks[0].content
            second_start = chunks[1].content
            assert first_end[-200:] == second_start[:200]

    def test_max_size_respected(self):
        """No chunk exceeds max_chars."""
        content = "## A\n" + "y" * 10000
        chunks = self.svc.chunk_markdown(content, max_chars=1024, overlap=100)
        for c in chunks:
            assert len(c.content) <= 1024

    def test_empty_input(self):
        """Empty string returns no chunks."""
        assert self.svc.chunk_markdown("") == []
        assert self.svc.chunk_markdown("   ") == []

    def test_metadata_preserved(self):
        """Title and URL propagate to all chunks."""
        content = "## Sec\nHello world"
        chunks = self.svc.chunk_markdown(content, title="My Doc", url="https://x.com/page")
        assert len(chunks) == 1
        assert chunks[0].title == "My Doc"
        assert chunks[0].url == "https://x.com/page"
        assert chunks[0].chunk_index == 0


# ---------------------------------------------------------------------------
# Embedding Generation Tests
# ---------------------------------------------------------------------------


class TestEmbedding:
    def setup_method(self):
        self.svc = DocsEmbeddingService()

    @pytest.mark.asyncio
    async def test_success(self):
        """Generate embedding returns vector on success."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
        mock_resp.raise_for_status = MagicMock()

        with (
            patch("src.services.docs_embedding_service.settings") as mock_settings,
            patch("src.services.docs_embedding_service.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.EMBEDDING_PROVIDER = "openai"
            mock_settings.EMBEDDING_API_KEY = "test-key"
            mock_settings.EMBEDDING_API_URL = "https://api.openai.com/v1/embeddings"
            mock_settings.EMBEDDING_MODEL = "text-embedding-3-small"
            mock_settings.EMBEDDING_DIMENSIONS = 1536

            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            vec = await self.svc.generate_embedding("hello world")
            assert vec == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_provider_disabled(self):
        """Provider 'none' returns empty."""
        with patch("src.services.docs_embedding_service.settings") as mock_settings:
            mock_settings.EMBEDDING_PROVIDER = "none"
            mock_settings.EMBEDDING_API_KEY = "key"
            vec = await self.svc.generate_embedding("hello")
            assert vec == []

    @pytest.mark.asyncio
    async def test_no_api_key(self):
        """Empty API key returns empty."""
        with patch("src.services.docs_embedding_service.settings") as mock_settings:
            mock_settings.EMBEDDING_PROVIDER = "openai"
            mock_settings.EMBEDDING_API_KEY = ""
            vec = await self.svc.generate_embedding("hello")
            assert vec == []

    @pytest.mark.asyncio
    async def test_http_error(self):
        """HTTP error returns empty, no crash."""
        with (
            patch("src.services.docs_embedding_service.settings") as mock_settings,
            patch("src.services.docs_embedding_service.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.EMBEDDING_PROVIDER = "openai"
            mock_settings.EMBEDDING_API_KEY = "test-key"
            mock_settings.EMBEDDING_API_URL = "https://api.openai.com/v1/embeddings"
            mock_settings.EMBEDDING_MODEL = "model"
            mock_settings.EMBEDDING_DIMENSIONS = 1536

            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.HTTPError("connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            vec = await self.svc.generate_embedding("hello")
            assert vec == []


# ---------------------------------------------------------------------------
# Semantic Search Tests
# ---------------------------------------------------------------------------


class TestSemanticSearch:
    def setup_method(self):
        self.svc = DocsEmbeddingService()

    @pytest.mark.asyncio
    async def test_returns_results(self):
        """Semantic search returns formatted results."""
        mock_os_response = MagicMock()
        mock_os_response.status_code = 200
        mock_os_response.json.return_value = {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "title": "Quick Start",
                            "url": "https://docs.gostoa.dev/guides/quickstart",
                            "content": "Get started quickly",
                            "heading": "Overview",
                        },
                        "_score": 0.95,
                    }
                ]
            }
        }

        with (
            patch.object(self.svc, "generate_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536),
            patch("src.services.docs_embedding_service.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_os_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            results = await self.svc.search_semantic("quick start", limit=5)
            assert len(results) == 1
            assert results[0]["title"] == "Quick Start"
            assert results[0]["score"] == 0.95

    @pytest.mark.asyncio
    async def test_empty_embedding_returns_empty(self):
        """If embedding generation fails, return empty results."""
        with patch.object(self.svc, "generate_embedding", new_callable=AsyncMock, return_value=[]):
            results = await self.svc.search_semantic("test query", limit=5)
            assert results == []


# ---------------------------------------------------------------------------
# Hybrid Search Tests (RRF)
# ---------------------------------------------------------------------------


class TestHybridSearch:
    def setup_method(self):
        self.svc = DocsEmbeddingService()

    @pytest.mark.asyncio
    async def test_rrf_fusion_scoring(self):
        """RRF merges keyword + semantic results with reciprocal rank scores."""
        keyword_response = DocsSearchResponse(
            query="mcp gateway",
            total=2,
            results=[
                DocsSearchResult(title="MCP Guide", url="https://docs.gostoa.dev/guides/mcp", snippet="...", score=1.0),
                DocsSearchResult(title="Gateway ADR", url="https://docs.gostoa.dev/adr/024", snippet="...", score=0.8),
            ],
        )
        semantic_results = [
            {"title": "Gateway ADR", "url": "https://docs.gostoa.dev/adr/024", "content": "...", "score": 0.9},
            {"title": "MCP Overview", "url": "https://docs.gostoa.dev/concepts/mcp", "content": "...", "score": 0.7},
        ]

        with (
            patch("src.routers.docs_search.get_docs_search_service") as mock_kw_svc,
            patch.object(self.svc, "search_semantic", new_callable=AsyncMock, return_value=semantic_results),
        ):
            mock_service = MagicMock()
            mock_service.search = AsyncMock(return_value=keyword_response)
            mock_kw_svc.return_value = mock_service

            results = await self.svc.search_hybrid("mcp gateway", limit=5)
            assert len(results) >= 2
            # Gateway ADR appears in both lists — should have highest RRF score
            urls = [r["url"] for r in results]
            assert "https://docs.gostoa.dev/adr/024" in urls

    @pytest.mark.asyncio
    async def test_url_deduplication(self):
        """Same URL from keyword + semantic should appear only once."""
        keyword_response = DocsSearchResponse(
            query="test",
            total=1,
            results=[
                DocsSearchResult(title="Shared Doc", url="https://docs.gostoa.dev/shared", snippet="...", score=1.0),
            ],
        )
        semantic_results = [
            {"title": "Shared Doc", "url": "https://docs.gostoa.dev/shared", "content": "...", "score": 0.9},
        ]

        with (
            patch("src.routers.docs_search.get_docs_search_service") as mock_kw_svc,
            patch.object(self.svc, "search_semantic", new_callable=AsyncMock, return_value=semantic_results),
        ):
            mock_service = MagicMock()
            mock_service.search = AsyncMock(return_value=keyword_response)
            mock_kw_svc.return_value = mock_service

            results = await self.svc.search_hybrid("test", limit=5)
            urls = [r["url"] for r in results]
            assert len(urls) == len({u.rstrip("/") for u in urls})


# ---------------------------------------------------------------------------
# Reindex Tests
# ---------------------------------------------------------------------------


class TestReindex:
    def setup_method(self):
        self.svc = DocsEmbeddingService()

    @pytest.mark.asyncio
    async def test_success_pipeline(self):
        """Full reindex: fetch → parse → chunk → embed → index."""
        mock_fetch_resp = MagicMock()
        mock_fetch_resp.text = "## Quick Start\n> Get started\n- URL: https://example.com/qs\n"
        mock_fetch_resp.raise_for_status = MagicMock()

        mock_head_resp = MagicMock()
        mock_head_resp.status_code = 200  # Index exists

        mock_put_resp = MagicMock()
        mock_put_resp.status_code = 201

        with (
            patch("src.services.docs_embedding_service.httpx.AsyncClient") as mock_client_cls,
            patch.object(self.svc, "generate_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536),
        ):
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_fetch_resp
            mock_client.head.return_value = mock_head_resp
            mock_client.put.return_value = mock_put_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await self.svc.reindex()
            assert result.total_entries == 1
            assert result.total_chunks >= 1
            assert result.indexed >= 1
            assert result.errors == 0

    @pytest.mark.asyncio
    async def test_fetch_failure(self):
        """Reindex returns error when llms-full.txt fetch fails."""
        with patch("src.services.docs_embedding_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.HTTPError("timeout")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await self.svc.reindex()
            assert result.errors == 1
            assert "Failed to fetch" in result.error_details[0]


# ---------------------------------------------------------------------------
# Search Mode Endpoint Tests
# ---------------------------------------------------------------------------


class TestSearchModeEndpoint:
    def setup_method(self):
        self.mock_keyword_svc = MagicMock(spec=DocsSearchService)
        self.mock_keyword_svc.search = AsyncMock(
            return_value=DocsSearchResponse(
                query="test",
                total=1,
                results=[
                    DocsSearchResult(
                        title="Keyword Result",
                        url="https://docs.gostoa.dev/test",
                        snippet="A keyword result",
                        score=1.0,
                    )
                ],
                took_ms=5.0,
            )
        )
        self.mock_embed_svc = MagicMock(spec=DocsEmbeddingService)
        self.mock_embed_svc.search_semantic = AsyncMock(
            return_value=[
                {
                    "title": "Semantic Result",
                    "url": "https://docs.gostoa.dev/semantic",
                    "content": "Semantic content",
                    "score": 0.85,
                }
            ]
        )
        self.mock_embed_svc.search_hybrid = AsyncMock(
            return_value=[
                {
                    "title": "Hybrid Result",
                    "url": "https://docs.gostoa.dev/hybrid",
                    "snippet": "Hybrid snippet",
                    "score": 0.75,
                }
            ]
        )

        app.dependency_overrides[get_docs_search_service] = lambda: self.mock_keyword_svc
        app.dependency_overrides[get_docs_embedding_service] = lambda: self.mock_embed_svc
        self.client = TestClient(app)

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_default_keyword_mode(self):
        resp = self.client.get("/v1/docs/search?q=test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "keyword"
        self.mock_keyword_svc.search.assert_called_once()

    def test_explicit_keyword_mode(self):
        resp = self.client.get("/v1/docs/search?q=test&mode=keyword")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "keyword"

    def test_semantic_mode(self):
        resp = self.client.get("/v1/docs/search?q=test&mode=semantic")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "semantic"
        assert data["results"][0]["title"] == "Semantic Result"
        self.mock_embed_svc.search_semantic.assert_called_once()

    def test_hybrid_mode(self):
        resp = self.client.get("/v1/docs/search?q=test&mode=hybrid")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "hybrid"
        assert data["results"][0]["title"] == "Hybrid Result"
        self.mock_embed_svc.search_hybrid.assert_called_once()


# ---------------------------------------------------------------------------
# Reindex Endpoint Tests
# ---------------------------------------------------------------------------


class TestReindexEndpoint:
    def test_disabled_by_default(self):
        mock_embed_svc = MagicMock(spec=DocsEmbeddingService)
        app.dependency_overrides[get_docs_embedding_service] = lambda: mock_embed_svc
        client = TestClient(app)

        resp = client.post("/v1/docs/admin/reindex")
        assert resp.status_code == 403
        assert "disabled" in resp.json()["detail"].lower()

        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Categorize URL Helper Tests
# ---------------------------------------------------------------------------


class TestCategorizeUrl:
    def test_blog(self):
        assert _categorize_url("https://docs.gostoa.dev/blog/post") == "blog"

    def test_adr(self):
        assert _categorize_url("https://docs.gostoa.dev/adr/adr-024") == "adr"

    def test_guide(self):
        assert _categorize_url("https://docs.gostoa.dev/guides/quickstart") == "guide"

    def test_docs(self):
        assert _categorize_url("https://docs.gostoa.dev/docs/overview") == "docs"

    def test_unknown(self):
        assert _categorize_url("https://example.com/other") is None


# ---------------------------------------------------------------------------
# Embedding Singleton Tests
# ---------------------------------------------------------------------------


class TestEmbeddingSingleton:
    def test_returns_instance(self):
        import src.services.docs_embedding_service as mod

        mod._embedding_service = None
        svc = get_docs_embedding_service()
        assert isinstance(svc, DocsEmbeddingService)

    def test_returns_same_instance(self):
        import src.services.docs_embedding_service as mod

        mod._embedding_service = None
        svc1 = get_docs_embedding_service()
        svc2 = get_docs_embedding_service()
        assert svc1 is svc2
