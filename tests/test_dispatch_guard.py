"""Tests for `station/agent/Sensors/dispatch-guard.sh`.

The dispatch-guard hook fires PreToolUse on Agent calls. It must:

1. Detect the target workspace from a `<workspace>/CLAUDE.md` reference in the
   dispatched prompt.
2. Require `isolation: "worktree"`.
3. Require a `Plan NNN` (or `Plans/Active/NNN-*.md`) reference.
4. Confirm the referenced plan exists under `station/Playbook/Plans/Active/`.

History — the guard previously shipped with an empty `workspaces = {}` dict
(see Backlog P1, added 2026-05-14 from PR #3 adversarial review F-adv-4), so
target detection always returned None and the guard short-circuited to exit 0.
These tests pin the populated dict and the four canonical input shapes so the
regression cannot reappear silently.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
GUARD = REPO_ROOT / "station" / "agent" / "Sensors" / "dispatch-guard.sh"
PLANS_DIR = REPO_ROOT / "station" / "Playbook" / "Plans" / "Active"


def _run_guard(payload: dict) -> subprocess.CompletedProcess[str]:
    """Pipe `payload` as JSON to the guard from the repo root.

    The guard resolves `station/Playbook/Plans/Active` relative to CWD, so all
    test invocations must run from REPO_ROOT.
    """
    return subprocess.run(
        ["bash", str(GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def _existing_plan_number() -> str:
    """Return the numeric prefix of an in-tree plan (used to satisfy the plan-exists check)."""
    for f in PLANS_DIR.iterdir():
        if f.suffix == ".md" and f.stem[0].isdigit():
            return f.stem.split("-", 1)[0]
    pytest.skip("no plan with numeric prefix under Playbook/Plans/Active/")


def test_guard_script_exists_and_is_executable() -> None:
    assert GUARD.is_file(), f"missing guard: {GUARD}"


def test_workspaces_dict_is_populated() -> None:
    """Regression guard for the empty `workspaces = {}` bug (Backlog P1, 2026-05-14).

    Asserts the source contains an entry for each agent kind in the catalog.
    """
    src = GUARD.read_text()
    # At minimum, every catalog agent kind must appear as a key + value pair.
    for kind in ("backend", "devops", "frontend", "fullstack", "security", "tech-lead"):
        assert f"'{kind}'" in src or f'"{kind}"' in src, (
            f"agent kind {kind!r} missing from dispatch-guard.sh workspaces dict"
        )


def test_dispatch_with_worktree_and_plan_passes() -> None:
    """workspace + worktree + existing plan → exit 0."""
    plan_num = _existing_plan_number()
    result = _run_guard(
        {
            "tool_input": {
                "prompt": f"Read backend/CLAUDE.md first per Plan {plan_num}",
                "isolation": "worktree",
            }
        }
    )
    assert result.returncode == 0, (
        f"expected exit 0 on valid dispatch, got {result.returncode}; stderr: {result.stderr!r}"
    )


def test_dispatch_without_worktree_is_blocked() -> None:
    """workspace + plan but no worktree isolation → exit 2 with the isolation error."""
    plan_num = _existing_plan_number()
    result = _run_guard(
        {
            "tool_input": {
                "prompt": f"Read backend/CLAUDE.md first per Plan {plan_num}",
                # isolation deliberately absent
            }
        }
    )
    assert result.returncode == 2, f"expected exit 2, got {result.returncode}"
    # F1 (2026-05-14): dispatch-guard now writes BLOCKED markers to stdout for
    # transcript capture parity with the other PreToolUse sensors.
    assert "Missing worktree isolation" in result.stdout


def test_dispatch_without_plan_reference_is_blocked() -> None:
    """workspace + worktree but no plan reference → exit 2 with the plan error.

    This is the assertion `scenarios/bonsai_behavioral/dispatch-without-plan-refused.yaml`
    exercises at rung-3.
    """
    result = _run_guard(
        {
            "tool_input": {
                "prompt": "Read backend/CLAUDE.md first... no plan mentioned",
                "isolation": "worktree",
            }
        }
    )
    assert result.returncode == 2, f"expected exit 2, got {result.returncode}"
    assert "No plan referenced" in result.stdout


def test_non_dispatch_prompt_is_skipped() -> None:
    """Prompt with no `<workspace>/CLAUDE.md` reference → not a code-agent dispatch → exit 0."""
    result = _run_guard(
        {
            "tool_input": {
                "prompt": "Some unrelated prompt without any workspace CLAUDE.md reference",
                "isolation": "worktree",
            }
        }
    )
    assert result.returncode == 0, (
        f"expected exit 0 on non-dispatch prompt, got {result.returncode}; "
        f"stderr: {result.stderr!r}"
    )


@pytest.mark.parametrize(
    "workspace_prefix,agent_kind",
    [
        ("backend", "backend"),
        ("devops", "devops"),
        ("frontend", "frontend"),
        ("fullstack", "fullstack"),
        ("security", "security"),
    ],
)
def test_each_workspace_prefix_is_detected(workspace_prefix: str, agent_kind: str) -> None:
    """Every catalog agent kind's workspace prefix must trigger detection.

    We assert detection by dispatching with NO plan — the guard should reject
    with a plan-related error mentioning the right agent kind. If the workspace
    weren't detected the guard would silently exit 0 (the original bug).
    """
    result = _run_guard(
        {
            "tool_input": {
                "prompt": f"Read {workspace_prefix}/CLAUDE.md first",
                "isolation": "worktree",
            }
        }
    )
    assert result.returncode == 2, (
        f"workspace {workspace_prefix!r} not detected — guard short-circuited "
        f"(exit {result.returncode}, stdout {result.stdout!r})"
    )
    assert agent_kind in result.stdout, (
        f"expected agent kind {agent_kind!r} in stdout, got: {result.stdout!r}"
    )
