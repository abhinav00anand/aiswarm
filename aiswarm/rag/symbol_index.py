"""Symbol index."""

from __future__ import annotations

from aiswarm.rag.ast_index import ASTIndex

class SymbolIndex:
    """
    Cross-file symbol lookup combining ASTIndex with import resolution.
    """

    def __init__(self) -> None:
        self._ast = ASTIndex()
        self._import_map: dict[str, str] = {}  # symbol → file

    def index_file(self, path: str) -> None:
        count = self._ast.index_file(path)
        for sym in self._ast.get_file_symbols(path):
            self._import_map[sym["name"]] = path

    def find(self, name: str) -> list[dict] | None:
        return self._ast.search(name)

    def file_for_symbol(self, name: str) -> str | None:
        return self._import_map.get(name)
