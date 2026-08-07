"""
Zymis — Lightweight multi-agent orchestration framework.

Hierarchy:
  Boss → Manager → Task Planner → Context Selector (RAG)
       → Coder → Pre-Check → Critics → Worker
       → Compiler → Tests → Benchmark → Merge Controller

Multiple LLM providers: Novita, OpenAI, Anthropic, Gemini, DeepSeek, Bedrock, Local.
"""

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "AISwarm Contributors"
__license__ = "MIT"

# Re-export top-level entry points for convenience
from aiswarm.core.orchestrator import Orchestrator
from aiswarm.schemas.task import Task, TaskState

__all__ = [
    "Orchestrator",
    "Task",
    "TaskState",
    "__version__",
]
