"""Docker worker — executes jobs inside an isolated Docker container."""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from aiswarm.worker.dispatcher import JobPayload

logger = structlog.get_logger(__name__)

_DEFAULT_IMAGE = "python:3.11-slim"


class DockerWorker:
    """Runs code inside a Docker container for isolation."""

    def __init__(
        self,
        image: str = _DEFAULT_IMAGE,
        timeout: float = 120.0,
        memory_limit: str = "512m",
        cpu_limit: str = "1.0",
    ) -> None:
        self._image = image
        self._timeout = timeout
        self._memory = memory_limit
        self._cpu = cpu_limit

    async def execute(self, payload: "JobPayload") -> dict[str, Any]:
        """Run code inside Docker and return structured output."""
        t0 = time.monotonic()
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(payload.code)
            code_path = Path(f.name)

        cmd = [
            "docker",
            "run",
            "--rm",
            f"--memory={self._memory}",
            f"--cpus={self._cpu}",
            "--network=none",
            "--read-only",
            "-v",
            f"{code_path}:/code.py:ro",
            self._image,
            "python",
            "/code.py",
        ]

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout),
            )
            success = result.returncode == 0
        except subprocess.TimeoutExpired:
            success = False
            result = type(
                "R", (), {"stdout": "", "stderr": f"Timeout {self._timeout}s", "returncode": -1}
            )()
        except Exception as exc:  # noqa: BLE001
            success = False
            result = type("R", (), {"stdout": "", "stderr": str(exc), "returncode": -1})()
        finally:
            code_path.unlink(missing_ok=True)

        return {
            "job_id": payload.job_id,
            "task_id": payload.task_id,
            "state_hash": payload.state_hash,
            "compile_success": success,
            "compile_stdout": result.stdout[:2000],
            "compile_stderr": result.stderr[:2000],
            "test_success": success,
            "test_stdout": "",
            "test_stderr": "",
            "bench_stdout": "",
            "duration_seconds": time.monotonic() - t0,
        }
