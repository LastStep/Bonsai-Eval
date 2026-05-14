"""Synthetic transcript fixtures used by scorer unit tests.

The helpers below build `ChatMessage*` lists that match the shapes scorers
inspect at eval time — see `bonsai_eval/scorers/_transcript_utils.py`.
Tests use these instead of recording real Inspect EvalLogs because:

  - Recording a real EvalLog requires a live API key and Docker, both of
    which the dispatch brief forbids in this PR.
  - The shape we care about is small: assistant messages with
    `tool_calls`, tool messages with `content`, and system messages with
    banner text. Synthetic fixtures cover every code path with full
    determinism.
"""

from __future__ import annotations

from typing import Any

from inspect_ai.model import (
    ChatMessageAssistant,
    ChatMessageSystem,
    ChatMessageTool,
    ChatMessageUser,
)
from inspect_ai.tool import ToolCall


def make_tool_call(
    *,
    tool: str,
    arguments: dict[str, Any] | None = None,
    call_id: str = "call_0",
) -> ToolCall:
    """Build a `ToolCall` mirroring what Anthropic / Claude Code emits."""
    return ToolCall(id=call_id, function=tool, arguments=arguments or {})


def assistant_with_tool_calls(*tool_calls: ToolCall, text: str = "") -> ChatMessageAssistant:
    return ChatMessageAssistant(content=text, tool_calls=list(tool_calls))


def tool_response(
    *,
    call_id: str,
    function: str,
    content: str,
    error: str | None = None,
) -> ChatMessageTool:
    kwargs: dict[str, Any] = {
        "tool_call_id": call_id,
        "function": function,
        "content": content,
    }
    if error is not None:
        kwargs["error"] = error
    return ChatMessageTool(**kwargs)


def system_message(text: str) -> ChatMessageSystem:
    return ChatMessageSystem(content=text)


def user_message(text: str) -> ChatMessageUser:
    return ChatMessageUser(content=text)


__all__ = [
    "assistant_with_tool_calls",
    "make_tool_call",
    "system_message",
    "tool_response",
    "user_message",
]
