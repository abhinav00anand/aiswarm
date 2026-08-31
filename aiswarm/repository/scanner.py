"""Repository scanner."""

from __future__ import annotations

from pathlib import Path

_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", "storage"}
_SOURCE_EXT = {".py", ".ts", ".js", ".cpp", ".rs", ".h", ".hpp"}
_TEST_PATTERNS = {"test_", "_test.", "spec.", ".test."}
_CONFIG_EXT = {".yaml", ".yml", ".toml", ".json", ".env"}


def classify_file(path: str) -> str:
    """Classify a file as: source | test | config | generated | other."""
    name = Path(path).name.lower()
    ext = Path(path).suffix.lower()
    if any(p in name for p in _TEST_PATTERNS):
        return "test"
    if ext in _CONFIG_EXT:
        return "config"
    if ext in _SOURCE_EXT:
        return "source"
    return "other"


def scan_repository(root: str = ".") -> dict[str, list[str]]:
    """Walk a repository and return files grouped by classification."""
    groups: dict[str, list[str]] = {"source": [], "test": [], "config": [], "other": []}
    for path in Path(root).rglob("*"):
        if any(p in _SKIP_DIRS for p in path.parts):
            continue
        if not path.is_file():
            continue
        rel = str(path.relative_to(root))
        classification = classify_file(rel)
        groups[classification].append(rel)
    return groups
