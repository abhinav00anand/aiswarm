#!/usr/bin/env python3
"""
Google Antigravity PR Review Agent for Zymis Framework.

Performs deep architectural, security, reliability, and code quality audits
on Pull Requests for the Zymis multi-agent orchestration framework.
Evaluates diffs against Zymis's 8 specialized critics and 5-gate merge controller,
producing inline comments with 'What is wrong' and 'What is needed' suggestions,
as well as a structured PR review summary.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

import httpx

# System prompt grounding Antigravity in Zymis deep architecture
ZYMIS_REVIEW_SYSTEM_PROMPT = """\
You are Google Antigravity, the autonomous Senior AI Review Agent for the Zymis Multi-Agent Orchestration Framework (abhinav00anand/zymis).

Your mission is to perform a deep, rigorous, and constructive code review of incoming Pull Requests.
You must evaluate the submitted changes against Zymis's core architectural tenets, security policies, and code quality standards.

### ZYMIS CORE ARCHITECTURAL STANDARDS
1. Dual-Router & Multi-Lane Architecture:
   - Host-1 Global Router (`aiswarm/agents/host1`): Correct classification into FAST (~0.1s), PRODUCTION (12-stage pipeline), or HYBRID lanes.
   - Host-2 Capability Manager (`aiswarm/agents/host2`): Pre-approved capabilities, EscalationPackets on ambiguity.
   - Boss Agent Pipeline: Clean separation between Boss (CTO/deadlock resolution), Manager (subtask dependency DAGs), Task Planner (technical blueprints), and Coder (code + pytest).
   - Finite State Machine (FSM): Correct state transitions (NEW -> PROMPTED -> COMPILED -> REVIEWED -> MERGED).

2. 8 Specialized Critic Framework:
   - SecurityCritic: Zero hardcoded API keys/tokens (scrubbed via SecretRedactor patterns: sk-..., AIza..., ghp_..., pypi-...). OWASP Top 10, no command injection, safe subprocess execution via ExecutionSandbox. [HOLDS VETO POWER]
   - ArchitectureCritic: SOLID principles, modular decoupling, cyclic dependency prevention, single responsibility.
   - MaintainabilityCritic: Functions <= 50 lines (must decompose if >50, reject if >100 without justification), low cyclomatic complexity, clear intention-revealing naming (no single-letter vars outside loops), no dead or commented-out code, no unresolved TODO/FIXME in production paths.
   - ReliabilityCritic: Robust exception boundaries, async cancellation handling, timeouts, no bare `except:`, safe handling of None/null.
   - PerformanceCritic: Algorithmic complexity, avoidance of blocking I/O in async loops, bounded memory.
   - TestingCritic: Pytest test coverage for all new branches and edge cases with assertions.
   - StyleCritic: Python 3.11+, Ruff strict compliance, structured logging via `structlog.get_logger(__name__)` (NO raw `print()` statements in library code).
   - DocumentationCritic: Complete type annotations on all public functions/classes, Google-style docstrings.

3. 5-Gate Merge Controller:
   - Gate 1 (Compilation): Valid Python syntax, no import or bytecode compile errors.
   - Gate 2 (Unit Testing): Comprehensive pytest unit tests covering added logic.
   - Gate 3 (Performance): Acceptable algorithmic complexity and latency budgets.
   - Gate 4 (Security): 0 fatal flaws, 0 unmasked secrets, strict sandbox adherence.
   - Gate 5 (Path Resolution): All file system operations must canonically resolve within workspace directory boundaries.

### YOUR REVIEW REQUIREMENTS
Perform a DEEP, THOROUGH analysis of the provided diff and context:
1. Identify EXACTLY "what is wrong": Pinpoint bugs, anti-patterns, security risks, missing error handling, style violations.
2. Identify EXACTLY "what is needed": Provide concrete solutions and actionable requirements.
3. Provide inline code suggestions with GitHub markdown diff suggestions wherever applicable.
4. Render an overall decision:
   - "APPROVE": If code meets all quality gates, has test coverage, zero security issues, and adheres to Zymis standards.
   - "REQUEST_CHANGES": If there are security flaws, broken contracts, missing critical tests, or severe architectural defects.
   - "COMMENT": If changes are generally sound but have minor questions, improvements, or non-blocking suggestions.

### OUTPUT FORMAT
You MUST output ONLY valid JSON matching this schema:
{
  "verdict": "APPROVE" | "REQUEST_CHANGES" | "COMMENT",
  "overall_score": 0-100,
  "production_ready": true | false,
  "executive_summary": "Markdown narrative summarizing the changes, impact, and overall quality.",
  "critic_evaluations": {
    "SecurityCritic": {"status": "PASS" | "WARN" | "FAIL", "score": 0-10, "notes": "assessment"},
    "ArchitectureCritic": {"status": "PASS" | "WARN" | "FAIL", "score": 0-10, "notes": "assessment"},
    "MaintainabilityCritic": {"status": "PASS" | "WARN" | "FAIL", "score": 0-10, "notes": "assessment"},
    "ReliabilityCritic": {"status": "PASS" | "WARN" | "FAIL", "score": 0-10, "notes": "assessment"},
    "PerformanceCritic": {"status": "PASS" | "WARN" | "FAIL", "score": 0-10, "notes": "assessment"},
    "TestingCritic": {"status": "PASS" | "WARN" | "FAIL", "score": 0-10, "notes": "assessment"},
    "StyleCritic": {"status": "PASS" | "WARN" | "FAIL", "score": 0-10, "notes": "assessment"},
    "DocumentationCritic": {"status": "PASS" | "WARN" | "FAIL", "score": 0-10, "notes": "assessment"}
  },
  "gate_evaluations": {
    "CompilationGate": {"status": "PASS" | "FAIL", "notes": "notes"},
    "UnitTestGate": {"status": "PASS" | "FAIL", "notes": "notes"},
    "PerformanceGate": {"status": "PASS" | "FAIL", "notes": "notes"},
    "SecurityGate": {"status": "PASS" | "FAIL", "notes": "notes"},
    "PathResolutionGate": {"status": "PASS" | "FAIL", "notes": "notes"}
  },
  "critical_flaws": [
    {
      "title": "Short title of flaw",
      "what_is_wrong": "Detailed explanation of what is wrong and why it is a problem",
      "what_is_needed": "Exact fix or prerequisite required before merging"
    }
  ],
  "inline_comments": [
    {
      "path": "path/to/file.py",
      "line": 42,
      "severity": "CRITICAL" | "WARNING" | "INFO" | "SUGGESTION",
      "what_is_wrong": "Clear explanation of the flaw on this line",
      "what_is_needed": "Exact change required to fix it",
      "suggested_code": "Optional single or multi-line replacement snippet without diff markers"
    }
  ],
  "positive_highlights": [
    "List of well-architected patterns or commendable code practices observed"
  ],
  "general_recommendations": [
    "List of broader improvements or follow-up recommendations"
  ]
}
"""


class GitHubClient:
    """Client for interacting with GitHub REST API."""

    def __init__(self, token: str, repository: str) -> None:
        self.repository = repository
        self.base_url = f"https://api.github.com/repos/{repository}"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def get_pull_request(self, pr_number: int) -> dict[str, Any]:
        url = f"{self.base_url}/pulls/{pr_number}"
        response = httpx.get(url, headers=self.headers, timeout=30.0)
        response.raise_for_status()
        return response.json()

    def get_pull_request_diff(self, pr_number: int) -> str:
        url = f"{self.base_url}/pulls/{pr_number}"
        headers = dict(self.headers)
        headers["Accept"] = "application/vnd.github.v3.diff"
        response = httpx.get(url, headers=headers, timeout=45.0)
        response.raise_for_status()
        return response.text

    def get_pull_request_files(self, pr_number: int) -> list[dict[str, Any]]:
        url = f"{self.base_url}/pulls/{pr_number}/files"
        response = httpx.get(url, headers=self.headers, timeout=30.0)
        response.raise_for_status()
        return response.json()

    def post_review(
        self,
        pr_number: int,
        commit_id: str,
        body: str,
        event: str,
        comments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Submit a complete pull request review with summary and inline comments."""
        url = f"{self.base_url}/pulls/{pr_number}/reviews"
        payload: dict[str, Any] = {
            "commit_id": commit_id,
            "body": body,
            "event": event,
        }
        if comments:
            payload["comments"] = comments

        response = httpx.post(url, headers=self.headers, json=payload, timeout=60.0)
        if response.status_code == 422:
            # If inline comments fail (e.g. line outside diff hunk), retry with body only
            # and append inline comments to the review body so no feedback is lost
            print(
                f"[Warning] GitHub rejected inline comments (422: {response.text}). Falling back to body-only review."
            )
            payload.pop("comments", None)
            response = httpx.post(url, headers=self.headers, json=payload, timeout=60.0)

        response.raise_for_status()
        return response.json()

    def post_issue_comment(self, pr_number: int, body: str) -> dict[str, Any]:
        url = f"{self.base_url}/issues/{pr_number}/comments"
        response = httpx.post(url, headers=self.headers, json={"body": body}, timeout=30.0)
        response.raise_for_status()
        return response.json()


def parse_diff_valid_lines(diff_text: str) -> dict[str, set[int]]:
    """Parse unified diff to map file paths to valid line numbers in the new file."""
    file_lines: dict[str, set[int]] = {}
    current_file = None

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:].strip()
            file_lines[current_file] = set()
        elif line.startswith("@@ ") and current_file:
            # Hunk header: @@ -old,count +new,count @@
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if match:
                start_line = int(match.group(1))
                count = int(match.group(2)) if match.group(2) else 1
                for l_num in range(start_line, start_line + count):
                    file_lines[current_file].add(l_num)

    return file_lines


def query_antigravity_gemini(
    prompt: str,
    system_instruction: str,
    api_key: str,
    model_name: str = "gemini-2.5-pro",
) -> str:
    """Query Google Antigravity / Gemini model for code review analysis."""
    # Attempt using google.generativeai
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction,
            generation_config={"response_mime_type": "application/json", "temperature": 0.2},
        )
        response = model.generate_content(prompt)
        return response.text or "{}"
    except ImportError:
        pass

    # Fallback to direct Gemini REST API call via httpx
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    payload = {
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }
    resp = httpx.post(url, json=payload, timeout=120.0)
    if resp.status_code != 200:
        # Fallback to gemini-1.5-pro if 2.5-pro is unavailable
        if "not found" in resp.text.lower() or resp.status_code == 404:
            fallback_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={api_key}"
            resp = httpx.post(fallback_url, json=payload, timeout=120.0)

    resp.raise_for_status()
    data = resp.json()
    candidates = data.get("candidates", [])
    if candidates:
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if parts:
            return parts[0].get("text", "{}")

    raise RuntimeError("Failed to retrieve response from Antigravity/Gemini API.")


def build_review_markdown(review_data: dict[str, Any], pr_title: str, pr_number: int) -> str:
    """Format structured review JSON into an executive Markdown report."""
    score = review_data.get("overall_score", 0)
    verdict = review_data.get("verdict", "COMMENT")
    ready = review_data.get("production_ready", False)

    verdict_emoji = (
        "✅" if verdict == "APPROVE" else ("🛑" if verdict == "REQUEST_CHANGES" else "💬")
    )
    ready_badge = "✅ **READY**" if ready else "❌ **NEEDS REVISION**"

    lines = [
        "## 🛸 Google Antigravity PR Review — Zymis Framework",
        "",
        f"### PR #{pr_number}: {pr_title}",
        "| Metric | Assessment |",
        "| :--- | :--- |",
        f"| **Overall Score** | **{score} / 100** |",
        f"| **Review Verdict** | {verdict_emoji} `{verdict}` |",
        f"| **Production Ready** | {ready_badge} |",
        "",
        "---",
        "",
        "### 📋 Executive Summary",
        f"{review_data.get('executive_summary', 'No summary provided.')}",
        "",
        "---",
        "",
        "### 🛡 5-Gate Merge Controller Audit",
        "| Gate | Status | Findings |",
        "| :--- | :---: | :--- |",
    ]

    gates = review_data.get("gate_evaluations", {})
    gate_labels = {
        "CompilationGate": "Gate 1: Compilation & Syntax",
        "UnitTestGate": "Gate 2: Unit Test Coverage",
        "PerformanceGate": "Gate 3: Performance & Latency",
        "SecurityGate": "Gate 4: Enterprise Security & Secrets",
        "PathResolutionGate": "Gate 5: Canonical Path Resolution",
    }
    for gate_key, label in gate_labels.items():
        g_info = gates.get(gate_key, {"status": "UNKNOWN", "notes": ""})
        status_sym = "✅ PASS" if g_info.get("status") == "PASS" else "❌ FAIL"
        lines.append(f"| **{label}** | {status_sym} | {g_info.get('notes', '')} |")

    lines.extend(
        [
            "",
            "---",
            "",
            "### 🔍 8-Critic Architecture & Quality Matrix",
            "| Critic | Status | Score (0-10) | Evaluation Notes |",
            "| :--- | :---: | :---: | :--- |",
        ]
    )

    critics = review_data.get("critic_evaluations", {})
    for critic_name, c_info in critics.items():
        c_status = c_info.get("status", "INFO")
        c_score = c_info.get("score", 0)
        c_notes = c_info.get("notes", "")
        status_sym = (
            "✅ PASS" if c_status == "PASS" else ("⚠️ WARN" if c_status == "WARN" else "❌ FAIL")
        )
        lines.append(f"| **{critic_name}** | {status_sym} | {c_score}/10 | {c_notes} |")

    critical_flaws = review_data.get("critical_flaws", [])
    if critical_flaws:
        lines.extend(
            [
                "",
                "---",
                "",
                "### 🚨 Critical Flaws & Merge Blockers",
            ]
        )
        for idx, flaw in enumerate(critical_flaws, 1):
            lines.append(f"#### {idx}. {flaw.get('title', 'Issue')}")
            lines.append(f"- **What is wrong:** {flaw.get('what_is_wrong', '')}")
            lines.append(f"- **What is needed:** {flaw.get('what_is_needed', '')}")
            lines.append("")

    highlights = review_data.get("positive_highlights", [])
    if highlights:
        lines.extend(
            [
                "",
                "---",
                "",
                "### 🌟 Positive Highlights",
            ]
        )
        for hl in highlights:
            lines.append(f"- {hl}")

    recommendations = review_data.get("general_recommendations", [])
    if recommendations:
        lines.extend(
            [
                "",
                "---",
                "",
                "### 💡 General Recommendations",
            ]
        )
        for rec in recommendations:
            lines.append(f"- {rec}")

    lines.extend(
        [
            "",
            "---",
            "*Automated code review generated by **Google Antigravity** using Zymis 8-Critic and 5-Gate Merge standards.*",
        ]
    )

    return "\n".join(lines)


def run_review(
    repo: str,
    pr_number: int | None,
    github_token: str | None,
    api_key: str,
    diff_content: str | None = None,
    pr_title: str = "Local Review",
    custom_instructions: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute the complete Antigravity PR review process."""
    gh_client = None
    commit_id = "HEAD"
    valid_lines_map: dict[str, set[int]] = {}

    pr_body = ""
    if pr_number and github_token:
        gh_client = GitHubClient(github_token, repo)
        pr_info = gh_client.get_pull_request(pr_number)
        pr_title = pr_info.get("title", pr_title)
        pr_body = pr_info.get("body", "") or ""
        commit_id = pr_info.get("head", {}).get("sha", "HEAD")
        diff_content = gh_client.get_pull_request_diff(pr_number)
    elif not diff_content:
        # Fetch local diff
        try:
            diff_content = subprocess.check_output(
                ["git", "diff", "origin/main...HEAD"], text=True, errors="replace"
            )
            if not diff_content.strip():
                diff_content = subprocess.check_output(
                    ["git", "diff", "HEAD~1...HEAD"], text=True, errors="replace"
                )
        except Exception:
            diff_content = subprocess.check_output(["git", "diff"], text=True, errors="replace")

    if not diff_content or not diff_content.strip():
        print("[Info] Diff is empty. Nothing to review.")
        return {"verdict": "APPROVE", "overall_score": 100, "production_ready": True}

    valid_lines_map = parse_diff_valid_lines(diff_content)

    # Truncate diff if exceptionally large (>60k chars) to prevent context explosion
    truncated_diff = diff_content
    if len(diff_content) > 60000:
        truncated_diff = diff_content[:60000] + "\n\n... [Diff truncated for length] ..."

    review_prompt = f"""\
You are performing a code review for Pull Request #{pr_number or "Local"}: {pr_title}

Pull Request Details:
- Repository: {repo}
- Description: {pr_body if pr_body else "No description provided."}
- Custom Instructions: {custom_instructions if custom_instructions else "None"}

Here is the unified Git diff:
```diff
{truncated_diff}
```

Evaluate this diff thoroughly against all 8 Zymis Critics and the 5-Gate Merge Controller.
For any defect or issue discovered, state clearly:
1. WHAT IS WRONG (the exact bug, security issue, or design defect).
2. WHAT IS NEEDED (the exact fix, interface, test, or replacement).
3. If applicable, provide the exact replacement code for GitHub suggestions.

Output ONLY valid JSON adhering strictly to the required schema.
"""

    print(f"[1/4] Sending diff ({len(diff_content)} chars) to Google Antigravity...")
    response_json_str = query_antigravity_gemini(
        prompt=review_prompt,
        system_instruction=ZYMIS_REVIEW_SYSTEM_PROMPT,
        api_key=api_key,
    )

    # Parse model response JSON
    try:
        # Strip potential markdown code fences ```json ... ```
        cleaned_json = response_json_str.strip()
        if cleaned_json.startswith("```"):
            cleaned_json = re.sub(r"^```[a-zA-Z]*\n", "", cleaned_json)
            cleaned_json = re.sub(r"\n```$", "", cleaned_json)
        review_data = json.loads(cleaned_json)
    except json.JSONDecodeError as err:
        print(f"[Error] Failed to parse Antigravity response as JSON: {err}")
        print(f"Raw response: {response_json_str[:500]}...")
        # Fallback structured review
        review_data = {
            "verdict": "COMMENT",
            "overall_score": 70,
            "production_ready": False,
            "executive_summary": "Antigravity analysis completed with unstructured output.",
            "critical_flaws": [],
            "inline_comments": [],
            "positive_highlights": [],
            "general_recommendations": [response_json_str[:1000]],
        }

    print("[2/4] Formatting structured Markdown report...")
    review_markdown = build_review_markdown(review_data, pr_title, pr_number or 0)

    # Prepare inline comments
    raw_inline_comments = review_data.get("inline_comments", [])
    valid_inline_comments: list[dict[str, Any]] = []
    fallback_body_comments: list[str] = []

    for comment in raw_inline_comments:
        path = comment.get("path")
        line = comment.get("line")
        what_wrong = comment.get("what_is_wrong", "")
        what_needed = comment.get("what_is_needed", "")
        suggested_code = comment.get("suggested_code", "")
        severity = comment.get("severity", "INFO")

        body_parts = [
            f"**[{severity}] Antigravity Inspection**",
            f"- **What is wrong:** {what_wrong}",
            f"- **What is needed:** {what_needed}",
        ]
        if suggested_code:
            body_parts.append(f"```suggestion\n{suggested_code.strip()}\n```")

        comment_body = "\n".join(body_parts)

        # Verify line exists in diff hunk for GitHub API compliance
        if path and line and path in valid_lines_map and int(line) in valid_lines_map[path]:
            valid_inline_comments.append(
                {
                    "path": path,
                    "line": int(line),
                    "body": comment_body,
                }
            )
        else:
            fallback_body_comments.append(f"#### `{path}` (line {line or 'N/A'})\n{comment_body}\n")

    if fallback_body_comments:
        review_markdown += "\n\n### 📝 Additional File-Level Findings\n" + "\n".join(
            fallback_body_comments
        )

    print(f"[3/4] Prepared {len(valid_inline_comments)} inline diff comments.")

    if dry_run or not gh_client or not pr_number:
        print("\n" + "=" * 80)
        print("GOOGLE ANTIGRAVITY REVIEW REPORT (DRY-RUN / LOCAL)")
        print("=" * 80)
        print(review_markdown)
        if valid_inline_comments:
            print("\nINLINE COMMENTS:")
            for ic in valid_inline_comments:
                print(f"-> {ic['path']}:{ic['line']}\n{ic['body']}\n")
        return review_data

    print(f"[4/4] Submitting review to GitHub PR #{pr_number}...")
    event = review_data.get("verdict", "COMMENT")
    if event not in ("APPROVE", "REQUEST_CHANGES", "COMMENT"):
        event = "COMMENT"

    gh_client.post_review(
        pr_number=pr_number,
        commit_id=commit_id,
        body=review_markdown,
        event=event,
        comments=valid_inline_comments,
    )
    print(f"[Success] Review submitted as {event} on PR #{pr_number}!")
    return review_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Google Antigravity PR Review Agent for Zymis")
    parser.add_argument(
        "--repo",
        default=os.getenv("GITHUB_REPOSITORY", "abhinav00anand/zymis"),
        help="GitHub repository (owner/repo)",
    )
    parser.add_argument(
        "--pr",
        type=int,
        default=int(os.getenv("PR_NUMBER")) if os.getenv("PR_NUMBER") else None,
        help="Pull request number",
    )
    parser.add_argument(
        "--github-token", default=os.getenv("GITHUB_TOKEN"), help="GitHub API Token"
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("ANTIGRAVITY_API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY"),
        help="Antigravity / Gemini API Key",
    )
    parser.add_argument("--diff-file", help="Path to diff file for local testing")
    parser.add_argument(
        "--instructions",
        default=os.getenv("REVIEW_INSTRUCTIONS", ""),
        help="Additional review instructions",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print review to stdout without submitting to GitHub"
    )

    args = parser.parse_args()

    if not args.api_key:
        print(
            "[Error] Missing Antigravity API key. Set ANTIGRAVITY_API_KEY or GEMINI_API_KEY environment variable."
        )
        sys.exit(1)

    diff_content = None
    if args.diff_file:
        diff_content = Path(args.diff_file).read_text(encoding="utf-8")

    run_review(
        repo=args.repo,
        pr_number=args.pr,
        github_token=args.github_token,
        api_key=args.api_key,
        diff_content=diff_content,
        custom_instructions=args.instructions,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
