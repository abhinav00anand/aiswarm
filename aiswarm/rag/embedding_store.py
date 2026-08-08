"""Embedding store."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

class EmbeddingStore:
    """Manages code embeddings backed by ChromaDB."""

    def __init__(self, store_path: str = "./storage/vector_db/embeddings") -> None:
        self._path = Path(store_path)
        self._collection: Any = None
        self._model: Any = None
        self._available = False
        self._init()

    def _init(self) -> None:
        try:
            import chromadb
            from sentence_transformers import SentenceTransformer
            self._path.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(self._path))
            self._collection = client.get_or_create_collection("embeddings")
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            self._available = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("embedding_store.unavailable", error=str(exc))

    def embed(self, text: str) -> list[float]:
        if not self._available:
            return []
        return self._model.encode(text).tolist()  # type: ignore[union-attr]

    def store(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        if not self._available:
            return
        embedding = self.embed(text[:2000])
        self._collection.upsert(  # type: ignore[union-attr]
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text[:2000]],
            metadatas=[metadata or {}],
        )

    def search(self, query: str, n: int = 10) -> list[dict[str, Any]]:
        if not self._available:
            return []
        embedding = self.embed(query)
        try:
            results = self._collection.query(  # type: ignore[union-attr]
                query_embeddings=[embedding], n_results=n,
                include=["documents", "metadatas", "distances"],
            )
            return [
                {"text": d, "metadata": m, "score": 1 - dist}
                for d, m, dist in zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0],
                )
            ]
        except Exception:  # noqa: BLE001
            return []
