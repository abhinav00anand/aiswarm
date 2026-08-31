"""Unit tests for all 8 Critic Agents — validates JSON parsing and decision logic."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
import pytest

from aiswarm.schemas.task import Task, TaskClass, ReviewDecision


def _make_task(code: str = "") -> Task:
    task = Task(
        title="Test task",
        description="desc",
        target_language="python",
        task_class=TaskClass.FEATURE,
    )
    task.generated_code = code
    return task


def _make_llm_response(decision: str = "APPROVE", score: int = 85) -> MagicMock:
    resp = MagicMock()
    resp.content = json.dumps(
        {
            "decision": decision,
            "production_ready": decision == "APPROVE",
            "fatal_flaw": None if decision == "APPROVE" else "Some flaw",
            "flaw_category": None if decision == "APPROVE" else "SECURITY",
            "flaw_explanation": "",
            "mandatory_fix": "" if decision == "APPROVE" else "Fix it",
            "suggestions": ["Suggestion A"],
            "overall_score": score,
        }
    )
    resp.model = "mock-model"
    resp.latency_ms = 100.0
    resp.total_tokens = 500
    return resp


# ── Architecture Critic ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_architecture_critic_approve():
    from aiswarm.agents.critics.architecture.agent import ArchitectureCritic

    critic = ArchitectureCritic.__new__(ArchitectureCritic)
    critic.call_llm = AsyncMock(return_value=_make_llm_response("APPROVE"))
    critic.build_ledger = MagicMock(return_value={})
    task = _make_task("def foo(): pass")
    review = await critic.run(task)
    assert review.decision == ReviewDecision.APPROVE
    assert review.production_ready is True
    assert review.score == 85


@pytest.mark.asyncio
async def test_architecture_critic_reject_empty_code():
    from aiswarm.agents.critics.architecture.agent import ArchitectureCritic

    critic = ArchitectureCritic.__new__(ArchitectureCritic)
    task = _make_task("")
    review = await critic.run(task)
    assert review.decision == ReviewDecision.REJECT
    assert review.fatal_flaw is not None


# ── Security Critic ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_security_critic_reject():
    from aiswarm.agents.critics.security.agent import SecurityCritic

    critic = SecurityCritic.__new__(SecurityCritic)
    critic.call_llm = AsyncMock(return_value=_make_llm_response("REJECT", score=20))
    critic.build_ledger = MagicMock(return_value={})
    task = _make_task("import os; os.system('rm -rf /')")
    review = await critic.run(task)
    assert review.decision == ReviewDecision.REJECT
    assert review.production_ready is False


# ── Testing Critic ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_testing_critic_approve():
    from aiswarm.agents.critics.testing.agent import TestingCritic

    critic = TestingCritic.__new__(TestingCritic)
    critic.call_llm = AsyncMock(return_value=_make_llm_response("APPROVE", 90))
    critic.build_ledger = MagicMock(return_value={})
    task = _make_task("def add(a, b): return a + b")
    review = await critic.run(task)
    assert review.decision == ReviewDecision.APPROVE
    assert review.critic_role == "testing"


@pytest.mark.asyncio
async def test_testing_critic_empty_code():
    from aiswarm.agents.critics.testing.agent import TestingCritic

    critic = TestingCritic.__new__(TestingCritic)
    task = _make_task("")
    review = await critic.run(task)
    assert review.decision == ReviewDecision.REJECT


# ── Reliability Critic ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reliability_critic_approve():
    from aiswarm.agents.critics.reliability.agent import ReliabilityCritic

    critic = ReliabilityCritic.__new__(ReliabilityCritic)
    critic.call_llm = AsyncMock(return_value=_make_llm_response("APPROVE", 88))
    critic.build_ledger = MagicMock(return_value={})
    task = _make_task("async def fetch(): pass")
    review = await critic.run(task)
    assert review.critic_role == "reliability"
    assert review.decision == ReviewDecision.APPROVE


# ── Maintainability Critic ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_maintainability_critic_approve():
    from aiswarm.agents.critics.maintainability.agent import MaintainabilityCritic

    critic = MaintainabilityCritic.__new__(MaintainabilityCritic)
    critic.call_llm = AsyncMock(return_value=_make_llm_response("APPROVE", 78))
    critic.build_ledger = MagicMock(return_value={})
    task = _make_task("class Foo: pass")
    review = await critic.run(task)
    assert review.critic_role == "maintainability"
    assert review.production_ready is True


# ── Documentation Critic ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_documentation_critic_approve():
    from aiswarm.agents.critics.documentation.agent import DocumentationCritic

    critic = DocumentationCritic.__new__(DocumentationCritic)
    critic.call_llm = AsyncMock(return_value=_make_llm_response("APPROVE", 92))
    critic.build_ledger = MagicMock(return_value={})
    task = _make_task('"""Module docstring."""\ndef foo(): pass')
    review = await critic.run(task)
    assert review.critic_role == "documentation"
    assert review.score == 92


# ── Style Critic ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_style_critic_reject():
    from aiswarm.agents.critics.style.agent import StyleCritic

    critic = StyleCritic.__new__(StyleCritic)
    critic.call_llm = AsyncMock(return_value=_make_llm_response("REJECT", 30))
    critic.build_ledger = MagicMock(return_value={})
    task = _make_task("from x import *; X=1")
    review = await critic.run(task)
    assert review.critic_role == "style"
    assert review.decision == ReviewDecision.REJECT


# ── Performance Critic ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_performance_critic_approve():
    from aiswarm.agents.critics.performance.agent import PerformanceCritic

    critic = PerformanceCritic.__new__(PerformanceCritic)
    critic.call_llm = AsyncMock(return_value=_make_llm_response("APPROVE", 80))
    critic.build_ledger = MagicMock(return_value={})
    task = _make_task("def sort(arr): return sorted(arr)")
    review = await critic.run(task)
    assert review.critic_role == "performance"
    assert review.decision == ReviewDecision.APPROVE


# ── Parse resilience ──────────────────────────────────────────────────────────


def test_parse_json_with_markdown_fences():
    from aiswarm.agents.critics.testing.agent import TestingCritic

    critic = TestingCritic.__new__(TestingCritic)
    resp = MagicMock()
    resp.model = "m"
    resp.latency_ms = 0
    resp.total_tokens = 0
    payload = {
        "decision": "APPROVE",
        "production_ready": True,
        "overall_score": 77,
        "fatal_flaw": None,
        "flaw_category": None,
        "flaw_explanation": "",
        "mandatory_fix": "",
        "suggestions": [],
    }
    resp.content = f"```json\n{json.dumps(payload)}\n```"
    review = critic._parse_review(resp.content, resp)
    assert review.decision == ReviewDecision.APPROVE
    assert review.score == 77


def test_parse_malformed_json_returns_reject():
    from aiswarm.agents.critics.style.agent import StyleCritic

    critic = StyleCritic.__new__(StyleCritic)
    resp = MagicMock()
    resp.model = "m"
    resp.latency_ms = 0
    resp.total_tokens = 0
    resp.content = "This is not JSON at all."
    review = critic._parse_review(resp.content, resp)
    assert review.decision == ReviewDecision.REJECT
