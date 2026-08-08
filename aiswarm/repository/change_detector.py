"""Change detector."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

_STATE_FILE = Path("./storage/file_hashes.json")

class ChangeDetector:
    """Detects changed source files using content hashing."""

    def __init__(self) -> None:
        self._hashes: dict[str, str] = self._load()

    def changed_files(self, root: str = ".") -> list[str]:
        """Return list of files that changed since last scan."""
        changed: list[str] = []
        ext = {".py", ".ts", ".js", ".cpp", ".rs", ".h"}
        skip = {".git", "__pycache__", "node_modules", ".venv", "dist", "build", "storage"}
        for path in Path(root).rglob("*"):
            if any(p in skip for p in path.parts):
                continue
            if not path.is_file() or path.suffix not in ext:
                continue
            rel = str(path)
            try:
                digest = hashlib.md5(path.read_bytes()).hexdigest()
                if self._hashes.get(rel) != digest:
                    changed.append(rel)
                    self._hashes[rel] = digest
            except OSError:
                continue
        self._save()
        return changed

    def _load(self) -> dict[str, str]:
        if not _STATE_FILE.exists():
            return {}
        try:
            return json.loads(_STATE_FILE.read_text())
        except Exception:  # noqa: BLE001
            return {}

    def _save(self) -> None:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(self._hashes, indent=2))
