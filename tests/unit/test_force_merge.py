"""Unit tests for the ForceMergeOperator."""

from __future__ import annotations

import pytest

from aiswarm.schemas.task import Task, TaskClass, TaskState
from aiswarm.core.force_merge import ForceMergeOperator


def _make_task() -> Task:
    return Task(
        title="ForceMerge test",
        description="desc",
        task_class=TaskClass.FEATURE,
    )


@pytest.mark.asyncio
async def test_force_merge_transitions_to_merged():
    task = _make_task()
    op = ForceMergeOperator()
    await op.force_merge(task, reason="Tests broken by unrelated flaky suite", operator="ci_bot")
    assert task.state == TaskState.MERGED
    assert task.merged is True
    assert task.merged_by == "force_merge:ci_bot"


@pytest.mark.asyncio
async def test_force_merge_requires_non_empty_reason():
    task = _make_task()
    op = ForceMergeOperator()
    with pytest.raises(ValueError, match="requires a non-empty reason"):
        await op.force_merge(task, reason="")


@pytest.mark.asyncio
async def test_force_merge_idempotent_if_already_merged():
    task = _make_task()
    op = ForceMergeOperator()
    await op.force_merge(task, reason="First merge", operator="human")
    await op.force_merge(task, reason="Second merge attempt", operator="human")
    # Should not raise — idempotent
    assert task.state == TaskState.MERGED


@pytest.mark.asyncio
async def test_force_merge_records_metadata():
    task = _make_task()
    op = ForceMergeOperator()
    await op.force_merge(task, reason="Algorithm critic wrong about FFT", operator="alice")
    assert task.metadata.get("force_merged") is True
    assert "FFT" in task.metadata.get("force_merge_reason", "")
    assert task.metadata.get("force_merge_operator") == "alice"


@pytest.mark.asyncio
async def test_force_merge_sets_boss_override():
    task = _make_task()
    op = ForceMergeOperator()
    await op.force_merge(task, reason="Budget deadline", operator="cto")
    assert task.boss_override is not None
    assert "cto" in task.boss_override.lower() or "FORCE-MERGE" in task.boss_override
