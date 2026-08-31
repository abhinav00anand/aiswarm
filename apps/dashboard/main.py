"""
AISwarm Operator Dashboard — FastAPI application.

Provides:
  GET  /                     — HTML dashboard UI
  GET  /api/tasks            — list all tasks with full state
  GET  /api/tasks/{id}       — task detail
  POST /api/tasks/{id}/force-merge  — operator force-merge override
  POST /api/tasks/{id}/cancel       — cancel task
  POST /api/tasks/{id}/retry        — reset retry counter and re-queue
  GET  /api/metrics          — system-wide metrics (cost, throughput, critics)
  GET  /api/cost             — budget / cost circuit breaker status
  GET  /api/providers        — LLM provider health
  GET  /api/rag/status       — RAG index status
  WS   /ws/events            — live task event stream (Server-Sent Events)
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

app = FastAPI(
    title="AISwarm Dashboard",
    description="Operator control panel for AISwarm",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Shared orchestrator reference (injected at startup) ────────────────────────
_orchestrator: Any = None


def set_orchestrator(orc: Any) -> None:
    global _orchestrator
    _orchestrator = orc


def _get_orc() -> Any:
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    return _orchestrator


# ── HTML Dashboard UI ──────────────────────────────────────────────────────────

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AISwarm Operator Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0d1117; color: #c9d1d9; }
  header { background: #161b22; border-bottom: 1px solid #30363d; padding: 16px 24px;
           display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 1.2rem; font-weight: 600; color: #58a6ff; }
  .badge { background: #1f6feb; color: #fff; font-size: 0.7rem; padding: 2px 8px;
           border-radius: 12px; font-weight: 600; }
  main { padding: 24px; max-width: 1400px; margin: 0 auto; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }
  .card h3 { font-size: 0.75rem; color: #8b949e; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; }
  .card .value { font-size: 2rem; font-weight: 700; color: #f0f6fc; }
  .card .sub { font-size: 0.8rem; color: #8b949e; margin-top: 4px; }
  table { width: 100%; border-collapse: collapse; background: #161b22;
          border: 1px solid #30363d; border-radius: 8px; overflow: hidden; }
  th { background: #1c2128; padding: 12px 16px; text-align: left; font-size: 0.75rem;
       color: #8b949e; text-transform: uppercase; letter-spacing: 0.05em; }
  td { padding: 10px 16px; border-top: 1px solid #21262d; font-size: 0.875rem; vertical-align: middle; }
  tr:hover td { background: #1c2128; }
  .state { padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
  .state-MERGED     { background: #1a4731; color: #3fb950; }
  .state-REJECTED   { background: #4d1818; color: #f85149; }
  .state-DEADLOCK   { background: #4d2a00; color: #e3b341; }
  .state-NEW,.state-PROMPTED,.state-GENERATED { background: #1f2d3d; color: #58a6ff; }
  .state-REVIEWED,.state-COMPILED,.state-TESTED,.state-BENCHMARKED { background: #1a2d1a; color: #3fb950; }
  .state-CANCELLED  { background: #2d2d2d; color: #8b949e; }
  .state-ESCALATED  { background: #3d2d00; color: #e3b341; }
  .state-PRECHECKED { background: #1f2d3d; color: #79c0ff; }
  .btn { padding: 4px 12px; border-radius: 4px; border: 1px solid; cursor: pointer;
         font-size: 0.75rem; font-weight: 500; transition: opacity 0.2s; }
  .btn:hover { opacity: 0.8; }
  .btn-danger  { border-color: #f85149; color: #f85149; background: transparent; }
  .btn-success { border-color: #3fb950; color: #3fb950; background: transparent; }
  .btn-primary { border-color: #58a6ff; color: #58a6ff; background: transparent; }
  .section-title { font-size: 1rem; font-weight: 600; color: #f0f6fc; margin: 24px 0 12px; }
  .cost-bar { height: 6px; background: #21262d; border-radius: 3px; margin-top: 8px; overflow: hidden; }
  .cost-fill { height: 100%; background: #3fb950; border-radius: 3px; transition: width 0.5s; }
  .cost-fill.warn  { background: #e3b341; }
  .cost-fill.danger { background: #f85149; }
  #status { position: fixed; bottom: 16px; right: 16px; background: #1f6feb;
            color: #fff; padding: 8px 16px; border-radius: 6px; font-size: 0.8rem;
            opacity: 0; transition: opacity 0.3s; }
  #status.show { opacity: 1; }
  .refresh-btn { background: #1f6feb; color: #fff; border: none; padding: 8px 16px;
                 border-radius: 6px; cursor: pointer; font-size: 0.875rem; font-weight: 500; }
  .refresh-btn:hover { background: #388bfd; }
</style>
</head>
<body>
<header>
  <h1>AISwarm</h1>
  <span class="badge">Operator Dashboard</span>
  <div style="margin-left:auto;display:flex;gap:8px;align-items:center">
    <span id="last-updated" style="font-size:0.75rem;color:#8b949e"></span>
    <button class="refresh-btn" onclick="loadAll()">↻ Refresh</button>
  </div>
</header>
<main>
  <div class="grid" id="metrics-grid">
    <div class="card"><h3>Total Tasks</h3><div class="value" id="m-total">—</div></div>
    <div class="card"><h3>Active</h3><div class="value" id="m-active">—</div></div>
    <div class="card"><h3>Merged</h3><div class="value" id="m-merged">—</div></div>
    <div class="card"><h3>Deadlocked</h3><div class="value" id="m-dead">—</div></div>
    <div class="card">
      <h3>Daily Spend</h3>
      <div class="value" id="m-cost">—</div>
      <div class="sub" id="m-cost-limit"></div>
      <div class="cost-bar"><div class="cost-fill" id="m-cost-bar" style="width:0%"></div></div>
    </div>
    <div class="card"><h3>Session Tokens</h3><div class="value" id="m-tokens">—</div></div>
  </div>

  <div class="section-title">Active & Recent Tasks</div>
  <table id="task-table">
    <thead><tr>
      <th>Task ID</th><th>Title</th><th>Class</th><th>Priority</th>
      <th>State</th><th>Retries</th><th>Cost ($)</th><th>Actions</th>
    </tr></thead>
    <tbody id="task-body"><tr><td colspan="8" style="text-align:center;color:#8b949e">Loading…</td></tr></tbody>
  </table>
</main>
<div id="status"></div>

<script>
async function api(path, opts) {
  const base = window.location.origin.replace(':5000','').replace(':3000','');
  const apiBase = window.location.origin.includes('5000') ? '' : '';
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function showStatus(msg, err) {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.style.background = err ? '#b62324' : '#1a7f37';
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 3000);
}

function stateClass(s) { return 'state state-' + s; }

async function loadMetrics() {
  try {
    const d = await api('/metrics/summary');
    const states = d.by_state || {};
    document.getElementById('m-total').textContent = d.total_tasks || 0;
    const active = Object.entries(states)
      .filter(([s]) => !['MERGED','REJECTED','DEADLOCK','CANCELLED'].includes(s))
      .reduce((a,[,v]) => a+v, 0);
    document.getElementById('m-active').textContent = active;
    document.getElementById('m-merged').textContent = states.MERGED || 0;
    document.getElementById('m-dead').textContent = states.DEADLOCK || 0;
  } catch(e) { /* ignore */ }

  try {
    const c = await api('/cost/status');
    const spend = c.session_cost_usd || 0;
    const limit = c.daily_limit_usd || 100;
    const pct = Math.min(100, (spend / limit) * 100);
    document.getElementById('m-cost').textContent = '$' + spend.toFixed(4);
    document.getElementById('m-cost-limit').textContent = 'Limit: $' + limit.toFixed(2);
    const bar = document.getElementById('m-cost-bar');
    bar.style.width = pct + '%';
    bar.className = 'cost-fill' + (pct > 90 ? ' danger' : pct > 75 ? ' warn' : '');
    document.getElementById('m-tokens').textContent = (c.session_tokens||0).toLocaleString();
  } catch(e) { /* ignore */ }
}

async function loadTasks() {
  try {
    const tasks = await api('/tasks');
    const tbody = document.getElementById('task-body');
    if (!tasks.length) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#8b949e">No tasks yet</td></tr>';
      return;
    }
    tbody.innerHTML = tasks.map(t => `
      <tr>
        <td style="font-family:monospace;font-size:0.75rem;color:#8b949e">${t.task_id.slice(0,8)}…</td>
        <td>${t.title}</td>
        <td style="color:#8b949e">${t.priority||'NORMAL'}</td>
        <td style="color:#8b949e">${t.priority||'NORMAL'}</td>
        <td><span class="${stateClass(t.state)}">${t.state}</span></td>
        <td style="text-align:center">${t.retry_count}</td>
        <td>$${(t.estimated_cost_usd||0).toFixed(4)}</td>
        <td style="display:flex;gap:6px;flex-wrap:wrap">
          ${['DEADLOCK','ESCALATED'].includes(t.state) ? `<button class="btn btn-success" onclick="forceMerge('${t.task_id}')">Force Merge</button>` : ''}
          ${!['MERGED','CANCELLED','REJECTED'].includes(t.state) ? `<button class="btn btn-danger" onclick="cancelTask('${t.task_id}')">Cancel</button>` : ''}
          ${['DEADLOCK','REJECTED'].includes(t.state) ? `<button class="btn btn-primary" onclick="retryTask('${t.task_id}')">Retry</button>` : ''}
        </td>
      </tr>`).join('');
  } catch(e) { showStatus('Failed to load tasks: ' + e.message, true); }
}

async function forceMerge(id) {
  if (!confirm('Force-merge task ' + id + '? This bypasses all critic and test gates.')) return;
  try {
    await api('/tasks/' + id + '/force-merge', { method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({reason: 'Operator force-merge from dashboard'}) });
    showStatus('Task force-merged');
    loadAll();
  } catch(e) { showStatus('Force-merge failed: ' + e.message, true); }
}

async function cancelTask(id) {
  try {
    await api('/tasks/' + id + '/cancel', { method: 'POST' });
    showStatus('Task cancelled');
    loadAll();
  } catch(e) { showStatus('Cancel failed: ' + e.message, true); }
}

async function retryTask(id) {
  try {
    await api('/tasks/' + id + '/retry', { method: 'POST' });
    showStatus('Task re-queued');
    loadAll();
  } catch(e) { showStatus('Retry failed: ' + e.message, true); }
}

async function loadAll() {
  await Promise.all([loadMetrics(), loadTasks()]);
  document.getElementById('last-updated').textContent = 'Updated ' + new Date().toLocaleTimeString();
}

loadAll();
setInterval(loadAll, 10000);
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def dashboard_ui() -> str:
    return _DASHBOARD_HTML


# ── API endpoints (proxied from main API) ─────────────────────────────────────


@app.post("/api/tasks/{task_id}/force-merge")
async def force_merge(task_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Operator override — merge a task bypassing all gates."""
    orc = _get_orc()
    task = await orc.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    from aiswarm.schemas.task import TaskState
    from aiswarm.core.state_machine import StateMachine

    reason = (body or {}).get("reason", "Operator force-merge")
    task.boss_override = reason
    from datetime import datetime, timezone

    task.merged = True
    task.merged_at = datetime.now(timezone.utc)
    task.merged_by = "operator_dashboard"
    task.completed_at = datetime.now(timezone.utc)
    StateMachine.transition(task, TaskState.MERGED, reason=reason, agent="operator_dashboard")

    import structlog

    structlog.get_logger(__name__).warning(
        "dashboard.force_merge",
        task_id=task_id,
        reason=reason,
    )
    return {"status": "force_merged", "task_id": task_id, "reason": reason}
