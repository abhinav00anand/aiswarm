"""
C++ Compiler Subsystem for AISwarm-Next.

Supports g++, clang++, and MSVC cl.exe compilation, warning diagnostics parsing,
and C++ GoogleTest/Catch2 test execution inside ExecutionSandbox.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from aiswarm.security.sandbox import ExecutionSandbox
from aiswarm.utils.compat_log import get_logger

logger = get_logger(__name__)


class CppCompiler:
    """C++ Compiler and Test Execution Engine."""

    def __init__(self, sandbox: ExecutionSandbox | None = None) -> None:
        self.sandbox = sandbox or ExecutionSandbox()
        self.compiler_path = self._detect_compiler()

    def _detect_compiler(self) -> str:
        """Detect available C++ compiler (g++, clang++, or cl.exe)."""
        for comp in ["g++", "clang++", "cl"]:
            if shutil.which(comp):
                logger.info("cpp_compiler.detected", compiler=comp)
                return comp
        return "g++"

    async def compile(
        self,
        source_files: list[str],
        output_binary: str = "main.exe",
        std_version: str = "c++17",
        extra_flags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Compile C++ source files into an executable binary using sandbox."""
        cmd = [self.compiler_path, f"-std={std_version}"] + source_files + ["-o", output_binary]
        if extra_flags:
            cmd.extend(extra_flags)

        logger.info("cpp_compiler.compiling", command=cmd)
        result = await self.sandbox.execute_sandboxed_command(cmd)
        return {
            "success": result.get("returncode") == 0,
            "compiler": self.compiler_path,
            "output_binary": output_binary,
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "returncode": result.get("returncode", -1),
        }

    async def run_tests(self, test_binary: str = "main.exe") -> dict[str, Any]:
        """Execute compiled C++ test binary in sandbox."""
        result = await self.sandbox.execute_sandboxed_command([f"./{test_binary}"])
        return {
            "passed": result.get("returncode") == 0,
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "returncode": result.get("returncode", -1),
        }
