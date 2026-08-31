"""Unit tests for SecretRedactor and secret scanning enhancements."""

from __future__ import annotations

from aiswarm.security.code_scanner import CodeScanner
from aiswarm.security.redaction import SecretRedactor


class TestSecretRedactor:
    def setup_method(self) -> None:
        self.redactor = SecretRedactor()

    def test_redact_standard_openai_key(self) -> None:
        mock_key = "sk-" + "mock_openai_test_token_" + ("a" * 30)
        raw = f"Using key {mock_key} for API"
        scrubbed = self.redactor.scrub(raw)
        assert "mock_openai" not in scrubbed
        assert "***OPENAI_KEY***" in scrubbed

    def test_redact_project_openai_key(self) -> None:
        mock_key = "sk-proj-" + "mock_project_test_token_" + ("b" * 30)
        raw = f"Using project key {mock_key} for API"
        scrubbed = self.redactor.scrub(raw)
        assert "sk-proj-" not in scrubbed
        assert "***OPENAI_KEY***" in scrubbed

    def test_redact_anthropic_key(self) -> None:
        mock_key = "sk-ant-" + "mock_anthropic_test_token_" + ("c" * 30)
        raw = f"Anthropic secret {mock_key}"
        scrubbed = self.redactor.scrub(raw)
        assert "sk-ant-" not in scrubbed
        assert "***ANTHROPIC_KEY***" in scrubbed

    def test_redact_github_pat(self) -> None:
        mock_pat = "ghp_" + ("1234567890" * 4)[:36]
        raw = f"token {mock_pat} in url"
        scrubbed = self.redactor.scrub(raw)
        assert "ghp_" not in scrubbed
        assert "***GH_PAT***" in scrubbed

    def test_redact_pypi_token(self) -> None:
        # Dynamically assembled mock token to prevent triggering static secret scanners
        mock_pypi = "pypi-" + "mock_pypi_test_payload_" + ("x" * 40)
        raw = f"upload {mock_pypi}"
        scrubbed = self.redactor.scrub(raw)
        assert "pypi-" not in scrubbed
        assert "***PYPI_TOKEN***" in scrubbed

    def test_redact_google_api_key(self) -> None:
        mock_google = "AIza" + ("SyD1234567890abcdef" * 3)[:35]
        raw = f"Google key {mock_google}"
        scrubbed = self.redactor.scrub(raw)
        assert "AIza" not in scrubbed
        assert "***GOOGLE_KEY***" in scrubbed

    def test_redact_aws_key(self) -> None:
        mock_aws = "AKIA" + "IOSFODNN7EXAMPLE"[:16]
        raw = f"AWS credentials {mock_aws}"
        scrubbed = self.redactor.scrub(raw)
        assert "AKIA" not in scrubbed
        assert "***AWS_KEY***" in scrubbed

    def test_clean_text_unchanged(self) -> None:
        text = "Just regular code with no secrets at all."
        assert self.redactor.scrub(text) == text


class TestCodeScannerTokenDetection:
    def setup_method(self) -> None:
        self.scanner = CodeScanner()

    def test_openai_project_key_detected(self) -> None:
        mock_key = "sk-proj-" + "mock_scanner_token_" + ("d" * 30)
        code = f'client = OpenAI("{mock_key}")'
        result = self.scanner.scan(code)
        assert not result.clean
        assert any("OpenAI" in v for v in result.violations)

    def test_github_pat_detected(self) -> None:
        mock_pat = "ghp_" + ("1234567890" * 4)[:36]
        code = f'url = "https://{mock_pat}@github.com"'
        result = self.scanner.scan(code)
        assert not result.clean
        assert any("GitHub" in v for v in result.violations)

    def test_pypi_token_detected(self) -> None:
        # Dynamically assembled mock token to prevent triggering static secret scanners
        mock_pypi = "pypi-" + "mock_pypi_test_payload_" + ("x" * 40)
        code = f'upload("{mock_pypi}")'
        result = self.scanner.scan(code)
        assert not result.clean
        assert any("PyPI" in v for v in result.violations)
