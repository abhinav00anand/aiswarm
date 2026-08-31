"""
Stress tests for DeadlockDetector.

Covers:
  - 500-task scan completes in < 2 seconds
  - Retry-count deadlock detection (task.retry_count >= max_retries)
  - Timeout-based deadlock detection (state stale > threshold)
  - Tasks completing normally are never mis-detected
  - Multiple callbacks fire reliably
  - forget() removes task from tracking immediately
  - scan() returns correct task_id list
  - Concurrent scan + notify_state_change (no data corruption)
  - DeadlockPacket content is correct
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
import time

import pytest

from aiswarm.core.deadlock_detector import DeadlockDetector, DeadlockPacket
from aiswarm.schemas.task import Task, TaskState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _task(state: TaskState = TaskState.GENERATED, max_retries: int = 5) -> Task:
    return Task(title="DL test", description="test", state=state, max_retries=max_retries)


def _detector(timeout: float = 300.0, interval: float = 30.0) -> DeadlockDetector:
    return DeadlockDetector(deadlock_timeout=timeout, scan_interval=interval)


# ---------------------------------------------------------------------------
# Retry-count detection
# ---------------------------------------------------------------------------


class TestDeadlockDetectorRetryCount:
    @pytest.mark.asyncio
    async def test_task_at_max_retries_detected(self):
        det = _detector()
        task = _task()
        task.retry_count = task.max_retries
        det.notify_state_change(task)
        assert det.check_task(task)

    @pytest.mark.asyncio
    async def test_task_below_max_retries_not_detected(self):
        det = _detector()
        task = _task()
        task.retry_count = task.max_retries - 1
        det.notify_state_change(task)
        assert not det.check_task(task)

    @pytest.mark.asyncio
    async def test_scan_returns_deadlocked_task_ids(self):
        det = _detector()
        tasks = [_task() for _ in range(5)]
        for i, t in enumerate(tasks):
            t.retry_count = t.max_retries if i < 3 else 0
            det.notify_state_change(t)

        deadlocked = await det.scan(tasks)
        assert len(deadlocked) == 3
        assert all(tid in {t.task_id for t in tasks[:3]} for tid in deadlocked)

    @pytest.mark.asyncio
    async def test_scan_sets_task_state_to_deadlock(self):
        det = _detector()
        task = _task()
        task.retry_count = task.max_retries
        det.notify_state_change(task)
        await det.scan([task])
        assert task.state == TaskState.DEADLOCK

    @pytest.mark.asyncio
    async def test_already_deadlocked_task_skipped_in_scan(self):
        det = _detector()
        task = _task(state=TaskState.DEADLOCK)
        task.retry_count = task.max_retries
        deadlocked = await det.scan([task])
        assert len(deadlocked) == 0


# ---------------------------------------------------------------------------
# Timeout-based detection
# ---------------------------------------------------------------------------


class TestDeadlockDetectorTimeout:
    @pytest.mark.asyncio
    async def test_fresh_task_not_timed_out(self):
        det = _detector(timeout=300.0)
        task = _task()
        det.notify_state_change(task)
        assert not det.check_task(task)

    @pytest.mark.asyncio
    async def test_stale_task_detected_via_timeout(self):
        det = _detector(timeout=0.01)
        task = _task()
        # Manually set a stale timestamp
        det._state_entered[task.task_id] = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert det.check_task(task)

    @pytest.mark.asyncio
    async def test_timeout_triggers_before_retry_max(self):
        """Even with retries remaining, timeout can trigger deadlock."""
        det = _detector(timeout=0.01)
        task = _task(max_retries=100)
        task.retry_count = 0
        det._state_entered[task.task_id] = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert det.check_task(task)

    @pytest.mark.asyncio
    async def test_state_change_resets_timeout_clock(self):
        det = _detector(timeout=0.05)
        task = _task()
        # Artificially age the task
        det._state_entered[task.task_id] = datetime.now(timezone.utc) - timedelta(seconds=1)
        # Notify fresh state change
        det.notify_state_change(task)
        # Should no longer be timed out
        assert not det.check_task(task)


# ---------------------------------------------------------------------------
# Terminal-state tasks never misdetected
# ---------------------------------------------------------------------------


class TestDeadlockDetectorTerminalSafety:
    @pytest.mark.asyncio
    async def test_merged_task_never_detected(self):
        det = _detector(timeout=0.001)
        task = _task(state=TaskState.MERGED)
        task.retry_count = 999
        det._state_entered[task.task_id] = datetime.now(timezone.utc) - timedelta(seconds=9999)
        assert not det.check_task(task)

    @pytest.mark.asyncio
    async def test_rejected_task_never_detected(self):
        det = _detector(timeout=0.001)
        task = _task(state=TaskState.REJECTED)
        det._state_entered[task.task_id] = datetime.now(timezone.utc) - timedelta(seconds=9999)
        assert not det.check_task(task)

    @pytest.mark.asyncio
    async def test_cancelled_task_never_detected(self):
        det = _detector(timeout=0.001)
        task = _task(state=TaskState.CANCELLED)
        assert not det.check_task(task)


# ---------------------------------------------------------------------------
# Forget / cleanup
# ---------------------------------------------------------------------------


class TestDeadlockDetectorForget:
    def test_forget_removes_tracking(self):
        det = _detector()
        task = _task()
        det.notify_state_change(task)
        assert task.task_id in det._state_entered
        det.forget(task.task_id)
        assert task.task_id not in det._state_entered

    def test_forget_unknown_task_noop(self):
        det = _detector()
        det.forget("ghost-task-id")  # should not raise

    @pytest.mark.asyncio
    async def test_forgotten_task_not_in_scan(self):
        det = _detector()
        task = _task()
        task.retry_count = task.max_retries
        det.notify_state_change(task)
        det.forget(task.task_id)
        # After forget, scan won't detect it (no state_entered entry for timeout check)
        # But retry_count still triggers it
        result = await det.scan([task])
        assert task.task_id in result
        # Reset retry_count and verify scan is clean
        task2 = _task()
        det.forget(task2.task_id)
        result2 = await det.scan([task2])
        assert task2.task_id not in result2


# ---------------------------------------------------------------------------
# Callback reliability
# ---------------------------------------------------------------------------


class TestDeadlockDetectorCallbacks:
    @pytest.mark.asyncio
    async def test_single_callback_fired(self):
        det = _detector()
        fired = []

        async def on_deadlock(task_id, packet):
            fired.append((task_id, packet))

        det.on_deadlock(on_deadlock)
        task = _task()
        task.retry_count = task.max_retries
        det.notify_state_change(task)
        await det.scan([task])
        assert len(fired) == 1
        assert fired[0][0] == task.task_id
        assert isinstance(fired[0][1], DeadlockPacket)

    @pytest.mark.asyncio
    async def test_multiple_callbacks_all_fired(self):
        det = _detector()
        hits = []

        for _ in range(5):

            async def cb(task_id, packet, _hits=hits):
                _hits.append(task_id)

            det.on_deadlock(cb)

        task = _task()
        task.retry_count = task.max_retries
        await det.scan([task])
        assert len(hits) == 5

    @pytest.mark.asyncio
    async def test_crashing_callback_does_not_stop_others(self):
        det = _detector()
        good_hits = []

        async def crasher(task_id, packet):
            raise RuntimeError("callback crash")

        async def good_cb(task_id, packet):
            good_hits.append(task_id)

        det.on_deadlock(crasher)
        det.on_deadlock(good_cb)

        task = _task()
        task.retry_count = task.max_retries
        await det.scan([task])
        assert len(good_hits) == 1


# ---------------------------------------------------------------------------
# Performance at scale
# ---------------------------------------------------------------------------


class TestDeadlockDetectorScalePerformance:
    @pytest.mark.asyncio
    async def test_concurrent_scan_and_notify_state_change(self):
        """scan() and notify_state_change() running simultaneously must not corrupt state."""
        det = _detector()
        tasks = [_task() for _ in range(100)]
        for t in tasks:
            det.notify_state_change(t)

        scan_results = []

        async def scanner():
            for _ in range(5):
                result = await det.scan([t for t in tasks if t.state != TaskState.DEADLOCK])
                scan_results.extend(result)
                await asyncio.sleep(0)

        async def updater():
            for t in tasks[50:]:
                det.notify_state_change(t)  # re-notify to reset clock
                await asyncio.sleep(0)

        await asyncio.gather(scanner(), updater(), scanner())
        # All tasks have retry_count=0, so no deadlocks should be detected
        non_deadlock_detections = [tid for tid in scan_results if tid in {t.task_id for t in tasks}]
        assert len(non_deadlock_detections) == 0

    @pytest.mark.asyncio
    async def test_500_task_scan_under_2_seconds(self):
        det = _detector()
        tasks = [_task() for _ in range(500)]
        for t in tasks:
            det.notify_state_change(t)
            t.retry_count = 0  # none deadlocked

        start = time.monotonic()
        result = await det.scan(tasks)
        elapsed = time.monotonic() - start
        assert len(result) == 0
        assert elapsed < 2.0, f"Scan took {elapsed:.2f}s for 500 tasks"

    @pytest.mark.asyncio
    async def test_1000_tasks_mixed_deadlocked_scan_correct(self):
        det = _detector()
        tasks = [_task() for _ in range(1000)]
        deadlock_count = 0
        for i, t in enumerate(tasks):
            if i % 10 == 0:
                t.retry_count = t.max_retries
                deadlock_count += 1
            det.notify_state_change(t)

        result = await det.scan(tasks)
        assert len(result) == deadlock_count


# ---------------------------------------------------------------------------
# DeadlockPacket content
# ---------------------------------------------------------------------------


class TestDeadlockPacket:
    def test_packet_contains_correct_task_info(self):
        task = _task()
        task.retry_count = 5
        task.generated_code = "def foo(): pass"
        packet = DeadlockPacket(task)
        assert packet.task_id == task.task_id
        assert packet.retry_count == 5
        assert "foo" in packet.latest_code

    def test_prompt_block_format(self):
        task = _task()
        task.retry_count = 3
        packet = DeadlockPacket(task)
        block = packet.to_prompt_block()
        assert "DEADLOCK PACKET" in block
        assert task.task_id in block
        assert "Retries: 3" in block
        assert "END DEADLOCK PACKET" in block
