"""
Vector Memory — semantic similarity store backed by ChromaDB.

Stores embeddings of past task descriptions, code snippets, and decisions.
Enables the context selector and planner to retrieve relevant past work.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_PERSIST_DIR = "./storage/vector_db"


class VectorMemory:
    """
    ChromaDB-backed vector store for semantic retrieval.

    Falls back gracefully if chromadb is not available.
    """

    def __init__(self, collection_name: str = "aiswarm_memory") -> None:
        self._collection_name = collection_name
        self._client: Any = None
        self._collection: Any = None
        self._available = False
        self._init()

    def _init(self) -> None:
        try:
            import chromadb
            Path(_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=_PERSIST_DIR)
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self._available = True
            logger.info("vector_memory.initialized", collection=self._collection_name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("vector_memory.unavailable", error=str(exc))
            self._available = False

    def add(
        self,
        doc_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self._available:
            return
        try:
            self._collection.upsert(
                ids=[doc_id],
                documents=[text],
                metadatas=[metadata or {}],
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("vector_memory.add_error", doc_id=doc_id, error=str(exc))

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not self._available:
            return []
        try:
            results = self._collection.query(
                query_texts=[query_text],
                n_results=n_results,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
            items = []
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            dists = results.get("distances", [[]])[0]
            for doc, meta, dist in zip(docs, metas, dists):
                items.append({
                    "text": doc,
                    "metadata": meta,
                    "similarity": 1.0 - dist,
                })
            return items
        except Exception as exc:  # noqa: BLE001
            logger.error("vector_memory.query_error", error=str(exc))
            return []

    @property
    def is_available(self) -> bool:
        return self._available
