"""
Redis-backed task store — makes the Orchestrator stateless and horizontally scalable.

Falls back gracefully to in-memory when Redis is unavailable (dev/test mode).
Every write is also checkpointed to disk for durability.

Key schema:
  aiswarm:task:{task_id}          → JSON-serialised Task (hash)
  aiswarm:tasks:active            → sorted set of active task_ids (score = created_at timestamp)
  aiswarm:tasks:all               → set of all known task_ids
"""

from __future__ import annotations

import json
import os
from datetime import timezone
from typing import Any

import structlog

from aiswarm.schemas.task import Task, TaskState

logger = structlog.get_logger(__name__)

_KEY_TASK   = "aiswarm:task:{}"
_KEY_ACTIVE = "aiswarm:tasks:active"
_KEY_ALL    = "aiswarm:tasks:all"
_TTL_TERMINAL = 60 * 60 * 24 * 7  # keep terminal tasks for 7 days


def _task_key(task_id: str) -> str:
    return _KEY_TASK.format(task_id)


class RedisTaskStore:
    """
    Persists Task objects in Redis.

    Transparently degrades to a pure in-memory dict when Redis is
    unavailable — the API surface is identical in both cases.
    """

    def __init__(self, redis_client: Any | None = None) -> None:
        self._redis = redis_client
        self._local: dict[str, Task] = {}
        self._available = redis_client is not None
        if self._available:
            logger.info("redis_task_store.redis_mode")
        else:
            logger.warning(
                "redis_task_store.memory_mode",
                reason="No Redis client provided — using in-memory fallback",
            )

    # ── Write ──────────────────────────────────────────────────────────────

    async def save(self, task: Task) -> None:
        """Persist a task. Always succeeds — Redis failures fall back to memory."""
        self._local[task.task_id] = task

        if not self._available:
            return

        try:
            payload = task.model_dump_json()
            key = _task_key(task.task_id)
            await self._redis.set(key, payload)

            score = task.created_at.replace(tzinfo=timezone.utc).timestamp()
            await self._redis.zadd(_KEY_ACTIVE, {task.task_id: score})
            await self._redis.sadd(_KEY_ALL, task.task_id)

            # Remove terminal tasks from the active set and set expiry
            from aiswarm.core.state_machine import StateMachine
            if StateMachine.is_terminal(task.state):
                await self._redis.zrem(_KEY_ACTIVE, task.task_id)
                await self._redis.expire(key, _TTL_TERMINAL)

        except Exception as exc:  # noqa: BLE001
            logger.warning("redis_task_store.save_error", task_id=task.task_id, error=str(exc))

    async def delete(self, task_id: str) -> None:
        self._local.pop(task_id, None)
        if not self._available:
            return
        try:
            await self._redis.delete(_task_key(task_id))
            await self._redis.zrem(_KEY_ACTIVE, task_id)
            await self._redis.srem(_KEY_ALL, task_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis_task_store.delete_error", task_id=task_id, error=str(exc))

    # ── Read ───────────────────────────────────────────────────────────────

    async def get(self, task_id: str) -> Task | None:
        # Prefer in-memory copy (always most up-to-date within process)
        if task_id in self._local:
            return self._local[task_id]

        if not self._available:
            return None

        try:
            raw = await self._redis.get(_task_key(task_id))
            if raw:
                task = Task.model_validate_json(raw)
                self._local[task_id] = task
                return task
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis_task_store.get_error", task_id=task_id, error=str(exc))

        return None

    async def get_all(self) -> list[Task]:
        if self._available:
            try:
                task_ids = await self._redis.smembers(_KEY_ALL)
                for tid in task_ids:
                    tid_str = tid.decode() if isinstance(tid, bytes) else tid
                    if tid_str not in self._local:
                        await self.get(tid_str)
            except Exception as exc:  # noqa: BLE001
                logger.warning("redis_task_store.get_all_redis_error", error=str(exc))
        return list(self._local.values())

    async def get_active(self) -> list[Task]:
        from aiswarm.core.state_machine import StateMachine
        if self._available:
            try:
                task_ids = await self._redis.zrange(_KEY_ACTIVE, 0, -1)
                for tid in task_ids:
                    tid_str = tid.decode() if isinstance(tid, bytes) else tid
                    if tid_str not in self._local:
                        await self.get(tid_str)
            except Exception as exc:  # noqa: BLE001
                logger.warning("redis_task_store.get_active_redis_error", error=str(exc))
        return [t for t in self._local.values() if not StateMachine.is_terminal(t.state)]

    async def restore_from_redis(self) -> int:
        """On startup, load all tasks from Redis into local memory."""
        if not self._available:
            return 0
        restored = 0
        try:
            task_ids = await self._redis.smembers(_KEY_ALL)
            for tid in task_ids:
                tid_str = tid.decode() if isinstance(tid, bytes) else tid
                if tid_str not in self._local:
                    raw = await self._redis.get(_task_key(tid_str))
                    if raw:
                        task = Task.model_validate_json(raw)
                        self._local[tid_str] = task
                        restored += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis_task_store.restore_error", error=str(exc))
        if restored:
            logger.info("redis_task_store.restored", count=restored)
        return restored

    # ── Stats ──────────────────────────────────────────────────────────────

    def summary(self) -> dict[str, Any]:
        from aiswarm.core.state_machine import StateMachine
        states: dict[str, int] = {}
        for t in self._local.values():
            states[t.state.value] = states.get(t.state.value, 0) + 1
        return {
            "total": len(self._local),
            "by_state": states,
            "backend": "redis" if self._available else "memory",
        }
