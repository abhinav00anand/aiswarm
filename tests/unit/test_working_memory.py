"""Unit tests for WorkingMemory and WorkingMemoryStore."""

from __future__ import annotations

from aiswarm.memory.working_memory import WorkingMemory, WorkingMemoryStore


class TestWorkingMemory:
    def test_store_and_retrieve_roundtrip(self) -> None:
        mem = WorkingMemory(task_id="t1")
        mem.store("key", "value")
        assert mem.retrieve("key") == "value"

    def test_retrieve_missing_key_returns_default(self) -> None:
        mem = WorkingMemory(task_id="t1")
        assert mem.retrieve("missing", default="fallback") == "fallback"

    def test_retrieve_missing_key_returns_none_by_default(self) -> None:
        mem = WorkingMemory(task_id="t1")
        assert mem.retrieve("missing") is None

    def test_clear_empties_intermediate_results(self) -> None:
        mem = WorkingMemory(task_id="t1")
        mem.store("a", 1)
        mem.clear()
        assert mem.retrieve("a") is None

    def test_clear_resets_prompt_and_response(self) -> None:
        mem = WorkingMemory(task_id="t1", current_prompt="p", last_response="r")
        mem.clear()
        assert mem.current_prompt == ""
        assert mem.last_response == ""

    def test_default_token_budget(self) -> None:
        mem = WorkingMemory(task_id="t1")
        assert mem.token_budget_remaining == 100_000

    def test_created_at_is_set(self) -> None:
        mem = WorkingMemory(task_id="t1")
        assert mem.created_at > 0


class TestWorkingMemoryStore:
    def test_get_or_create_returns_same_instance(self) -> None:
        store = WorkingMemoryStore()
        m1 = store.get_or_create("t1")
        m2 = store.get_or_create("t1")
        assert m1 is m2

    def test_different_task_ids_get_different_instances(self) -> None:
        store = WorkingMemoryStore()
        m1 = store.get_or_create("t1")
        m2 = store.get_or_create("t2")
        assert m1 is not m2

    def test_clear_does_not_evict(self) -> None:
        store = WorkingMemoryStore()
        mem = store.get_or_create("t1")
        mem.store("k", "v")
        store.clear("t1")
        assert store.get_or_create("t1") is mem
        assert mem.retrieve("k") is None

    def test_evict_removes_entry(self) -> None:
        store = WorkingMemoryStore()
        m1 = store.get_or_create("t1")
        store.evict("t1")
        m2 = store.get_or_create("t1")
        assert m1 is not m2

    def test_clear_nonexistent_task_is_noop(self) -> None:
        store = WorkingMemoryStore()
        store.clear("never-existed")  # should not raise

    def test_evict_nonexistent_task_is_noop(self) -> None:
        store = WorkingMemoryStore()
        store.evict("never-existed")  # should not raise
