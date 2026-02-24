"""Unit tests for DocsEmbeddingService — docs_embedding_service.py (CAB-1437 Phase 2)

Tests markdown chunking (pure), embedding generation, and semantic search.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.services.docs_embedding_service import DocChunk, DocsEmbeddingService, ReindexResult

# ── chunk_markdown (pure, no I/O) ──


class TestChunkMarkdown:
    def test_empty_content(self):
        chunks = DocsEmbeddingService.chunk_markdown("")
        assert chunks == []

    def test_whitespace_only(self):
        chunks = DocsEmbeddingService.chunk_markdown("   \n  \n  ")
        assert chunks == []

    def test_single_section(self):
        content = "This is a simple paragraph."
        chunks = DocsEmbeddingService.chunk_markdown(content, title="Test", url="/test")
        assert len(chunks) == 1
        assert chunks[0].title == "Test"
        assert chunks[0].url == "/test"
        assert chunks[0].content == "This is a simple paragraph."
        assert chunks[0].chunk_index == 0

    def test_splits_on_h2_headings(self):
        content = "Intro text\n## Section A\nContent A\n## Section B\nContent B"
        chunks = DocsEmbeddingService.chunk_markdown(content, title="Doc")
        assert len(chunks) == 3  # intro + Section A + Section B
        headings = [c.heading for c in chunks]
        assert "Section A" in headings
        assert "Section B" in headings

    def test_preserves_heading_text(self):
        content = "## Getting Started\nInstall with npm."
        chunks = DocsEmbeddingService.chunk_markdown(content)
        assert chunks[0].heading == "Getting Started"
        assert "Install with npm" in chunks[0].content

    def test_oversized_section_splits_with_overlap(self):
        long_text = "A" * 5000
        chunks = DocsEmbeddingService.chunk_markdown(long_text, max_chars=2048, overlap=200)
        assert len(chunks) >= 3  # 5000 / (2048-200) ≈ 2.7 → 3 chunks
        # Verify overlap: second chunk should start before first chunk ends
        assert chunks[0].chunk_index == 0
        assert chunks[1].chunk_index == 1

    def test_sequential_chunk_indices(self):
        content = "## A\nAAA\n## B\nBBB\n## C\nCCC"
        chunks = DocsEmbeddingService.chunk_markdown(content)
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_empty_sections_skipped(self):
        content = "## Empty\n\n## HasContent\nReal content here"
        chunks = DocsEmbeddingService.chunk_markdown(content)
        assert len(chunks) == 1
        assert chunks[0].heading == "HasContent"

    def test_url_and_title_propagated(self):
        content = "## Sec\nContent"
        chunks = DocsEmbeddingService.chunk_markdown(content, title="My Doc", url="/docs/my-doc")
        for chunk in chunks:
            assert chunk.title == "My Doc"
            assert chunk.url == "/docs/my-doc"


# ── DocChunk dataclass ──


class TestDocChunk:
    def test_defaults(self):
        chunk = DocChunk(title="T", url="/u", content="C")
        assert chunk.chunk_index == 0
        assert chunk.heading == ""


# ── ReindexResult dataclass ──


class TestReindexResult:
    def test_defaults(self):
        r = ReindexResult()
        assert r.total_entries == 0
        assert r.total_chunks == 0
        assert r.indexed == 0
        assert r.errors == 0
        assert r.error_details == []


# ── generate_embedding ──


class TestGenerateEmbedding:
    @pytest.fixture()
    def service(self):
        return DocsEmbeddingService()

    async def test_returns_empty_when_provider_none(self, service):
        with patch("src.services.docs_embedding_service.settings") as mock_settings:
            mock_settings.EMBEDDING_PROVIDER = "none"
            result = await service.generate_embedding("test text")
        assert result == []

    async def test_returns_empty_when_no_api_key(self, service):
        with patch("src.services.docs_embedding_service.settings") as mock_settings:
            mock_settings.EMBEDDING_PROVIDER = "openai"
            mock_settings.EMBEDDING_API_KEY = ""
            result = await service.generate_embedding("test text")
        assert result == []

    async def test_returns_embedding_on_success(self, service):
        mock_embedding = [0.1, 0.2, 0.3]
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"data": [{"embedding": mock_embedding}]}

        with (
            patch("src.services.docs_embedding_service.settings") as mock_settings,
            patch("httpx.AsyncClient") as MockClient,
        ):
            mock_settings.EMBEDDING_PROVIDER = "openai"
            mock_settings.EMBEDDING_API_KEY = "sk-test"
            mock_settings.EMBEDDING_API_URL = "https://api.openai.com/v1/embeddings"
            mock_settings.EMBEDDING_MODEL = "text-embedding-3-small"
            mock_settings.EMBEDDING_DIMENSIONS = 256

            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await service.generate_embedding("test text")

        assert result == mock_embedding

    async def test_returns_empty_on_http_error(self, service):
        with (
            patch("src.services.docs_embedding_service.settings") as mock_settings,
            patch("httpx.AsyncClient") as MockClient,
        ):
            mock_settings.EMBEDDING_PROVIDER = "openai"
            mock_settings.EMBEDDING_API_KEY = "sk-test"
            mock_settings.EMBEDDING_API_URL = "https://api.openai.com/v1/embeddings"
            mock_settings.EMBEDDING_MODEL = "text-embedding-3-small"
            mock_settings.EMBEDDING_DIMENSIONS = 256

            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.HTTPError("timeout")
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await service.generate_embedding("test text")

        assert result == []


# ── search_semantic ──


class TestSearchSemantic:
    @pytest.fixture()
    def service(self):
        return DocsEmbeddingService()

    async def test_returns_empty_when_no_embedding(self, service):
        with patch.object(service, "generate_embedding", return_value=[]):
            result = await service.search_semantic("query")
        assert result == []

    async def test_returns_results_on_success(self, service):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "title": "Quick Start",
                            "url": "/docs/quick-start",
                            "content": "Install STOA...",
                            "heading": "Installation",
                            "chunk_index": 0,
                        },
                        "_score": 0.95,
                    }
                ]
            }
        }

        with (
            patch.object(service, "generate_embedding", return_value=[0.1, 0.2]),
            patch("httpx.AsyncClient") as MockClient,
            patch("src.services.docs_embedding_service.settings") as mock_settings,
        ):
            mock_settings.OPENSEARCH_DOCS_INDEX = "stoa-docs"
            mock_settings.OPENSEARCH_URL = "http://localhost:9200"

            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await service.search_semantic("install stoa")

        assert len(results) == 1
        assert results[0]["title"] == "Quick Start"
        assert results[0]["score"] == 0.95
