"""C++ compiler adapter — wraps g++ for C++ source files."""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
import time
from pathlib import Path

from aiswarm.schemas.task import Task, CompilerOutput


class CppCompiler:
    """Compiles C++ source using g++."""

    def __init__(self, standard: str = "c++17", timeout: float = 60.0) -> None:
        self._std = standard
        self._timeout = timeout

    async def compile(self, task: Task) -> CompilerOutput:
        code = task.generated_code or ""
        t0 = time.monotonic()
        with tempfile.NamedTemporaryFile(suffix=".cpp", delete=False, mode="w") as f:
            f.write(code)
            src = Path(f.name)
        out_bin = src.with_suffix("")
        cmd = ["g++", f"-std={self._std}", "-O2", "-Wall", "-Wextra", str(src), "-o", str(out_bin)]
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout),
            )
        except Exception as exc:  # noqa: BLE001
            src.unlink(missing_ok=True)
            return CompilerOutput(success=False, stderr=str(exc), exit_code=-1)
        finally:
            src.unlink(missing_ok=True)
            out_bin.unlink(missing_ok=True)
        output = CompilerOutput(
            success=result.returncode == 0,
            stdout=result.stdout[:2000],
            stderr=result.stderr[:2000],
            exit_code=result.returncode,
            duration_seconds=time.monotonic() - t0,
            command=" ".join(cmd[:3]),
        )
        task.compiler_output = output
        return output
