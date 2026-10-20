"""
llm/embeddings.py — Local, zero-cost sentence embeddings.

Uses sentence-transformers (all-MiniLM-L6-v2) running entirely on CPU.
No API keys, no rate limits, no external network calls after initial download.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import List

import numpy as np

from core.config import settings

logger = logging.getLogger(__name__)

_model = None  # lazy-loaded singleton


def _get_model():
    """Lazy-load the embedding model once and cache it in the module."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embedding model: %s", settings.embedding_model)
            _model = SentenceTransformer(settings.embedding_model)
            logger.info("Embedding model loaded. Dim=%d", _model.get_sentence_embedding_dimension())
        except ImportError:
            raise RuntimeError(
                "sentence-transformers is not installed. "
                "Run: pip install sentence-transformers"
            )
    return _model


class EmbeddingService:
    """
    Thin wrapper around sentence-transformers for generating dense embeddings.

    All methods are synchronous because sentence-transformers runs on CPU
    and is fast enough for in-process use.  If needed, wrap in asyncio.to_thread().
    """

    def __init__(self, model_name: str | None = None):
        self._model_name = model_name or settings.embedding_model
        self._dim: int | None = None

    def embed(self, text: str) -> List[float]:
        """
        Embed a single string.  Returns a list of floats (the dense vector).
        """
        model = _get_model()
        vector = model.encode(text, normalize_embeddings=True)
        self._dim = len(vector)
        return vector.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Embed multiple strings efficiently using batched inference.
        """
        if not texts:
            return []
        model = _get_model()
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        self._dim = vectors.shape[1]
        return vectors.tolist()

    def similarity(self, a: List[float], b: List[float]) -> float:
        """
        Cosine similarity between two embedding vectors.
        Since both are L2-normalised, dot product == cosine similarity.
        """
        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)
        return float(np.dot(va, vb))

    @property
    def dimension(self) -> int:
        """Return embedding dimension (requires at least one embed() call first)."""
        if self._dim is None:
            # Trigger a dummy embed to populate dimension
            self.embed("warmup")
        return self._dim  # type: ignore[return-value]


# Module-level singleton
embedding_service = EmbeddingService()
