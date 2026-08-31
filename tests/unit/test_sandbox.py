"""
Unit Tests for Execution Sandbox & Isolation.
"""

from pathlib import Path
from aiswarm.security.sandbox import ExecutionSandbox, SandboxViolationError, scrub_secrets


def test_scrub_secrets():
    """Secrets in output should be redacted."""
    raw_output = "Connected with token='MOCK_SECRET_TOKEN_VALUE_12345'"
    sanitized = scrub_secrets(raw_output)
    assert "MOCK_SECRET_TOKEN_VALUE_12345" not in sanitized
    assert "***REDACTED***" in sanitized


def test_allowlist_command_validation(tmp_path: Path):
    """Only allowlisted commands should be permitted."""
    sandbox = ExecutionSandbox(workspace_dir=tmp_path)

    # Allowed command
    parsed = sandbox.validate_command(["python", "-c", "print('hello')"])
    assert parsed[0] == "python"

    # Forbidden command
    raised = False
    try:
        sandbox.validate_command(["malicious_binary", "--eval"])
    except SandboxViolationError:
        raised = True
    assert raised is True


def test_path_traversal_validation(tmp_path: Path):
    """Path traversal outside workspace should be blocked."""
    sandbox = ExecutionSandbox(workspace_dir=tmp_path)
    inside_path = tmp_path / "scratch.py"
    inside_path.touch()

    # Valid path inside workspace
    assert sandbox.validate_path_in_workspace(inside_path) == inside_path.resolve()

    # Path outside workspace
    outside_path = tmp_path.parent / "system.sys"
    raised = False
    try:
        sandbox.validate_path_in_workspace(outside_path)
    except SandboxViolationError:
        raised = True
    assert raised is True


async def test_sandboxed_command_execution(tmp_path: Path):
    """Valid sandboxed command should execute safely and return output."""
    sandbox = ExecutionSandbox(workspace_dir=tmp_path)
    result = await sandbox.execute_sandboxed_command(["python", "-c", "print('sandbox_test_ok')"])
    assert result["returncode"] == 0
    assert "sandbox_test_ok" in result["stdout"]
    assert result["timed_out"] is False
