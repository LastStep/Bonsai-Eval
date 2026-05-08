"""Shared pytest fixtures."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def _build_joined_fixture(fixtures_dir: Path) -> None:
    """Regenerate `tests/fixtures/joined.parquet` if missing.

    Plan 38 §Verification requires the analysis notebook to run on placeholder
    fixtures (Risk #7 — no real-data run pre-merge). The fixture is a binary
    parquet, so we keep `build_fixtures.py` in version control and regenerate
    on first test run rather than committing the binary.
    """
    out = fixtures_dir / "joined.parquet"
    if out.exists():
        return
    builder = fixtures_dir / "build_fixtures.py"
    subprocess.run([sys.executable, str(builder)], check=True, capture_output=True)


def pytest_configure(config: pytest.Config) -> None:
    """Ensure the placeholder fixture parquet is built before any test runs."""
    fixtures_dir = Path(__file__).parent / "fixtures"
    _build_joined_fixture(fixtures_dir)


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to the synthetic fixture tree under `tests/fixtures/`."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_transcript_line_with_content() -> str:
    """A JSONL line that contains forbidden `tool_input.content` and `tool_result.content`.

    Used to verify the privacy assertion in `parse_transcripts`. If this line ever
    leaks `content` into the output parquet, the unit test fails loudly.
    """
    payload = {
        "type": "tool_use",
        "sessionId": "synthetic-session-001",
        "timestamp": "2026-04-15T12:34:56Z",
        "message": {
            "tool_name": "Edit",
            "tool_input": {
                "path": "/tmp/example.py",
                # FORBIDDEN — must be dropped before write.
                "content": "secret payload that must never reach parquet",
            },
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 25,
                "cache_creation_input_tokens": 10,
            },
        },
        "tool_result": {
            # FORBIDDEN — must be dropped.
            "content": "another secret payload",
        },
    }
    return json.dumps(payload)
