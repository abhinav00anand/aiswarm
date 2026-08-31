"""Git tools."""

from __future__ import annotations

import subprocess
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


class GitTools:
    """Wraps common git operations needed by the orchestrator."""

    def __init__(self, repo_root: str = ".") -> None:
        self._root = Path(repo_root)

    def diff(self, staged: bool = False) -> str:
        """Return the current diff (staged or unstaged)."""
        cmd = ["git", "diff", "--staged"] if staged else ["git", "diff"]
        return self._run(cmd)

    def status(self) -> str:
        return self._run(["git", "status", "--short"])

    def log(self, n: int = 10) -> str:
        return self._run(["git", "log", f"-{n}", "--oneline"])

    def add(self, path: str) -> None:
        self._run(["git", "add", path])

    def commit(self, message: str) -> str:
        return self._run(["git", "commit", "-m", message])

    def create_branch(self, name: str) -> str:
        return self._run(["git", "checkout", "-b", name])

    def changed_files(self, base: str = "HEAD") -> list[str]:
        out = self._run(["git", "diff", "--name-only", base])
        return [f.strip() for f in out.splitlines() if f.strip()]

    def _run(self, cmd: list[str]) -> str:
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self._root),
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.stdout.strip()
        except Exception as exc:  # noqa: BLE001
            logger.error("git.command_error", cmd=cmd, error=str(exc))
            return ""
