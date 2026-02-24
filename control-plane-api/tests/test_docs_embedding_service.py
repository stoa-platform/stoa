"""Tests for DocsEmbeddingService — chunking, embedding, search, RRF (CAB-1327 Phase 2)."""

from unittest.mock import AsyncMock, MagicMock, patch

from src.services.docs_embedding_service import (
    DocChunk,
    DocsEmbeddingService,
    get_docs_embedding_service,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service() -> DocsEmbeddingService:
    return DocsEmbeddingService()


def _make_response(status_code: int, json_data: dict | None = None, text: str = "") -> MagicMock:
    """Build a minimal mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    if json_data is not None:
        resp.json = MagicMock(return_value=json_data)
    else:
        resp.json = MagicMock(return_value={})
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# chunk_markdown
# ---------------------------------------------------------------------------


class TestChunkMarkdown:
    def test_empty_content_returns_empty_list(self) -> None:
        result = DocsEmbeddingService.chunk_markdown("")
        assert result == []

    def test_whitespace_only_returns_empty_list(self) -> None:
        result = DocsEmbeddingService.chunk_markdown("   \n\n  ")
        assert result == []

    def test_single_section_no_heading(self) -> None:
        content = "Hello world.\nThis is a paragraph."
        result = DocsEmbeddingService.chunk_markdown(content, title="My Doc", url="/doc")
        assert len(result) == 1
        chunk = result[0]
        assert isinstance(chunk, DocChunk)
        assert chunk.title == "My Doc"
        assert chunk.url == "/doc"
        assert "Hello world" in chunk.content
        assert chunk.chunk_index == 0

    def test_multiple_h2_sections_produce_multiple_chunks(self) -> None:
        content = "Intro text.\n## Section A\nContent A.\n## Section B\nContent B."
        result = DocsEmbeddingService.chunk_markdown(content, title="T", url="/t")
        # 3 sections: intro + Section A + Section B
        assert len(result) == 3

    def test_h2_headings_captured_as_heading_field(self) -> None:
        content = "## Authentication\nHow to auth.\n## Authorization\nHow to authz."
        result = DocsEmbeddingService.chunk_markdown(content)
        headings = [c.heading for c in result]
        assert "Authentication" in headings
        assert "Authorization" in headings

    def test_oversized_section_split_into_windows(self) -> None:
        # Build a section larger than max_chars=100
        big_text = "A" * 250
        content = f"## Big Section\n{big_text}"
        result = DocsEmbeddingService.chunk_markdown(content, max_chars=100, overlap=10)
        # Should produce multiple chunks
        assert len(result) > 1
        for chunk in result:
            assert len(chunk.content) <= 100

    def test_oversized_section_overlap_produces_repeated_content(self) -> None:
        """The tail of chunk N should appear at the start of chunk N+1 (overlap behavior)."""
        big_text = "X" * 300
        content = f"## Overlap Section\n{big_text}"
        result = DocsEmbeddingService.chunk_markdown(content, max_chars=100, overlap=20)
        assert len(result) >= 2
        # The last 20 chars of chunk 0 should equal the first 20 chars of chunk 1
        tail = result[0].content[-20:]
        head = result[1].content[:20]
        assert tail == head

    def test_chunk_indices_are_sequential(self) -> None:
        content = "## A\nContent A.\n## B\nContent B.\n## C\nContent C."
        result = DocsEmbeddingService.chunk_markdown(content)
        indices = [c.chunk_index for c in result]
        assert indices == list(range(len(indices)))

    def test_section_with_empty_text_is_skipped(self) -> None:
        """Sections that contain only whitespace are not chunked."""
        content = "## Empty\n   \n## HasContent\nSome real text."
        result = DocsEmbeddingService.chunk_markdown(content)
        assert len(result) == 1
        assert "Some real text" in result[0].content

    def test_title_used_as_initial_heading_for_pre_h2_content(self) -> None:
        content = "Preamble before any heading.\n## Section\nContent."
        result = DocsEmbeddingService.chunk_markdown(content, title="Doc Title")
        # First chunk comes from lines before ## heading — heading should be the title
        first = result[0]
        assert first.heading == "Doc Title"


# ---------------------------------------------------------------------------
# generate_embedding
# ---------------------------------------------------------------------------


class TestGenerateEmbedding:
    async def test_disabled_provider_returns_empty(self) -> None:
        svc = _make_service()
        with patch("src.services.docs_embedding_service.settings") as mock_settings:
            mock_settings.EMBEDDING_PROVIDER = "none"
            mock_settings.EMBEDDING_API_KEY = "somekey"
            result = await svc.generate_embedding("hello")
        assert result == []

    async def test_no_api_key_returns_empty(self) -> None:
        svc = _make_service()
        with patch("src.services.docs_embedding_service.settings") as mock_settings:
            mock_settings.EMBEDDING_PROVIDER = "openai"
            mock_settings.EMBEDDING_API_KEY = ""
            result = await svc.generate_embedding("hello")
        assert result == []

    async def test_success_returns_vector(self) -> None:
        svc = _make_service()
        embedding_vector = [0.1, 0.2, 0.3]
        mock_resp = _make_response(
            200,
            json_data={"data": [{"embedding": embedding_vector}]},
        )

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("src.services.docs_embedding_service.settings") as mock_settings,
            patch(
                "src.services.docs_embedding_service.httpx.AsyncClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.EMBEDDING_PROVIDER = "openai"
            mock_settings.EMBEDDING_API_KEY = "sk-test"
            mock_settings.EMBEDDING_API_URL = "https://api.openai.com/v1/embeddings"
            mock_settings.EMBEDDING_MODEL = "text-embedding-3-small"
            mock_settings.EMBEDDING_DIMENSIONS = 1536
            result = await svc.generate_embedding("test text")

        assert result == embedding_vector

    async def test_http_error_returns_empty(self) -> None:
        import httpx

        svc = _make_service()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

        with (
            patch("src.services.docs_embedding_service.settings") as mock_settings,
            patch(
                "src.services.docs_embedding_service.httpx.AsyncClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.EMBEDDING_PROVIDER = "openai"
            mock_settings.EMBEDDING_API_KEY = "sk-test"
            mock_settings.EMBEDDING_API_URL = "https://api.openai.com/v1/embeddings"
            mock_settings.EMBEDDING_MODEL = "text-embedding-3-small"
            mock_settings.EMBEDDING_DIMENSIONS = 1536
            result = await svc.generate_embedding("test")

        assert result == []

    async def test_malformed_response_returns_empty(self) -> None:
        """Response missing the 'data' key should return [] gracefully."""
        svc = _make_service()
        # Response with wrong structure — no 'data' key
        mock_resp = _make_response(200, json_data={"unexpected": "structure"})
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("src.services.docs_embedding_service.settings") as mock_settings,
            patch(
                "src.services.docs_embedding_service.httpx.AsyncClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.EMBEDDING_PROVIDER = "openai"
            mock_settings.EMBEDDING_API_KEY = "sk-test"
            mock_settings.EMBEDDING_API_URL = "https://api.openai.com/v1/embeddings"
            mock_settings.EMBEDDING_MODEL = "text-embedding-3-small"
            mock_settings.EMBEDDING_DIMENSIONS = 1536
            result = await svc.generate_embedding("test")

        assert result == []


# ---------------------------------------------------------------------------
# search_semantic
# ---------------------------------------------------------------------------


class TestSearchSemantic:
    async def test_no_embedding_returns_empty(self) -> None:
        svc = _make_service()
        svc.generate_embedding = AsyncMock(return_value=[])  # type: ignore[method-assign]

        result = await svc.search_semantic("query")

        assert result == []

    async def test_success_returns_hits(self) -> None:
        svc = _make_service()
        query_vec = [0.1, 0.2, 0.3]
        svc.generate_embedding = AsyncMock(return_value=query_vec)  # type: ignore[method-assign]

        os_response = {
            "hits": {
                "hits": [
                    {
                        "_score": 0.95,
                        "_source": {
                            "title": "Getting Started",
                            "url": "/docs/getting-started",
                            "content": "Welcome to STOA.",
                            "heading": "Introduction",
                            "chunk_index": 0,
                        },
                    }
                ]
            }
        }
        mock_resp = _make_response(200, json_data=os_response)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("src.services.docs_embedding_service.settings") as mock_settings,
            patch(
                "src.services.docs_embedding_service.httpx.AsyncClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.OPENSEARCH_URL = "http://opensearch:9200"
            mock_settings.OPENSEARCH_DOCS_INDEX = "docs-embeddings"
            result = await svc.search_semantic("getting started")

        assert len(result) == 1
        assert result[0]["title"] == "Getting Started"
        assert result[0]["score"] == 0.95

    async def test_non_200_response_returns_empty(self) -> None:
        svc = _make_service()
        svc.generate_embedding = AsyncMock(return_value=[0.1, 0.2])  # type: ignore[method-assign]

        mock_resp = _make_response(503)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("src.services.docs_embedding_service.settings") as mock_settings,
            patch(
                "src.services.docs_embedding_service.httpx.AsyncClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.OPENSEARCH_URL = "http://opensearch:9200"
            mock_settings.OPENSEARCH_DOCS_INDEX = "docs-embeddings"
            result = await svc.search_semantic("test")

        assert result == []

    async def test_http_error_returns_empty(self) -> None:
        import httpx

        svc = _make_service()
        svc.generate_embedding = AsyncMock(return_value=[0.1, 0.2])  # type: ignore[method-assign]

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

        with (
            patch("src.services.docs_embedding_service.settings") as mock_settings,
            patch(
                "src.services.docs_embedding_service.httpx.AsyncClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.OPENSEARCH_URL = "http://opensearch:9200"
            mock_settings.OPENSEARCH_DOCS_INDEX = "docs-embeddings"
            result = await svc.search_semantic("test")

        assert result == []

    async def test_empty_hits_returns_empty_list(self) -> None:
        svc = _make_service()
        svc.generate_embedding = AsyncMock(return_value=[0.1])  # type: ignore[method-assign]

        mock_resp = _make_response(200, json_data={"hits": {"hits": []}})

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("src.services.docs_embedding_service.settings") as mock_settings,
            patch(
                "src.services.docs_embedding_service.httpx.AsyncClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.OPENSEARCH_URL = "http://opensearch:9200"
            mock_settings.OPENSEARCH_DOCS_INDEX = "docs-embeddings"
            result = await svc.search_semantic("nothing")

        assert result == []


# ---------------------------------------------------------------------------
# search_hybrid (RRF)
# ---------------------------------------------------------------------------


class TestSearchHybrid:
    def _make_keyword_result(self, url: str, title: str, snippet: str = "") -> MagicMock:
        r = MagicMock()
        r.url = url
        r.title = title
        r.snippet = snippet
        r.category = None
        return r

    async def test_both_sources_fused_by_rrf(self) -> None:
        """When both keyword and semantic return results, RRF scores are merged."""
        svc = _make_service()

        kw_result = self._make_keyword_result("/docs/a", "Doc A")
        kw_response = MagicMock()
        kw_response.results = [kw_result]

        sem_result = {"url": "/docs/b", "title": "Doc B", "content": "B content", "heading": ""}
        svc.search_semantic = AsyncMock(return_value=[sem_result])  # type: ignore[method-assign]

        mock_kw_svc = MagicMock()
        mock_kw_svc.search = AsyncMock(return_value=kw_response)

        with patch(
            "src.routers.docs_search.get_docs_search_service",
            return_value=mock_kw_svc,
        ):
            result = await svc.search_hybrid("test query", limit=5)

        urls = [r["url"] for r in result]
        # Both sources should appear
        assert "/docs/a" in urls
        assert "/docs/b" in urls

    async def test_rrf_score_computed_correctly(self) -> None:
        """RRF formula: weight / (k + rank) with k=60, keyword_weight=semantic_weight=0.5."""
        svc = _make_service()

        # Rank 1 keyword result
        kw_result = self._make_keyword_result("/docs/same", "Same Doc")
        kw_response = MagicMock()
        kw_response.results = [kw_result]

        # Same URL also appears as rank 1 semantic result
        sem_result = {"url": "/docs/same", "title": "Same Doc", "content": "c", "heading": ""}
        svc.search_semantic = AsyncMock(return_value=[sem_result])  # type: ignore[method-assign]

        mock_kw_svc = MagicMock()
        mock_kw_svc.search = AsyncMock(return_value=kw_response)

        with patch(
            "src.routers.docs_search.get_docs_search_service",
            return_value=mock_kw_svc,
        ):
            result = await svc.search_hybrid("query", limit=5, keyword_weight=0.5, semantic_weight=0.5)

        assert len(result) == 1
        expected_score = 0.5 / (60 + 1) + 0.5 / (60 + 1)
        assert abs(result[0]["score"] - expected_score) < 1e-9

    async def test_keyword_only_result_scored_from_keyword(self) -> None:
        """A URL that appears only in keyword results gets only the keyword RRF term."""
        svc = _make_service()

        kw_result = self._make_keyword_result("/docs/kw-only", "KW Only")
        kw_response = MagicMock()
        kw_response.results = [kw_result]

        # Semantic returns empty
        svc.search_semantic = AsyncMock(return_value=[])  # type: ignore[method-assign]

        mock_kw_svc = MagicMock()
        mock_kw_svc.search = AsyncMock(return_value=kw_response)

        with patch(
            "src.routers.docs_search.get_docs_search_service",
            return_value=mock_kw_svc,
        ):
            result = await svc.search_hybrid("query", limit=5, keyword_weight=0.5, semantic_weight=0.5)

        assert len(result) == 1
        expected_score = 0.5 / (60 + 1)
        assert abs(result[0]["score"] - expected_score) < 1e-9

    async def test_semantic_only_result_scored_from_semantic(self) -> None:
        """A URL that appears only in semantic results gets only the semantic RRF term."""
        svc = _make_service()

        kw_response = MagicMock()
        kw_response.results = []

        sem_result = {"url": "/docs/sem-only", "title": "Sem Only", "content": "c", "heading": ""}
        svc.search_semantic = AsyncMock(return_value=[sem_result])  # type: ignore[method-assign]

        mock_kw_svc = MagicMock()
        mock_kw_svc.search = AsyncMock(return_value=kw_response)

        with patch(
            "src.routers.docs_search.get_docs_search_service",
            return_value=mock_kw_svc,
        ):
            result = await svc.search_hybrid("query", limit=5, keyword_weight=0.5, semantic_weight=0.5)

        assert len(result) == 1
        expected_score = 0.5 / (60 + 1)
        assert abs(result[0]["score"] - expected_score) < 1e-9

    async def test_trailing_slash_normalised_in_url(self) -> None:
        """URLs differing only by trailing slash should be merged to the same entry."""
        svc = _make_service()

        kw_result = self._make_keyword_result("/docs/page/", "Page")
        kw_response = MagicMock()
        kw_response.results = [kw_result]

        sem_result = {"url": "/docs/page", "title": "Page", "content": "c", "heading": ""}
        svc.search_semantic = AsyncMock(return_value=[sem_result])  # type: ignore[method-assign]

        mock_kw_svc = MagicMock()
        mock_kw_svc.search = AsyncMock(return_value=kw_response)

        with patch(
            "src.routers.docs_search.get_docs_search_service",
            return_value=mock_kw_svc,
        ):
            result = await svc.search_hybrid("query", limit=5)

        # Both /docs/page/ and /docs/page normalise to /docs/page → single result
        assert len(result) == 1

    async def test_limit_respected(self) -> None:
        """Result list should not exceed limit."""
        svc = _make_service()

        # Return 5 keyword results
        kw_results = [self._make_keyword_result(f"/docs/{i}", f"Doc {i}") for i in range(5)]
        kw_response = MagicMock()
        kw_response.results = kw_results

        # Return 5 semantic results (different URLs)
        sem_results = [{"url": f"/docs/sem-{i}", "title": f"Sem {i}", "content": "c", "heading": ""} for i in range(5)]
        svc.search_semantic = AsyncMock(return_value=sem_results)  # type: ignore[method-assign]

        mock_kw_svc = MagicMock()
        mock_kw_svc.search = AsyncMock(return_value=kw_response)

        with patch(
            "src.routers.docs_search.get_docs_search_service",
            return_value=mock_kw_svc,
        ):
            result = await svc.search_hybrid("query", limit=3)

        assert len(result) <= 3


# ---------------------------------------------------------------------------
# Singleton: get_docs_embedding_service
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_returns_same_instance(self) -> None:
        import src.services.docs_embedding_service as module

        # Reset singleton for test isolation
        original = module._embedding_service
        module._embedding_service = None
        try:
            svc1 = get_docs_embedding_service()
            svc2 = get_docs_embedding_service()
            assert svc1 is svc2
        finally:
            module._embedding_service = original

    def test_returns_docs_embedding_service_instance(self) -> None:
        import src.services.docs_embedding_service as module

        original = module._embedding_service
        module._embedding_service = None
        try:
            svc = get_docs_embedding_service()
            assert isinstance(svc, DocsEmbeddingService)
        finally:
            module._embedding_service = original

    def test_does_not_recreate_if_already_set(self) -> None:
        import src.services.docs_embedding_service as module

        pre_existing = DocsEmbeddingService()
        module._embedding_service = pre_existing
        try:
            result = get_docs_embedding_service()
            assert result is pre_existing
        finally:
            module._embedding_service = None
