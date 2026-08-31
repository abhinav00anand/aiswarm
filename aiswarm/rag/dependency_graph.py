"""Dependency graph."""

from __future__ import annotations

import ast
from pathlib import Path


class DependencyGraph:
    """
    Builds and queries an import dependency graph for a Python codebase.
    """

    def __init__(self) -> None:
        self._graph: dict[str, set[str]] = {}  # file → set of imported modules

    def add_file(self, path: str) -> None:
        """Parse a Python file and add its imports to the graph."""
        try:
            source = Path(path).read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception:  # noqa: BLE001
            return

        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])
        self._graph[path] = imports

    def dependents_of(self, module: str) -> list[str]:
        """Return all files that import from the given module."""
        return [path for path, deps in self._graph.items() if module in deps]

    def dependencies_of(self, path: str) -> set[str]:
        """Return modules imported by the given file."""
        return self._graph.get(path, set())

    def has_circular(self) -> bool:
        """Simple cycle detection — returns True if any circular dependency exists."""
        visited: set[str] = set()
        path_stack: set[str] = set()

        def dfs(node: str) -> bool:
            visited.add(node)
            path_stack.add(node)
            for dep in self._graph.get(node, set()):
                if dep not in visited:
                    if dfs(dep):
                        return True
                elif dep in path_stack:
                    return True
            path_stack.discard(node)
            return False

        return any(dfs(node) for node in self._graph if node not in visited)
