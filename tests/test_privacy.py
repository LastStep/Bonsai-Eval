"""Privacy-guarantee tests — Plan 38 §P1.2 + §Security.

The transcript parser MUST drop `tool_input.content` and `tool_result.content`
before parquet write. These tests build synthetic JSONL lines that contain those
fields and assert the resulting parquet has no `content` column anywhere.

Tests run without an API key — no `requires_api` marker.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from bonsai_eval.telemetry.parse_transcripts import (
    FORBIDDEN_COLUMNS,
    OUTPUT_COLUMNS,
    assert_no_content_columns,
    parse_line,
    parse_to_parquet,
    rows_to_dataframe,
    write_parquet,
)


def test_parse_line_drops_content(sample_transcript_line_with_content: str) -> None:
    row = parse_line(sample_transcript_line_with_content, project_slug="synthetic")
    assert row is not None
    # Path is kept (metadata-only).
    assert row["tool_input_path"] == "/tmp/example.py"
    # No content keys anywhere in the parsed row.
    for key in row:
        assert "content" not in key, f"content leaked in key {key}"
    for value in row.values():
        if isinstance(value, str):
            assert "secret payload" not in value


def test_parse_line_keeps_metadata(sample_transcript_line_with_content: str) -> None:
    row = parse_line(sample_transcript_line_with_content, project_slug="synthetic")
    assert row is not None
    assert row["session_id"] == "synthetic-session-001"
    assert row["tool_name"] == "Edit"
    assert row["input_tokens"] == 100
    assert row["cache_read_tokens"] == 25
    assert row["project_slug"] == "synthetic"


def test_assert_no_content_columns_catches_direct() -> None:
    df = pd.DataFrame({"tool_input.content": ["bad"], "session_id": ["x"]})
    with pytest.raises(AssertionError, match="Privacy violation"):
        assert_no_content_columns(df)


def test_assert_no_content_columns_catches_suffix() -> None:
    df = pd.DataFrame({"my_custom.content": ["bad"]})
    with pytest.raises(AssertionError, match="Privacy violation"):
        assert_no_content_columns(df)


def test_assert_no_content_columns_passes_clean() -> None:
    df = pd.DataFrame({col: [None] for col in OUTPUT_COLUMNS})
    assert_no_content_columns(df)  # no raise


def test_end_to_end_parquet_has_no_content_column(
    tmp_path: Path, sample_transcript_line_with_content: str
) -> None:
    """Full pipeline: synthetic JSONL → parquet → schema check.

    Plan 38 §P1.2 mandatory test: build a fake JSONL with `content`, run the
    parser, assert the resulting parquet has no `content` column.
    """
    projects_root = tmp_path / "projects" / "synthetic-project"
    projects_root.mkdir(parents=True)
    jsonl = projects_root / "session.jsonl"
    jsonl.write_text(sample_transcript_line_with_content + "\n")

    out_path = tmp_path / "transcripts.parquet"
    n = parse_to_parquet(
        root=tmp_path / "projects",
        output_path=out_path,
        max_age_days=365 * 10,  # synthetic timestamps shouldn't be filtered
    )
    assert n == 1, f"expected 1 row, got {n}"

    # Read back via pyarrow to inspect raw schema names (catches any rename oddity).
    schema = pq.read_schema(out_path)
    column_names = set(schema.names)
    assert FORBIDDEN_COLUMNS.isdisjoint(column_names), (
        f"forbidden columns leaked: {FORBIDDEN_COLUMNS & column_names}"
    )
    for name in column_names:
        assert not name.endswith(".content"), f"{name} ends with .content"

    # Round-trip via pandas.
    df = pd.read_parquet(out_path)
    assert len(df) == 1
    assert df.iloc[0]["tool_input_path"] == "/tmp/example.py"


def test_empty_root_writes_schema_only_parquet(tmp_path: Path) -> None:
    """A transcripts root that doesn't exist still produces a valid parquet."""
    df = rows_to_dataframe([])
    out_path = tmp_path / "empty.parquet"
    write_parquet(df, out_path)
    assert out_path.exists()
    schema = pq.read_schema(out_path)
    assert set(schema.names) == set(OUTPUT_COLUMNS)
