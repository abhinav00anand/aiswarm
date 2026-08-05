"""Unit tests for the checkpoint save/load/list/delete functions."""

from __future__ import annotations

from pathlib import Path

import pytest

import aiswarm.core.checkpoint as checkpoint_module
from aiswarm.schemas.task import Task


@pytest.fixture()
def isolated_checkpoint_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ckpt_dir = tmp_path / "checkpoints"
    ckpt_dir.mkdir()
    monkeypatch.setattr(checkpoint_module, "_CHECKPOINT_DIR", ckpt_dir)
    return ckpt_dir


class TestSaveAndLoadTask:
    def test_save_creates_file(self, isolated_checkpoint_dir: Path) -> None:
        task = Task(title="T", description="D")
        path = checkpoint_module.save_task(task)
        assert path.exists()

    def test_load_restores_equivalent_task(self, isolated_checkpoint_dir: Path) -> None:
        task = Task(title="T", description="D")
        checkpoint_module.save_task(task)
        loaded = checkpoint_module.load_task(task.task_id)
        assert loaded is not None
        assert loaded.task_id == task.task_id
        assert loaded.title == "T"

    def test_load_nonexistent_returns_none(self, isolated_checkpoint_dir: Path) -> None:
        assert checkpoint_module.load_task("does-not-exist") is None

    def test_load_corrupted_file_returns_none(self, isolated_checkpoint_dir: Path) -> None:
        bad_path = isolated_checkpoint_dir / "bad-task.json"
        bad_path.write_text("{not valid json")
        assert checkpoint_module.load_task("bad-task") is None

    def test_save_uses_atomic_write_no_leftover_tmp(self, isolated_checkpoint_dir: Path) -> None:
        task = Task(title="T", description="D")
        checkpoint_module.save_task(task)
        tmp_files = list(isolated_checkpoint_dir.glob("*.tmp"))
        assert tmp_files == []

    def test_resave_overwrites_previous_checkpoint(self, isolated_checkpoint_dir: Path) -> None:
        task = Task(title="Original", description="D")
        checkpoint_module.save_task(task)
        task.title = "Updated"
        checkpoint_module.save_task(task)
        loaded = checkpoint_module.load_task(task.task_id)
        assert loaded is not None
        assert loaded.title == "Updated"


class TestListAndDeleteCheckpoints:
    def test_list_checkpoints_empty_initially(self, isolated_checkpoint_dir: Path) -> None:
        assert checkpoint_module.list_checkpoints() == []

    def test_list_checkpoints_returns_saved_ids(self, isolated_checkpoint_dir: Path) -> None:
        t1 = Task(title="A", description="D")
        t2 = Task(title="B", description="D")
        checkpoint_module.save_task(t1)
        checkpoint_module.save_task(t2)
        ids = checkpoint_module.list_checkpoints()
        assert t1.task_id in ids
        assert t2.task_id in ids

    def test_delete_checkpoint_removes_file(self, isolated_checkpoint_dir: Path) -> None:
        task = Task(title="T", description="D")
        checkpoint_module.save_task(task)
        checkpoint_module.delete_checkpoint(task.task_id)
        assert checkpoint_module.load_task(task.task_id) is None

    def test_delete_nonexistent_checkpoint_is_noop(self, isolated_checkpoint_dir: Path) -> None:
        checkpoint_module.delete_checkpoint("never-existed")  # should not raise


class TestCheckpointManager:
    def test_stop_sets_running_false(self) -> None:
        mgr = checkpoint_module.CheckpointManager(interval=60.0)
        mgr._running = True
        mgr.stop()
        assert mgr._running is False

    def test_default_interval(self) -> None:
        mgr = checkpoint_module.CheckpointManager()
        assert mgr._interval == 60.0

    def test_custom_interval_respected(self) -> None:
        mgr = checkpoint_module.CheckpointManager(interval=5.0)
        assert mgr._interval == 5.0
