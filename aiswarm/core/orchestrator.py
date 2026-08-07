"""
Orchestrator — the central control plane of Blynx.

Responsibilities:
- Receives high-level tasks from Boss/Manager
- Maintains the task registry (in-memory + checkpointed)
- Dispatches tasks to the WorkflowEngine
- Routes events through the EventBus
- Runs background services: DeadlockDetector, CheckpointManager
- Exposes the agent registry so any component can resolve an agent by role
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from aiswarm.utils.compat_log import get_logger

from aiswarm.schemas.task import Task, TaskState
from aiswarm.schemas.events import Event, EventType
from aiswarm.core.event_bus import EventBus
from aiswarm.core.state_machine import StateMachine
from aiswarm.core.deadlock_detector import DeadlockDetector
from aiswarm.core.checkpoint import CheckpointManager, save_task, load_task, list_checkpoints
from aiswarm.agents.host1.router import Host1Router
from aiswarm.security.governor import EngineeringGovernor
from aiswarm.security.audit import get_audit_ledger

logger = get_logger(__name__)


class Orchestrator:
    """
    The Blynx control plane.

    Usage::

        orc = Orchestrator()
        await orc.start()
        task = await orc.submit_task(Task(title="Write softmax kernel", ...))
        await orc.shutdown()
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        event_bus: EventBus | None = None,
        host1_router: Host1Router | None = None,
        governor: EngineeringGovernor | None = None,
    ) -> None:
        self._config = config or {}
        self._bus = event_bus or EventBus()
        self.host1_router = host1_router
        self.governor = governor
        self._tasks: dict[str, Task] = {}
        self._agents: dict[str, Any] = {}
        self._semaphore = asyncio.Semaphore(
            self._config.get("max_concurrent_tasks", 10)
        )
        self._deadlock_detector = DeadlockDetector(
            deadlock_timeout=self._config.get("deadlock_timeout", 300.0),
            scan_interval=self._config.get("scan_interval", 30.0),
        )
        self._checkpoint_mgr = CheckpointManager(
            interval=self._config.get("checkpoint_interval", 60.0)
        )
        self._running = False
        self._background_tasks: list[asyncio.Task] = []  # type: ignore[type-arg]
        self._task_store: Any | None = None

        # Register deadlock callback
        self._deadlock_detector.on_deadlock(self._on_deadlock)

    # ── Task store ────────────────────────────────────────────────────────────

    def set_task_store(self, store: Any) -> None:
        """Attach a shared TaskStore (e.g. RedisTaskStore) to the orchestrator."""
        self._task_store = store
        logger.info("orchestrator.task_store_set", store_type=type(store).__name__)

    # ── Agent registry ────────────────────────────────────────────────────────

    def register_agent(self, role: str, agent: Any) -> None:
        self._agents[role] = agent
        logger.info("orchestrator.agent_registered", role=role, agent=type(agent).__name__)

    def get_agent(self, role: str) -> Any | None:
        return self._agents.get(role)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the orchestrator and all background services."""
        self._running = True
        logger.info("orchestrator.starting")

        # Restore checkpointed tasks
        await self._restore_checkpoints()

        # Start background services
        self._background_tasks = [
            asyncio.create_task(
                self._deadlock_detector.run_forever(self._get_active_tasks),
                name="deadlock_detector",
            ),
            asyncio.create_task(
                self._checkpoint_mgr.run_forever(self._get_active_tasks),
                name="checkpoint_manager",
            ),
        ]

        await self._bus.publish(Event(
            event_type=EventType.SYSTEM_STARTED,
            source="orchestrator",
            payload={"active_tasks": len(self._tasks)},
        ))
        logger.info("orchestrator.started", agent_count=len(self._agents))

    async def shutdown(self) -> None:
        """Graceful shutdown — checkpoint all tasks, cancel background services."""
        logger.info("orchestrator.shutting_down")
        self._running = False
        self._deadlock_detector.stop()
        self._checkpoint_mgr.stop()

        for t in self._background_tasks:
            t.cancel()
        await asyncio.gather(*self._background_tasks, return_exceptions=True)

        # Final checkpoint
        for task in self._tasks.values():
            save_task(task)

        await self._bus.publish(Event(
            event_type=EventType.SYSTEM_SHUTDOWN,
            source="orchestrator",
            payload={"tasks_saved": len(self._tasks)},
        ))
        logger.info("orchestrator.shutdown_complete")

    # ── Task management ───────────────────────────────────────────────────────

    async def submit_task(self, task: Task) -> Task:
        """
        Submit a task for execution.

        The task is registered, then executed asynchronously within the
        concurrency semaphore. Returns immediately with the registered task;
        the caller can poll task.state or subscribe to events.
        """
        if self.host1_router:
            # Build a dict payload from the Task object for Host1Router
            task_payload = {
                "task_id": task.task_id,
                "title": task.title,
                "description": getattr(task, "description", ""),
                "target_files": getattr(task, "target_files", []),
                "budget_tier": "normal",
            }
            decision = self.host1_router.evaluate_task(task_payload)
            if not hasattr(task, "metadata") or task.metadata is None:
                task.metadata = {}
            task.metadata["route_decision"] = decision

            if self.governor:
                # governor.check_task_admission is synchronous
                self.governor.check_task_admission(
                    {"task_id": task.task_id, "estimated_cost_usd": decision.estimated_cost_usd}
                )

            ledger = get_audit_ledger()
            await ledger.record(
                event_type="ROUTE_DECISION",
                actor="host1_router",
                action=f"route:{decision.route.value}",
                outcome=f"confidence:{decision.confidence:.2f}",
                task_id=task.task_id,
                metadata={
                    "route": decision.route.value,
                    "risk_level": decision.risk_level.value,
                    "estimated_cost_usd": decision.estimated_cost_usd,
                },
            )

        self._tasks[task.task_id] = task
        task.started_at = datetime.now(timezone.utc)
        self._deadlock_detector.notify_state_change(task)

        if self._task_store and hasattr(self._task_store, "put"):
            await self._task_store.put(task)

        await self._bus.publish(Event(
            event_type=EventType.TASK_CREATED,
            source="orchestrator",
            task_id=task.task_id,
            payload={"title": task.title, "priority": task.priority.value},
        ))

        asyncio.create_task(self._execute(task), name=f"task:{task.task_id}")
        return task

    async def _execute(self, task: Task) -> None:
        """Run a task inside the concurrency semaphore."""
        async with self._semaphore:
            from aiswarm.core.workflow_engine import WorkflowEngine
            engine = WorkflowEngine(self)
            try:
                await engine.run(task)
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001
                logger.error("orchestrator.execute_error", task_id=task.task_id, error=str(exc))
            finally:
                save_task(task)
                if self._task_store and hasattr(self._task_store, "put"):
                    try:
                        await self._task_store.put(task)
                    except Exception as exc:
                        logger.warning("orchestrator.task_store_update_error", task_id=task.task_id, error=str(exc))
                state_event_map = {
                    TaskState.MERGED: EventType.TASK_COMPLETED,
                    TaskState.REJECTED: EventType.TASK_REJECTED,
                    TaskState.DEADLOCK: EventType.TASK_DEADLOCK,
                    TaskState.ESCALATED: EventType.TASK_ESCALATED,
                    TaskState.CANCELLED: EventType.TASK_CANCELLED,
                }
                event_type = state_event_map.get(task.state, EventType.TASK_FAILED)
                await self._bus.publish(Event(
                    event_type=event_type,
                    source="orchestrator",
                    task_id=task.task_id,
                    payload={"final_state": task.state.value},
                ))


    async def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    async def list_tasks(self, state: TaskState | None = None) -> list[Task]:
        tasks = list(self._tasks.values())
        if state:
            tasks = [t for t in tasks if t.state == state]
        return tasks

    async def cancel_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        if not StateMachine.is_terminal(task.state):
            task.transition(TaskState.CANCELLED, "Cancelled by operator", agent="orchestrator")
            save_task(task)
        return True

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _get_active_tasks(self) -> list[Task]:
        return [
            t for t in self._tasks.values()
            if not StateMachine.is_terminal(t.state)
        ]

    async def _restore_checkpoints(self) -> None:
        restored = 0
        for task_id in list_checkpoints():
            if task_id not in self._tasks:
                task = load_task(task_id)
                if task and not StateMachine.is_terminal(task.state):
                    self._tasks[task_id] = task
                    restored += 1
        if restored:
            logger.info("orchestrator.checkpoints_restored", count=restored)

    async def _on_deadlock(self, task_id: str, packet: Any) -> None:
        task = self._tasks.get(task_id)
        if not task:
            return
        task.deadlock_summary = packet.to_prompt_block()
        await self._bus.publish(Event(
            event_type=EventType.TASK_DEADLOCK,
            source="orchestrator",
            task_id=task_id,
            payload={"retry_count": task.retry_count},
        ))

        # Escalate to Boss agent
        boss = self.get_agent("boss")
        if boss:
            try:
                await boss.handle_deadlock(task)
            except Exception as exc:  # noqa: BLE001
                logger.error("orchestrator.boss_escalation_error", error=str(exc))

    @property
    def event_bus(self) -> EventBus:
        return self._bus

    def summary(self) -> dict[str, Any]:
        states: dict[str, int] = {}
        for task in self._tasks.values():
            states[task.state.value] = states.get(task.state.value, 0) + 1
        return {
            "total_tasks": len(self._tasks),
            "by_state": states,
            "agents_registered": list(self._agents.keys()),
            "running": self._running,
        }
