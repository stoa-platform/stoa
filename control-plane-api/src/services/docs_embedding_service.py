"""Docs embedding service for semantic search (CAB-1327 Phase 2).

Provides chunking, embedding generation via OpenAI API, OpenSearch k-NN
indexing, and hybrid search (RRF fusion of Algolia keyword + k-NN semantic).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from ..config import settings
from ..logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DocChunk:
    """A chunk of documentation content for embedding."""

    title: str
    url: str
    content: str
    chunk_index: int = 0
    heading: str = ""


@dataclass
class ReindexResult:
    """Result of a reindex operation."""

    total_entries: int = 0
    total_chunks: int = 0
    indexed: int = 0
    errors: int = 0
    error_details: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class DocsEmbeddingService:
    """Handles embedding generation, OpenSearch k-NN indexing, and semantic search."""

    # -- Chunking ----------------------------------------------------------

    @staticmethod
    def chunk_markdown(
        content: str,
        title: str = "",
        url: str = "",
        max_chars: int = 2048,
        overlap: int = 200,
    ) -> list[DocChunk]:
        """Split markdown content by H2 headings with overlap.

        Strategy: split on ``## `` boundaries first. If a section exceeds
        *max_chars*, split it further with character-based windowing.
        """
        if not content.strip():
            return []

        sections: list[tuple[str, str]] = []  # (heading, text)
        current_heading = title
        current_lines: list[str] = []

        for line in content.splitlines():
            if line.startswith("## "):
                # Flush previous section
                if current_lines:
                    sections.append((current_heading, "\n".join(current_lines)))
                current_heading = line[3:].strip()
                current_lines = []
            else:
                current_lines.append(line)

        # Flush last section
        if current_lines:
            sections.append((current_heading, "\n".join(current_lines)))

        chunks: list[DocChunk] = []
        chunk_idx = 0
        for heading, text in sections:
            text = text.strip()
            if not text:
                continue

            if len(text) <= max_chars:
                chunks.append(
                    DocChunk(
                        title=title,
                        url=url,
                        content=text,
                        chunk_index=chunk_idx,
                        heading=heading,
                    )
                )
                chunk_idx += 1
            else:
                # Character-based windowing for oversized sections
                start = 0
                while start < len(text):
                    end = start + max_chars
                    chunk_text = text[start:end]
                    chunks.append(
                        DocChunk(
                            title=title,
                            url=url,
                            content=chunk_text,
                            chunk_index=chunk_idx,
                            heading=heading,
                        )
                    )
                    chunk_idx += 1
                    start = end - overlap if end < len(text) else len(text)

        return chunks

    # -- Embedding generation ----------------------------------------------

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate an embedding vector via the configured provider.

        Returns an empty list if the provider is disabled or the call fails.
        """
        if settings.EMBEDDING_PROVIDER == "none" or not settings.EMBEDDING_API_KEY:
            return []

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    settings.EMBEDDING_API_URL,
                    json={
                        "input": text[:8000],  # OpenAI limit ~8191 tokens
                        "model": settings.EMBEDDING_MODEL,
                        "dimensions": settings.EMBEDDING_DIMENSIONS,
                    },
                    headers={
                        "Authorization": f"Bearer {settings.EMBEDDING_API_KEY}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data["data"][0]["embedding"]
        except (httpx.HTTPError, KeyError, IndexError) as exc:
            logger.warning("Embedding generation failed: %s", exc)
            return []

    # -- OpenSearch k-NN ---------------------------------------------------

    async def _ensure_index(self, client: httpx.AsyncClient) -> None:
        """Create the k-NN index if it does not exist."""
        index = settings.OPENSEARCH_DOCS_INDEX
        resp = await client.head(f"{settings.OPENSEARCH_URL}/{index}")
        if resp.status_code == 200:
            return

        body = {
            "settings": {
                "index": {"knn": True, "knn.algo_param.ef_search": 100},
                "number_of_shards": 1,
                "number_of_replicas": 0,
            },
            "mappings": {
                "properties": {
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": settings.EMBEDDING_DIMENSIONS,
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "nmslib",
                        },
                    },
                    "title": {"type": "text"},
                    "url": {"type": "keyword"},
                    "content": {"type": "text"},
                    "heading": {"type": "keyword"},
                    "chunk_index": {"type": "integer"},
                }
            },
        }
        resp = await client.put(
            f"{settings.OPENSEARCH_URL}/{index}",
            json=body,
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code in (200, 201):
            logger.info("Created k-NN index: %s", index)
        else:
            logger.warning("Failed to create k-NN index: %s %s", resp.status_code, resp.text)

    async def reindex(self) -> ReindexResult:
        """Fetch llms-full.txt, chunk, embed, and bulk-upsert to OpenSearch k-NN."""
        result = ReindexResult()

        # Fetch llms-full.txt
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(settings.LLMS_FULL_TXT_URL)
                resp.raise_for_status()
                raw_text = resp.text
        except httpx.HTTPError as exc:
            result.errors = 1
            result.error_details.append(f"Failed to fetch llms-full.txt: {exc}")
            return result

        # Parse into entries
        from ..routers.docs_search import DocsSearchService

        entries = DocsSearchService._parse_llms_txt(raw_text)
        result.total_entries = len(entries)

        # Chunk all entries
        all_chunks: list[DocChunk] = []
        for entry in entries:
            chunks = self.chunk_markdown(
                content=entry.get("description", ""),
                title=entry.get("title", ""),
                url=entry.get("url", ""),
            )
            all_chunks.extend(chunks)
        result.total_chunks = len(all_chunks)

        if not all_chunks:
            return result

        # Ensure index exists + bulk upsert
        async with httpx.AsyncClient(timeout=60.0) as client:
            await self._ensure_index(client)

            index = settings.OPENSEARCH_DOCS_INDEX
            for chunk in all_chunks:
                embedding = await self.generate_embedding(f"{chunk.title} {chunk.heading} {chunk.content}")
                if not embedding:
                    result.errors += 1
                    result.error_details.append(f"No embedding for: {chunk.title}[{chunk.chunk_index}]")
                    continue

                doc = {
                    "title": chunk.title,
                    "url": chunk.url,
                    "content": chunk.content,
                    "heading": chunk.heading,
                    "chunk_index": chunk.chunk_index,
                    "embedding": embedding,
                }
                doc_id = f"{chunk.url}:{chunk.chunk_index}"
                resp = await client.put(
                    f"{settings.OPENSEARCH_URL}/{index}/_doc/{doc_id}",
                    json=doc,
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code in (200, 201):
                    result.indexed += 1
                else:
                    result.errors += 1
                    result.error_details.append(f"Index failed for {doc_id}: {resp.status_code}")

        logger.info(
            "Reindex complete: entries=%d chunks=%d indexed=%d errors=%d",
            result.total_entries,
            result.total_chunks,
            result.indexed,
            result.errors,
        )
        return result

    # -- Semantic search ---------------------------------------------------

    async def search_semantic(
        self,
        query: str,
        limit: int = 5,
    ) -> list[dict]:
        """Embed the query and run k-NN search against OpenSearch.

        Returns a list of dicts with title, url, content, heading, score.
        """
        query_vec = await self.generate_embedding(query)
        if not query_vec:
            return []

        index = settings.OPENSEARCH_DOCS_INDEX
        body = {
            "size": limit,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": query_vec,
                        "k": limit,
                    }
                }
            },
            "_source": ["title", "url", "content", "heading", "chunk_index"],
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{settings.OPENSEARCH_URL}/{index}/_search",
                    json=body,
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code != 200:
                    logger.warning("k-NN search failed: %s", resp.status_code)
                    return []
                data = resp.json()
        except httpx.HTTPError as exc:
            logger.warning("k-NN search error: %s", exc)
            return []

        results = []
        for hit in data.get("hits", {}).get("hits", []):
            src = hit.get("_source", {})
            results.append(
                {
                    "title": src.get("title", ""),
                    "url": src.get("url", ""),
                    "content": src.get("content", ""),
                    "heading": src.get("heading", ""),
                    "score": hit.get("_score", 0.0),
                }
            )
        return results

    # -- Hybrid search (RRF) -----------------------------------------------

    async def search_hybrid(
        self,
        query: str,
        limit: int = 5,
        keyword_weight: float = 0.5,
        semantic_weight: float = 0.5,
    ) -> list[dict]:
        """Reciprocal Rank Fusion of Algolia keyword + k-NN semantic results.

        RRF formula: score(d) = sum( weight / (k + rank_i(d)) )
        where k=60 (standard constant).
        """
        from ..routers.docs_search import get_docs_search_service

        # Run keyword + semantic in parallel
        keyword_svc = get_docs_search_service()

        import asyncio

        keyword_task = asyncio.create_task(keyword_svc.search(query, limit=limit * 2))
        semantic_task = asyncio.create_task(self.search_semantic(query, limit=limit * 2))

        keyword_response = await keyword_task
        semantic_results = await semantic_task

        # RRF fusion
        k = 60  # Standard RRF constant
        rrf_scores: dict[str, float] = {}
        doc_data: dict[str, dict] = {}

        # Score keyword results
        for rank, result in enumerate(keyword_response.results, start=1):
            url = result.url.rstrip("/")
            rrf_scores[url] = rrf_scores.get(url, 0) + keyword_weight / (k + rank)
            if url not in doc_data:
                doc_data[url] = {
                    "title": result.title,
                    "url": result.url,
                    "snippet": result.snippet,
                    "category": result.category,
                }

        # Score semantic results
        for rank, result in enumerate(semantic_results, start=1):
            url = result["url"].rstrip("/")
            rrf_scores[url] = rrf_scores.get(url, 0) + semantic_weight / (k + rank)
            if url not in doc_data:
                doc_data[url] = {
                    "title": result["title"],
                    "url": result["url"],
                    "snippet": result["content"][:200],
                    "category": None,
                }

        # Sort by RRF score and return top results
        sorted_urls = sorted(rrf_scores, key=lambda u: rrf_scores[u], reverse=True)[:limit]
        return [{**doc_data[url], "score": rrf_scores[url]} for url in sorted_urls if url in doc_data]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_embedding_service: DocsEmbeddingService | None = None


def get_docs_embedding_service() -> DocsEmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = DocsEmbeddingService()
    return _embedding_service
