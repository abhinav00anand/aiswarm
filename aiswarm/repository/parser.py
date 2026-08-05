"""Source code parser — extracts AST-level information from Python files."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FunctionInfo:
    name: str
    line_start: int
    line_end: int
    has_docstring: bool
    has_type_hints: bool
    args: list[str] = field(default_factory=list)
    return_annotation: str = ""
    is_async: bool = False


@dataclass
class ModuleInfo:
    path: str
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    has_module_docstring: bool = False


def parse_python_file(path: str) -> ModuleInfo | None:
    """Parse a Python source file and return structured module info."""
    file_path = Path(path)
    if not file_path.exists():
        return None
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, OSError):
        return None

    info = ModuleInfo(path=path)
    info.has_module_docstring = (
        isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        if tree.body else False
    )

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn = FunctionInfo(
                name=node.name,
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                has_docstring=bool(
                    node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                ),
                has_type_hints=node.returns is not None or any(
                    a.annotation is not None for a in node.args.args
                ),
                args=[a.arg for a in node.args.args],
                return_annotation=ast.unparse(node.returns) if node.returns else "",
                is_async=isinstance(node, ast.AsyncFunctionDef),
            )
            info.functions.append(fn)
        elif isinstance(node, ast.ClassDef):
            info.classes.append(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                info.imports.extend(a.name for a in node.names)
            else:
                info.imports.append(node.module or "")

    return info
