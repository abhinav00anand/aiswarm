"""
RAG Retriever — semantic + structural file retrieval.

Uses sentence-transformers for embedding and ChromaDB for retrieval.
Falls back to keyword search if embeddings are unavailable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class RAGRetriever:
    """
    Retrieves relevant files from a repository using semantic search.
    """

    def __init__(
        self,
        repo_root: str = ".",
        embedding_model: str = "all-MiniLM-L6-v2",
        vector_store_path: str = "./storage/vector_db/rag",
        top_k: int = 10,
    ) -> None:
        self._root = Path(repo_root)
        self._model_name = embedding_model
        self._store_path = vector_store_path
        self._top_k = top_k
        self._model: Any = None
        self._collection: Any = None
        self._available = False
        self._init()

    def _init(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
            import chromadb
            self._model = SentenceTransformer(self._model_name)
            Path(self._store_path).mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=self._store_path)
            self._collection = client.get_or_create_collection(
                name="code_index",
                metadata={"hnsw:space": "cosine"},
            )
            self._available = True
            logger.info("rag.initialized", model=self._model_name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("rag.unavailable", error=str(exc))
            self._available = False

    def index_file(self, path: str, content: str) -> None:
        if not self._available:
            return
        try:
            embedding = self._model.encode(content[:2000]).tolist()
            self._collection.upsert(
                ids=[path],
                embeddings=[embedding],
                documents=[content[:2000]],
                metadatas=[{"path": path}],
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("rag.index_error", path=path, error=str(exc))

    def retrieve(self, query: str, n_results: int | None = None) -> list[dict[str, Any]]:
        if not self._available:
            return self._keyword_fallback(query)
        n = n_results or self._top_k
        try:
            embedding = self._model.encode(query).tolist()
            results = self._collection.query(
                query_embeddings=[embedding],
                n_results=n,
                include=["documents", "metadatas", "distances"],
            )
            items = []
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                items.append({
                    "path": meta["path"],
                    "content": doc,
                    "similarity": 1.0 - dist,
                })
            return items
        except Exception as exc:  # noqa: BLE001
            logger.error("rag.retrieve_error", error=str(exc))
            return self._keyword_fallback(query)

    def _keyword_fallback(self, query: str) -> list[dict[str, Any]]:
        """Simple keyword search when semantic search is unavailable."""
        keywords = set(query.lower().split())
        results: list[dict[str, Any]] = []
        extensions = {".py", ".ts", ".js", ".cpp", ".rs", ".h"}
        skip = {".git", "__pycache__", "node_modules", ".venv", "dist", "build"}

        for path in self._root.rglob("*"):
            if any(p in skip for p in path.parts):
                continue
            if not path.is_file() or path.suffix not in extensions:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")[:3000]
                hits = sum(1 for kw in keywords if kw in content.lower())
                if hits > 0:
                    rel = str(path.relative_to(self._root))
                    results.append({"path": rel, "content": content, "similarity": hits / len(keywords)})
            except OSError:
                continue

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[: self._top_k]

    @property
    def is_available(self) -> bool:
        return self._available
