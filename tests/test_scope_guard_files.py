"""Tests for `station/agent/Sensors/scope-guard-files.sh`.

The scope-guard-files hook fires PreToolUse on Edit / Write. It enforces the
tech-lead agent's workspace boundary: only `station/` (plus an allowlist) is
writable. Anything else — cross-domain edits, sibling worktrees, .env
secrets, host-config paths, traversal escapes — must be blocked with the
literal marker `BLOCKED: Tech Lead Agent cannot modify` (pinned by
`bonsai_eval/scorers/deterministic.py:_HOOK_MARKERS`).

History — the prior version only blocked `.env*` writes despite a docstring
that claimed "outside station/". F2 of the 2026-05-14 meta-review rewrote
the sensor to enforce the documented contract; these tests pin that contract
so any silent regression fails CI loudly.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
GUARD = REPO_ROOT / "station" / "agent" / "Sensors" / "scope-guard-files.sh"

BLOCK_MARKER = "BLOCKED: Tech Lead Agent cannot modify"


def _run_guard(
    file_path: str,
    *,
    tool: str = "Edit",
    repo_root: Path | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Pipe a synthetic PreToolUse payload to the guard.

    `repo_root` overrides the sensor's repo-root detection via the
    `BONSAI_SCOPE_GUARD_REPO_ROOT` env var (used by tests that need a
    sandbox repo on a tmp path). `cwd` defaults to that override or REPO_ROOT.
    """
    payload = {
        "tool_name": tool,
        "tool_input": {"file_path": file_path},
    }
    env = os.environ.copy()
    effective_root = repo_root or REPO_ROOT
    env["BONSAI_SCOPE_GUARD_REPO_ROOT"] = str(effective_root)
    return subprocess.run(
        ["bash", str(GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=cwd or effective_root,
        env=env,
    )


def test_guard_script_exists_and_is_executable() -> None:
    assert GUARD.is_file(), f"missing guard: {GUARD}"


# --- allow cases -----------------------------------------------------------


def test_edit_inside_station_is_allowed() -> None:
    result = _run_guard("station/foo.md")
    assert result.returncode == 0, (
        f"expected allow under station/, got exit {result.returncode}; stderr: {result.stderr!r}"
    )
    assert result.stderr == ""


def test_edit_bonsai_yaml_is_allowed() -> None:
    """.bonsai.yaml is on the EXPLICIT_ALLOW list — tech-lead owns catalog state."""
    result = _run_guard(".bonsai.yaml")
    assert result.returncode == 0, (
        f"expected allow for .bonsai.yaml, got exit {result.returncode}; stderr: {result.stderr!r}"
    )


def test_edit_non_existent_path_under_station_is_allowed() -> None:
    """Write of a brand-new file under station/ must pass — sensor doesn't require existence."""
    result = _run_guard("station/Reports/Pending/brand-new-file.md")
    assert result.returncode == 0, (
        f"expected allow on new station/ path, got exit {result.returncode}; "
        f"stderr: {result.stderr!r}"
    )


# --- deny cases ------------------------------------------------------------


def test_write_bonsai_eval_is_denied_as_cross_domain() -> None:
    result = _run_guard("bonsai_eval/__init__.py", tool="Write")
    assert result.returncode == 2
    assert BLOCK_MARKER in result.stderr
    assert "cross-domain" in result.stderr or "bonsai_eval" in result.stderr


def test_edit_env_is_denied_as_secrets() -> None:
    result = _run_guard(".env")
    assert result.returncode == 2
    assert "BLOCKED" in result.stderr
    assert ".env" in result.stderr


def test_edit_scenarios_yaml_is_denied() -> None:
    result = _run_guard("scenarios/foo.yaml")
    assert result.returncode == 2
    assert BLOCK_MARKER in result.stderr


def test_traversal_out_of_station_is_denied(tmp_path: Path) -> None:
    """`station/../bonsai_eval/x.py` resolves to a sibling directory — must deny."""
    # Build a synthetic repo root on tmp_path so we don't depend on the real layout.
    (tmp_path / "station").mkdir()
    (tmp_path / "bonsai_eval").mkdir()
    result = _run_guard(
        "station/../bonsai_eval/x.py",
        repo_root=tmp_path,
    )
    assert result.returncode == 2, (
        f"expected deny on `..`-traversal, got {result.returncode}; stderr: {result.stderr!r}"
    )
    assert BLOCK_MARKER in result.stderr


def test_symlink_under_station_pointing_outside_is_denied(tmp_path: Path) -> None:
    """A symlink under station/ that points at /etc/hosts must be denied
    after resolve()."""
    station = tmp_path / "station"
    station.mkdir()
    link = station / "etc-hosts-link"
    link.symlink_to("/etc/hosts")
    result = _run_guard(
        "station/etc-hosts-link",
        repo_root=tmp_path,
    )
    assert result.returncode == 2, (
        f"expected deny on symlink escape, got {result.returncode}; stderr: {result.stderr!r}"
    )
    assert BLOCK_MARKER in result.stderr


def test_absolute_etc_passwd_is_denied() -> None:
    result = _run_guard("/etc/passwd")
    assert result.returncode == 2
    assert BLOCK_MARKER in result.stderr


def test_sibling_agent_worktree_is_denied() -> None:
    result = _run_guard(".claude/worktrees/agent-XYZ/bonsai_eval/foo.py", tool="Write")
    assert result.returncode == 2
    assert BLOCK_MARKER in result.stderr
    # sibling-agent detail message OR the generic outside-station message —
    # both are acceptable; what matters is the BLOCKED prefix.


def test_home_claude_projects_is_denied() -> None:
    result = _run_guard("~/.claude/projects/foo/transcript.jsonl")
    assert result.returncode == 2
    assert BLOCK_MARKER in result.stderr


def test_tests_dir_is_denied_as_cross_domain() -> None:
    result = _run_guard("tests/test_new.py", tool="Write")
    assert result.returncode == 2
    assert BLOCK_MARKER in result.stderr


def test_scripts_dir_is_denied_as_cross_domain() -> None:
    result = _run_guard("scripts/new_script.py", tool="Write")
    assert result.returncode == 2
    assert BLOCK_MARKER in result.stderr


# --- non-payload / pass-through --------------------------------------------


def test_empty_file_path_is_allowed() -> None:
    """No file_path → not a path-bearing edit → allow (Inspect surfaces its own error)."""
    result = _run_guard("")
    assert result.returncode == 0


@pytest.mark.parametrize("missing_key", ["tool_input", "everything"])
def test_malformed_payloads_fail_open(missing_key: str) -> None:
    """Malformed JSON / missing keys → exit 0 (fail open — don't break the tool loop)."""
    payload = "" if missing_key == "everything" else json.dumps({"tool_name": "Edit"})
    env = os.environ.copy()
    env["BONSAI_SCOPE_GUARD_REPO_ROOT"] = str(REPO_ROOT)
    result = subprocess.run(
        ["bash", str(GUARD)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )
    assert result.returncode == 0
