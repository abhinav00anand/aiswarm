"""
Worker Dispatcher — routes jobs to local, Docker, or sandboxed workers via Redis.

Architecture:
  CPU Orchestrator → Redis job queue → Worker (local/docker/sandboxed) → Redis result queue

The dispatcher:
  1. Serializes the job payload + state hash.
  2. Pushes to Redis LPUSH aiswarm:jobs.
  3. Polls BRPOP aiswarm:results until result arrives or timeout.
  4. Validates the state hash on the result.
  5. Deserializes and returns the worker output.

Workers poll independently; the dispatcher never maintains a direct connection.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_JOB_QUEUE = "aiswarm:jobs"
_RESULT_QUEUE_PREFIX = "aiswarm:result:"
_DEFAULT_TIMEOUT = 300  # seconds


class JobPayload:
    """Serializable job package sent from CPU to Worker."""

    def __init__(
        self,
        task_id: str,
        code: str,
        language: str = "python",
        test_command: list[str] | None = None,
        benchmark_command: list[str] | None = None,
        environment: dict[str, str] | None = None,
    ) -> None:
        self.job_id = str(uuid.uuid4())
        self.task_id = task_id
        self.code = code
        self.language = language
        self.test_command = test_command or []
        self.benchmark_command = benchmark_command or []
        self.environment = environment or {}
        self.state_hash = hashlib.sha256(code.encode()).hexdigest()
        self.created_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "task_id": self.task_id,
            "code": self.code,
            "language": self.language,
            "test_command": self.test_command,
            "benchmark_command": self.benchmark_command,
            "environment": self.environment,
            "state_hash": self.state_hash,
            "created_at": self.created_at,
        }


class WorkerDispatcher:
    """
    Dispatches jobs to workers via Redis polling.
    Falls back to local execution if Redis is unavailable.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        timeout: float = _DEFAULT_TIMEOUT,
        mode: str = "local",
    ) -> None:
        self._redis_url = redis_url
        self._timeout = timeout
        self._mode = mode
        self._redis: Any = None

    async def _get_redis(self) -> Any:
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(
                    self._redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                await self._redis.ping()
                logger.info("dispatcher.redis_connected", url=self._redis_url)
            except Exception as exc:  # noqa: BLE001
                logger.warning("dispatcher.redis_unavailable", error=str(exc))
                self._redis = None
        return self._redis

    async def dispatch(self, payload: JobPayload) -> dict[str, Any] | None:
        """
        Push a job and wait for a result. Returns the result dict or None on timeout.
        """
        redis = await self._get_redis()
        if redis is None:
            logger.info("dispatcher.fallback_local", job_id=payload.job_id)
            return await self._run_local(payload)

        # Push job
        await redis.lpush(_JOB_QUEUE, json.dumps(payload.to_dict()))
        logger.info(
            "dispatcher.job_dispatched",
            job_id=payload.job_id,
            task_id=payload.task_id,
        )

        # Poll for result
        result_key = f"{_RESULT_QUEUE_PREFIX}{payload.job_id}"
        t0 = time.monotonic()
        while (time.monotonic() - t0) < self._timeout:
            raw = await redis.brpop([result_key], timeout=5)
            if raw:
                _, value = raw
                result: dict[str, Any] = json.loads(value)
                # Validate state hash
                if result.get("state_hash") != payload.state_hash:
                    logger.error(
                        "dispatcher.hash_mismatch",
                        job_id=payload.job_id,
                        expected=payload.state_hash,
                        got=result.get("state_hash"),
                    )
                    return None
                return result
            await asyncio.sleep(1)

        logger.warning(
            "dispatcher.timeout",
            job_id=payload.job_id,
            timeout=self._timeout,
        )
        return None

    async def _run_local(self, payload: JobPayload) -> dict[str, Any]:
        """Fallback: run the job locally in a subprocess."""
        from aiswarm.worker.local_worker import LocalWorker
        worker = LocalWorker()
        return await worker.execute(payload)
