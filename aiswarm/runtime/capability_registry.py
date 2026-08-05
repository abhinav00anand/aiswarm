"""
Capability Registry Subsystem — Dynamic Tool, Worker, and Sub-Agent Management.

Provides capability lookup, registration, and safe execution through sandboxing and governance policies.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from aiswarm.schemas.capabilities import CapabilityHandle, CapabilityRequest
from aiswarm.security.sandbox import ExecutionSandbox

from aiswarm.utils.compat_log import get_logger

logger = get_logger(__name__)


class CapabilityRegistry:
    """Registry maintaining available tools, CLI adapters, workers, and helper agents."""

    def __init__(self, sandbox: ExecutionSandbox | None = None) -> None:
        self.sandbox = sandbox or ExecutionSandbox()
        self._handlers: dict[str, Callable[[dict[str, Any]], Any]] = {}
        self._register_default_capabilities()

    def _register_default_capabilities(self) -> None:
        """Register built-in CLI tool and code execution capabilities."""
        self.register("pytest", self._handle_pytest)
        self.register("ruff", self._handle_ruff)
        self.register("git", self._handle_git)
        self.register("python_exec", self._handle_python_exec)

    def register(self, name: str, handler: Callable[[dict[str, Any]], Any]) -> None:
        """Register a new capability handler."""
        self._handlers[name.lower()] = handler
        logger.info("capability_registry.registered", name=name)

    async def invoke(self, request: CapabilityRequest) -> CapabilityHandle:
        """Invoke a capability by request and return a structured CapabilityHandle."""
        cap_name = request.capability_name.lower()
        if cap_name not in self._handlers:
            logger.error("capability_registry.unknown_capability", name=cap_name)
            return CapabilityHandle(
                request_id=request.request_id,
                capability_name=request.capability_name,
                status="FAILED",
                output=f"Capability '{request.capability_name}' is not registered in capability registry.",
            )

        try:
            logger.info("capability_registry.invoke_start", name=cap_name, request_id=request.request_id)
            handler = self._handlers[cap_name]

            # Execute handler (supports both async and sync handlers)
            if asyncio.iscoroutinefunction(handler):
                result = await handler(request.parameters)
            else:
                result = handler(request.parameters)

            status = "SUCCESS"
            exec_time = 0.0
            if isinstance(result, dict):
                exec_time = result.get("duration_seconds", 0.0)
                if "returncode" in result and result["returncode"] != 0:
                    status = "FAILED"
                elif "exit_code" in result and result["exit_code"] != 0:
                    status = "FAILED"

            return CapabilityHandle(
                request_id=request.request_id,
                capability_name=request.capability_name,
                status=status,
                output=result,
                execution_time_seconds=exec_time,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("capability_registry.invoke_error", name=cap_name, error=str(exc))
            return CapabilityHandle(
                request_id=request.request_id,
                capability_name=request.capability_name,
                status="FAILED",
                output=str(exc),
            )


    # Built-in capability handlers running via ExecutionSandbox
    async def _handle_pytest(self, params: dict[str, Any]) -> dict[str, Any]:
        test_path = params.get("path", ".")
        return await self.sandbox.execute_sandboxed_command(["pytest", str(test_path)])

    async def _handle_ruff(self, params: dict[str, Any]) -> dict[str, Any]:
        target_path = params.get("path", ".")
        return await self.sandbox.execute_sandboxed_command(["ruff", "check", str(target_path)])

    async def _handle_git(self, params: dict[str, Any]) -> dict[str, Any]:
        subcmd = params.get("subcommand", "status")
        return await self.sandbox.execute_sandboxed_command(["git", subcmd])

    async def _handle_python_exec(self, params: dict[str, Any]) -> dict[str, Any]:
        script_path = params.get("script", "main.py")
        return await self.sandbox.execute_sandboxed_command(["python", str(script_path)])
