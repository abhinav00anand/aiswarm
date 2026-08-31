"""Application startup."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import structlog

from aiswarm.llm.provider_router import ProviderRouter
from aiswarm.core.orchestrator import Orchestrator
from aiswarm.core.lifecycle import LifecycleManager
from aiswarm.core.cost_guard import CostGuard
from aiswarm.core.rate_limiter import ProviderRateLimiter
from aiswarm.core.redis_task_store import RedisTaskStore
from aiswarm.telemetry.logging import configure_logging
from aiswarm.telemetry.notifications import NotificationRouter

from aiswarm.security.auth import APIKeyValidator

logger = structlog.get_logger(__name__)

def _try_build_redis() -> Any:
    """Attempt to connect to Redis. Returns None if Redis is unavailable."""
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    import importlib
    try:
        redis_mod = importlib.import_module("redis.asyncio")
        client = redis_mod.from_url(url, decode_responses=False)
        logger.info("startup.redis_configured", url=url)
        return client
    except Exception as exc:  # noqa: BLE001
        logger.warning("startup.redis_unavailable", error=str(exc))
        return None

def build_orchestrator(
    config: dict[str, Any] | None = None,
    repo_root: str = ".",
    api_key: str | None = None,
) -> tuple[Orchestrator, LifecycleManager]:
    """
    Wire up the full AISwarm stack and return the Orchestrator + LifecycleManager.

    This is the single composition root — all dependencies are created here.
    Enforces mandatory API key verification before initializing services.
    """
    # Enforce API Key Verification
    APIKeyValidator.verify_api_keys(api_key)

    cfg = config or {}
    
    is_notebook_mode = (
        os.getenv("ZYMIS_NOTEBOOK_MODE") in ("1", "true", "True") or 
        cfg.get("profile") == "notebook"
    )
    adapter_url = os.getenv("OPENAI_API_ADAPTER_URL")

    if is_notebook_mode or adapter_url:
        os.environ["OMP_NUM_THREADS"] = "1"
        os.environ["MKL_NUM_THREADS"] = "1"

    agents_cfg = cfg.get("agents", {})

    configure_logging(
        level=os.getenv("LOG_LEVEL", "INFO"),
        log_format=os.getenv("LOG_FORMAT", "console"),
    )

    redis_client = _try_build_redis()

    cost_guard = CostGuard(
        max_daily_usd=float(os.getenv("MAX_DAILY_SPEND_USD", "100.0")),
        max_session_usd=float(os.getenv("MAX_SESSION_SPEND_USD", "10.0")),
        redis_client=redis_client,
    )
    rate_limiter = ProviderRateLimiter()
    task_store = RedisTaskStore(redis_client=redis_client)

    router = ProviderRouter(
        cost_guard=cost_guard,
        rate_limiter=rate_limiter,
    )
    logger.info(
        "startup.providers_available",
        providers=router.list_available(),
    )

    from aiswarm.agents.boss.agent import BossAgent
    from aiswarm.agents.manager.agent import ManagerAgent
    from aiswarm.agents.planner.agent import PlannerAgent
    from aiswarm.agents.context_selector.agent import ContextSelectorAgent
    from aiswarm.agents.coder.agent import CoderAgent
    from aiswarm.agents.precheck.agent import PreCheckAgent
    from aiswarm.agents.critics.architecture.agent import ArchitectureCritic
    from aiswarm.agents.critics.performance.agent import PerformanceCritic
    from aiswarm.agents.critics.security.agent import SecurityCritic
    from aiswarm.agents.critics.testing.agent import TestingCritic
    from aiswarm.agents.critics.reliability.agent import ReliabilityCritic
    from aiswarm.agents.critics.maintainability.agent import MaintainabilityCritic
    from aiswarm.agents.critics.documentation.agent import DocumentationCritic
    from aiswarm.agents.critics.style.agent import StyleCritic
    from aiswarm.compiler.python import PythonCompiler
    from aiswarm.testing.unit_runner import UnitRunner
    from aiswarm.testing.benchmark_runner import BenchmarkRunner

    def _model(role: str, default: str) -> str:
        if adapter_url:
            from aiswarm.llm.provider_router import get_adapter_model
            adv = get_adapter_model()
            if adv and adv != "adapter-default":
                return adv
            return "distilgpt2"
        if is_notebook_mode:
            return "distilgpt2"
        return agents_cfg.get(role, {}).get("model", default)

    def _pref(role: str) -> list[str]:
        pref = agents_cfg.get(role, {}).get("provider_preference", ["novita", "openai", "anthropic"])
        if os.getenv("ZEPHYR_API_KEY") or os.getenv("ZEPHYR_API_URL") or os.getenv("ZYMIS_PREFERRED_PROVIDER") == "zephyr":
            if "zephyr" not in pref:
                pref = ["zephyr"] + pref
        if adapter_url:
            if "adapter" not in pref:
                pref = ["adapter"] + pref
        return pref

    from aiswarm.agents.host2.manager import Host2CapabilityManager
    from aiswarm.runtime.capability_registry import CapabilityRegistry
    from aiswarm.security.governor import EngineeringGovernor

    capability_registry = CapabilityRegistry()
    governor = EngineeringGovernor(
        max_daily_budget_usd=float(os.getenv("MAX_DAILY_SPEND_USD", "100.0")),
        max_session_budget_usd=float(os.getenv("MAX_SESSION_SPEND_USD", "10.0")),
    )
    host2_manager = Host2CapabilityManager(
        capability_registry=capability_registry,
        governor=governor,
    )

    boss = BossAgent(
        router=router,
        model=_model("boss", "meta-llama/llama-3.1-70b-instruct"),
        provider_preference=_pref("boss"),
        repo_root=repo_root,
        host2_manager=host2_manager,
        temperature=0.1,
    )

    manager = ManagerAgent(
        router=router,
        model=_model("manager", "meta-llama/llama-3.1-70b-instruct"),
        provider_preference=_pref("manager"),
        temperature=0.2,
    )
    planner = PlannerAgent(
        router=router,
        model=_model("planner", "meta-llama/llama-3.1-70b-instruct"),
        provider_preference=_pref("planner"),
        temperature=0.1,
    )
    ctx_selector = ContextSelectorAgent(
        router=router,
        model=_model("context_selector", "meta-llama/llama-3.1-8b-instruct"),
        provider_preference=_pref("context_selector"),
        temperature=0.0,
        repo_root=repo_root,
    )
    coder = CoderAgent(
        router=router,
        model=_model("coder", "meta-llama/llama-3.1-405b-instruct"),
        provider_preference=_pref("coder"),
        temperature=0.15,
        max_tokens=8192,
    )
    precheck = PreCheckAgent(
        router=router,
        model=_model("precheck", "meta-llama/llama-3.1-8b-instruct"),
        provider_preference=_pref("precheck"),
        temperature=0.0,
        max_tokens=1024,
    )

    _critic_model = _model("critics", "meta-llama/llama-3.1-70b-instruct")
    _critic_pref = _pref("critics")

    arch_critic = ArchitectureCritic(
        router=router, model=_critic_model, provider_preference=_critic_pref, temperature=0.1,
    )
    perf_critic = PerformanceCritic(
        router=router, model=_critic_model, provider_preference=_critic_pref, temperature=0.1,
    )
    sec_critic = SecurityCritic(
        router=router, model=_critic_model, provider_preference=_critic_pref, temperature=0.0,
    )
    test_critic = TestingCritic(
        router=router, model=_critic_model, provider_preference=_critic_pref, temperature=0.1,
    )
    rely_critic = ReliabilityCritic(
        router=router, model=_critic_model, provider_preference=_critic_pref, temperature=0.1,
    )
    maint_critic = MaintainabilityCritic(
        router=router, model=_critic_model, provider_preference=_critic_pref, temperature=0.1,
    )
    doc_critic = DocumentationCritic(
        router=router, model=_critic_model, provider_preference=_critic_pref, temperature=0.1,
    )
    style_critic = StyleCritic(
        router=router, model=_critic_model, provider_preference=_critic_pref, temperature=0.0,
    )

    py_compiler = PythonCompiler(timeout=30.0)
    unit_runner = UnitRunner(repo_root=repo_root, timeout=120.0)
    bench_runner = BenchmarkRunner(repo_root=repo_root, timeout=120.0)

    # Wrap compiler/runners as agents
    class _CompilerAgent:
        role = "compiler"

        async def run(self, task: Any) -> None:
            await py_compiler.compile(task)

    class _TesterAgent:
        role = "tester"

        async def run(self, task: Any) -> None:
            await unit_runner.run(task)

    class _BenchmarkAgent:
        role = "benchmark"

        async def run(self, task: Any) -> None:
            await bench_runner.run(task)

    from aiswarm.agents.host1.router import Host1Router
    from aiswarm.core.self_healing import SelfHealingEngine
    from aiswarm.core.confidence_engine import ConfidenceEngine

    host1_router = Host1Router()
    # NOTE: governor, capability_registry and host2_manager are already created above.
    # Do NOT create a second instance here — reuse the configured shared objects.
    self_healing = SelfHealingEngine()
    confidence_engine = ConfidenceEngine()

    orchestrator = Orchestrator(
        config=cfg.get("orchestrator", {}),
        host1_router=host1_router,
        governor=governor,
    )

    # Inject Redis task store if orchestrator supports it
    if hasattr(orchestrator, "set_task_store"):
        orchestrator.set_task_store(task_store)

    from aiswarm.core.merge_controller import MergeController
    merge_controller = MergeController(repo_root=repo_root)

    orchestrator.register_agent("boss", boss)
    orchestrator.register_agent("manager", manager)
    orchestrator.register_agent("planner", planner)
    orchestrator.register_agent("context_selector", ctx_selector)
    orchestrator.register_agent("coder", coder)
    orchestrator.register_agent("precheck", precheck)
    orchestrator.register_agent("critic_architecture", arch_critic)
    orchestrator.register_agent("critic_performance", perf_critic)
    orchestrator.register_agent("critic_security", sec_critic)
    orchestrator.register_agent("critic_testing", test_critic)
    orchestrator.register_agent("critic_reliability", rely_critic)
    orchestrator.register_agent("critic_maintainability", maint_critic)
    orchestrator.register_agent("critic_documentation", doc_critic)
    orchestrator.register_agent("critic_style", style_critic)
    orchestrator.register_agent("compiler", _CompilerAgent())
    orchestrator.register_agent("tester", _TesterAgent())
    orchestrator.register_agent("host1", host1_router)
    orchestrator.register_agent("host1_router", host1_router)
    orchestrator.register_agent("host2", host2_manager)
    orchestrator.register_agent("governor", governor)
    orchestrator.register_agent("self_healing", self_healing)
    orchestrator.register_agent("confidence_engine", confidence_engine)
    orchestrator.register_agent("merge_controller", merge_controller)

    lifecycle = LifecycleManager()
    lifecycle.register("orchestrator", orchestrator, priority=10)
    lifecycle.register("notifications", NotificationRouter(), priority=90)

    logger.info("startup.complete", agents=list(orchestrator._agents.keys()))
    return orchestrator, lifecycle
