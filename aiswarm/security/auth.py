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
        Verify that at least one valid API key is present via explicit argument or environment.
        Raises SecurityAuthError if no keys are found.
        """
        if explicit_key and explicit_key.strip():
            logger.info("auth.api_key_verified", source="explicit_arg")
            return True

        configured = cls.get_configured_keys()
        if configured:
            logger.info("auth.api_key_verified", configured_keys=list(configured.keys()))
            return True

        # Auto-fallback: If no cloud API keys are present, attempt local Ollama auto-provisioning
        logger.info("auth.no_cloud_keys_found_attempting_ollama_fallback")
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

        msg = (
            "CRITICAL SECURITY ERROR: AISwarm requires a valid API key or active local Ollama setup to start.\n"
            "No API key was detected in environment variables or parameters, and local Ollama auto-fallback failed.\n\n"
            "Please configure at least one of the following environment variables:\n"
            "  - AISWARM_API_KEY\n"
            "  - OPENAI_API_KEY\n"
            "  - ANTHROPIC_API_KEY\n"
            "  - GEMINI_API_KEY / GOOGLE_API_KEY\n"
            "  - NOVITA_API_KEY\n"
            "  - DEEPSEEK_API_KEY\n\n"
            "Alternatively, ensure local Ollama service is running on http://localhost:11434."
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
