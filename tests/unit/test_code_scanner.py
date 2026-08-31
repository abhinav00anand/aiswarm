"""Unit tests for the static code scanner."""

from __future__ import annotations


from aiswarm.security.code_scanner import CodeScanner


class TestCodeScanner:
    def setup_method(self) -> None:
        self.scanner = CodeScanner()

    def test_clean_code_passes(self) -> None:
        code = '''
def add(a: int, b: int) -> int:
    """Return the sum of a and b."""
    return a + b
'''
        result = self.scanner.scan(code)
        assert result.clean
        assert len(result.violations) == 0

    def test_os_system_detected(self) -> None:
        code = 'import os\nos.system("rm -rf /")'
        result = self.scanner.scan(code)
        assert not result.clean
        assert any("os.system" in v for v in result.violations)

    def test_eval_detected(self) -> None:
        code = 'x = eval(input("enter code: "))'
        result = self.scanner.scan(code)
        assert not result.clean
        assert any("eval" in v for v in result.violations)

    def test_pickle_loads_detected(self) -> None:
        code = "import pickle\ndata = pickle.loads(user_input)"
        result = self.scanner.scan(code)
        assert not result.clean
        assert any("pickle" in v.lower() for v in result.violations)

    def test_hardcoded_secret_detected(self) -> None:
        code = 'SECRET = "my_super_secret_token_12345"'
        result = self.scanner.scan(code)
        assert any("secret" in v.lower() for v in result.violations)

    def test_syntax_error_detected(self) -> None:
        code = "def broken(:"
        result = self.scanner.scan(code, language="python")
        assert not result.clean
        assert any("syntax" in v.lower() for v in result.violations)

    def test_weak_hash_in_warnings(self) -> None:
        code = "import hashlib\nh = hashlib.md5(data)"
        result = self.scanner.scan(code)
        # md5 for password = violation, md5 in general = warning
        assert len(result.violations) > 0 or len(result.warnings) > 0

    def test_tls_disabled_detected(self) -> None:
        code = "requests.get(url, verify=False)"
        result = self.scanner.scan(code)
        # verify=False should appear in violations or warnings
        all_findings = result.violations + result.warnings
        assert any("verify" in f.lower() for f in all_findings)
