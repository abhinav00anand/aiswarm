"""Python compiler/runner."""

from __future__ import annotations

import ast
import asyncio
import subprocess
import tempfile
import time
from pathlib import Path

import structlog

from aiswarm.schemas.task import Task, CompilerOutput

logger = structlog.get_logger(__name__)


class PythonCompiler:
    """Validates and executes Python code."""

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout

    async def compile(self, task: Task) -> CompilerOutput:
        """
        Validate Python code: syntax check + import check.
        Stores result in task.compiler_output.
        """
        code = task.generated_code or ""
        t0 = time.monotonic()

        try:
            ast.parse(code)
        except SyntaxError as exc:
            output = CompilerOutput(
                success=False,
                stderr=f"SyntaxError: {exc.msg} (line {exc.lineno})",
                exit_code=1,
                duration_seconds=time.monotonic() - t0,
                command="ast.parse",
            )
            task.compiler_output = output
            return output

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            tmp_path = f.name

        posix_path = Path(tmp_path).as_posix()
        cmd = [
            "python",
            "-c",
            f"import importlib.util; spec=importlib.util.spec_from_file_location('m','{posix_path}'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)",
        ]  # noqa: E501

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                ),
            )
        except subprocess.TimeoutExpired:
            Path(tmp_path).unlink(missing_ok=True)
            output = CompilerOutput(
                success=False,
                stderr=f"Compile timeout after {self._timeout}s",
                exit_code=-1,
                duration_seconds=time.monotonic() - t0,
            )
            task.compiler_output = output
            return output
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        duration = time.monotonic() - t0
        success = result.returncode == 0

        output = CompilerOutput(
            success=success,
            stdout=result.stdout[:2000],
            stderr=result.stderr[:2000],
            exit_code=result.returncode,
            duration_seconds=duration,
            command=" ".join(cmd[:3]),
        )
        task.compiler_output = output

        logger.info(
            "python_compiler.result",
            task_id=task.task_id,
            success=success,
            duration=round(duration, 3),
            stderr=result.stderr[:200] if not success else "",
        )
        return output
