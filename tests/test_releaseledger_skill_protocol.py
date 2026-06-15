"""Regression tests for the releaseledger skill protocol text.

These guard the skill prompt against drift away from the mandatory
commit-by-commit git audit and the no-parallel-mutations rules introduced in
``releaseledger_skill_commit_audit_fix.md``. They are prompt-text guards, not
runtime feature tests.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "releaseledger" / "SKILL.md"


def test_skill_requires_commit_by_commit_git_audit() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert "For any non-empty git range" in text
    assert "Every `git:<sha>`" in text
    assert "Aggregate `git log`, aggregate `git diff --stat`" in text
    assert "No coverage, no build" in text


def test_skill_disallows_parallel_releaseledger_mutations() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert "Do not run multiple releaseledger mutating commands concurrently" in text
    assert "Do not replace this with many parallel entry add calls" in text
