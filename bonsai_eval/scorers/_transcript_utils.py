"""Transcript-walking helpers shared across scorers.

Plan 38 §P2.3 scorers operate on `inspect_ai.solver.TaskState.messages` — a
chronological list of `ChatMessageSystem | ChatMessageUser |
ChatMessageAssistant | ChatMessageTool`. Each scorer needs to:

  - extract textual content from messages whose `content` may be a `str` OR a
    list of structured `Content*` blocks (per `inspect_ai.model` typing);
  - iterate every `ToolCall` issued by the assistant (Inspect captures these
    on `ChatMessageAssistant.tool_calls`, even when a PreToolUse hook later
    denies the call — per SCHEMA.md §Evaluators "blocked calls count");
  - search system messages for SessionStart-hook banners (see F5
    dual-semantic in dispatch brief §1 for `tool_call_made` on Read).

These helpers are intentionally pure (no side-effects, no I/O). They take a
`list[ChatMessage*]`-shaped argument so they can be unit-tested with synthetic
fixtures and reused from the eval-time `Scorer` callable.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any


def message_text(content: Any) -> str:
    """Return the textual portion of a `ChatMessage*.content`.

    `inspect_ai.model.ChatMessage*` types declare `content: str | list[Content]`.
    For the structured-list form, each `Content*` block has a `text` attribute
    (Content blocks without text — ContentImage, ContentAudio, ContentVideo,
    ContentData — yield empty strings; that's fine for substring matching).

    Returns the empty string for `None` content (rare, but the type allows it).
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    # Assumed to be an iterable of Content blocks with `.text` attribute.
    parts: list[str] = []
    for block in content:
        text_attr = getattr(block, "text", None)
        if isinstance(text_attr, str):
            parts.append(text_attr)
    return "\n".join(parts)


def iter_messages(state_or_messages: Any) -> Iterator[Any]:
    """Yield messages from a TaskState OR a bare list of ChatMessage* objects.

    Scorer callbacks receive `state: TaskState`, but unit-test fixtures pass a
    plain `list[ChatMessage*]` directly. Normalising here keeps the
    individual check functions agnostic.
    """
    if hasattr(state_or_messages, "messages"):
        messages = state_or_messages.messages
    else:
        messages = state_or_messages
    yield from messages


def iter_tool_calls(state_or_messages: Any) -> Iterator[tuple[Any, Any]]:
    """Yield (assistant_message, tool_call) pairs for every attempted tool call.

    Yields ATTEMPTED calls, including ones that were later denied by a
    PreToolUse hook. Inspect AI records the call on the assistant message
    *before* the hook gets a chance to deny it, which is exactly the
    semantics SCHEMA.md §Evaluators pins for `tool_call_made` (see the
    "blocked calls count" note).
    """
    for msg in iter_messages(state_or_messages):
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            continue
        for tc in tool_calls:
            yield msg, tc


# --- Tool-call argument extraction ---
#
# Different tool definitions name their path-shaped argument differently:
#
#   - Claude Code / Inspect `Read`, `Edit`, `Write`: `file_path`
#   - Claude Code `Glob` / some shims: `path`
#   - Claude Code `Task` (subagent dispatch): no explicit path; the
#     subagent_type / description / prompt carry the dispatch target.
#
# We normalise these by searching a fixed precedence list against each
# `tool_call.arguments` dict. If none match, the call still matches the
# tool-name predicate; the scenario author's `path:` substring is then
# compared against the *string representation* of the full arguments dict,
# which is loose enough to catch `Task(prompt="... in backend workspace ...")`
# without forcing every scenario to know the exact argument name.

_PATH_ARG_NAMES: tuple[str, ...] = (
    "file_path",
    "path",
    "filepath",
    "filename",
)


def tool_call_path_argument(tc: Any) -> str | None:
    """Extract the path-shaped argument from a `ToolCall`, or None if not present.

    Looks at known argument names in precedence order. Returns the first
    non-empty string match, or `None` if no path-shaped arg exists.
    """
    args = getattr(tc, "arguments", None) or {}
    if not isinstance(args, dict):
        return None
    for name in _PATH_ARG_NAMES:
        val = args.get(name)
        if isinstance(val, str) and val:
            return val
    return None


def tool_call_command_argument(tc: Any) -> str | None:
    """Extract the `command` argument from a `ToolCall` (used by `tool: Bash`)."""
    args = getattr(tc, "arguments", None) or {}
    if not isinstance(args, dict):
        return None
    val = args.get("command")
    return val if isinstance(val, str) and val else None


def tool_call_arguments_blob(tc: Any) -> str:
    """Return a single string concatenating every string value in a ToolCall's args.

    Fallback substring-match target when no canonical path/command argument
    exists (e.g. `Task` dispatch — the relevant signal is in `prompt`,
    `description`, or `subagent_type`).
    """
    args = getattr(tc, "arguments", None) or {}
    if not isinstance(args, dict):
        return ""
    parts: list[str] = []
    for v in args.values():
        if isinstance(v, str):
            parts.append(v)
    return "\n".join(parts)


def system_message_text(state_or_messages: Any) -> str:
    """Concatenate the text of every system message in the transcript.

    Used by the F5 dual-semantic check on `tool_call_made` for `Read`:
    Bonsai's SessionStart hook (`station/agent/Sensors/session-context.sh`)
    injects core memory/identity files via stdout, which Inspect captures
    as a `ChatMessageSystem` rather than as a `Read` tool call. Scenarios
    that assert "the agent read memory.md" must accept either signal.

    See dispatch brief §1 and `session-context.sh` for the banner format
    (`=== CORE: memory.md ===`, `=== CORE: identity.md ===`, etc.).
    """
    parts: list[str] = []
    for msg in iter_messages(state_or_messages):
        if getattr(msg, "role", None) == "system":
            parts.append(message_text(msg.content))
    return "\n".join(parts)


def all_message_text(state_or_messages: Any) -> str:
    """Concatenate text of every message — system, user, assistant, tool.

    Used by `hook_event_fired` (hooks emit `BLOCKED:` strings into tool
    error messages and SessionStart banners into system messages — either
    surface needs to be searchable).
    """
    parts: list[str] = []
    for msg in iter_messages(state_or_messages):
        parts.append(message_text(getattr(msg, "content", None)))
    return "\n".join(parts)


def tool_calls_matching(
    state_or_messages: Any,
    *,
    tool: str,
    path: str | None = None,
    command: str | None = None,
) -> Iterable[Any]:
    """Yield every ToolCall whose function matches `tool` and arg substring matches.

    Match rules (per SCHEMA.md §Evaluators):
      - `tool == "Bash"` => match against `command` substring on the tool
        call's `command` argument.
      - other tools => match against `path` substring on any of the known
        path-shaped arguments; if no canonical path arg exists, fall back to
        substring-match against the full arguments-blob.
      - When `path` / `command` is None, match on tool-name alone.
    """
    for _msg, tc in iter_tool_calls(state_or_messages):
        if getattr(tc, "function", None) != tool:
            continue
        if tool == "Bash":
            if command is None:
                yield tc
                continue
            cmd = tool_call_command_argument(tc)
            if cmd is not None and command in cmd:
                yield tc
        else:
            if path is None:
                yield tc
                continue
            canonical = tool_call_path_argument(tc)
            if canonical is not None and path in canonical:
                yield tc
                continue
            # Fallback: search every string-valued argument (handles `Task` etc.)
            blob = tool_call_arguments_blob(tc)
            if path in blob:
                yield tc
