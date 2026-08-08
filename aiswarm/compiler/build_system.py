"""Build system router."""

from __future__ import annotations

from aiswarm.schemas.task import Task, CompilerOutput

class BuildSystem:
    """Routes compilation tasks to the appropriate language compiler."""

    async def compile(self, task: Task) -> CompilerOutput:
        language = task.target_language.lower()
        if language in ("python", "py"):
            from aiswarm.compiler.python import PythonCompiler
            return await PythonCompiler().compile(task)
        if language in ("cpp", "c++", "c"):
            from aiswarm.compiler.cpp import CppCompiler
            comp = CppCompiler()
            target_files = task.target_files or ["main.cpp"]
            res = await comp.compile(source_files=target_files)
            output = CompilerOutput(
                success=res.get("success", False),
                stdout=res.get("stdout", ""),
                stderr=res.get("stderr", ""),
                exit_code=res.get("returncode", -1),
                command=f"cpp_compile:{res.get('compiler', 'g++')}",
            )
            task.compiler_output = output
            return output
        if language in ("rust", "rs"):
            from aiswarm.compiler.rust import RustCompiler
            return await RustCompiler().compile(task)

        # Fail closed for unsupported languages
        output = CompilerOutput(
            success=False,
            stdout="",
            stderr=f"No compiler configured for unsupported language: {language}",
            exit_code=1,
            command=f"unsupported:{language}",
        )
        task.compiler_output = output
        return output
