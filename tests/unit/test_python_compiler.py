"""Unit tests for the PythonCompiler — syntax + import validation."""

from __future__ import annotations

import pytest

from aiswarm.compiler.python import PythonCompiler
from aiswarm.schemas.task import Task


def _task_with_code(code: str) -> Task:
    t = Task(title="t", description="d")
    t.generated_code = code
    return t


class TestPythonCompiler:
    @pytest.mark.asyncio
    async def test_valid_code_compiles_successfully(self) -> None:
        compiler = PythonCompiler()
        task = _task_with_code("x = 1 + 1\n")
        result = await compiler.compile(task)
        assert result.success is True
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_syntax_error_fails_fast(self) -> None:
        compiler = PythonCompiler()
        task = _task_with_code("def broken(:\n    pass\n")
        result = await compiler.compile(task)
        assert result.success is False
        assert "SyntaxError" in result.stderr

    @pytest.mark.asyncio
    async def test_syntax_error_does_not_spawn_subprocess(self) -> None:
        compiler = PythonCompiler()
        task = _task_with_code("this is not python (((")
        result = await compiler.compile(task)
        assert result.command == "ast.parse"

    @pytest.mark.asyncio
    async def test_import_error_at_runtime_is_captured(self) -> None:
        compiler = PythonCompiler()
        task = _task_with_code("import totally_nonexistent_module_xyz\n")
        result = await compiler.compile(task)
        assert result.success is False
        assert result.exit_code != 0

    @pytest.mark.asyncio
    async def test_stores_result_on_task(self) -> None:
        compiler = PythonCompiler()
        task = _task_with_code("y = 2\n")
        result = await compiler.compile(task)
        assert task.compiler_output is result

    @pytest.mark.asyncio
    async def test_empty_code_treated_as_valid_noop(self) -> None:
        compiler = PythonCompiler()
        task = _task_with_code("")
        result = await compiler.compile(task)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_timeout_produces_failure_output(self) -> None:
        compiler = PythonCompiler(timeout=0.05)
        task = _task_with_code("import time\ntime.sleep(5)\n")
        result = await compiler.compile(task)
        assert result.success is False
        assert result.exit_code == -1

    @pytest.mark.asyncio
    async def test_duration_is_recorded_and_nonnegative(self) -> None:
        compiler = PythonCompiler()
        task = _task_with_code("z = 3\n")
        result = await compiler.compile(task)
        assert result.duration_seconds >= 0
