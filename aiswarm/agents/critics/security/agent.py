"""Security Critic Agent."""

from __future__ import annotations

import json
from typing import Any

import structlog

from aiswarm.agents.base.agent import BaseAgent
from aiswarm.llm.adapter import LLMMessage
from aiswarm.schemas.task import Task, CriticReview, ReviewDecision

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are the Security Critic Agent of AISwarm.

You have UNCONDITIONAL VETO POWER. A security rejection always blocks the merge.
You review code exclusively for security vulnerabilities and risks.

Your evaluation follows OWASP Top 10 and SANS Top 25:

1. Injection — SQL, command, LDAP, XML, path traversal
2. Broken Authentication — hardcoded credentials, weak session management
3. Sensitive Data Exposure — secrets in code, unencrypted PII, verbose errors
4. Broken Access Control — privilege escalation, IDOR, missing authz checks
5. Security Misconfiguration — debug mode in production, open CORS, default credentials
6. Insecure Deserialization — pickle.loads, yaml.load without Loader, eval on input
7. Known Vulnerable Dependencies — deprecated crypto, pinned to vulnerable version
8. Insufficient Logging — security events not logged, sensitive data in logs
9. Cryptographic Issues — MD5/SHA1 for passwords, hardcoded IV, weak key size
10. Input Validation — missing validation, regex DoS (ReDoS), integer overflow

Automatic REJECT triggers:
- Any hardcoded secret, token, or password
- Use of eval/exec on user input
- SQL string formatting (not parameterized)
- pickle.loads on untrusted data
- MD5 or SHA1 for password hashing
- Disabled TLS verification
- User-controlled path without validation

Output ONLY valid JSON:
{
  "decision": "APPROVE" | "REJECT" | "ESCALATE",
  "production_ready": true | false,
  "has_injection_risk": true | false,
  "has_auth_issues": true | false,
  "has_data_exposure": true | false,
  "has_dependency_risk": true | false,
  "has_crypto_issues": true | false,
  "has_input_validation": true | false,
  "cve_references": ["CVE-XXXX-XXXX if applicable"],
  "fatal_flaw": null or "precise vulnerability description",
  "flaw_category": null or "INJECTION|AUTH|EXPOSURE|CRYPTO|VALIDATION|DESERIALIZATION",
  "flaw_explanation": "OWASP category and risk level",
  "mandatory_fix": "Exact remediation the coder must implement",
  "mitigations": ["additional security hardening suggestions"],
  "overall_score": 0-100
}

If ANY critical security flaw exists, decision MUST be REJECT.
Security is non-negotiable.
"""


class SecurityCritic(BaseAgent):
    """Reviews code for security vulnerabilities — has veto power."""

    role = "critic_security"

    async def run(self, task: Task) -> CriticReview:
        code = task.generated_code or ""
        if not code.strip():
            review = CriticReview(
                critic_role="security",
                decision=ReviewDecision.REJECT,
                production_ready=False,
                fatal_flaw="No code generated",
                mandatory_fix="Generate code first",
            )
            task.reviews.append(review)
            return review

        messages = [
            LLMMessage(role="system", content=_SYSTEM_PROMPT),
            LLMMessage(
                role="user",
                content=f"""
Perform a thorough security review of this code.

Task: {task.title}
Language: {task.target_language}
Security considerations from plan:
{", ".join(task.metadata.get("blueprint", {}).get("security_considerations", []) if isinstance(task.metadata.get("blueprint"), dict) else [])}

Code:
```{task.target_language}
{code[:8000]}
```

Respond with ONLY the JSON review object.
""",
            ),
        ]
        response = await self.call_llm(messages, task=task, temperature=0.0)
        task.prompt_ledger.append(self.build_ledger(messages, response, "sec_critic_v1"))
        review = self._parse_review(response.content, response)
        task.reviews.append(review)

        if review.decision == ReviewDecision.REJECT:
            logger.warning(
                "critic.security.VETO",
                task_id=task.task_id,
                fatal_flaw=review.fatal_flaw,
                flaw_category=review.flaw_category,
            )
        else:
            logger.info(
                "critic.security",
                task_id=task.task_id,
                decision=review.decision.value,
                score=review.score,
            )
        return review

    def _parse_review(self, content: str, response: Any) -> CriticReview:
        text = content.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        start, end = text.find("{"), text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end])
                return CriticReview(
                    critic_role="security",
                    decision=ReviewDecision(data.get("decision", "REJECT")),
                    production_ready=data.get("production_ready", False),
                    fatal_flaw=data.get("fatal_flaw"),
                    flaw_category=data.get("flaw_category"),
                    flaw_explanation=data.get("flaw_explanation", ""),
                    mandatory_fix=data.get("mandatory_fix", ""),
                    suggestions=data.get("mitigations", []),
                    score=data.get("overall_score", 50),
                    model_used=response.model,
                    latency_ms=response.latency_ms,
                    token_count=response.total_tokens,
                )
            except (json.JSONDecodeError, ValueError, KeyError):
                pass
        return CriticReview(
            critic_role="security",
            decision=ReviewDecision.REJECT,
            production_ready=False,
            fatal_flaw="Security critic response could not be parsed",
            mandatory_fix="Treat as security failure and retry",
        )
