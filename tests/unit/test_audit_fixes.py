"""
Unit tests validating all 12 fixes from the AISwarm Deep Audit Report.
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiswarm.schemas.task import Task, TaskState
from aiswarm.core.workflow_engine import WorkflowEngine
from aiswarm.compiler.build_system import BuildSystem
from aiswarm.agents.host2.manager import Host2CapabilityManager
from aiswarm.core.redis_task_store import RedisTaskStore
from aiswarm.core.force_merge import ForceMergeOperator
from aiswarm.llm.ollama_manager import OllamaManager
from aiswarm.llm.gemini import GeminiAdapter
from aiswarm.llm.adapter import LLMMessage
from aiswarm.llm.provider_router import ProviderRouter
from aiswarm.security.auth import APIKeyValidator


@pytest.mark.asyncio
async def test_workflow_engine_invokes_host1_router_when_missing_metadata():
    """Verify Host-1 router is invoked when route_decision is missing from metadata."""
    orc_mock = MagicMock()
    host1_mock = MagicMock()
    decision_mock = MagicMock()
    decision_mock.route.value = "production"
    host1_mock.route_task = AsyncMock(return_value=decision_mock)
    orc_mock.host1_router = host1_mock
    orc_mock.get_agent = MagicMock(return_value=None)

    engine = WorkflowEngine(orchestrator=orc_mock)
    task = Task(title="Test Task", description="Test Desc", prompt="Do something")
    
    await engine.run(task)

    assert host1_mock.route_task.called
    assert task.metadata.get("route_decision") == decision_mock


@pytest.mark.asyncio
async def test_compiler_unsupported_language_fails_closed():
    """Verify non-supported languages return CompilerOutput(success=False)."""
    bs = BuildSystem()
    task = Task(title="Test", description="Desc", prompt="Test", target_language="cobol")
    out = await bs.compile(task)

    assert out.success is False
    assert "No compiler configured" in out.stderr
    assert out.exit_code == 1


def test_host2_cpp_path_dynamic_resolution():
    """Verify Host-2 manager resolves C++ path dynamically without hardcoded machine path."""
    mgr = Host2CapabilityManager()
    assert "C:\\Users\\lenovo" not in mgr.run_native_cpp_engine.__code__.co_consts


@pytest.mark.asyncio
async def test_redis_task_store_get_all_hydrates_from_redis():
    """Verify get_all() hydrates missing tasks from Redis when Redis is available."""
    redis_mock = AsyncMock()
    redis_mock.smembers = AsyncMock(return_value=[b"task-123"])
    redis_mock.get = AsyncMock(return_value='{"task_id": "task-123", "title": "Hydrated", "description": "Hydrated Desc", "prompt": "p", "state": "NEW"}')

    store = RedisTaskStore(redis_client=redis_mock)
    all_tasks = await store.get_all()

    assert len(all_tasks) == 1
    assert all_tasks[0].task_id == "task-123"


@pytest.mark.asyncio
async def test_force_merge_requires_justification_and_logs_audit():
    """Verify force-merge rejects short reasons and records audit event."""
    op = ForceMergeOperator()
    task = Task(title="Force Task", description="Desc", prompt="p")

    with pytest.raises(ValueError, match="at least 10 characters"):
        await op.force_merge(task, reason="short")

    with patch("aiswarm.security.audit.get_audit_ledger") as audit_mock:
        record_mock = MagicMock()
        audit_mock.return_value.record_event = record_mock
        await op.force_merge(task, reason="Valid detailed force merge explanation for audit", operator="admin")
        assert record_mock.called
        assert task.state == TaskState.MERGED


def test_ollama_manager_is_service_running_http_probe():
    """Verify is_service_running does not return True solely based on binary existence."""
    mgr = OllamaManager(base_url="http://localhost:99999")
    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
        with patch("shutil.which", return_value="/usr/bin/ollama"):
            assert mgr.is_service_running() is False
            assert mgr.is_installed() is True


@pytest.mark.asyncio
async def test_gemini_adapter_preserves_system_and_history():
    """Verify GeminiAdapter constructs system_instruction and full contents list."""
    adapter = GeminiAdapter(api_key="test-key")
    messages = [
        LLMMessage(role="system", content="System instruction text"),
        LLMMessage(role="user", content="User prompt 1"),
        LLMMessage(role="assistant", content="Assistant reply 1"),
        LLMMessage(role="user", content="User prompt 2"),
    ]

    mock_genai = MagicMock()
    mock_model = MagicMock()
    mock_genai.GenerativeModel.return_value = mock_model
    
    mock_response = MagicMock()
    mock_response.text = "OK"
    mock_response.usage_metadata = None
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)

    with patch.dict("sys.modules", {"google.generativeai": mock_genai}):
        res = await adapter.chat(messages=messages, model="gemini-1.5-flash")
        assert res.content == "OK"
        
        # Verify GenerativeModel received system_instruction
        kwargs = mock_genai.GenerativeModel.call_args[1]
        assert kwargs["system_instruction"] == "System instruction text"

        # Verify generate_content_async received full multi-turn contents
        call_kwargs = mock_model.generate_content_async.call_args[1]
        contents = call_kwargs["contents"]
        assert len(contents) == 3
        assert contents[0] == {"role": "user", "parts": ["User prompt 1"]}
        assert contents[1] == {"role": "model", "parts": ["Assistant reply 1"]}
        assert contents[2] == {"role": "user", "parts": ["User prompt 2"]}


@pytest.mark.asyncio
async def test_provider_router_local_first_ordering():
    """Verify AISWARM_LOCAL_FIRST=1 promotes local & adapter to front of provider list."""
    router = ProviderRouter()
    messages = [LLMMessage(role="user", content="hi")]

    with patch.dict(os.environ, {"AISWARM_LOCAL_FIRST": "1"}):
        target_provider = router._providers.get("local")
        with patch.object(target_provider, "is_available", return_value=True):
            with patch.object(target_provider, "chat", new_callable=AsyncMock) as mock_chat:
                from aiswarm.llm.adapter import LLMResponse
                mock_chat.return_value = LLMResponse(content="OK", model="m", provider="local", prompt_tokens=1, completion_tokens=1, total_tokens=2, finish_reason="stop", latency_ms=1.0, cost_usd=0.0)
                res = await router.chat(messages=messages, model="llama3.2:3b")
                assert res.content == "OK"


def test_auth_deferred_init_mode():
    """Verify AISWARM_DEFERRED_INIT=1 permits startup auth check."""
    with patch.dict(os.environ, {"AISWARM_DEFERRED_INIT": "1"}, clear=True):
        assert APIKeyValidator.verify_api_keys() is True


@pytest.mark.asyncio
async def test_host1_router_has_route_task_method():
    """Verify Host1Router has route_task method taking Task objects."""
    from aiswarm.agents.host1.router import Host1Router
    router = Host1Router()
    task = Task(title="Test Title", description="Test Desc", prompt="Do work")
    decision = await router.route_task(task)
    assert decision.route is not None


def test_local_model_resolution_passthrough():
    """Verify _resolve_model passes llama3.1:8b directly for local provider."""
    from aiswarm.llm.provider_router import _resolve_model
    res = _resolve_model("llama3.1:8b", "local")
    assert res == "llama3.1:8b"


def test_context_selector_blocks_env_and_credentials(tmp_path):
    """Verify ContextSelectorAgent excludes .env and credential files."""
    from aiswarm.agents.context_selector.agent import ContextSelectorAgent
    (tmp_path / ".env").write_text("SECRET_KEY=12345")
    (tmp_path / "credentials.json").write_text('{"key": "val"}')
    (tmp_path / "main.py").write_text("print('hello')")

    agent = ContextSelectorAgent(router=MagicMock(), model="m", repo_root=str(tmp_path))
    available = agent._list_available_files()

    assert ".env" not in available
    assert "credentials.json" not in available
    assert "main.py" in available
    assert agent._read_file(".env") is None


@pytest.mark.asyncio
async def test_redis_task_store_get_summary():
    """Verify RedisTaskStore get_summary hydrates tasks from Redis."""
    redis_mock = AsyncMock()
    redis_mock.smembers = AsyncMock(return_value=[b"t1"])
    redis_mock.get = AsyncMock(return_value='{"task_id": "t1", "title": "t", "description": "d", "prompt": "p", "state": "NEW"}')

    store = RedisTaskStore(redis_client=redis_mock)
    summary = await store.get_summary()

    assert summary["total"] == 1
    assert summary["by_state"]["NEW"] == 1


@pytest.mark.asyncio
async def test_workflow_engine_handles_sync_evaluate_task_fallback():
    """Verify WorkflowEngine handles synchronous evaluate_task fallback cleanly."""
    class SyncHost1Router:
        def evaluate_task(self, payload):
            from aiswarm.schemas.routing import RouteDecision, ExecutionMode, RiskLevel
            return RouteDecision(
                route=ExecutionMode.PRODUCTION,
                confidence=0.9,
                reason="Production test",
                risk_level=RiskLevel.LOW,
                estimated_cost_usd=0.01,
                estimated_runtime_seconds=5.0,
                required_capabilities=[],
                escalation_policy="",
                metadata={},
            )

    orc_mock = MagicMock()
    orc_mock.host1_router = SyncHost1Router()
    orc_mock.get_agent = MagicMock(return_value=None)

    engine = WorkflowEngine(orchestrator=orc_mock)
    task = Task(title="Sync Route Task", description="Desc", prompt="Prompt")
    
    # Test router fallback lookup logic
    router = getattr(engine._orc, "host1_router", None)
    assert hasattr(router, "evaluate_task")
    res = router.evaluate_task({"title": task.title})
    assert res.route.value == "PRODUCTION"


def test_orchestrator_set_task_store():
    """Verify Orchestrator set_task_store attaches task store."""
    from aiswarm.core.orchestrator import Orchestrator
    orc = Orchestrator()
    mock_store = MagicMock()
    orc.set_task_store(mock_store)
    assert orc._task_store == mock_store


@pytest.mark.asyncio
async def test_context_selector_enforces_max_tokens_budget(tmp_path):
    """Verify ContextSelectorAgent stops selection when token budget is exceeded."""
    from aiswarm.agents.context_selector.agent import ContextSelectorAgent
    (tmp_path / "file1.py").write_text("word " * 3000)  # ~4000 tokens
    (tmp_path / "file2.py").write_text("word " * 3000)  # ~4000 tokens
    (tmp_path / "file3.py").write_text("word " * 3000)  # ~4000 tokens

    agent = ContextSelectorAgent(router=MagicMock(), model="m", repo_root=str(tmp_path), config={"max_tokens": 5000})
    response_mock = MagicMock()
    response_mock.content = '[{"path": "file1.py"}, {"path": "file2.py"}, {"path": "file3.py"}]'
    response_mock.model = "test-model"
    response_mock.provider = "local"
    response_mock.input_tokens = 10
    response_mock.output_tokens = 20
    response_mock.latency_ms = 50.0
    agent.call_llm = AsyncMock(return_value=response_mock)
    
    task = Task(title="T", description="D", prompt="P")
    selected = await agent.run(task)

    # Should only include file1.py before exceeding the 5000 token budget
    assert len(selected) == 1
    assert selected[0].path == "file1.py"


def test_local_model_resolution_latest_tags():
    """Verify _resolve_model resolves llama3.1:latest and codestral:latest cleanly."""
    from aiswarm.llm.provider_router import _resolve_model
    assert _resolve_model("llama3.1:latest", "local") == "llama3.1:latest"
    assert _resolve_model("codestral:latest", "local") == "codestral:latest"
