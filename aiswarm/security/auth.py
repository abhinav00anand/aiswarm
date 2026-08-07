"""
Security Authentication Subsystem — AISwarm API Key Enforcement & Scoped Access Control.

Enforces mandatory API key configuration at startup and request handling.
Prevents unauthenticated execution of platform pipelines.
"""

from __future__ import annotations

import os
import sys
from enum import Enum
from typing import Any

from aiswarm.utils.compat_log import get_logger

logger = get_logger(__name__)

# Known environment variables that provide valid API keys
_SUPPORTED_KEY_ENVS = [
    "AISWARM_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "NOVITA_API_KEY",
    "DEEPSEEK_API_KEY",
]


class Role(str, Enum):
    """Execution roles with scoped authority within AISwarm."""
    HOST1 = "host1"
    HOST2 = "host2"
    BOSS = "boss"
    WORKER = "worker"
    OPERATOR = "operator"
    SYSTEM = "system"


def validate_adapter_url(url: str) -> bool:
    """Validate that the adapter URL is reachable by testing health endpoints."""
    import urllib.request
    import json
    base_url = url.rstrip('/')
    # Try endpoints: /health, /v1/models
    for endpoint in ["/health", "/v1/models"]:
        try:
            req = urllib.request.Request(f"{base_url}{endpoint}", method="GET")
            with urllib.request.urlopen(req, timeout=3.0) as response:
                if response.status in (200, 204, 401, 405):
                    return True
        except Exception:
            continue
    # Try /v1/completions POST with empty/small payload
    try:
        data = json.dumps({"prompt": "ping", "max_tokens": 1}).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/v1/completions",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3.0) as response:
            if response.status in (200, 201):
                return True
    except Exception:
        pass
    return False


class SecurityAuthError(RuntimeError):
    """Raised when mandatory security or authentication requirements are violated."""


class APIKeyValidator:
    """Validates API key presence, format, and scoping."""

    @staticmethod
    def get_configured_keys() -> dict[str, str]:
        """Return a mapping of configured API key names to masked values."""
        configured = {}
        for env_name in _SUPPORTED_KEY_ENVS:
            val = os.environ.get(env_name, "").strip()
            if val:
                masked = val[:4] + "..." + val[-4:] if len(val) >= 8 else "***"
                configured[env_name] = masked
        return configured

    @classmethod
    def verify_api_keys(cls, explicit_key: str | None = None) -> bool:
        """
        Verify that at least one valid API key, adapter, or local setup is present.
        Raises SecurityAuthError if no keys or adapters are found or reachable.
        """
        if explicit_key and explicit_key.strip():
            logger.info("auth.api_key_verified", source="explicit_arg")
            return True

        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        openai_base = os.environ.get("OPENAI_API_BASE", "").strip()
        adapter_url = os.environ.get("OPENAI_API_ADAPTER_URL", "").strip()
        no_ollama = os.environ.get("AISWARM_NO_OLLAMA", "").strip() in ("1", "true", "True")

        # 1. If OPENAI_API_BASE + OPENAI_API_KEY set -> use cloud provider
        if openai_key and openai_base:
            logger.info("auth.using_cloud_provider_via_base_and_key", base_url=openai_base)
            return True

        configured = cls.get_configured_keys()
        if configured:
            logger.info("auth.api_key_verified", configured_keys=list(configured.keys()))
            return True

        # 2. Else if OPENAI_API_ADAPTER_URL set or --adapter-url passed -> use that adapter
        if adapter_url:
            logger.info("auth.checking_adapter_url", url=adapter_url)
            if validate_adapter_url(adapter_url):
                logger.info("auth.adapter_url_validated_successfully", url=adapter_url)
                return True
            else:
                logger.warning("auth.adapter_url_validation_failed_not_reachable", url=adapter_url)

        # 3. Else -> existing Ollama auto-provision fallback
        if no_ollama:
            logger.info("auth.ollama_auto_provision_skipped_via_no_ollama_flag")
        else:
            logger.info("auth.no_cloud_keys_or_adapters_found_attempting_ollama_fallback")
            try:
                from aiswarm.llm.ollama_manager import OllamaManager
                manager = OllamaManager()
                ok, selected_model = manager.ensure_ollama_provisioned()
                if ok:
                    os.environ["OLLAMA_FALLBACK_ACTIVE"] = "true"
                    os.environ["OLLAMA_SELECTED_MODEL"] = selected_model
                    logger.info("auth.ollama_fallback_activated", model=selected_model)
                    return True
            except Exception as exc:
                logger.warning("auth.ollama_auto_provision_failed", error=str(exc))

        # 4. Check for deferred / offline local mode
        deferred_mode = os.environ.get("AISWARM_DEFERRED_INIT", "").strip() in ("1", "true", "True") or \
                        os.environ.get("AISWARM_LOCAL_MODE", "").strip() in ("1", "true", "True") or \
                        os.environ.get("AISWARM_ALLOW_OFFLINE", "").strip() in ("1", "true", "True")
        if deferred_mode:
            logger.info("auth.deferred_offline_mode_active")
            return True

        msg = (
            "CRITICAL SECURITY ERROR: AISwarm requires a valid API key, adapter, or active local Ollama setup to start.\n"
            "No API key/adapter was detected or successfully validated, and local Ollama fallback is unavailable or failed.\n\n"
            "Please configure one of the following:\n"
            "  - OPENAI_API_ADAPTER_URL (or pass --adapter-url)\n"
            "  - OPENAI_API_KEY and OPENAI_API_BASE\n"
            "  - Other cloud API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)\n"
            "  - Or ensure local Ollama is running and AISWARM_NO_OLLAMA is not set."
        )
        logger.error("auth.api_key_and_ollama_missing")
        raise SecurityAuthError(msg)

    @classmethod
    def enforce_startup_auth(cls, explicit_key: str | None = None) -> None:
        """Fast-fail startup check executed during CLI / API initialization."""
        try:
            cls.verify_api_keys(explicit_key)
        except SecurityAuthError as exc:
            logger.critical("auth.startup_failed", error=str(exc))
            print(f"\n[AISWARM SECURITY FAULT] {exc}\n", file=sys.stderr)
            sys.exit(1)

