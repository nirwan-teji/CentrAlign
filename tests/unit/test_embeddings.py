"""
tests/unit/test_embeddings.py — Unit tests for the local embedding service.

Tests run without any API calls — sentence-transformers runs on CPU.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from llm.embeddings import EmbeddingService


@pytest.fixture
def svc():
    return EmbeddingService()


class TestEmbeddingServiceEmbed:
    def test_embed_returns_list_of_floats(self, svc):
        vec = svc.embed("hello world")
        assert isinstance(vec, list)
        assert len(vec) > 0
        assert all(isinstance(v, float) for v in vec)

    def test_embed_dimension_is_positive(self, svc):
        vec = svc.embed("test sentence")
        assert len(vec) > 0

    def test_embed_is_deterministic(self, svc):
        """Same text should always produce the same vector."""
        v1 = svc.embed("invoice total")
        v2 = svc.embed("invoice total")
        assert v1 == v2

    def test_embed_different_texts_differ(self, svc):
        v1 = svc.embed("apple")
        v2 = svc.embed("quantum physics")
        assert v1 != v2


class TestEmbeddingServiceBatch:
    def test_batch_embed_returns_correct_count(self, svc):
        texts = ["first sentence", "second sentence", "third sentence"]
        vecs = svc.embed_batch(texts)
        assert len(vecs) == 3

    def test_batch_embed_empty_returns_empty(self, svc):
        result = svc.embed_batch([])
        assert result == []

    def test_batch_consistent_with_single(self, svc):
        """Single embed and batch embed must produce the same vector."""
        text = "vendor invoice reconciliation"
        single = svc.embed(text)
        batch = svc.embed_batch([text])
        # Allow tiny floating point drift
        diffs = [abs(a - b) for a, b in zip(single, batch[0])]
        assert max(diffs) < 1e-5


class TestEmbeddingServiceSimilarity:
    def test_self_similarity_is_one(self, svc):
        v = svc.embed("autonomous AI worker")
        sim = svc.similarity(v, v)
        assert abs(sim - 1.0) < 1e-5

    def test_similar_texts_high_score(self, svc):
        v1 = svc.embed("invoice amount due")
        v2 = svc.embed("total amount on invoice")
        sim = svc.similarity(v1, v2)
        assert sim > 0.5

    def test_dissimilar_texts_low_score(self, svc):
        v1 = svc.embed("invoice payment accounting")
        v2 = svc.embed("rocket engine combustion chamber")
        sim = svc.similarity(v1, v2)
        assert sim < 0.7  # should be noticeably lower

    def test_similarity_is_symmetric(self, svc):
        v1 = svc.embed("purchase order approval")
        v2 = svc.embed("vendor payment processing")
        assert abs(svc.similarity(v1, v2) - svc.similarity(v2, v1)) < 1e-6


class TestEmbeddingDimension:
    def test_dimension_property_after_embed(self, svc):
        svc.embed("trigger dimension load")
        assert svc.dimension > 0
        assert svc.dimension == len(svc.embed("any text"))
