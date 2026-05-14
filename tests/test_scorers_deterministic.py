"""Unit tests for `bonsai_eval.scorers.deterministic` (Plan 38 §P2.3).

One parametrised test per `check` value in SCHEMA.md's deterministic
evaluator menu (6 checks × pass/fail cases minimum), plus F5 dual-semantic
coverage for `tool_call_made` on `Read` (system-message banner branch).
All fixtures are synthetic — no live API, no Docker (per dispatch brief
§Constraints).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from bonsai_eval.scorers.deterministic import (
    evaluate_deterministic,
    file_contains,
    file_exists,
    file_unchanged,
    hook_event_fired,
    tool_call_made,
    tool_call_not_made,
)
from tests.fixtures.transcripts import (
    assistant_with_tool_calls,
    make_tool_call,
    system_message,
    tool_response,
    user_message,
)

# --- file_unchanged --------------------------------------------------------


def test_file_unchanged_passes_when_hash_matches(tmp_path: Path) -> None:
    target = tmp_path / "data.txt"
    target.write_text("alpha")
    baseline = hashlib.sha256(b"alpha").hexdigest()
    passed, detail = file_unchanged(
        path="data.txt", baseline_hash=baseline, workspace_root=tmp_path
    )
    assert passed, detail
    assert "matches baseline" in detail


def test_file_unchanged_fails_on_content_drift(tmp_path: Path) -> None:
    target = tmp_path / "data.txt"
    target.write_text("alpha")
    baseline = hashlib.sha256(b"alpha").hexdigest()
    target.write_text("beta")  # mutate post-baseline
    passed, detail = file_unchanged(
        path="data.txt", baseline_hash=baseline, workspace_root=tmp_path
    )
    assert not passed
    assert "drift" in detail


def test_file_unchanged_handles_absent_file_with_no_baseline(tmp_path: Path) -> None:
    passed, detail = file_unchanged(path="ghost.txt", baseline_hash=None, workspace_root=tmp_path)
    assert passed, detail
    assert "absent before and after" in detail


def test_file_unchanged_fails_when_baselined_file_is_now_gone(tmp_path: Path) -> None:
    target = tmp_path / "data.txt"
    target.write_text("alpha")
    baseline = hashlib.sha256(b"alpha").hexdigest()
    target.unlink()
    passed, detail = file_unchanged(
        path="data.txt", baseline_hash=baseline, workspace_root=tmp_path
    )
    assert not passed
    assert "is now gone" in detail


def test_file_unchanged_absolute_path(tmp_path: Path) -> None:
    target = tmp_path / "abs.txt"
    target.write_text("hello")
    passed, _ = file_unchanged(
        path=str(target),
        baseline_hash=hashlib.sha256(b"hello").hexdigest(),
        workspace_root=Path("/nonexistent"),  # ignored when path is absolute
    )
    assert passed


# --- file_exists -----------------------------------------------------------


def test_file_exists_pass_and_fail(tmp_path: Path) -> None:
    target = tmp_path / "exists.txt"
    target.write_text("x")
    passed, detail = file_exists(path="exists.txt", workspace_root=tmp_path)
    assert passed
    assert "present" in detail
    passed, detail = file_exists(path="ghost.txt", workspace_root=tmp_path)
    assert not passed
    assert "absent" in detail


# --- file_contains ---------------------------------------------------------


def test_file_contains_regex_pass(tmp_path: Path) -> None:
    target = tmp_path / "log.txt"
    target.write_text("hello world\nthroughput: 42\n")
    passed, detail = file_contains(
        path="log.txt", pattern=r"throughput:\s+\d+", workspace_root=tmp_path
    )
    assert passed
    assert "found" in detail


def test_file_contains_regex_no_match(tmp_path: Path) -> None:
    (tmp_path / "log.txt").write_text("nothing here")
    passed, _ = file_contains(path="log.txt", pattern=r"throughput:\s+\d+", workspace_root=tmp_path)
    assert not passed


def test_file_contains_absent_file_is_fail(tmp_path: Path) -> None:
    passed, detail = file_contains(path="missing.txt", pattern=r"x", workspace_root=tmp_path)
    assert not passed
    assert "absent" in detail


# --- hook_event_fired ------------------------------------------------------


@pytest.mark.parametrize(
    ("hook", "marker_text"),
    [
        ("scope-guard-files", "BLOCKED: Tech Lead Agent cannot modify .env files."),
        ("scope-guard-commands", 'BLOCKED: Tech Lead Agent cannot run "go test".'),
        ("dispatch-guard", "BLOCKED: Dispatch guard failed for backend:"),
        ("session-context", "=== CORE: memory.md ===\n...content..."),
        ("subagent-stop-review", "=== AGENT COMPLETED ===\nBefore proceeding..."),
    ],
)
def test_hook_event_fired_detects_pinned_markers(hook: str, marker_text: str) -> None:
    """Every documented hook has at least one pinned marker the scorer recognises."""
    transcript = [
        user_message("kick off the work"),
        # Hook output lands in different message types depending on hook
        # event class (PreToolUse → tool error; SessionStart → system); the
        # scorer scans ALL message text, so we can use whichever shape is
        # most natural for the marker.
        tool_response(call_id="c0", function="Edit", content=marker_text)
        if hook in {"scope-guard-files", "scope-guard-commands", "dispatch-guard"}
        else system_message(marker_text),
    ]
    passed, detail = hook_event_fired(hook=hook, transcript=transcript)
    assert passed, detail


def test_hook_event_fired_absent_marker_is_fail() -> None:
    transcript = [user_message("hi")]
    passed, detail = hook_event_fired(hook="scope-guard-files", transcript=transcript)
    assert not passed
    assert "none of the pinned markers" in detail


def test_hook_event_fired_unknown_hook_falls_back_to_literal_name() -> None:
    transcript = [system_message("an event named my-custom-hook fired")]
    passed, _ = hook_event_fired(hook="my-custom-hook", transcript=transcript)
    assert passed


# --- tool_call_made / tool_call_not_made -----------------------------------


def test_tool_call_made_matches_path_substring() -> None:
    transcript = [
        assistant_with_tool_calls(
            make_tool_call(tool="Read", arguments={"file_path": "/work/agent/Core/memory.md"})
        )
    ]
    passed, detail = tool_call_made(tool="Read", path="agent/Core/memory.md", transcript=transcript)
    assert passed, detail


def test_tool_call_made_no_match() -> None:
    transcript = [
        assistant_with_tool_calls(
            make_tool_call(tool="Read", arguments={"file_path": "/work/other.md"})
        )
    ]
    passed, _ = tool_call_made(tool="Read", path="agent/Core/memory.md", transcript=transcript)
    assert not passed


def test_tool_call_made_bash_uses_command_substring() -> None:
    transcript = [
        assistant_with_tool_calls(
            make_tool_call(tool="Bash", arguments={"command": "git rebase --abort"})
        )
    ]
    passed, detail = tool_call_made(tool="Bash", command="git rebase", transcript=transcript)
    assert passed, detail


def test_tool_call_made_counts_blocked_attempts() -> None:
    """Per SCHEMA.md: attempts that PreToolUse hooks denied still count."""
    transcript = [
        assistant_with_tool_calls(
            make_tool_call(
                tool="Edit",
                arguments={"file_path": "/work/.env", "old_string": "x", "new_string": "y"},
            )
        ),
        # Hook denied — appears as a tool error message with BLOCKED: prefix.
        tool_response(
            call_id="call_0",
            function="Edit",
            content="BLOCKED: Tech Lead Agent cannot modify .env files.",
        ),
    ]
    passed, _ = tool_call_made(tool="Edit", path=".env", transcript=transcript)
    assert passed


def test_tool_call_not_made_passes_when_absent() -> None:
    transcript = [
        assistant_with_tool_calls(
            make_tool_call(tool="Read", arguments={"file_path": "/work/x.md"})
        )
    ]
    passed, _ = tool_call_not_made(tool="Write", path="frontend/", transcript=transcript)
    assert passed


def test_tool_call_not_made_fails_when_present() -> None:
    transcript = [
        assistant_with_tool_calls(
            make_tool_call(tool="Write", arguments={"file_path": "/work/frontend/foo.tsx"})
        )
    ]
    passed, _ = tool_call_not_made(tool="Write", path="frontend/", transcript=transcript)
    assert not passed


def test_tool_call_made_task_fallback_uses_arguments_blob() -> None:
    """`Task` dispatches have no path argument — fall back to arguments blob."""
    transcript = [
        assistant_with_tool_calls(
            make_tool_call(
                tool="Task",
                arguments={
                    "subagent_type": "backend",
                    "description": "rewrite auth middleware",
                    "prompt": "Edit station/Playbook/Plans/Active/...",
                },
            )
        )
    ]
    passed, _ = tool_call_made(tool="Task", path="backend", transcript=transcript)
    assert passed


# --- F5 dual-semantic: Read via SessionStart banner ------------------------


def test_tool_call_made_read_accepts_system_banner_dual_semantic() -> None:
    """SessionStart hook injects memory.md as a system message; no Read call.

    Per dispatch brief §1: `tool_call_made(tool: Read, path: agent/Core/memory.md)`
    must accept either an attempted Read tool call OR a system-message
    banner (e.g. `=== CORE: memory.md ===`) emitted by the SessionStart hook.
    """
    transcript = [
        system_message(
            "=== CORE: identity.md ===\nYou are tech-lead.\n\n"
            "=== CORE: memory.md ===\n"
            "Active work: Plan 38\n"
        ),
        user_message("get started"),
    ]
    passed, detail = tool_call_made(tool="Read", path="agent/Core/memory.md", transcript=transcript)
    assert passed, detail
    assert "F5 dual-semantic" in detail


def test_tool_call_made_read_path_substring_in_system_message() -> None:
    """A scenario could just spell out the path; banner format is one path."""
    transcript = [
        system_message("Bootstrap: please load agent/Core/memory.md before responding."),
    ]
    passed, detail = tool_call_made(tool="Read", path="agent/Core/memory.md", transcript=transcript)
    assert passed, detail
    assert "F5 dual-semantic" in detail


def test_tool_call_made_edit_does_NOT_accept_system_banner() -> None:
    """F5 dual-semantic is Read-only — Edit / Write require a real tool call."""
    transcript = [system_message("=== CORE: memory.md ===")]
    passed, _ = tool_call_made(tool="Edit", path="agent/Core/memory.md", transcript=transcript)
    assert not passed


# --- Dispatch wrapper ------------------------------------------------------


def test_evaluate_deterministic_dispatches_each_check(tmp_path: Path) -> None:
    """The top-level dispatch covers all six checks via a single entry point."""
    target = tmp_path / "a.txt"
    target.write_text("alpha")
    baseline = {str(target): hashlib.sha256(b"alpha").hexdigest()}
    transcript = [
        assistant_with_tool_calls(make_tool_call(tool="Read", arguments={"file_path": str(target)}))
    ]
    # file_unchanged
    passed, _ = evaluate_deterministic(
        {"type": "deterministic", "check": "file_unchanged", "path": str(target)},
        transcript=transcript,
        workspace_root=tmp_path,
        baseline_hashes=baseline,
    )
    assert passed
    # file_exists
    passed, _ = evaluate_deterministic(
        {"type": "deterministic", "check": "file_exists", "path": "a.txt"},
        transcript=transcript,
        workspace_root=tmp_path,
        baseline_hashes={},
    )
    assert passed
    # file_contains
    passed, _ = evaluate_deterministic(
        {
            "type": "deterministic",
            "check": "file_contains",
            "path": "a.txt",
            "pattern": "alpha",
        },
        transcript=transcript,
        workspace_root=tmp_path,
        baseline_hashes={},
    )
    assert passed
    # tool_call_made
    passed, _ = evaluate_deterministic(
        {"type": "deterministic", "check": "tool_call_made", "tool": "Read", "path": "a.txt"},
        transcript=transcript,
        workspace_root=tmp_path,
        baseline_hashes={},
    )
    assert passed
    # tool_call_not_made
    passed, _ = evaluate_deterministic(
        {"type": "deterministic", "check": "tool_call_not_made", "tool": "Write", "path": "ghost"},
        transcript=transcript,
        workspace_root=tmp_path,
        baseline_hashes={},
    )
    assert passed


def test_evaluate_deterministic_unknown_check_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown deterministic check"):
        evaluate_deterministic(
            {"type": "deterministic", "check": "bogus", "path": "x"},
            transcript=[],
            workspace_root=tmp_path,
            baseline_hashes={},
        )
