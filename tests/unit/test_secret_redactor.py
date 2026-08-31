"""Unit tests for SecretRedactor and secret scanning enhancements."""

from __future__ import annotations

from aiswarm.security.code_scanner import CodeScanner
from aiswarm.security.redaction import SecretRedactor


class TestSecretRedactor:
    def setup_method(self) -> None:
        self.redactor = SecretRedactor()

    def test_redact_standard_openai_key(self) -> None:
        raw = "Using key sk-abcdef1234567890abcdef1234567890 for API"
        scrubbed = self.redactor.scrub(raw)
        assert "sk-abcdef" not in scrubbed
        assert "***OPENAI_KEY***" in scrubbed

    def test_redact_project_openai_key(self) -> None:
        raw = "Using project key sk-proj-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8 for API"
        scrubbed = self.redactor.scrub(raw)
        assert "sk-proj-" not in scrubbed
        assert "***OPENAI_KEY***" in scrubbed

    def test_redact_anthropic_key(self) -> None:
        raw = "Anthropic secret sk-ant-api03-abcdef1234567890abcdef12345"
        scrubbed = self.redactor.scrub(raw)
        assert "sk-ant-" not in scrubbed
        assert "***ANTHROPIC_KEY***" in scrubbed

    def test_redact_github_pat(self) -> None:
        raw = "token ghp_123456789012345678901234567890123456 in url"
        scrubbed = self.redactor.scrub(raw)
        assert "ghp_" not in scrubbed
        assert "***GH_PAT***" in scrubbed

    def test_redact_pypi_token(self) -> None:
        raw = "upload pypi-AgEIcHlwaS5vcmcCJDEyMzQ1Njc4LTBhYmMtZGVmMC0xMjM0LTU2Nzg5MGFiY2RlZgACK"
        scrubbed = self.redactor.scrub(raw)
        assert "pypi-" not in scrubbed
        assert "***PYPI_TOKEN***" in scrubbed

    def test_redact_google_api_key(self) -> None:
        raw = "Google key AIzaSyD1234567890abcdef1234567890abcdef"
        scrubbed = self.redactor.scrub(raw)
        assert "AIza" not in scrubbed
        assert "***GOOGLE_KEY***" in scrubbed

    def test_redact_aws_key(self) -> None:
        raw = "AWS credentials AKIAIOSFODNN7EXAMPLE"
        scrubbed = self.redactor.scrub(raw)
        assert "AKIAIOSFODNN7EXAMPLE" not in scrubbed
        assert "***AWS_KEY***" in scrubbed

    def test_clean_text_unchanged(self) -> None:
        text = "Just regular code with no secrets at all."
        assert self.redactor.scrub(text) == text


class TestCodeScannerTokenDetection:
    def setup_method(self) -> None:
        self.scanner = CodeScanner()

    def test_openai_project_key_detected(self) -> None:
        code = 'client = OpenAI("sk-proj-1234567890abcdef1234567890abcdef12")'
        result = self.scanner.scan(code)
        assert not result.clean
        assert any("OpenAI" in v for v in result.violations)

    def test_github_pat_detected(self) -> None:
        code = 'url = "https://ghp_123456789012345678901234567890123456@github.com"'
        result = self.scanner.scan(code)
        assert not result.clean
        assert any("GitHub" in v for v in result.violations)

    def test_pypi_token_detected(self) -> None:
        code = (
            'upload("pypi-AgEIcHlwaS5vcmcCJDEyMzQ1Njc4LTBhYmMtZGVmMC0xMjM0LTU2Nzg5MGFiY2RlZgACK")'
        )
        result = self.scanner.scan(code)
        assert not result.clean
        assert any("PyPI" in v for v in result.violations)
