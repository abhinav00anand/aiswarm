"""Checkpoint system."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import structlog

from aiswarm.schemas.task import Task

logger = structlog.get_logger(__name__)

_CHECKPOINT_DIR = Path("./storage/checkpoints")
_CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

def _checkpoint_path(task_id: str) -> Path:
    return _CHECKPOINT_DIR / f"{task_id}.json"

def save_task(task: Task) -> Path:
    """Atomically serialize a task to disk."""
    path = _checkpoint_path(task.task_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(task.model_dump_json(indent=2))
    os.replace(tmp, path)

    logger.debug("checkpoint.saved", task_id=task.task_id, path=str(path))
    return path

def load_task(task_id: str) -> Task | None:
    """Load a task from its checkpoint file, or return None if not found."""
    path = _checkpoint_path(task_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        task = Task.model_validate(data)
        logger.info("checkpoint.restored", task_id=task_id)
        return task
    except Exception as exc:  # noqa: BLE001
        logger.error("checkpoint.load_error", task_id=task_id, error=str(exc))
        return None

def list_checkpoints() -> list[str]:
    """Return all saved task IDs."""
    return [p.stem for p in _CHECKPOINT_DIR.glob("*.json")]

def delete_checkpoint(task_id: str) -> None:
    path = _checkpoint_path(task_id)
    if path.exists():
        path.unlink()
        logger.debug("checkpoint.deleted", task_id=task_id)

class CheckpointManager:
    """
    Background service that periodically saves all active tasks.
    """

    def __init__(self, interval: float = 60.0) -> None:
        self._interval = interval
        self._running = False

    async def run_forever(self, task_registry_fn) -> None:  # type: ignore[type-arg]
        self._running = True
        logger.info("checkpoint_manager.started", interval=self._interval)
        while self._running:
            await asyncio.sleep(self._interval)
            try:
                tasks: list[Task] = await task_registry_fn()
                for task in tasks:
                    save_task(task)
                logger.debug("checkpoint.batch_saved", count=len(tasks))
            except Exception as exc:  # noqa: BLE001
                logger.error("checkpoint.batch_error", error=str(exc))

    def stop(self) -> None:
        self._running = False
