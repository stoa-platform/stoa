# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Local embedding model wrapper — CAB-881.

Uses sentence-transformers/all-MiniLM-L6-v2 (~22MB, 384 dims).
Runs locally — zero external API calls.
"""

import hashlib
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger(__name__)

# Model config
MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# Lazy-loaded singleton
_model: Any = None


def _get_model() -> Any:
    """Lazy-load the sentence-transformers model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model", model=MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME)
        logger.info("Embedding model loaded", model=MODEL_NAME, dim=EMBEDDING_DIM)
    return _model


class Embedder:
    """Wraps sentence-transformers for cache key embedding."""

    def __init__(self) -> None:
        self._dim = EMBEDDING_DIM

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        """Compute embedding vector for a text string.

        Returns a list of floats (384 dimensions).
        """
        model = _get_model()
        vec = model.encode(text, normalize_embeddings=True)
        return vec.tolist()

    @staticmethod
    def hash_key(text: str) -> str:
        """SHA-256 hash of text for fast exact-match path."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def build_cache_key(self, tool_name: str, arguments: dict) -> str:
        """Build a canonical cache key from tool name + sorted arguments."""
        import json

        canonical = json.dumps(
            {"tool": tool_name, "args": arguments},
            sort_keys=True,
            separators=(",", ":"),
        )
        return canonical
