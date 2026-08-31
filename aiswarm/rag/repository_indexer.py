"""Repository Indexer."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".mypy_cache",
    ".ruff_cache",
    "storage",
}
_SOURCE_EXTENSIONS = {
    ".py",
    ".ts",
    ".js",
    ".cpp",
    ".c",
    ".rs",
    ".go",
    ".java",
    ".h",
    ".hpp",
    ".md",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".env",
    ".ini",
    ".xml",
    ".cfg",
    ".txt",
}


class RepositoryIndexer:
    """
    Indexes an entire repository into the RAG retriever.
    """

    def __init__(self, repo_root: str = ".", retriever: Any = None) -> None:
        self._root = Path(repo_root)
        self._retriever = retriever
        self._indexed: dict[str, str] = {}  # path → content hash

    async def index_all(self) -> int:
        """
        Walk and index all source files. Returns count of files indexed.
        """
        count = 0
        for path in self._root.rglob("*"):
            if any(part in _SKIP_DIRS for part in path.parts):
                continue
            if not path.is_file() or path.suffix not in _SOURCE_EXTENSIONS:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                file_hash = hashlib.md5(content.encode()).hexdigest()
                rel = str(path.relative_to(self._root))

                if self._indexed.get(rel) == file_hash:
                    continue  # Skip unchanged files

                if self._retriever:
                    self._retriever.index_file(rel, content)
                self._indexed[rel] = file_hash
                count += 1
            except OSError:
                continue

        logger.info("indexer.complete", files_indexed=count)
        return count

    def extract_symbols(self, path: str) -> list[str]:
        """Extract top-level symbol names from a Python file."""
        full = self._root / path
        if not full.exists() or full.suffix != ".py":
            return []
        try:
            tree = ast.parse(full.read_text(encoding="utf-8"))
            return [
                node.name
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            ]
        except SyntaxError:
            return []
