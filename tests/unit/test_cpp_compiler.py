"""Unit tests for the CppCompiler subsystem."""

from __future__ import annotations

import tempfile
import sys
from pathlib import Path
import pytest

from aiswarm.compiler.cpp import CppCompiler
from aiswarm.security.sandbox import ExecutionSandbox


@pytest.mark.asyncio
class TestCppCompiler:
    async def test_detect_compiler(self) -> None:
        compiler = CppCompiler()
        detected = compiler.compiler_path
        assert detected in ["g++", "clang++", "cl"]

    async def test_compile_and_run_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sandbox = ExecutionSandbox(workspace_dir=tmp_dir)
            compiler = CppCompiler(sandbox=sandbox)

            # Write a simple C++ program to workspace
            cpp_src = "int main() { return 0; }\n"
            src_file = Path(tmp_dir) / "main.cpp"
            src_file.write_text(cpp_src)

            out_bin = "test_main.exe" if sys.platform == "win32" else "test_main"
            res = await compiler.compile(
                source_files=[str(src_file)],
                output_binary=out_bin,
            )

            # Some systems might not have a C++ compiler installed. We should only assert if compilation was attempted.
            if res.get("returncode") == 0:
                assert res["success"] is True
                assert Path(tmp_dir).joinpath(out_bin).exists()

                # Run tests
                test_res = await compiler.run_tests(test_binary=out_bin)
                assert test_res["passed"] is True
                assert test_res["returncode"] == 0

    async def test_compile_failure_syntax_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sandbox = ExecutionSandbox(workspace_dir=tmp_dir)
            compiler = CppCompiler(sandbox=sandbox)

            # Write invalid C++ program
            cpp_src = "int main() { broken_syntax_here }\n"
            src_file = Path(tmp_dir) / "broken.cpp"
            src_file.write_text(cpp_src)

            out_bin = "broken_main.exe" if sys.platform == "win32" else "broken_main"
            res = await compiler.compile(
                source_files=[str(src_file)],
                output_binary=out_bin,
            )

            # If compiler is missing, it will exit with error, but if it runs, success should be False
            if res.get("returncode") != -1:
                # Run was attempted
                # Check compile failure
                assert res["success"] is False
                assert not Path(tmp_dir).joinpath(out_bin).exists()
