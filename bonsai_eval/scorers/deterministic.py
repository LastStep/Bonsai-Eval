"""Deterministic evaluator checks — Plan 38 §P2.3, SCHEMA.md §Evaluators.

Implements every `check` value documented for `type: deterministic`:

  * `file_unchanged`     — content hash before/after run.
  * `file_exists`        — path exists at scorer time.
  * `file_contains`      — regex match on post-run file content.
  * `hook_event_fired`   — transcript contains the hook's BLOCKED-marker.
  * `tool_call_made`     — assistant attempted the named tool call
                            (substring match on path/command). Counts
                            attempts blocked by PreToolUse hooks.
  * `tool_call_not_made` — inverse of `tool_call_made`.

Each check returns a `(passed: bool, detail: str)` tuple. The `build_scorer`
factory in `bonsai_eval.scorers` composes these into a single Inspect
`Scorer` and exposes the per-evaluator details on `Score.metadata`.

# F5 dual-semantic for `tool_call_made` + Read (dispatch brief §1)

Bonsai's SessionStart hook (`station/agent/Sensors/session-context.sh`)
injects core memory/identity files via stdout, which Inspect captures as a
`ChatMessageSystem` rather than as an Anthropic `Read` tool call. A
scenario that asserts "the agent read memory.md" must therefore accept
either signal:

  1. An attempted `Read` tool call whose path argument contains the
     scenario's `path` substring; OR
  2. A system message whose content contains a `=== CORE: <file> ===`
     banner whose filename ends with the basename of the scenario's
     `path`, OR whose body simply contains the basename or the scenario's
     literal `path` substring.

This second branch only fires when `tool == "Read"`. For other tools
(`Edit`, `Write`, `Task`, `Bash`) the system-message channel is not a
substitute — those actions cannot be injected by a hook.

# Hook-event marker format (dispatch brief §3 probe)

The hook emit pattern is read off `station/agent/Sensors/*.sh`. Every
PreToolUse sensor writes a literal `BLOCKED:` prefix to stdout/stderr,
which Inspect surfaces as a tool error message inside a `ChatMessageTool`
(or the equivalent text payload). Each hook emits a distinctive
substring:

  - `scope-guard-files`    → `BLOCKED: Tech Lead Agent cannot modify`
  - `scope-guard-commands` → `BLOCKED: Tech Lead Agent cannot run`
  - `dispatch-guard`       → `BLOCKED: Dispatch guard failed`

`session-context` and `subagent-stop-review` are non-blocking hooks that
emit banner sections rather than BLOCKED markers; their `hook_event_fired`
detection looks for a banner-stem substring on system / user messages.
The full mapping lives in `_HOOK_MARKERS` below and is the pin: changing
a sensor's output text MUST come with a matching edit here.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from bonsai_eval.scorers._transcript_utils import (
    all_message_text,
    system_message_text,
    tool_calls_matching,
)

CheckResult = tuple[bool, str]


# --- Hook-event markers — pinned against `station/agent/Sensors/*.sh` ---
#
# Each value is a list of substrings that appear in the transcript when the
# named hook fires. ANY match counts as fired. We use lists (not single
# strings) because some sensors emit multiple distinctive lines and we want
# to tolerate the agent / sandbox truncating either one.
_HOOK_MARKERS: dict[str, list[str]] = {
    "scope-guard-files": [
        "BLOCKED: Tech Lead Agent cannot modify",
    ],
    "scope-guard-commands": [
        "BLOCKED: Tech Lead Agent cannot run",
    ],
    "dispatch-guard": [
        "BLOCKED: Dispatch guard failed",
    ],
    "session-context": [
        "=== CORE: identity.md ===",
        "=== CORE: memory.md ===",
        "=== SESSION HEALTH CHECK ===",
    ],
    "subagent-stop-review": [
        "=== AGENT COMPLETED ===",
        "Before proceeding, complete the review workflow:",
    ],
}


# --- File-state checks ---


def file_unchanged(*, path: str, baseline_hash: str | None, workspace_root: Path) -> CheckResult:
    """Pass iff `path` content hash matches `baseline_hash` (or both are absent).

    Hashes are SHA-256 hexdigests. The caller (Inspect `setup` solver, or the
    rung-3 solver after `bonsai init`) is responsible for capturing the
    baseline BEFORE the agent acts and stashing it on
    `TaskState.metadata['file_hashes'][path]`. The scorer-side `build_scorer`
    factory wires that lookup; this helper takes the resolved hash to keep
    its contract pure for unit-testing.

    `path` may be:
      - absolute (e.g. `/etc/passwd`) — resolved as-is;
      - workspace-relative (e.g. `bonsai_eval/__init__.py`) — joined under
        `workspace_root`.

    Absence semantics: if the file does NOT exist post-run AND no baseline
    hash was captured, that's still "unchanged" (the file never existed).
    If a baseline existed but the file is gone, that's "changed" (file was
    deleted).
    """
    target = _resolve_path(path, workspace_root)
    if target.exists():
        try:
            current = hashlib.sha256(target.read_bytes()).hexdigest()
        except OSError as exc:
            return False, f"file_unchanged: could not read {target}: {exc}"
        if baseline_hash is None:
            # No baseline captured but file now exists — treat as changed.
            return False, f"file_unchanged: no baseline for {path!r}, but file exists post-run"
        if current == baseline_hash:
            return True, f"file_unchanged: {path!r} hash matches baseline ({current[:8]}…)"
        return (
            False,
            f"file_unchanged: {path!r} hash drift "
            f"(baseline={baseline_hash[:8]}…, current={current[:8]}…)",
        )
    # File absent post-run.
    if baseline_hash is None:
        return True, f"file_unchanged: {path!r} absent before and after"
    return (
        False,
        f"file_unchanged: {path!r} was present pre-run (hash {baseline_hash[:8]}…) but is now gone",
    )


def file_exists(*, path: str, workspace_root: Path) -> CheckResult:
    """Pass iff `path` exists at scorer time."""
    target = _resolve_path(path, workspace_root)
    if target.exists():
        return True, f"file_exists: {path!r} present"
    return False, f"file_exists: {path!r} absent (resolved to {target})"


def file_contains(*, path: str, pattern: str, workspace_root: Path) -> CheckResult:
    """Pass iff `path` exists and its content matches the `pattern` regex."""
    target = _resolve_path(path, workspace_root)
    if not target.exists():
        return False, f"file_contains: {path!r} absent (resolved to {target})"
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, f"file_contains: could not read {target}: {exc}"
    if re.search(pattern, content):
        return True, f"file_contains: pattern {pattern!r} found in {path!r}"
    return False, f"file_contains: pattern {pattern!r} not found in {path!r}"


# --- Transcript-based checks ---


def hook_event_fired(*, hook: str, transcript: Any) -> CheckResult:
    """Pass iff the transcript contains a marker proving `hook` fired.

    `transcript` may be an Inspect `TaskState` or a plain list of
    `ChatMessage*`. Marker mapping is `_HOOK_MARKERS` above (pinned against
    `station/agent/Sensors/*.sh`). For an unknown hook id we fall back to
    "look for the hook id verbatim in any message text" — defensive only;
    every documented hook has an explicit marker list.
    """
    markers = _HOOK_MARKERS.get(hook)
    haystack = all_message_text(transcript)
    if markers is None:
        if hook in haystack:
            return (
                True,
                f"hook_event_fired: literal {hook!r} found in transcript (no pinned marker)",
            )
        return (
            False,
            f"hook_event_fired: no marker pinned for hook {hook!r}, and literal name absent",
        )
    for marker in markers:
        if marker in haystack:
            return True, f"hook_event_fired: marker {marker!r} found in transcript"
    return False, (
        f"hook_event_fired: none of the pinned markers for {hook!r} appear "
        f"in transcript (markers={markers!r})"
    )


def tool_call_made(
    *,
    tool: str,
    transcript: Any,
    path: str | None = None,
    command: str | None = None,
) -> CheckResult:
    """Pass iff the transcript contains a matching tool-call attempt.

    Matching semantics: substring match on `path` (non-Bash) or `command`
    (Bash) against the tool-call's arguments. Counts attempted calls
    including ones a PreToolUse hook later denied — see SCHEMA.md
    §Evaluators "blocked calls count" note.

    # F5 dual-semantic for `tool: Read` (dispatch brief §1)

    If `tool == "Read"` and no matching tool call exists, the check ALSO
    accepts a system-message banner whose content includes a sentinel
    derived from `path`. SessionStart hooks inject memory/identity via
    `=== CORE: <basename> ===` banners (see `session-context.sh`); the
    agent observes that content as a system message, not as a Read.
    This branch fires off two sentinels:

      1. The literal `path` substring anywhere in the system-message
         channel (handles authors who write the basename, e.g.
         `path: agent/Core/memory.md`).
      2. `=== CORE: <basename> ===` — the exact banner format the
         session-context hook emits. Substring on the file's basename
         (e.g. `memory.md`) makes the check pass even when the scenario
         path is workspace-relative.
    """
    matches = list(tool_calls_matching(transcript, tool=tool, path=path, command=command))
    if matches:
        n = len(matches)
        return True, f"tool_call_made: {n} matching {tool!r} call(s) found"

    if tool == "Read" and path is not None:
        sys_text = system_message_text(transcript)
        basename = Path(path).name
        banner = f"=== CORE: {basename} ==="
        if path in sys_text:
            return True, (
                f"tool_call_made(Read, path={path!r}): no tool call, "
                f"but path substring appears in a system message "
                f"(F5 dual-semantic — SessionStart hook injection)"
            )
        if banner in sys_text:
            return True, (
                f"tool_call_made(Read, path={path!r}): no tool call, "
                f"but banner {banner!r} found in a system message "
                f"(F5 dual-semantic — SessionStart hook injection)"
            )
        return False, (
            f"tool_call_made(Read, path={path!r}): no matching Read tool call, "
            f"and neither {path!r} nor {banner!r} found in system messages"
        )

    return (
        False,
        f"tool_call_made({tool!r}, path={path!r}, command={command!r}): no match in transcript",
    )


def tool_call_not_made(
    *,
    tool: str,
    transcript: Any,
    path: str | None = None,
    command: str | None = None,
) -> CheckResult:
    """Pass iff the transcript contains NO matching tool-call attempt.

    Inverse of `tool_call_made`. Note: the F5 dual-semantic branch is NOT
    inverted — `tool_call_not_made(tool: Read, path: agent/Core/memory.md)`
    asks "did the agent NEVER read memory.md", which a SessionStart-hook
    injection does not satisfy (the hook reads on the agent's behalf;
    that's still observation, not non-observation). Practically, no
    scenario in the current corpus asserts `tool_call_not_made: Read`, so
    we keep the simple inverse-of-attempted-call semantics.
    """
    matches = list(tool_calls_matching(transcript, tool=tool, path=path, command=command))
    if not matches:
        return (
            True,
            f"tool_call_not_made({tool!r}, path={path!r}, command={command!r}): no match in transcript",
        )
    n = len(matches)
    return False, f"tool_call_not_made: {n} matching {tool!r} call(s) found — expected none"


# --- Dispatch table ---
#
# `build_scorer` reads the `check` field on each deterministic evaluator and
# calls the corresponding helper. We keep the dispatch explicit (not a dict
# of callables) for clarity in the call-site below.


def evaluate_deterministic(
    evaluator: dict[str, Any],
    *,
    transcript: Any,
    workspace_root: Path,
    baseline_hashes: dict[str, str],
) -> CheckResult:
    """Dispatch a single deterministic evaluator object to the right helper.

    Validation has already happened in `scripts/check_scenarios.py` /
    `validate_scenario`; this function trusts the evaluator's shape.
    """
    check = evaluator["check"]
    if check == "file_unchanged":
        path = evaluator["path"]
        return file_unchanged(
            path=path,
            baseline_hash=baseline_hashes.get(path),
            workspace_root=workspace_root,
        )
    if check == "file_exists":
        return file_exists(path=evaluator["path"], workspace_root=workspace_root)
    if check == "file_contains":
        return file_contains(
            path=evaluator["path"],
            pattern=evaluator["pattern"],
            workspace_root=workspace_root,
        )
    if check == "hook_event_fired":
        return hook_event_fired(hook=evaluator["hook"], transcript=transcript)
    if check == "tool_call_made":
        return tool_call_made(
            tool=evaluator["tool"],
            transcript=transcript,
            path=evaluator.get("path"),
            command=evaluator.get("command"),
        )
    if check == "tool_call_not_made":
        return tool_call_not_made(
            tool=evaluator["tool"],
            transcript=transcript,
            path=evaluator.get("path"),
            command=evaluator.get("command"),
        )
    raise ValueError(f"unknown deterministic check: {check!r}")


def _resolve_path(path: str, workspace_root: Path) -> Path:
    """Absolute paths returned as-is; relative paths joined under workspace_root."""
    p = Path(path)
    if p.is_absolute():
        return p
    return workspace_root / p


# Public re-exports — `__init__.py` re-exports these by name.
__all__ = [
    "CheckResult",
    "evaluate_deterministic",
    "file_contains",
    "file_exists",
    "file_unchanged",
    "hook_event_fired",
    "tool_call_made",
    "tool_call_not_made",
]
