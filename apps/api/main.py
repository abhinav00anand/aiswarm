"""
Zymis FastAPI Application.

Endpoints:
  POST /tasks                   — submit a new task
  GET  /tasks                   — list all tasks
  GET  /tasks/{id}              — get task detail
  POST /tasks/{id}/cancel       — cancel a running task
  POST /tasks/{id}/force-merge  — operator force-merge (bypass all gates)
  POST /tasks/{id}/retry        — reset and re-queue a failed task
  GET  /health                  — liveness check
  GET  /metrics/summary         — system-wide metrics summary
  GET  /cost/status             — budget and cost circuit breaker status
  GET  /providers               — list available LLM providers with health
  GET  /rag/status              — RAG index status
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from aiswarm.schemas.task import Task, TaskState, TaskPriority, TaskClass
from aiswarm.bootstrap.startup import build_orchestrator
from aiswarm.telemetry.logging import configure_logging

# ── Application state ─────────────────────────────────────────────────────────
_orchestrator = None
_lifecycle = None
_router_ref = None  # holds the ProviderRouter for cost/rate stats


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _orchestrator, _lifecycle, _router_ref
    import time
    app.state.start_time = time.time()
    
    from aiswarm.security.auth import APIKeyValidator
    APIKeyValidator.verify_api_keys()
    
    configure_logging()
    _orchestrator, _lifecycle = build_orchestrator(repo_root=".")
    # Expose the ProviderRouter for /cost/status
    try:
        boss = _orchestrator._agents.get("boss")
        if boss and hasattr(boss, "_router"):
            _router_ref = boss._router
    except Exception:  # noqa: BLE001
        pass
    await _lifecycle.startup()
    yield
    await _lifecycle.shutdown()


app = FastAPI(
    title="Zymis API",
    description="Lightweight multi-agent orchestration framework",
    version="0.1.2",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / response models ─────────────────────────────────────────────────

class CreateTaskRequest(BaseModel):
    title: str
    description: str
    target_files: list[str] = []
    target_language: str = "python"
    task_class: str = "FEATURE"
    priority: str = "NORMAL"
    acceptance_criteria: list[str] = []
    max_retries: int = 5


class TaskSummary(BaseModel):
    task_id: str
    title: str
    state: str
    priority: str
    retry_count: int
    merged: bool
    total_tokens_used: int
    estimated_cost_usd: float


class ForceMergeRequest(BaseModel):
    reason: str


# ── Dependency ────────────────────────────────────────────────────────────────

def get_orchestrator():  # type: ignore[return]
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    return _orchestrator


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
async def health() -> dict[str, Any]:
    from aiswarm.security.auth import APIKeyValidator
    import time
    
    keys = APIKeyValidator.get_configured_keys()
    masked_keys = {k: "***" for k in keys}
    uptime = time.time() - getattr(app.state, "start_time", time.time())
    
    return {
        "status": "healthy",
        "version": "1.0.0",
        "orchestrator": _orchestrator.summary() if _orchestrator else None,
        "configured_keys": masked_keys,
        "uptime": uptime,
    }


@app.get("/audit", tags=["security"])
async def get_audit_log() -> list[dict[str, Any]]:
    from aiswarm.security.audit import get_audit_ledger
    ledger = get_audit_ledger()
    events = await ledger.get_events(limit=100)
    return [e.model_dump(mode="json") if hasattr(e, "model_dump") else getattr(e, "__dict__", str(e)) for e in events]



@app.post("/tasks", response_model=TaskSummary, tags=["tasks"])
async def create_task(
    req: CreateTaskRequest,
    orc: Any = Depends(get_orchestrator),
) -> TaskSummary:
    task = Task(
        title=req.title,
        description=req.description,
        target_files=req.target_files,
        target_language=req.target_language,
        task_class=TaskClass(req.task_class),
        priority=TaskPriority(req.priority),
        acceptance_criteria=req.acceptance_criteria,
        max_retries=req.max_retries,
    )
    submitted = await orc.submit_task(task)
    return _to_summary(submitted)


@app.get("/tasks", response_model=list[TaskSummary], tags=["tasks"])
async def list_tasks(
    state: str | None = None,
    orc: Any = Depends(get_orchestrator),
) -> list[TaskSummary]:
    state_filter = TaskState(state) if state else None
    tasks = await orc.list_tasks(state=state_filter)
    return [_to_summary(t) for t in tasks]


@app.get("/tasks/{task_id}", response_model=dict[str, Any], tags=["tasks"])
async def get_task(
    task_id: str,
    orc: Any = Depends(get_orchestrator),
) -> dict[str, Any]:
    task = await orc.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task.model_dump(mode="json")


@app.post("/tasks/{task_id}/cancel", tags=["tasks"])
async def cancel_task(
    task_id: str,
    orc: Any = Depends(get_orchestrator),
) -> dict[str, str]:
    cancelled = await orc.cancel_task(task_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return {"status": "cancelled", "task_id": task_id}


@app.post("/tasks/{task_id}/force-merge", tags=["tasks"])
async def force_merge_task(
    task_id: str,
    req: ForceMergeRequest,
    orc: Any = Depends(get_orchestrator),
) -> dict[str, Any]:
    """
    Operator override — merge a task bypassing all critic and test gates.
    Requires a mandatory reason for the audit log.
    """
    task = await orc.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    if task.state == TaskState.MERGED:
        return {"status": "already_merged", "task_id": task_id}

    from aiswarm.core.force_merge import ForceMergeOperator
    op = ForceMergeOperator()
    try:
        await op.force_merge(task, reason=req.reason, operator="api")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"status": "force_merged", "task_id": task_id, "reason": req.reason}


@app.post("/tasks/{task_id}/retry", tags=["tasks"])
async def retry_task(
    task_id: str,
    orc: Any = Depends(get_orchestrator),
) -> dict[str, Any]:
    """Reset retry counter and re-queue a failed/deadlocked task."""
    task = await orc.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    if task.state == TaskState.MERGED:
        raise HTTPException(status_code=400, detail="Cannot retry a merged task")

    task.retry_count = 0
    task.state = TaskState.NEW
    submitted = await orc.submit_task(task)
    return {"status": "requeued", "task_id": task_id, "state": submitted.state.value}


@app.get("/metrics/summary", tags=["metrics"])
async def metrics_summary(
    orc: Any = Depends(get_orchestrator),
) -> dict[str, Any]:
    return orc.summary()


@app.get("/cost/status", tags=["metrics"])
async def cost_status() -> dict[str, Any]:
    """Return current budget consumption and remaining allowances."""
    if _router_ref is not None:
        guard = _router_ref.cost_guard
        return guard.check_budget_remaining()
    # Fallback: zero budget consumed (no LLM calls made yet)
    return {
        "session_cost_usd": 0.0,
        "session_tokens": 0,
        "session_limit_usd": float(os.getenv("MAX_SESSION_SPEND_USD", "10.0")),
        "daily_limit_usd": float(os.getenv("MAX_DAILY_SPEND_USD", "100.0")),
        "session_remaining_usd": float(os.getenv("MAX_SESSION_SPEND_USD", "10.0")),
        "provider_breakdown": {},
    }


@app.get("/providers", tags=["system"])
async def list_providers() -> dict[str, Any]:
    from aiswarm.llm.provider_router import ProviderRouter
    router = ProviderRouter()
    return {
        "available": router.list_available(),
        "stats": router.stats,
    }


@app.get("/rag/status", tags=["system"])
async def rag_status() -> dict[str, Any]:
    """Return RAG index health and document count."""
    try:
        from aiswarm.rag.retriever import RAGRetriever
        retriever = RAGRetriever()
        return retriever.status()
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "error": str(exc)}


class DirectModelRequest(BaseModel):
    prompt: str
    model: str = "gpt-4o"
    system_prompt: str = "You are a helpful AI assistant coordinated by Zymis."
    temperature: float = 0.7


@app.post("/direct-model/run", tags=["direct-model"])
async def run_direct_model(req: DirectModelRequest) -> dict[str, Any]:
    """Execute a direct LLM model prompt coordinated with Zymis security and audit logging."""
    from aiswarm.llm.direct_runner import DirectModelCoordinator
    coord = DirectModelCoordinator()
    return await coord.run_direct(
        prompt=req.prompt,
        model=req.model,
        system_prompt=req.system_prompt,
        temperature=req.temperature,
    )



def _to_summary(task: Task) -> TaskSummary:
    return TaskSummary(
        task_id=task.task_id,
        title=task.title,
        state=task.state.value,
        priority=task.priority.value,
        retry_count=task.retry_count,
        merged=task.merged,
        total_tokens_used=task.total_tokens_used,
        estimated_cost_usd=task.estimated_cost_usd,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "apps.api.main:app",
        host="127.0.0.1",
        port=int(os.getenv("PORT", "5000")),
        reload=False,
        log_level="info",
    )
