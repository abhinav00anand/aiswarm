"""
Unit tests for config file retrieval in ContextSelectorAgent and RAGRetriever.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from aiswarm.agents.context_selector.agent import ContextSelectorAgent
from aiswarm.rag.retriever import RAGRetriever
from aiswarm.rag.repository_indexer import RepositoryIndexer


def test_context_selector_lists_config_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "config.yaml").write_text("setting: 1", encoding="utf-8")
        (root / "settings.json").write_text("{}", encoding="utf-8")
        (root / "main.py").write_text("print(1)", encoding="utf-8")

        agent = ContextSelectorAgent(router=None, model="dummy", repo_root=str(root))
        files = agent._list_available_files()

        assert "config.yaml" in files
        assert "settings.json" in files
        assert "main.py" in files


def test_rag_fallback_includes_config_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "production.yaml").write_text("database_url: postgres://localhost", encoding="utf-8")

        retriever = RAGRetriever(repo_root=str(root))
        results = retriever.retrieve("database_url")

        assert len(results) >= 1
        assert any(r["path"] == "production.yaml" for r in results)
