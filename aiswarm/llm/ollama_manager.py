"""
Ollama Auto-Provisioning & Dynamic Model Management Engine.

Provides automatic environment discovery, disk space analysis, optimal model selection,
local server liveness checks, dynamic model pulling, and Ollama service initialization.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Any

from aiswarm.utils.compat_log import get_logger

logger = get_logger(__name__)

# Model selection threshold constants (in GB)
LARGE_MODEL_DISK_THRESHOLD_GB = 16.0
MEDIUM_MODEL_DISK_THRESHOLD_GB = 8.0

# Selected default models by disk tier
MODEL_LARGE = "llama3.1:8b"
MODEL_MEDIUM = "llama3.2:3b"
MODEL_SMALL = "llama3.2:1b"


class OllamaManager:
    """
    Manages local Ollama installation, service health, disk space evaluation,
    and automatic model selection/pulling.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("LOCAL_MODEL_URL", "http://localhost:11434")).rstrip("/")
        if self.base_url.endswith("/v1"):
            self.base_url = self.base_url[:-3]

    @staticmethod
    def get_free_disk_gb(path: str = ".") -> float:
        """Calculate available free disk space in Gigabytes for the specified path."""
        try:
            total, used, free = shutil.disk_usage(path)
            return round(free / (1024 ** 3), 2)
        except Exception as exc:
            logger.warning("ollama_manager.disk_check_failed", error=str(exc))
            return 10.0  # Safe default fallback

    @classmethod
    def select_model_for_space(cls, free_gb: float) -> str:
        """
        Select the optimal Ollama model based on free disk space heuristics.
        - >= 16 GB: llama3.1:8b
        - 8 GB - 16 GB: llama3.2:3b
        - < 8 GB: llama3.2:1b
        """
        if free_gb >= LARGE_MODEL_DISK_THRESHOLD_GB:
            selected = MODEL_LARGE
        elif free_gb >= MEDIUM_MODEL_DISK_THRESHOLD_GB:
            selected = MODEL_MEDIUM
        else:
            selected = MODEL_SMALL

        logger.info("ollama_manager.model_selected", free_gb=free_gb, selected_model=selected)
        return selected

    def is_installed(self) -> bool:
        """Check if the ollama binary is installed in PATH."""
        return shutil.which("ollama") is not None

    def is_service_running(self) -> bool:
        """
        Check if the local Ollama or LM Studio HTTP server is responsive.
        Probes both /api/version (Ollama) and /v1/models (LM Studio / OpenAI compatible).
        """
        endpoints = [f"{self.base_url}/api/version", f"{self.base_url}/v1/models"]
        if self.base_url.endswith("/v1"):
            endpoints.append(f"{self.base_url}/models")

        for url in endpoints:
            req = urllib.request.Request(url, headers={"User-Agent": "Zymis-HealthCheck"})
            try:
                with urllib.request.urlopen(req, timeout=2) as res:
                    if res.status == 200:
                        logger.info("ollama_manager.service_detected", url=url)
                        return True
            except Exception:
                continue

        return False

    def start_ollama_service_if_needed(self) -> bool:
        """
        Attempt to start background Ollama server process if binary exists but service isn't up.
        """
        if self.is_service_running():
            return True

        if not self.is_installed():
            logger.warning("ollama_manager.binary_not_found")
            return False

        ollama_bin = shutil.which("ollama")
        try:
            logger.info("ollama_manager.starting_service", binary=ollama_bin)
            subprocess.Popen(
                [ollama_bin, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            # Short wait for server socket initialization
            import time
            for _ in range(5):
                time.sleep(0.5)
                if self.is_service_running():
                    return True
        except Exception as exc:
            logger.error("ollama_manager.service_start_error", error=str(exc))

        return self.is_service_running()

    def pull_model(self, model_name: str) -> bool:
        """
        Pull the requested model via Ollama REST API or fallback to `ollama pull` CLI.
        """
        logger.info("ollama_manager.pull_started", model=model_name)

        # Attempt REST API pull
        url = f"{self.base_url}/api/pull"
        payload = json.dumps({"name": model_name, "stream": False}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "Zymis-Puller"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                if res.status == 200:
                    logger.info("ollama_manager.pull_success_api", model=model_name)
                    return True
        except Exception as exc:
            logger.warning("ollama_manager.api_pull_failed", error=str(exc))

        # Fallback to CLI subprocess pull if ollama CLI is in PATH
        ollama_bin = shutil.which("ollama")
        if ollama_bin:
            try:
                result = subprocess.run(
                    [ollama_bin, "pull", model_name],
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                if result.returncode == 0:
                    logger.info("ollama_manager.pull_success_cli", model=model_name)
                    return True
                logger.error("ollama_manager.cli_pull_error", stderr=result.stderr)
            except Exception as exc:
                logger.error("ollama_manager.cli_pull_failed", error=str(exc))

        return False

    def ensure_ollama_provisioned(self, target_dir: str = ".") -> tuple[bool, str]:
        """
        Complete auto-provisioning workflow:
        1. Evaluate disk space and choose model.
        2. Ensure Ollama service is running.
        3. Pull model if required.
        Returns tuple of (success, selected_model_name).
        """
        free_gb = self.get_free_disk_gb(target_dir)
        selected_model = self.select_model_for_space(free_gb)

        if not self.start_ollama_service_if_needed():
            logger.warning("ollama_manager.provision_failed_no_service")
            return False, selected_model

        # Attempt pull (or verify model is ready)
        pull_ok = self.pull_model(selected_model)
        if pull_ok:
            logger.info("ollama_manager.provision_complete", model=selected_model)
            return True, selected_model

        # If pull of chosen model fails (e.g. disk constrained), try fallback small model
        if selected_model != MODEL_SMALL:
            logger.info("ollama_manager.trying_fallback_small_model", fallback=MODEL_SMALL)
            if self.pull_model(MODEL_SMALL):
                return True, MODEL_SMALL

        return False, selected_model
