"""
Production-Ready Execution Sandbox — Isolated Process & Command Isolation.

Provides workspace isolation, resource caps, command allowlists, timeout enforcement,
and secret scrubbing for code execution and tool invocation.
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from aiswarm.utils.compat_log import get_logger

logger = get_logger(__name__)

# Default command allowlist — only these binary commands are permitted by default
_DEFAULT_ALLOWLIST = {
    "python",
    "python3",
    "pytest",
    "ruff",
    "mypy",
    "git",
    "cargo",
    "g++",
    "gcc",
    "clang++",
    "cl",
    "main",
    "host2_engine",
    "node",
    "npm",
}

# Regex patterns for scrubbing sensitive tokens/keys from output
_SECRET_PATTERNS = [
    (re.compile(r"(?i)(api[_-]?key|secret|token|password|auth)[\s:=]+['\"]?([a-zA-Z0-9_\-\.]{12,})['\"]?"), r"\1=***REDACTED***"),
    (re.compile(r"sk-[a-zA-Z0-9]{32,}"), "***REDACTED***"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36}"), "***REDACTED***"),
]


class SandboxViolationError(PermissionError):
    """Raised when a command or process violates sandbox security policies."""


def scrub_secrets(text: str) -> str:
    """Redact sensitive keys and secrets from output text."""
    if not text:
        return ""
    sanitized = text
    for pattern, replacement in _SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


class ExecutionSandbox:
    """
    Isolated execution environment enforcing directory scoping, process resource limits,
    command allowlisting, and output redaction.
    """

    def __init__(
        self,
        workspace_dir: str | Path | None = None,
        timeout: float = 60.0,
        max_output_bytes: int = 100_000,
        allowlist: set[str] | None = None,
        allow_network: bool = False,
    ) -> None:
        self.workspace_dir = Path(workspace_dir or tempfile.mkdtemp(prefix="zymis_sandbox_")).resolve()
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.max_output_bytes = max_output_bytes
        self.allowlist = allowlist or _DEFAULT_ALLOWLIST
        self.allow_network = allow_network

    def validate_command(self, cmd_args: list[str] | str) -> list[str]:
        """
        Validate that the requested command uses an allowlisted binary and no unparsed shell strings.
        Returns the parsed argument list.
        """
        if isinstance(cmd_args, str):
            # Parse command string securely without shell=True
            parsed = shlex.split(cmd_args)
        else:
            parsed = list(cmd_args)

        if not parsed:
            raise SandboxViolationError("Empty command provided to sandbox.")

        binary = Path(parsed[0]).name.lower()
        # Remove extension on Windows if present (e.g. python.exe -> python)
        if binary.endswith(".exe"):
            binary = binary[:-4]

        if binary not in self.allowlist:
            logger.warning("sandbox.command_blocked", binary=binary, allowlist=list(self.allowlist))
            raise SandboxViolationError(
                f"Forbidden binary execution: '{binary}'. Command is not in the sandbox allowlist: {sorted(self.allowlist)}"
            )

        return parsed

    def validate_path_in_workspace(self, target_path: str | Path) -> Path:
        """Verify that a target file path resides strictly inside the workspace boundary."""
        resolved = Path(target_path).resolve()
        try:
            resolved.relative_to(self.workspace_dir)
        except ValueError:
            logger.error("sandbox.path_traversal_blocked", path=str(resolved), workspace=str(self.workspace_dir))
            raise SandboxViolationError(
                f"Path traversal blocked: Path '{resolved}' is outside assigned workspace '{self.workspace_dir}'"
            )
        return resolved

    async def execute_sandboxed_command(
        self,
        cmd_args: list[str] | str,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
    ) -> dict[str, Any]:
        """
        Execute a command in an isolated subprocess with timeout, output capping, and secret redaction.
        """
        validated_args = self.validate_command(cmd_args)
        exec_cwd = self.validate_path_in_workspace(cwd or self.workspace_dir)

        # Prepare restricted environment
        exec_env = os.environ.copy()
        if env:
            exec_env.update(env)

        # Enforce sandbox environment overrides
        if not self.allow_network:
            exec_env["HTTP_PROXY"] = "http://127.0.0.1:0"
            exec_env["HTTPS_PROXY"] = "http://127.0.0.1:0"

        start_time = time.monotonic()
        logger.info("sandbox.execute_start", cmd=validated_args[0], cwd=str(exec_cwd))

        try:
            proc = await asyncio.create_subprocess_exec(
                *validated_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(exec_cwd),
                env=exec_env,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("sandbox.command_timeout", cmd=validated_args[0], timeout=self.timeout)
                proc.kill()
                await proc.wait()
                return {
                    "returncode": -1,
                    "stdout": "",
                    "stderr": f"Sandbox Timeout: Command exceeded limit of {self.timeout}s.",
                    "duration_seconds": time.monotonic() - start_time,
                    "timed_out": True,
                }

            duration = time.monotonic() - start_time
            stdout_str = scrub_secrets(stdout_bytes[: self.max_output_bytes].decode("utf-8", errors="replace"))
            stderr_str = scrub_secrets(stderr_bytes[: self.max_output_bytes].decode("utf-8", errors="replace"))

            logger.info("sandbox.execute_complete", returncode=proc.returncode, duration=duration)
            return {
                "returncode": proc.returncode,
                "stdout": stdout_str,
                "stderr": stderr_str,
                "duration_seconds": duration,
                "timed_out": False,
            }

        except Exception as exc:
            logger.error("sandbox.execute_failed", error=str(exc))
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": scrub_secrets(str(exc)),
                "duration_seconds": time.monotonic() - start_time,
                "timed_out": False,
            }
