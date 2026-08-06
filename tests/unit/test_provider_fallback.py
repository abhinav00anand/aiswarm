"""
Unit tests for provider router model ID fallback resolution.
"""

from __future__ import annotations

import pytest
from aiswarm.llm.provider_router import _resolve_model


def test_novita_model_passthrough():
    assert _resolve_model("meta-llama/llama-3.1-70b-instruct", "novita") == "meta-llama/llama-3.1-70b-instruct"
    assert _resolve_model("mistralai/mistral-nemo", "novita") == "mistralai/mistral-nemo"


def test_explicit_mapping_resolution():
    assert _resolve_model("meta-llama/llama-3.1-405b-instruct", "openai") == "gpt-4o"
    assert _resolve_model("meta-llama/llama-3.1-70b-instruct", "anthropic") == "claude-3-5-haiku-20241022"
    assert _resolve_model("meta-llama/llama-3.1-8b-instruct", "local") == "llama3"


def test_native_model_passthrough():
    assert _resolve_model("gpt-4o", "openai") == "gpt-4o"
    assert _resolve_model("claude-3-5-sonnet-20241022", "anthropic") == "claude-3-5-sonnet-20241022"
    assert _resolve_model("gemini-2.0-flash", "gemini") == "gemini-2.0-flash"


def test_fallback_unmapped_model_defaults_to_valid_provider_native_model():
    # Unsupported / unmapped model ID falling back to OpenAI or Anthropic must NOT return the invalid ID
    resolved_openai = _resolve_model("unmapped-vendor/custom-model", "openai")
    assert resolved_openai == "gpt-4o"

    resolved_anthropic = _resolve_model("unmapped-vendor/custom-model", "anthropic")
    assert resolved_anthropic == "claude-3-5-sonnet-20241022"
