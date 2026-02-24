"""Tests for docs search router — /v1/docs/search and /v1/docs/admin/reindex.

Complements test_docs_search.py (which tests service internals and the search
mode endpoint comprehensively). This file focuses on:
- _categorize_url helper
- Query param validation (empty query, limit bounds, invalid mode)
- Reindex gating via DOCS_REINDEX_ENABLED flag
- Reindex success path
"""

from unittest.mock import AsyncMock, MagicMock, patch

from src.routers.docs_search import (
    DocsEmbeddingService,
    DocsSearchResponse,
    DocsSearchResult,
    DocsSearchService,
    _categorize_url,
    get_docs_embedding_service,
    get_docs_search_service,
)

# ---------------------------------------------------------------------------
# Helper: _categorize_url
# ---------------------------------------------------------------------------


class TestCategorizeUrl:
    """Unit tests for _categorize_url helper."""

    def test_blog_url_returns_blog(self):
        assert _categorize_url("https://docs.gostoa.dev/blog/some-post") == "blog"

    def test_adr_url_returns_adr(self):
        assert _categorize_url("https://docs.gostoa.dev/architecture/adr/adr-024") == "adr"

    def test_guides_url_returns_guide(self):
        assert _categorize_url("https://docs.gostoa.dev/guides/quickstart") == "guide"

    def test_docs_url_returns_docs(self):
        assert _categorize_url("https://docs.gostoa.dev/docs/concepts/architecture") == "docs"

    def test_unknown_url_returns_none(self):
        assert _categorize_url("https://example.com/random") is None

    def test_empty_url_returns_none(self):
        assert _categorize_url("") is None


# ---------------------------------------------------------------------------
# Query param validation
# ---------------------------------------------------------------------------


class TestSearchQueryValidation:
    """GET /v1/docs/search — input validation via FastAPI."""

    def setup_method(self):
        from src.main import app

        self.mock_svc = MagicMock(spec=DocsSearchService)
        self.mock_svc.search = AsyncMock(return_value=DocsSearchResponse(query="x", total=0, results=[], took_ms=1.0))
        self.mock_embed = MagicMock(spec=DocsEmbeddingService)
        self.mock_embed.search_semantic = AsyncMock(return_value=[])
        self.mock_embed.search_hybrid = AsyncMock(return_value=[])

        app.dependency_overrides[get_docs_search_service] = lambda: self.mock_svc
        app.dependency_overrides[get_docs_embedding_service] = lambda: self.mock_embed

        from fastapi.testclient import TestClient

        self.client = TestClient(app)

    def teardown_method(self):
        from src.main import app

        app.dependency_overrides.clear()

    def test_empty_query_returns_422(self):
        """Empty q value (min_length=1) returns 422."""
        resp = self.client.get("/v1/docs/search?q=")
        assert resp.status_code == 422

    def test_missing_query_returns_422(self):
        """Missing q param returns 422."""
        resp = self.client.get("/v1/docs/search")
        assert resp.status_code == 422

    def test_limit_zero_returns_422(self):
        """limit=0 (below min=1) returns 422."""
        resp = self.client.get("/v1/docs/search?q=test&limit=0")
        assert resp.status_code == 422

    def test_limit_too_large_returns_422(self):
        """limit=21 (above max=20) returns 422."""
        resp = self.client.get("/v1/docs/search?q=test&limit=21")
        assert resp.status_code == 422

    def test_invalid_mode_returns_422(self):
        """Unknown mode value returns 422 (Literal validation)."""
        resp = self.client.get("/v1/docs/search?q=test&mode=fuzzy")
        assert resp.status_code == 422

    def test_valid_query_returns_200(self):
        """Valid query returns 200."""
        resp = self.client.get("/v1/docs/search?q=stoa+gateway")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Search mode routing
# ---------------------------------------------------------------------------


class TestSearchModeRouting:
    """Verify each mode routes to the correct service method."""

    def setup_method(self):
        from src.main import app

        self.mock_kw_svc = MagicMock(spec=DocsSearchService)
        self.mock_kw_svc.search = AsyncMock(
            return_value=DocsSearchResponse(
                query="test",
                total=1,
                results=[
                    DocsSearchResult(
                        title="Keyword Hit",
                        url="https://docs.gostoa.dev/blog/keyword",
                        snippet="keyword snippet",
                        score=1.0,
                        category="blog",
                    )
                ],
                took_ms=5.0,
            )
        )
        self.mock_embed_svc = MagicMock(spec=DocsEmbeddingService)
        self.mock_embed_svc.search_semantic = AsyncMock(
            return_value=[
                {
                    "title": "Semantic Hit",
                    "url": "https://docs.gostoa.dev/docs/guides/quickstart",
                    "content": "semantic content",
                    "score": 0.9,
                }
            ]
        )
        self.mock_embed_svc.search_hybrid = AsyncMock(
            return_value=[
                {
                    "title": "Hybrid Hit",
                    "url": "https://docs.gostoa.dev/guides/hybrid",
                    "snippet": "hybrid snippet",
                    "score": 0.85,
                }
            ]
        )

        app.dependency_overrides[get_docs_search_service] = lambda: self.mock_kw_svc
        app.dependency_overrides[get_docs_embedding_service] = lambda: self.mock_embed_svc

        from fastapi.testclient import TestClient

        self.client = TestClient(app)

    def teardown_method(self):
        from src.main import app

        app.dependency_overrides.clear()

    def test_keyword_mode_calls_service_search(self):
        """mode=keyword delegates to DocsSearchService.search."""
        resp = self.client.get("/v1/docs/search?q=test&mode=keyword")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "keyword"
        self.mock_kw_svc.search.assert_awaited_once_with(query="test", limit=5)
        self.mock_embed_svc.search_semantic.assert_not_called()
        self.mock_embed_svc.search_hybrid.assert_not_called()

    def test_semantic_mode_calls_embed_search(self):
        """mode=semantic delegates to DocsEmbeddingService.search_semantic."""
        resp = self.client.get("/v1/docs/search?q=mcp+protocol&mode=semantic&limit=3")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "semantic"
        assert len(data["results"]) == 1
        assert data["results"][0]["title"] == "Semantic Hit"
        self.mock_embed_svc.search_semantic.assert_awaited_once_with("mcp protocol", limit=3)
        self.mock_kw_svc.search.assert_not_called()

    def test_hybrid_mode_calls_hybrid_search(self):
        """mode=hybrid delegates to DocsEmbeddingService.search_hybrid."""
        resp = self.client.get("/v1/docs/search?q=api+gateway&mode=hybrid")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "hybrid"
        assert len(data["results"]) == 1
        self.mock_embed_svc.search_hybrid.assert_awaited_once_with("api gateway", limit=5)
        self.mock_kw_svc.search.assert_not_called()

    def test_default_mode_is_keyword(self):
        """When mode is omitted, defaults to keyword."""
        resp = self.client.get("/v1/docs/search?q=test")
        assert resp.status_code == 200
        assert resp.json()["mode"] == "keyword"
        self.mock_kw_svc.search.assert_awaited_once()

    def test_semantic_categorizes_blog_url(self):
        """Semantic results have category derived from URL path."""
        self.mock_embed_svc.search_semantic = AsyncMock(
            return_value=[
                {
                    "title": "Blog Post",
                    "url": "https://docs.gostoa.dev/blog/esb-is-dead",
                    "content": "content",
                    "score": 0.9,
                }
            ]
        )
        resp = self.client.get("/v1/docs/search?q=esb&mode=semantic")
        result = resp.json()["results"][0]
        assert result["category"] == "blog"

    def test_semantic_categorizes_adr_url(self):
        """ADR URLs get category=adr in semantic mode."""
        self.mock_embed_svc.search_semantic = AsyncMock(
            return_value=[
                {
                    "title": "ADR-024",
                    "url": "https://docs.gostoa.dev/architecture/adr/adr-024-modes",
                    "content": "content",
                    "score": 0.88,
                }
            ]
        )
        resp = self.client.get("/v1/docs/search?q=gateway+modes&mode=semantic")
        result = resp.json()["results"][0]
        assert result["category"] == "adr"


# ---------------------------------------------------------------------------
# POST /v1/docs/admin/reindex
# ---------------------------------------------------------------------------


class TestReindexDocs:
    """POST /v1/docs/admin/reindex"""

    def setup_method(self):
        from src.main import app

        self.mock_embed_svc = MagicMock(spec=DocsEmbeddingService)
        app.dependency_overrides[get_docs_embedding_service] = lambda: self.mock_embed_svc

        from fastapi.testclient import TestClient

        self.client = TestClient(app)

    def teardown_method(self):
        from src.main import app

        app.dependency_overrides.clear()

    def test_reindex_disabled_returns_403(self):
        """DOCS_REINDEX_ENABLED=false → 403."""
        with patch("src.routers.docs_search.settings") as mock_settings:
            mock_settings.DOCS_REINDEX_ENABLED = False
            resp = self.client.post("/v1/docs/admin/reindex")

        assert resp.status_code == 403
        assert "disabled" in resp.json()["detail"].lower()

    def test_reindex_enabled_triggers_pipeline(self):
        """DOCS_REINDEX_ENABLED=true → runs reindex and returns stats."""
        mock_result = MagicMock()
        mock_result.total_entries = 50
        mock_result.total_chunks = 200
        mock_result.indexed = 198
        mock_result.errors = 2
        mock_result.error_details = ["chunk-x failed"]
        self.mock_embed_svc.reindex = AsyncMock(return_value=mock_result)

        with patch("src.routers.docs_search.settings") as mock_settings:
            mock_settings.DOCS_REINDEX_ENABLED = True
            resp = self.client.post("/v1/docs/admin/reindex")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_entries"] == 50
        assert data["total_chunks"] == 200
        assert data["indexed"] == 198
        assert data["errors"] == 2
        assert "chunk-x failed" in data["error_details"]
        self.mock_embed_svc.reindex.assert_awaited_once()

    def test_reindex_enabled_zero_errors(self):
        """Successful reindex with no errors returns correct stats."""
        mock_result = MagicMock()
        mock_result.total_entries = 10
        mock_result.total_chunks = 40
        mock_result.indexed = 40
        mock_result.errors = 0
        mock_result.error_details = []
        self.mock_embed_svc.reindex = AsyncMock(return_value=mock_result)

        with patch("src.routers.docs_search.settings") as mock_settings:
            mock_settings.DOCS_REINDEX_ENABLED = True
            resp = self.client.post("/v1/docs/admin/reindex")

        assert resp.status_code == 200
        assert resp.json()["errors"] == 0
        assert resp.json()["error_details"] == []
