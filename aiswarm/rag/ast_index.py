"""AST index — indexes Python source at function/class granularity."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from aiswarm.repository.parser import parse_python_file

logger = structlog.get_logger(__name__)


class ASTIndex:
    """
    Indexes Python functions and classes for fine-grained RAG retrieval.
    Allows the context selector to retrieve specific functions rather than entire files.
    """

    def __init__(self) -> None:
        self._index: dict[str, list[dict[str, Any]]] = {}  # file → list of symbols

    def index_file(self, path: str) -> int:
        """Index all symbols in a Python file. Returns count of symbols indexed."""
        info = parse_python_file(path)
        if not info:
            return 0
        symbols = []
        for fn in info.functions:
            symbols.append({
                "type": "function",
                "name": fn.name,
                "path": path,
                "line_start": fn.line_start,
                "line_end": fn.line_end,
                "has_docstring": fn.has_docstring,
                "has_type_hints": fn.has_type_hints,
                "is_async": fn.is_async,
                "args": fn.args,
                "return_type": fn.return_annotation,
            })
        for cls in info.classes:
            symbols.append({"type": "class", "name": cls, "path": path})
        self._index[path] = symbols
        return len(symbols)

    def search(self, symbol_name: str) -> list[dict[str, Any]]:
        """Search for a symbol by name across all indexed files."""
        results: list[dict[str, Any]] = []
        for symbols in self._index.values():
            for sym in symbols:
                if symbol_name.lower() in sym["name"].lower():
                    results.append(sym)
        return results

    def get_file_symbols(self, path: str) -> list[dict[str, Any]]:
        return self._index.get(path, [])

    def coverage_report(self) -> dict[str, Any]:
        """Return a summary of documentation and type hint coverage."""
        total = documented = typed = 0
        for symbols in self._index.values():
            for sym in symbols:
                if sym["type"] == "function":
                    total += 1
                    if sym.get("has_docstring"):
                        documented += 1
                    if sym.get("has_type_hints"):
                        typed += 1
        return {
            "total_functions": total,
            "documented_pct": round(documented / total * 100, 1) if total else 0.0,
            "typed_pct": round(typed / total * 100, 1) if total else 0.0,
        }
