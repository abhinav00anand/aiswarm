"""Host."""

from __future__ import annotations

import asyncio
from typing import Any

from aiswarm.runtime.capability_registry import CapabilityRegistry
from aiswarm.schemas.capabilities import CapabilityHandle, CapabilityRequest, EscalationPacket
from aiswarm.security.governor import EngineeringGovernor

from aiswarm.utils.compat_log import get_logger

logger = get_logger(__name__)

class Host2CapabilityManager:
    """
    Host-2 Executive Manager for Fast-Mode Execution.
    Decomposes fast-path tasks, invokes tools/workers via CapabilityRegistry,
    and escalates to Boss if execution thresholds are crossed.
    """

    def __init__(
        self,
        capability_registry: CapabilityRegistry | None = None,
        governor: EngineeringGovernor | None = None,
        max_retries: int = 2,
    ) -> None:
        self.capability_registry = capability_registry or CapabilityRegistry()
        self.governor = governor or EngineeringGovernor()
        self.max_retries = max_retries

    async def execute_capability(self, request: CapabilityRequest) -> dict[str, Any]:
        """
        Public adapter interface for executing a direct capability request.
        Invoked by BossAgent or WorkflowEngine.
        """
        logger.info("host2.execute_capability_start", capability=request.capability_name, role=request.requester_role)
        self.governor.check_capability_spawn_policy(request.capability_name, request.requester_role)
        handle: CapabilityHandle = await self.capability_registry.invoke(request)
        return {
            "status": handle.status,
            "capability_name": handle.capability_name,
            "output": handle.output,
            "execution_time_seconds": handle.execution_time_seconds,
            "handle": handle.model_dump(),
        }

    async def run_native_cpp_engine(self, capability: str, path: str, request_id: str = "cpp_req") -> dict[str, Any]:
        """
        Runs the native C++ Host-2 execution engine for the given capability and path.
        """
        import sys
        import shutil
        from pathlib import Path

        base_pkg = Path(__file__).parents[2]
        cpp_src = base_pkg / "host2_cpp" / "host2_engine.cpp"
        if not cpp_src.exists():
            # Fallback check relative to cwd
            alt_src = Path.cwd() / "aiswarm" / "host2_cpp" / "host2_engine.cpp"
            if alt_src.exists():
                cpp_src = alt_src
        bin_name = "host2_engine.exe" if sys.platform == "win32" else "host2_engine"
        bin_path = cpp_src.parent / bin_name

        # Compile if not present
        if not bin_path.exists():
            compiler = "g++"
            if shutil.which("clang++"):
                compiler = "clang++"
            elif shutil.which("cl"):
                compiler = "cl"

            if compiler == "cl":
                cmd = ["cl", "/EHsc", str(cpp_src), f"/Fe:{bin_path}"]
            else:
                cmd = [compiler, "-std=c++17", str(cpp_src), "-o", str(bin_path)]

            logger.info("host2.compile_native_engine", command=cmd)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error("host2.compile_native_engine_failed", stderr=stderr.decode())
                raise RuntimeError(f"Failed to compile native C++ Host-2 engine: {stderr.decode()}")

        # Execute the native engine in the sandbox
        cmd = [str(bin_path), "--capability", capability, "--path", path, "--request-id", request_id]
        logger.info("host2.run_native_engine", command=cmd)

        # Run via sandbox
        result = await self.capability_registry.sandbox.execute_sandboxed_command(cmd)
        if result.get("returncode") == 0:
            import json
            try:
                # The stdout contains JSON from the C++ engine
                return json.loads(result.get("stdout", "{}").strip())
            except Exception:
                pass
        return result

    async def execute_fast_task(self, task_payload: dict[str, Any]) -> dict[str, Any]:
        """
        Execute a fast-mode task using optimal capabilities.
        Returns task completion dictionary or escalates to Boss via EscalationPacket.
        """
        task_id = task_payload.get("task_id", "fast_task")
        code = task_payload.get("code", "")
        target_file = task_payload.get("target_file") or task_payload.get("path", ".")
        language = (task_payload.get("language") or "python").lower()
        test_command = task_payload.get("test_command")
        capability_name = task_payload.get("capability_name")
        completed_steps = []

        # Auto-detect C++ language tasks
        is_cpp = language in ["c++", "cpp"] or str(target_file).endswith((".cpp", ".hpp", ".cxx", ".cc"))
        if is_cpp:
            capability_name = capability_name or "cpp_compile"
        elif test_command and test_command != "pytest":
            capability_name = capability_name or "custom_test"
        else:
            capability_name = capability_name or "pytest"

        logger.info("host2.execute_start", task_id=task_id, language=language, capability=capability_name)

        # Check governance spawn permissions
        self.governor.check_capability_spawn_policy(capability_name, "host2")

        if is_cpp:
            try:
                native_res = await self.run_native_cpp_engine(capability_name, target_file, request_id=task_id)
                if native_res.get("status") == "SUCCESS":
                    completed_steps.append(f"C++ Native Host-2 Engine executed successfully: {native_res}")
            except Exception as e:
                logger.warning("host2.native_cpp_engine_failed", task_id=task_id, error=str(e))
                completed_steps.append(f"C++ Native Host-2 Engine execution failed: {e}")

        # Step 1: Run code/test capability in sandbox
        retry_count = 0
        while retry_count <= self.max_retries:
            logger.info("host2.step_execute", task_id=task_id, attempt=retry_count + 1)
            
            # Task-scoped invocation parameters
            params: dict[str, Any] = {"path": target_file}
            if code:
                params["code"] = code
            if test_command:
                params["test_command"] = test_command
            if "instruction" in task_payload:
                params["instruction"] = task_payload["instruction"]

            request = CapabilityRequest(
                capability_name=capability_name,
                requester_role="host2",
                parameters=params,
            )
            handle: CapabilityHandle = await self.capability_registry.invoke(request)

            if handle.status == "SUCCESS":
                completed_steps.append(f"Execution passed on attempt {retry_count + 1}")
                logger.info("host2.execute_success", task_id=task_id)
                return {
                    "status": "COMPLETED",
                    "task_id": task_id,
                    "completed_steps": completed_steps,
                    "handle": handle.model_dump(),
                    "escalated": False,
                }

            retry_count += 1
            completed_steps.append(f"Attempt {retry_count} failed: {handle.output}")

        # Retries exhausted — promote task to Boss via EscalationPacket
        logger.warning("host2.retries_exhausted_escalating", task_id=task_id, retries=retry_count)
        escalation_packet = EscalationPacket(
            task_id=task_id,
            reason=f"Fast-mode execution failed after {retry_count} attempts.",
            completed_steps=completed_steps,
            failed_stage="EXECUTING_TESTS",
            remaining_risks=["Test failure in fast mode", "Requires deep reasoning / Boss deadlock resolution"],
            suggested_next_action="PROMOTE_TO_PRODUCTION_PIPELINE",
        )

        return {
            "status": "ESCALATED",
            "task_id": task_id,
            "escalation_packet": escalation_packet.model_dump(),
            "escalated": True,
        }

