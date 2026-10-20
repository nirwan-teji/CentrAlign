"""
memory/episodic_memory.py — ChromaDB-backed vector store for cross-run memory.

Stores execution runbooks, past error resolutions, company schemas, and
policy guidelines. The agent retrieves semantically similar past experiences
to guide current decisions.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.config import settings

logger = logging.getLogger(__name__)


class EpisodicMemory:
    """
    Persistent vector memory backed by ChromaDB (local, disk-based).
    Falls back to a simple in-memory list if ChromaDB is unavailable.
    """

    def __init__(self, collection_name: str | None = None, db_path: str | None = None) -> None:
        self._collection_name = collection_name or settings.memory_collection
        self._db_path = db_path or settings.chroma_db_path
        self._collection = None
        self._fallback: List[Dict[str, Any]] = []
        self._use_chroma = False
        self._init_chroma()

    def _init_chroma(self) -> None:
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            client = chromadb.PersistentClient(
                path=self._db_path,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._collection = client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self._use_chroma = True
            logger.info("EpisodicMemory: ChromaDB ready at %s", self._db_path)
        except Exception as exc:
            logger.warning("ChromaDB unavailable (%s). Using in-memory fallback.", exc)
            self._use_chroma = False

    # ── Write ─────────────────────────────────────────────────────────────────

    def store(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None,
    ) -> str:
        """Store a text memory and return its ID."""
        mid = doc_id or str(uuid.uuid4())
        meta = metadata or {}
        meta["timestamp"] = datetime.utcnow().isoformat()

        if self._use_chroma:
            from llm.embeddings import embedding_service
            embedding = embedding_service.embed(text)
            self._collection.upsert(
                ids=[mid],
                documents=[text],
                embeddings=[embedding],
                metadatas=[meta],
            )
        else:
            self._fallback.append({"id": mid, "text": text, "meta": meta})
        logger.debug("EpisodicMemory: stored doc %s", mid)
        return mid

    # ── Read ──────────────────────────────────────────────────────────────────

    def retrieve(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Retrieve the most semantically similar memories for a query."""
        if self._use_chroma:
            from llm.embeddings import embedding_service
            query_vec = embedding_service.embed(query)
            results = self._collection.query(
                query_embeddings=[query_vec],
                n_results=min(n_results, self._collection.count()),
                include=["documents", "metadatas", "distances"],
            )
            items = []
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                items.append({
                    "text": doc,
                    "metadata": meta,
                    "similarity": float(1 - dist),  # cosine distance → similarity
                })
            return items
        # Fallback: linear scan (fine for small collections)
        from llm.embeddings import embedding_service
        qvec = embedding_service.embed(query)
        scored = []
        for entry in self._fallback:
            evec = embedding_service.embed(entry["text"])
            sim = embedding_service.similarity(qvec, evec)
            scored.append({"text": entry["text"], "metadata": entry["meta"], "similarity": sim})
        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:n_results]

    def count(self) -> int:
        if self._use_chroma and self._collection:
            return self._collection.count()
        return len(self._fallback)


# Module-level singleton
episodic_memory = EpisodicMemory()
