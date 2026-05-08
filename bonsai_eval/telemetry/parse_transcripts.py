"""Transcript parser — Plan 38 §P1.2.

Streams every JSONL file in `~/.claude/projects/` (configurable via
`CLAUDE_PROJECTS_ROOT` env var) and writes metadata-only rows to
`data/transcripts.parquet`.

PRIVACY GUARANTEE (non-negotiable, Plan 38 §Security):
- `tool_input.content` and `tool_result.content` are dropped before write.
- An assertion at the parquet-write boundary fails loud if either column is
  present in the DataFrame. Unit-tested in `tests/test_privacy.py`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

# Columns that MUST NOT appear in the output parquet. Plan 38 §Security:
# transcripts may contain user prompts, tool I/O, secrets, internal URLs.
FORBIDDEN_COLUMNS = frozenset({"tool_input.content", "tool_result.content"})

# Columns we DO emit — keep this list narrow (metadata only).
OUTPUT_COLUMNS = (
    "session_id",
    "project_slug",
    "timestamp",
    "event_type",
    "tool_name",
    "tool_input_path",
    "hook_event_name",
    "subagent_type",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_creation_tokens",
)


def default_projects_root() -> Path:
    """Resolve the Claude Code projects root — env var override, else `~/.claude/projects`."""
    override = os.environ.get("CLAUDE_PROJECTS_ROOT")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude" / "projects"


def default_max_age_days() -> int:
    """Skip files older than this many days. Configurable via `TRANSCRIPT_MAX_AGE_DAYS`."""
    return int(os.environ.get("TRANSCRIPT_MAX_AGE_DAYS", "90"))


def _safe_get(d: dict[str, Any], path: str) -> Any:
    """Walk dotted path through nested dicts, returning None if any step misses."""
    cur: Any = d
    for key in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
        if cur is None:
            return None
    return cur


def parse_line(raw: str, *, project_slug: str) -> dict[str, Any] | None:
    """Parse one JSONL line into a metadata-only dict, or None if unparseable.

    Drops `tool_input.content` and `tool_result.content` — only `path` and
    metadata are extracted. Bytes-content fields never enter the returned dict.
    """
    raw = raw.strip()
    if not raw:
        return None
    try:
        obj: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        return None

    return {
        "session_id": obj.get("sessionId") or obj.get("session_id"),
        "project_slug": project_slug,
        "timestamp": obj.get("timestamp"),
        "event_type": obj.get("type") or obj.get("event_type"),
        "tool_name": _safe_get(obj, "message.tool_name") or obj.get("tool_name"),
        # Path is the ONLY part of tool_input we keep — never `content`.
        "tool_input_path": (
            _safe_get(obj, "message.tool_input.path")
            or _safe_get(obj, "tool_input.path")
            or _safe_get(obj, "toolInput.file_path")
        ),
        "hook_event_name": obj.get("hook_event_name") or _safe_get(obj, "hookEventName"),
        "subagent_type": obj.get("subagent_type") or obj.get("subagentType"),
        "input_tokens": _safe_get(obj, "message.usage.input_tokens"),
        "output_tokens": _safe_get(obj, "message.usage.output_tokens"),
        "cache_read_tokens": _safe_get(obj, "message.usage.cache_read_input_tokens"),
        "cache_creation_tokens": _safe_get(obj, "message.usage.cache_creation_input_tokens"),
    }


def iter_transcript_rows(
    *,
    root: Path | None = None,
    max_age_days: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield one metadata dict per JSONL line, across all projects under `root`."""
    root = root or default_projects_root()
    max_age = max_age_days if max_age_days is not None else default_max_age_days()
    cutoff = datetime.now(UTC) - timedelta(days=max_age)

    if not root.exists():
        return

    for jsonl_path in sorted(root.rglob("*.jsonl")):
        try:
            mtime = datetime.fromtimestamp(jsonl_path.stat().st_mtime, tz=UTC)
        except OSError:
            continue
        if mtime < cutoff:
            continue
        project_slug = jsonl_path.parent.name
        with jsonl_path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                row = parse_line(line, project_slug=project_slug)
                if row is not None:
                    yield row


def assert_no_content_columns(df: pd.DataFrame) -> None:
    """Hard guard — raise if any `content` field smuggled into the output.

    This runs immediately before parquet write. Plan 38 §P1.2 + §Security:
    the privacy guarantee is that no user prompt or tool-result body ever
    lands in the parquet store.
    """
    leaked = sorted(set(df.columns) & FORBIDDEN_COLUMNS)
    # Also catch any column ending in `.content` to defend against schema drift.
    suffix_leaks = sorted(c for c in df.columns if c.endswith(".content"))
    leaked = sorted(set(leaked + suffix_leaks))
    if leaked:
        raise AssertionError(
            f"Privacy violation — forbidden content columns reached parquet write: {leaked}"
        )


def rows_to_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a DataFrame with the canonical column set, even when rows is empty."""
    if not rows:
        return pd.DataFrame(columns=list(OUTPUT_COLUMNS))
    df = pd.DataFrame(rows)
    # Reorder + ensure every output column exists, even if no row had a value.
    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = pd.Series([None] * len(df))
    df = df[list(OUTPUT_COLUMNS)]
    return df


def write_parquet(df: pd.DataFrame, output_path: Path) -> None:
    """Validate schema, then write parquet."""
    assert_no_content_columns(df)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)


def parse_to_parquet(
    *,
    root: Path | None = None,
    output_path: Path,
    max_age_days: int | None = None,
) -> int:
    """End-to-end: read all transcripts under `root`, write parquet, return row count."""
    rows = list(iter_transcript_rows(root=root, max_age_days=max_age_days))
    df = rows_to_dataframe(rows)
    write_parquet(df, output_path)
    return len(df)
