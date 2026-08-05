"""
Secret Redaction Engine — scrubs sensitive data from prompts, logs, and artifacts.

Provides multi-pattern secret detection and replacement to prevent credential leakage
across all AISwarm output channels.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from aiswarm.utils.compat_log import get_logger

logger = get_logger(__name__)

@dataclass
class RedactionRule:
    name: str
    pattern: re.Pattern
    replacement: str = "***REDACTED***"

class SecretRedactor:
    """Multi-pattern secret scrubber for all platform output channels."""
    
    _DEFAULT_RULES: list[tuple[str, str, str]] = [
        ("openai_key", r"sk-[a-zA-Z0-9]{32,}", "***OPENAI_KEY***"),
        ("anthropic_key", r"sk-ant-[a-zA-Z0-9\-]{30,}", "***ANTHROPIC_KEY***"),
        ("github_pat", r"ghp_[a-zA-Z0-9]{36}", "***GH_PAT***"),
        ("google_api_key", r"AIza[0-9A-Za-z\-_]{35}", "***GOOGLE_KEY***"),
        ("generic_secret", r"(?i)(api[_-]?key|secret|token|password|bearer)\s*[=:]\s*['\"]?([a-zA-Z0-9_\-\.]{16,})['\"]?", r"\1=***REDACTED***"),
        ("aws_key", r"AKIA[0-9A-Z]{16}", "***AWS_KEY***"),
        ("env_assignment", r"(?m)^([A-Z_]{4,}_KEY|[A-Z_]{4,}_SECRET|[A-Z_]{4,}_TOKEN)=.+$", r"\1=***REDACTED***"),
    ]
    
    def __init__(self, extra_rules: list[RedactionRule] | None = None) -> None:
        self._rules: list[RedactionRule] = [
            RedactionRule(name=name, pattern=re.compile(pattern, re.IGNORECASE), replacement=repl)
            for name, pattern, repl in self._DEFAULT_RULES
        ]
        if extra_rules:
            self._rules.extend(extra_rules)
    
    def scrub(self, text: str) -> str:
        """Apply all redaction rules to text, returning sanitized output."""
        if not text:
            return text
        sanitized = text
        redacted_count = 0
        for rule in self._rules:
            new_text, count = rule.pattern.subn(rule.replacement, sanitized)
            if count:
                redacted_count += count
                sanitized = new_text
        if redacted_count:
            logger.debug("redactor.secrets_scrubbed", count=redacted_count)
        return sanitized
    
    def scrub_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively scrub all string values in a dictionary."""
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.scrub(value)
            elif isinstance(value, dict):
                result[key] = self.scrub_dict(value)
            elif isinstance(value, list):
                result[key] = [self.scrub(v) if isinstance(v, str) else v for v in value]
            else:
                result[key] = value
        return result

_DEFAULT_REDACTOR = SecretRedactor()

def scrub(text: str) -> str:
    """Module-level convenience: scrub secrets from a string."""
    return _DEFAULT_REDACTOR.scrub(text)

def scrub_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Module-level convenience: scrub secrets from a dict."""
    return _DEFAULT_REDACTOR.scrub_dict(data)
