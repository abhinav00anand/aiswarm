"""Call graph — tracks function call relationships within a module."""

from __future__ import annotations

import ast
from pathlib import Path


class CallGraph:
    """Builds a call graph from Python AST analysis."""

    def __init__(self) -> None:
        self._calls: dict[str, list[str]] = {}  # caller → [callee, ...]

    def analyze_file(self, path: str) -> None:
        """Build the call graph for a single Python file."""
        try:
            source = Path(path).read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception:  # noqa: BLE001
            return

        class _Visitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.current_fn: str | None = None
                self.calls: dict[str, list[str]] = {}

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # type: ignore
                prev = self.current_fn
                self.current_fn = node.name
                self.calls.setdefault(node.name, [])
                self.generic_visit(node)
                self.current_fn = prev

            visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore

            def visit_Call(self, node: ast.Call) -> None:  # type: ignore
                if self.current_fn:
                    if isinstance(node.func, ast.Name):
                        self.calls[self.current_fn].append(node.func.id)
                    elif isinstance(node.func, ast.Attribute):
                        self.calls[self.current_fn].append(node.func.attr)
                self.generic_visit(node)

        v = _Visitor()
        v.visit(tree)
        self._calls.update(v.calls)

    def callers_of(self, function_name: str) -> list[str]:
        return [fn for fn, callees in self._calls.items() if function_name in callees]

    def callees_of(self, function_name: str) -> list[str]:
        return self._calls.get(function_name, [])
