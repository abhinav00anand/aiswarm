"""Unit tests for FailureMemory — pattern matching and persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiswarm.memory.failure_memory import FailureMemory, FailureRecord
import aiswarm.memory.failure_memory as failure_memory_module


@pytest.fixture()
def isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store_path = tmp_path / "failure_memory.json"
    monkeypatch.setattr(failure_memory_module, "_STORE_PATH", store_path)
    return store_path


class TestFailureMemory:
    def test_starts_empty_when_no_file_exists(self, isolated_store: Path) -> None:
        mem = FailureMemory()
        assert mem.find_similar("anything") == []

    def test_record_persists_to_disk(self, isolated_store: Path) -> None:
        mem = FailureMemory()
        mem.record(
            FailureRecord(
                task_id="t1",
                task_title="Fix bug",
                error_pattern="circular import",
                error_source="compiler",
                resolution="moved import inline",
            )
        )
        assert isolated_store.exists()
        data = json.loads(isolated_store.read_text())
        assert len(data) == 1

    def test_find_similar_matches_substring(self, isolated_store: Path) -> None:
        mem = FailureMemory()
        mem.record(
            FailureRecord(
                task_id="t1",
                task_title="T",
                error_pattern="numpy not available",
                error_source="compiler",
                resolution="add numpy to requirements",
            )
        )
        matches = mem.find_similar("ImportError: numpy not available in sandbox")
        assert len(matches) == 1

    def test_find_similar_case_insensitive(self, isolated_store: Path) -> None:
        mem = FailureMemory()
        mem.record(
            FailureRecord(
                task_id="t1",
                task_title="T",
                error_pattern="Circular Import",
                error_source="compiler",
                resolution="fix",
            )
        )
        matches = mem.find_similar("error: circular import detected")
        assert len(matches) == 1

    def test_find_similar_respects_top_k(self, isolated_store: Path) -> None:
        mem = FailureMemory()
        for i in range(5):
            mem.record(
                FailureRecord(
                    task_id=f"t{i}",
                    task_title="T",
                    error_pattern="timeout",
                    error_source="test",
                    resolution=f"fix-{i}",
                )
            )
        matches = mem.find_similar("timeout occurred", top_k=2)
        assert len(matches) == 2

    def test_resolution_hint_returns_none_when_no_match(self, isolated_store: Path) -> None:
        mem = FailureMemory()
        assert mem.resolution_hint("totally unrelated error") is None

    def test_resolution_hint_includes_resolution_text(self, isolated_store: Path) -> None:
        mem = FailureMemory()
        mem.record(
            FailureRecord(
                task_id="t1",
                task_title="T",
                error_pattern="hardcoded secret",
                error_source="security_critic",
                resolution="use env var instead",
            )
        )
        hint = mem.resolution_hint("found hardcoded secret in config.py")
        assert hint is not None
        assert "use env var instead" in hint

    def test_corrupted_file_falls_back_to_empty(self, isolated_store: Path) -> None:
        isolated_store.parent.mkdir(parents=True, exist_ok=True)
        isolated_store.write_text("{not valid json")
        mem = FailureMemory()
        assert mem.find_similar("anything") == []

    def test_most_recent_match_returned_first(self, isolated_store: Path) -> None:
        mem = FailureMemory()
        mem.record(
            FailureRecord(
                task_id="t1",
                task_title="T",
                error_pattern="deadlock",
                error_source="orchestrator",
                resolution="old-fix",
                resolved_at=100.0,
            )
        )
        mem.record(
            FailureRecord(
                task_id="t2",
                task_title="T",
                error_pattern="deadlock",
                error_source="orchestrator",
                resolution="new-fix",
                resolved_at=200.0,
            )
        )
        matches = mem.find_similar("deadlock detected", top_k=1)
        assert matches[0].resolution == "new-fix"
