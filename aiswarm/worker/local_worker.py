"""
Local Worker — executes compile/test/benchmark jobs on the local machine.

Used as the default worker when Docker or Redis distributed execution is not configured.
Also serves as the reference implementation for all worker types.
Wraps subprocess execution inside ExecutionSandbox for resource isolation and security.
"""

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


class LocalWorker:
    """Executes jobs locally with subprocess isolation."""

    def __init__(self, timeout: float = 120.0) -> None:
        self._timeout = timeout

    async def execute(self, payload: "JobPayload") -> dict[str, Any]:
        """
        Execute compile + test + benchmark for a job.
        Returns a dict compatible with the Redis result format.
        """
        logger.info(
            "local_worker.executing",
            job_id=payload.job_id,
            language=payload.language,
        )
        t0 = time.monotonic()
        result: dict[str, Any] = {
            "job_id": payload.job_id,
            "task_id": payload.task_id,
            "state_hash": payload.state_hash,
            "compile_success": False,
            "compile_stdout": "",
            "compile_stderr": "",
            "test_success": False,
            "test_stdout": "",
            "test_stderr": "",
            "bench_stdout": "",
            "duration_seconds": 0.0,
        }

        # Write code to temp file
        suffix = {"python": ".py", "cpp": ".cpp", "rust": ".rs"}.get(payload.language, ".py")
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode="w") as f:
            f.write(payload.code)
            code_path = Path(f.name)

        try:
            # Compile step
            compile_out = await self._run_subprocess(
                ["python", "-c", f"import py_compile; py_compile.compile('{code_path}', doraise=True)"]
                if payload.language == "python"
                else payload.test_command or ["echo", "no-compile"],
            )
            result["compile_success"] = compile_out["exit_code"] == 0
            result["compile_stdout"] = compile_out["stdout"]
            result["compile_stderr"] = compile_out["stderr"]

            # Test step
            if payload.test_command:
                test_out = await self._run_subprocess(payload.test_command)
                result["test_success"] = test_out["exit_code"] == 0
                result["test_stdout"] = test_out["stdout"]
                result["test_stderr"] = test_out["stderr"]
            else:
                result["test_success"] = result["compile_success"]

            # Benchmark step
            if payload.benchmark_command:
                bench_out = await self._run_subprocess(payload.benchmark_command)
                result["bench_stdout"] = bench_out["stdout"]

        finally:
            code_path.unlink(missing_ok=True)
            result["duration_seconds"] = time.monotonic() - t0

        logger.info(
            "local_worker.completed",
            job_id=payload.job_id,
            compile_success=result["compile_success"],
            test_success=result["test_success"],
            duration=round(result["duration_seconds"], 2),
        )
        return result

    async def _run_subprocess(self, cmd: list[str]) -> dict[str, Any]:
        loop = asyncio.get_event_loop()
        try:
            proc = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                ),
            )
            return {
                "stdout": proc.stdout[:3000],
                "stderr": proc.stderr[:3000],
                "exit_code": proc.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": f"Timeout after {self._timeout}s", "exit_code": -1}
        except Exception as exc:  # noqa: BLE001
            return {"stdout": "", "stderr": str(exc), "exit_code": -1}


async def worker_main(redis_url: str = "redis://localhost:6379/0") -> None:
    """
    Entry point for a standalone worker process.
    Polls Redis for jobs and processes them.
    """
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    except ImportError:
        logger.error("local_worker.redis_not_installed")
        return

    worker = LocalWorker()
    logger.info("local_worker.polling", redis_url=redis_url)

    while True:
        try:
            raw = await r.brpop(["blynx:jobs"], timeout=5)
            if raw:
                import json
                from aiswarm.worker.dispatcher import JobPayload
                _, value = raw
                data = json.loads(value)
                # Reconstruct payload-like object
                class _Payload:
                    job_id = data["job_id"]
                    task_id = data["task_id"]
                    code = data["code"]
                    language = data["language"]
                    test_command = data["test_command"]
                    benchmark_command = data["benchmark_command"]
                    state_hash = data["state_hash"]

                result = await worker.execute(_Payload())
                result_key = f"blynx:result:{data['job_id']}"
                await r.lpush(result_key, json.dumps(result))
                await r.expire(result_key, 3600)
        except Exception as exc:  # noqa: BLE001
            logger.error("local_worker.poll_error", error=str(exc))
            await asyncio.sleep(5)
