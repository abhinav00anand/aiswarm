"""Impact analysis."""

from __future__ import annotations

from pathlib import Path


def find_affected_tests(changed_files: list[str], test_root: str = "tests") -> list[str]:
    """
    Given changed source files, return the set of tests that should be re-run.

    Heuristic: if tests/unit/test_X.py exists for source/X.py, include it.
    Also include any test file that imports from the changed module.
    """
    affected: set[str] = set()
    test_path = Path(test_root)

    for changed in changed_files:
        stem = Path(changed).stem
        candidates = [
            test_path / "unit" / f"test_{stem}.py",
            test_path / f"test_{stem}.py",
            test_path / "integration" / f"test_{stem}.py",
        ]
        for candidate in candidates:
            if candidate.exists():
                affected.add(str(candidate))

    # Also scan test files for imports of changed modules
    for test_file in test_path.rglob("test_*.py"):
        try:
            content = test_file.read_text(encoding="utf-8")
            for changed in changed_files:
                module = Path(changed).stem
                if f"import {module}" in content or f"from {module}" in content:
                    affected.add(str(test_file))
        except OSError:
            continue

    return sorted(affected)
