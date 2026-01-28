# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Semantic Cache — CAB-881 Step 4/4.

Embedding-based deduplication for MCP tool responses.
Uses pgvector for cosine similarity search with strict tenant isolation.
"""

from .embedder import Embedder
from .semantic_cache import SemanticCache
from .cleanup import CacheCleanupWorker

__all__ = [
    "Embedder",
    "SemanticCache",
    "CacheCleanupWorker",
]
