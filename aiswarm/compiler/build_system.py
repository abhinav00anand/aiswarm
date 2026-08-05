"""Build system router — dispatches to the right compiler based on language."""

from __future__ import annotations

from aiswarm.schemas.task import Task, CompilerOutput


class BuildSystem:
    """Routes compilation tasks to the appropriate language compiler."""

    async def compile(self, task: Task) -> CompilerOutput:
        language = task.target_language.lower()
        if language in ("python", "py"):
            from aiswarm.compiler.python import PythonCompiler
            return await PythonCompiler().compile(task)
        # For other languages, return a pass-through result
        return CompilerOutput(
            success=True,
            stdout=f"No compiler configured for {language}",
            exit_code=0,
            command=f"noop:{language}",
        )
